import datetime
import re
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot import BaseCog, Bot, Ctx


def p(desc, default=None):
    return commands.parameter(description=desc, default=default)


desc1, desc2 = "How many codes", "Where to send"
promos_link = "https://support.discord.com/hc/en-us/sections/22113084771863-Promotions"
no_active_promo_str = f"There is no active nitro promotion. Check yourself: [Support page](<{promos_link}>)"
tz_map = {"UTC": "UTC", "GMT": "GMT"}
tz_map.update(dict.fromkeys(["PT", "PST", "PDT"], "US/Pacific"))
tz_map.update(dict.fromkeys(["ET", "EST", "EDT"], "US/Eastern"))


def parse_date(text: str) -> datetime.datetime:
    """Parse promo dates like 'January 1, 2024 (12:00AM PST)' or '(12AM PST)' into UTC datetime.
    Also handles typos like '11:59M' -> '11:59PM'.
    """
    # Modified regex to allow 1-2 char AM/PM (e.g. 'M') and handle slight variations
    match = re.search(r"([A-Za-z]+\s+\d{1,2},\s+\d{4})\s+\((\d{1,2}(?::\d{2})?[APMapm]{1,2})\s*([A-Z]{2,4})\)", text)
    if not match:
        msg = f"Unparsable datetime: {text}"
        raise ValueError(msg)
    date_part, time_part, tz_abbr = match.groups()
    tz = tz_map.get(tz_abbr.upper())
    if not tz:
        msg = f"Unknown timezone: {tz_abbr}"
        raise ValueError(msg)
    time_part_up = time_part.upper()
    # Fix 'M' typo to 'PM' (assuming 11:59M -> 11:59PM)
    if time_part_up.endswith("M") and not (time_part_up.endswith("AM") or time_part_up.endswith("PM")):
        time_part_up = time_part_up.replace("M", "PM")
    # choose appropriate strptime format depending on whether minutes are present
    fmt = "%B %d, %Y %I:%M%p" if ":" in time_part_up else "%B %d, %Y %I%p"
    dt_obj = datetime.datetime.strptime(f"{date_part} {time_part_up}", fmt).replace(tzinfo=ZoneInfo(tz))
    return dt_obj.astimezone(datetime.UTC)


def extract_dates(strongs: list[str]) -> list[datetime.datetime]:
    """Extracts all valid dates from a list of strong tags, handling split date/time strings."""
    found_dates = []
    i = 0
    while i < len(strongs):
        s = strongs[i].strip()
        # Clean HTML tags if any (though findall usually handles inner text)
        s = re.sub(r"<[^>]+>", "", s)
        # 1. Try to parse as full date
        try:
            d = parse_date(s)
            found_dates.append(d)
            i += 1
            continue
        except ValueError:
            pass
        # 2. Check for split match (Date part + Time part)
        # Regex for Date part: Month D, YYYY
        if re.search(r"[A-Za-z]+\s+\d{1,2},\s+\d{4}", s) and i + 1 < len(strongs):
            next_s = strongs[i + 1].strip()
            next_s = re.sub(r"<[^>]+>", "", next_s)
            # Regex for Time part: (12AM PST)
            if re.search(r"\(\d{1,2}(?::\d{2})?[APMapm]{1,2}\s*[A-Z]{2,4}\)", next_s):
                combined = f"{s} {next_s}"
                try:
                    d = parse_date(combined)
                    found_dates.append(d)
                    i += 2  # Skip next
                    continue
                except ValueError:
                    pass
        i += 1
    return sorted(set(found_dates))


class NitroCog(BaseCog):
    def __init__(self, bot: Bot):
        super().__init__(bot)
        self.nitro_usage = bot.db["nitro_usage"]
        self.eco = bot.db["economy"]
        self.embed_settings = bot.db["embed_settings"]
        self.promo_exclusions = bot.db["promo_exclusions"]
        self.active_promo = False

    async def cog_load(self):
        # load variables in async
        self.embed_var = await self.embed_settings.find().to_list()
        counter_ids = ["nitro_counter", "nitro_limit", "b1mult", "b2mult", "new_nitro_system", "nitro_toggle"]
        results = await self.bot.agather(*[self.bot.counter.find_one({"_id": id_}) for id_ in counter_ids])
        # Map results to instance variables
        for id_, doc in zip(counter_ids, results, strict=False):
            if isinstance(doc, Exception):
                self.logger.warning("Error finding counter %s: %s", id_, doc)
                continue
            if not isinstance(doc, dict):
                self.logger.warning("Counter %s is missing or invalid, not a dict.", id_)
                continue
            value = doc.get("count", 0) if doc else 0
            if id_ in {"new_nitro_system", "nitro_toggle"}:
                value = doc.get("state", True) if doc else True
            setattr(self, id_, value)
        if not self.nitro_toggle:
            self.logger.warning("Nitro commands are disabled.")
        elif not self.new_nitro_system:
            self.logger.warning("Using old nitro system.")

    async def cog_on_ready(self):
        self.check_promos.start()
        self.cleanup_old_usage.start()
        self.update_embed.start()

    async def get_active_promo(self):
        """Fetch promotions via JSON API. Returns a list of active Nitro promos, or False."""
        base = "https://support.discord.com/api/v2/help_center/en-us/articles.json"
        async with self.bot.session.get(f"{base}?per_page=100") as resp:
            data = await resp.json()
        # Clean up expired auto-hide entries
        now = self.bot.now_utc()
        await self.promo_exclusions.delete_many({"auto_hide_until": {"$lt": now}})
        # Get current exclusions (both manual and auto-hide that haven't expired)
        exclusions = [
            doc["promo_name"]
            for doc in await self.promo_exclusions.find({
                "$or": [{"manually_hidden": True}, {"auto_hide_until": {"$gte": now}}],
            }).to_list()
        ]
        valid_promos = []
        for article in data["articles"]:
            if article["section_id"] != 22113084771863:  # Promotions section
                continue
            name = article["title"]
            if any(ex in name.lower() for ex in exclusions):
                continue
            body_html = article["body"]
            if "Nitro promotion is free" not in body_html or "purchase" in body_html:
                continue
            strongs = re.findall(r"<strong>(.*?)</strong>", body_html, flags=re.DOTALL)
            if len(strongs) < 2:
                continue
            dates = extract_dates(strongs)
            if len(dates) < 2:
                self.logger.warning("Not enough dates found for: %s", name)
                continue
            start = dates[0]
            redeem_end = dates[-1]
            # Heuristic: If we found > 2 dates, the middle one is likely the claim end.
            # If only 2, claim end is same as redeem end (or unknown).
            claim_end = dates[1] if len(dates) > 2 else redeem_end
            if start <= now <= redeem_end:
                status = "Active"
                end_ref = claim_end
                if now > claim_end:
                    status = "Redeem Only"
                    end_ref = redeem_end
                time_left = str(end_ref - now).split(".")[0]
                # Format time_left nicer if it's negative (though now <= end_ref usually)
                # If now > claim_end, we are in Redeem Only, so end_ref is redeem_end.
                # Since now <= redeem_end, time_left should be positive.
                valid_promos.append({
                    "name": name,
                    "url": article["html_url"],
                    "time_left": f"{time_left} ({status})",
                    "status": status,
                    "claim_end": claim_end,
                    "redeem_end": redeem_end,
                    "expiry_dt": end_ref,
                })
        return valid_promos or False

    async def old_nitro_check(self, ctx: Ctx, amount: int, guild: discord.Guild, user: discord.Member):
        # old nitro system
        today_dt = self.bot.now_utc(combine=True)
        result = await self.nitro_usage.find_one({"user_id": user.id, "date": today_dt})
        limit = self.nitro_limit
        if result:
            rcount = result["count"]
            boost_count = await self.bot.check_boost(guild, user)
            if boost_count == -1:
                return await ctx.send("There was an error getting your boost count.")
            if boost_count == 1:
                limit *= self.b1mult
            elif boost_count >= 2:
                limit *= self.b2mult
            if rcount >= limit:
                if boost_count == 0:
                    await ctx.send("You have reached the free limit. Try again tomorrow or boost the server.", delete_after=15)
                elif boost_count == 1:
                    await ctx.send("You have reached the daily limit. Try again tomorrow or boost again.", delete_after=15)
                elif boost_count >= 2:
                    await ctx.send("You have reached the daily limit. Try again tomorrow.", delete_after=15)
                else:
                    await ctx.send("Reached the daily limit, idk boost count.", delete_after=15)
                return None
            if rcount + amount > limit:
                amount = limit - rcount
        amount = min(amount, limit)
        await self.nitro_usage.update_one({"user_id": user.id, "date": today_dt}, {"$inc": {"count": amount}}, upsert=True)
        return True

    @commands.hybrid_command(name="nitro", help="Sends a free nitro link", aliases=["promo"])
    @commands.cooldown(1, 5, commands.BucketType.user)
    @app_commands.describe(amount=desc1, place=desc2)
    @app_commands.choices(
        place=[
            app_commands.Choice(name="dm (default)", value="dm"),
            app_commands.Choice(name="channel (here)", value="channel"),
        ],
    )
    async def nitro(self, ctx: Ctx, amount: int = p(desc1, 1), place: str = p(desc2, "dm")):
        guild, author = self.bot.verify_guild_user(ctx.guild, ctx.author)
        if not self.nitro_toggle:
            return await ctx.respond("Nitro commands are disabled.")
        if not self.active_promo:
            return await ctx.respond(no_active_promo_str)
        if await (self.bot_path / "lock.txt").exists():
            return await ctx.respond("The bot is in maintenance, please retry later.")
        place = place.lower()
        if place not in {"dm", "channel"}:
            return await ctx.respond("Invalid place. Must be 'dm' or 'channel'.")
        amount = min(amount, 40)
        if amount < 0:
            return await ctx.respond("Amount can't be negative.")
        try:
            lines = await self.bot.count_lines("nitro.txt")
            if lines is None:
                return await ctx.send("There was an error checking the code stock.")
            if lines == 0:
                return await ctx.respond("No nitro codes left.", 10)
            if amount == 0:
                return await ctx.send(f"There are {lines} codes available.")
            await ctx.defer()
            amount = min(amount, lines)
            if await self.bot.is_owner(author):
                pass
            else:
                user_id = author.id
                if self.new_nitro_system:
                    user = await self.eco.find_one({"_id": user_id})
                    if not user:
                        return await ctx.send(f"You are not in database. (no {self.bot.currency})")
                    user_bal = self.to_d129(user["balance"])
                    if user_bal < amount:
                        return await ctx.send(f"You don't have enough {self.bot.currency}. {user_bal!s}/{amount}.")
                    await self.eco.update_one({"_id": user_id}, {"$inc": {"balance": self.to_d129(-amount)}})
                else:
                    result = await self.old_nitro_check(ctx, amount, guild, author)
                    if result is not True:
                        return None
            lines = await self.bot.get_lines(amount, "nitro.txt")
            if lines is None:
                return await ctx.send("There was an error getting the codes.")
            if amount > 1:
                codes = []
                count = 0
                for line in lines:
                    if line:
                        if "https://" in line:
                            line = line.split("https://")[1]
                        codes.append(line)
                        count += 1
                        if count == amount:
                            break
                    else:
                        break
                await self.bot.counter.update_one({"_id": "nitro_counter"}, {"$inc": {"count": count}}, upsert=True)
                self.nitro_counter += count
                codes = "\n".join(codes)
                await self.bot.log_to_file(f"{author.name} got {count} nitro codes: {codes}", "nitro_log.txt")
                codes = f"```\n{codes}```"
                if place == "dm":
                    try:
                        if author.dm_channel is None:
                            await author.create_dm()
                        await ctx.send(f"Sent {count} codes in dm.")
                        await author.send(codes)
                    except Exception as e:
                        await ctx.send(f"Failed to send dm, sending codes here. Error: {e}")
                        await ctx.send(codes)
                else:
                    await ctx.send(codes)
            else:
                first_line = lines[0].strip()
                await self.bot.counter.update_one({"_id": "nitro_counter"}, {"$inc": {"count": 1}}, upsert=True)
                self.nitro_counter += 1
                await self.bot.log_to_file(f"{author.name} got nitro code: {first_line}", "nitro_log.txt")
                if "https://" in first_line:
                    first_line = first_line.split("https://")[1]
                code = f"```{first_line}```"
                if place == "dm":
                    try:
                        if author.dm_channel is None:
                            await author.create_dm()
                        await author.send(code)
                        await ctx.send("Sent code in dm.")
                    except Exception as e:
                        await ctx.send(f"Failed to send dm, sending code here. Error: {e}\n{code}")
                else:
                    await ctx.send(code)
        except Exception:
            self.logger.exception("Nitro error for %s:", author)
            await ctx.send("An error occurred while processing your request.")

    @nitro.error
    async def nitro_error(self, ctx: Ctx, error):
        self.logger.warning("Nitro error for %s:", ctx.author)
        if isinstance(error, commands.BadArgument):
            amount = ctx.message.content.split()[1]
            if amount == "dm":
                await ctx.send("Wrong format. Usage: >nitro [amount] [dm/channel]")
            elif not amount.isdigit():
                await ctx.send("Amount must be an integer.")
            else:
                await ctx.send("Invalid argument.")
        else:
            ctx.unhandled_error = True

    @commands.hybrid_command(name="limit", help="Set nitro limit and multipliers.")
    @commands.is_owner()
    async def set_limit(self, ctx: Ctx, amount: int, limit: str = "nitro_limit"):
        if amount < 1:
            return await ctx.respond("Amount must be at least 1.", 10)
        if limit not in {"nitro_limit", "b1mult", "b2mult"}:
            return await ctx.respond("Invalid limit choice.", 10)
        if limit == "b1mult":
            self.b1mult = amount
        elif limit == "b2mult":
            self.b2mult = amount
        else:
            self.nitro_limit = amount
        await self.bot.counter.update_one({"_id": limit}, {"$set": {"count": amount}}, upsert=True)
        return await ctx.respond(f"Updated {limit} to {amount}.", delete_after=False)

    @commands.hybrid_command(name="what", help="View nitro limit.")
    async def get_limit(self, ctx: Ctx):
        if not self.nitro_toggle:
            return await ctx.respond("Nitro commands are disabled.")
        if not self.active_promo:
            return await ctx.respond(no_active_promo_str)
        if self.new_nitro_system:
            return await ctx.respond(f"1 promo = 1 {self.bot.currency}", delete_after=False, del_cmd=False)
        limit_str = f"Current nitro limit (daily): {self.nitro_limit}, 1 boost = x{self.b1mult}, 2 boosts = x{self.b2mult}"
        return await ctx.respond(limit_str, delete_after=False, del_cmd=False)

    @commands.hybrid_command(name="usage", help="View nitro usage.")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def usage(self, ctx: Ctx):
        guild, member = self.bot.verify_guild_user(ctx.guild, ctx.author)
        if not self.nitro_toggle:
            return await ctx.respond("Nitro commands are disabled.")
        if not self.active_promo:
            return await ctx.respond(no_active_promo_str)
        if self.new_nitro_system:
            return await ctx.respond("This command is not available in the new nitro system.")
        today_dt = self.bot.now_utc(combine=True)
        user_id = member.id
        result = await self.nitro_usage.find_one({"user_id": user_id, "date": today_dt})
        if not result:
            result = {}
            result["count"] = 0
        count = result["count"]

        def count_usage():
            """Returns the "Your usage is count/limit" string, calculated."""
            if boost_count == 0:
                mult = 1
            elif boost_count == 1:
                mult = self.b1mult
            elif boost_count == 2:
                mult = self.b2mult
            elif boost_count > 2:
                mult = self.b2mult
                return f"There are no more perks after 2 boosts. Your usage is {count}/{self.nitro_limit * mult}."
            else:
                mult = 1
            return f"Your usage is {count}/{self.nitro_limit * mult}."

        boost_count = await self.bot.check_boost(guild, member)
        if boost_count == -1:
            await ctx.send("There was an error getting your boost count.")
        elif boost_count == 0:
            await ctx.send(f"No boosts. {count_usage()}")
        else:
            await ctx.send(f"{boost_count} boosts. {count_usage()}")
        return None

    @tasks.loop(hours=24)
    async def cleanup_old_usage(self):
        yesterday_dt = self.bot.now_utc(combine=True, days=-1)
        await self.nitro_usage.delete_many({"date": {"$lt": yesterday_dt}})

    @tasks.loop(hours=2)
    async def check_promos(self):
        try:
            self.active_promo = await self.get_active_promo()
            # self.logger.info(f"Checked promos. Active: {self.active_promo}")
        except Exception:
            self.logger.exception("Failed to check promos:")

    @commands.hybrid_command(name="promos", help="Check active nitro promos.")
    async def promos(self, ctx: Ctx):
        if not self.nitro_toggle:
            return await ctx.respond("Nitro commands are disabled.")
        if not self.active_promo:
            return await ctx.respond(no_active_promo_str)
        if not isinstance(self.active_promo, list):
            return await ctx.respond("active_promo is not a list.")
        # all promos in one message
        promo_messages = []
        promo_messages.append(f"Found {len(self.active_promo)} Active Free Nitro Promos!")
        promo_messages.extend(f"Title: [{promo['name']}](<{promo['url']}>)\nTime left: {promo['time_left']}" for promo in self.active_promo)
        await ctx.send("\n".join(promo_messages))
        return None

    @tasks.loop(minutes=5)
    async def update_embed(self):
        setting, guild_id = None, None
        try:
            if self.nitro_toggle:
                if self.active_promo:
                    nitro_count = await self.bot.count_lines("nitro.txt")
                    if nitro_count is None:
                        nitro_count = "Error"
                else:
                    nitro_count = "No promo"
            else:
                nitro_count = "Disabled"
            try:
                ping = round(self.bot.latency * 1000)
            except OverflowError:
                ping = 0
            guild_count, user_count = len(self.bot.guilds), len(self.bot.users)
            title, desc = "Bot Status", "Online 24/7, hosted somewhere..."
            for setting in self.embed_var:
                guild_id = setting["guild_id"]
                channel_id = setting["channel_id"]
                message_id = setting["message_id"]
                channel = self.bot.get_channel(channel_id)
                if channel and isinstance(channel, discord.TextChannel):
                    embed = discord.Embed(title=title, description=desc, color=discord.Color.random(), timestamp=self.bot.now_utc())
                    embed.add_field(name="Servers", value=f"{guild_count}")
                    embed.add_field(name="Users", value=f"{user_count}")
                    embed.add_field(name="Ping", value=f"{ping} ms")
                    embed.add_field(name="Nitro stock", value=f"{nitro_count}")
                    embed.add_field(name="Nitro given", value=f"{self.nitro_counter}")
                    embed.set_footer(text="coded by n01b")
                    message = await channel.fetch_message(message_id)
                    await message.edit(embed=embed)
                elif channel:
                    self.logger.warning("Channel %s is not a TextChannel, skipping embed update.", channel_id)
                elif "beta" not in str(self.bot.user).lower():
                    self.logger.warning("Bot does not have access to %s", channel_id)
        except discord.NotFound:
            await self.embed_settings.delete_one({"guild_id": guild_id})
            self.embed_var.remove(setting)
        except Exception:
            self.logger.exception("Failed to update embed:")

    @commands.hybrid_command(name="embe", help="Enable embed updates in the current channel.")
    @commands.is_owner()
    async def enable_embed(self, ctx: Ctx):
        guild, channel = self.bot.verify_guild_channel(ctx.guild, ctx.channel)
        existing_entry = await self.embed_settings.find_one({"guild_id": guild.id})
        if existing_entry:
            return await ctx.respond("Embed updates are already enabled in this channel.")
        embed = discord.Embed(title="Enabled embed updates", description="Waiting for update.", color=discord.Color.green())
        message = await ctx.send(embed=embed)
        await self.embed_settings.insert_one({
            "guild_id": guild.id,
            "channel_id": channel.id,
            "message_id": message.id,
        })
        self.embed_var.append({"guild_id": guild.id, "channel_id": channel.id, "message_id": message.id})
        await ctx.respond(f"Embed updates enabled in {channel.mention}!")
        return None

    @commands.hybrid_command(name="embd", help="Disable embed updates in the current channel.")
    @commands.is_owner()
    async def disable_embed(self, ctx: Ctx):
        guild, channel = self.bot.verify_guild_channel(ctx.guild, ctx.channel)
        existing_entry = await self.embed_settings.find_one({"guild_id": guild.id})
        if not existing_entry:
            return await ctx.respond("Embed updates are not enabled in this channel.")
        try:
            message = await ctx.channel.fetch_message(existing_entry["message_id"])
            await message.delete()
        except Exception:
            self.logger.exception("Failed to delete or fetch embed, ignoring:")
        await self.embed_settings.delete_one({"guild_id": guild.id})
        for i in self.embed_var[:]:
            if i["channel_id"] == channel.id:
                self.embed_var.remove(i)
        await ctx.respond(f"Embed updates disabled in {channel.mention}.")
        return None

    @commands.hybrid_command(name="nitrotoggle", help="Toggle nitro related commands.")
    @commands.is_owner()
    async def toggle_nitro(self, ctx, choice=None):
        if choice is None:
            self.nitro_toggle = not self.nitro_toggle
            await self.bot.counter.update_one({"_id": "nitro_toggle"}, {"$set": {"state": self.nitro_toggle}}, upsert=True)
            await ctx.respond(f"Nitro commands {'enabled' if self.nitro_toggle else 'disabled'}")
            return
        # toggle the new nitro system
        self.new_nitro_system = not self.new_nitro_system
        await self.bot.counter.update_one({"_id": "new_nitro_system"}, {"$set": {"state": self.new_nitro_system}}, upsert=True)
        await ctx.respond(f"New nitro system {'enabled' if self.new_nitro_system else 'disabled'}")

    async def promo_autocomplete(self, interaction: discord.Interaction, current: str):
        """Autocomplete for active and hidden promo names."""
        choices = []
        # Get active promos
        if self.active_promo and isinstance(self.active_promo, list):
            for promo in self.active_promo:
                name = promo["name"]
                if current.lower() in name.lower():
                    choices.append(app_commands.Choice(name=name[:100], value=name))
        # Get hidden promos
        for doc in await self.promo_exclusions.find({}).to_list():
            promo_name = doc["promo_name"]
            if current.lower() in promo_name.lower():
                choice_name = f"{promo_name} (hidden)"[:100]
                choices.append(app_commands.Choice(name=choice_name, value=promo_name))
        return choices[:25]

    @commands.hybrid_command(name="togglepromo", help="Hide/unhide a promo from the list.")
    @commands.is_owner()
    @app_commands.autocomplete(promo_name=promo_autocomplete)
    async def togglepromo(self, ctx: Ctx, promo_name: str, *, auto_hide: bool = p("Auto-hide until promo expires?", True)):  # noqa: FBT003
        """Toggles a promo in the exclusion list. Can auto-hide until the promo duration ends."""
        promo_name_lower = promo_name.lower()
        existing = await self.promo_exclusions.find_one({"promo_name": promo_name_lower})
        if existing and existing.get("manually_hidden"):
            # If manually hidden, unhide it
            await self.promo_exclusions.delete_one({"promo_name": promo_name_lower})
            await ctx.send(f"Promo '{promo_name}' has been unhidden.")
            self.active_promo = await self.get_active_promo()
            return
        # Hide the promo
        hide_data = {
            "promo_name": promo_name_lower,
            "added_at": self.bot.now_utc(),
            "manually_hidden": True,
        }
        # If auto_hide is enabled and promo is active, set auto_hide_until to promo end time
        if auto_hide and isinstance(self.active_promo, list):
            for promo in self.active_promo:
                if promo["name"].lower() != promo_name_lower:
                    continue
                hide_data["auto_hide_until"] = promo["expiry_dt"]
                break
        if existing:
            await self.promo_exclusions.update_one({"promo_name": promo_name_lower}, {"$set": hide_data})
        else:
            await self.promo_exclusions.insert_one(hide_data)
        status = "auto-hidden until it expires" if hide_data.get("auto_hide_until") else "hidden"
        await ctx.respond(f"Promo '{promo_name}' has been {status}.")
        # Refresh active promo list
        self.active_promo = await self.get_active_promo()

    @commands.hybrid_command(name="hiddenpromos", help="List all hidden promos.")
    @commands.is_owner()
    async def hiddenpromos(self, ctx: Ctx):
        """Lists all hidden promos."""
        names = [doc["promo_name"] for doc in await self.promo_exclusions.find({}).to_list()]
        if not names:
            await ctx.send("There are no hidden promos.")
        else:
            await ctx.send("Hidden promos:\n- " + "\n- ".join(names))


async def setup(bot: Bot):
    await bot.add_cog(NitroCog(bot))
