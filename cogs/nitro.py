import discord, os, datetime, asyncio, cloudscraper, pytz, re
from bs4 import BeautifulSoup
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime as dt, timezone
from bot import Bot, Default_Cog

desc1, desc2 = "How many codes", "Where to send"
def p(desc, default = None):
    return commands.parameter(description=desc, default=default)
no_active_promo_str = "There is no active nitro promo."

tz_map = {abbr: "US/Pacific" for abbr in ("PT", "PST", "PDT")}
tz_map.update({abbr: "US/Eastern" for abbr in ("ET", "EST", "EDT")})
tz_map.update({"UTC": "UTC", "GMT": "GMT"})

def parse_date(text: str):
    match = re.search(r'([A-Za-z]+\s+\d{1,2},\s+\d{4})\s+\((\d{1,2}:\d{2}[APMapm]{2})\s*([A-Z]{2,4})\)', text)
    if not match:
        raise ValueError(f"Unparsable datetime: {text}")
    date_part, time_part, tz_abbr = match.groups()
    tz = tz_map.get(tz_abbr.upper())
    if not tz:
        raise ValueError(f"Unknown timezone: {tz_abbr}")
    dt_obj = dt.strptime(f"{date_part} {time_part.upper()}", "%B %d, %Y %I:%M%p")
    return pytz.timezone(tz).localize(dt_obj).astimezone(timezone.utc)

def get_active_promo(scraper: cloudscraper.CloudScraper):
    """Tries to find some active nitro promotion. Returns True on success."""
    base = 'https://support.discord.com'
    html = scraper.get(f'{base}/hc/en-us/sections/22113084771863-Promotions').text
    soup = BeautifulSoup(html, 'html.parser')
    exclusions = {'customers', 'youtube', 'game pass ultimate'}
    for a in soup.select('ul.article-list a.article-list-link'):
        name, href = a.get_text(strip=True), str(a['href'])
        html = scraper.get(base + href).text
        if 'Nitro promotion is free' in html and not any(ex in name.lower() for ex in exclusions):
            soup = BeautifulSoup(html, 'html.parser')
            strongs = soup.select('div.article-body p strong')
            if len(strongs) < 2:
                continue
            try:
                start_date = parse_date(strongs[0].get_text(strip=True))
                end_date = parse_date(strongs[1].get_text(strip=True))
            except ValueError:
                continue
            now = dt.now(timezone.utc)
            is_active = start_date <= now <= end_date
            if is_active:
                return True
    return False

class NitroCog(Default_Cog):
    def __init__(self, bot: Bot):
        super().__init__(bot)
        self.nitro_usage = bot.db['nitro_usage']
        self.eco = bot.db['economy']
        self.embed_settings = bot.db['embed_settings']
        self.scraper = cloudscraper.create_scraper()
        self.active_promo = False
        self.check_promos.start()
        self.cleanup_old_usage.start()

    async def cog_load(self):
        # load variables in async
        self.embed_var = [doc async for doc in self.embed_settings.find()]
        counter_ids = ['nitro_counter', 'nitro_limit', 'b1mult', 'b2mult', 'new_nitro_system', 'nitro_toggle']
        results = await asyncio.gather(*[self.bot.counter.find_one({'_id': _id}) for _id in counter_ids])
        # Map results to instance variables
        for _id, doc in zip(counter_ids, results):
            value = doc.get('count', 0) if doc else 0
            if _id in ['new_nitro_system', 'nitro_toggle']:
                value = doc.get('state', True) if doc else True
            setattr(self, _id, value)
        if not self.nitro_toggle:
            self.logger.warning("Nitro commands are disabled.")
        elif not self.new_nitro_system:
            self.logger.warning("Using old nitro system.")
        self.update_embed.start()

    @commands.hybrid_command(name="nitro", help="Sends a free nitro link")
    @commands.cooldown(1, 5, commands.BucketType.user)
    @app_commands.describe(amount=desc1, place=desc2)
    @app_commands.choices(
        place=[
            app_commands.Choice(name="dm (default)", value="dm"),
            app_commands.Choice(name="channel (here)", value="channel")
        ]
    )
    async def nitro(self, ctx: commands.Context, amount: int = p(desc1, 1), place: str = p(desc2, "dm")):
        if not self.nitro_toggle:
            return await self.bot.respond(ctx, "Nitro commands are disabled.")
        if not self.active_promo:
            return await self.bot.respond(ctx, no_active_promo_str)
        if os.path.exists(f'{self.bot.script_path}/lock.txt'):
            return await self.bot.respond(ctx, 'The bot is in maintenance, please retry later.')
        if not isinstance(ctx.author, discord.Member) or not ctx.guild:
            return await ctx.send("You must be in a server to use this command.")
        place = place.lower()
        if place != "dm" and place != "channel":
            return await self.bot.respond(ctx, "Invalid place. Must be 'dm' or 'channel'.")
        if amount > 40:
            amount = 40
        if amount < 0:
            return await self.bot.respond(ctx, "Amount can't be negative.")
        try:
            lines = await self.bot.count_lines("nitro.txt")
            if lines is None:
                return await ctx.send("There was an error checking the code stock.")
            if lines == 0:
                return await self.bot.respond(ctx, "No nitro codes left.", 10)
            if amount == 0:
                return await ctx.send(f"There are {lines} codes available.")
            await ctx.defer()
            if amount > lines:
                amount = lines
            if await self.bot.is_owner(ctx.author):
                pass
            else:
                user_id = ctx.author.id
                if self.new_nitro_system:
                    user = await self.eco.find_one({'_id': user_id})
                    if not user:
                        return await ctx.send("You are not in database. (no nitro credits)")
                    if user['balance'] < amount:
                        return await ctx.send(f"You don't have enough nitro credits. {user['balance']:g}/{amount}.")
                    await self.eco.update_one({'_id': user_id}, {'$inc': {'balance': -amount}})
                else:
                    # old nitro system
                    today_dt = dt.combine(datetime.date.today(), datetime.time(0, 0, 0))
                    result = await self.nitro_usage.find_one({'user_id': user_id, 'date': today_dt})
                    limit = self.nitro_limit
                    if result:
                        rcount = result['count']
                        if ctx.author.premium_since:
                            boost_count = await self.bot.check_boost(ctx.guild.id, user_id)
                            if not boost_count:
                                return await ctx.send("There was an error getting your boost count.")
                            if boost_count == 1:
                                limit *= self.b1mult
                            elif boost_count >= 2:
                                limit *= self.b2mult
                        if rcount >= limit:
                            if ctx.author.premium_since:
                                if boost_count == 1:
                                    await ctx.send("You have reached the daily limit. Try again tomorrow or boost again.", delete_after=15)
                                elif boost_count >= 2:
                                    await ctx.send("You have reached the daily limit. Try again tomorrow.", delete_after=15)
                            else:
                                await ctx.send("You have reached the free limit. Try again tomorrow or boost the server.", delete_after=15)
                            return
                        elif rcount + amount > limit:
                            amount = limit - rcount
                    if amount > limit:
                        amount = limit
                    await self.nitro_usage.update_one({'user_id': user_id, 'date': today_dt}, {'$inc': {'count': amount}}, upsert=True)
            lines = await self.bot.get_lines(amount, 'nitro.txt')
            if lines is None:
                return await ctx.send("There was an error getting the codes.")
            if amount > 1:
                codes = []  
                count = 0
                for line in lines:
                    if line:
                        if 'https://' in line:
                            line = line.split('https://')[1]
                        codes.append(line)
                        count += 1
                        if count == amount:
                            break
                    else:
                        break
                await self.bot.counter.find_one_and_update({'_id': 'nitro_counter'}, {'$inc': {'count': count}}, upsert=True)
                self.nitro_counter += count
                codes = '\n'.join(codes)
                await self.bot.log_to_file(f'{ctx.author.name} got {count} nitro codes: {codes}', 'nitro_log.txt')
                codes = f'```\n{codes}```'
                if place == "dm":
                    try:
                        if ctx.author.dm_channel is None:
                            await ctx.author.create_dm()
                        await ctx.send(f"Sent {count} codes in dm.")
                        await ctx.author.send(codes)
                    except Exception as e:
                        await ctx.send(f"Failed to send dm, sending codes here. Error: {e}")
                        await ctx.send(codes)
                else:
                    await ctx.send(codes)
            else:
                first_line = lines[0].strip()
                await self.bot.counter.find_one_and_update({'_id': 'nitro_counter'}, {'$inc': {'count': 1}}, upsert=True)
                self.nitro_counter += 1
                await self.bot.log_to_file(f'{ctx.author.name} got nitro code: {first_line}', 'nitro_log.txt')
                if 'https://' in first_line:
                    first_line = first_line.split('https://')[1]
                code = f'```{first_line}```'
                if place == "dm":
                    try:
                        if ctx.author.dm_channel is None:
                            await ctx.author.create_dm()
                        await ctx.author.send(code)
                        await ctx.send("Sent code in dm.")
                    except Exception as e:
                        await ctx.send(f"Failed to send dm, sending code here. Error: {e}\n{code}")
                else:
                    await ctx.send(code)
        except Exception as e:
            self.logger.exception(f'Nitro error: {e}')
            await ctx.send("An error occurred while processing your request.")

    @nitro.error
    async def nitro_error(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            amount = ctx.message.content.split()[1]
            if amount == 'dm':
                await ctx.send("Wrong format. Usage: >nitro [amount] [dm/channel]")
            elif not amount.isdigit():
                await ctx.send("Amount must be an integer.")
            else:
                await ctx.send("Invalid argument.")
        else:
            ctx.unhandled_error = True

    @commands.hybrid_command(name="limit", help="Set nitro limit and multipliers.")
    @commands.is_owner()
    async def set_limit(self, ctx, amount: int, limit: str = "nitro_limit"):
        if amount < 1:
            return await self.bot.respond(ctx, "Amount must be at least 1.", 10)
        if limit != "nitro_limit" and limit != "b1mult" and limit != "b2mult":
            return await self.bot.respond(ctx, "Invalid limit choice.", 10)
        if limit == "b1mult":
            self.b1mult = amount
        elif limit == "b2mult":
            self.b2mult = amount
        else:
            self.nitro_limit = amount
        await self.bot.counter.find_one_and_update({'_id': limit}, {'$set': {'count': amount}}, upsert=True)
        await self.bot.respond(ctx, f"Updated {limit} to {amount}.", False)
    
    @commands.hybrid_command(name="what", help="View nitro limit.")
    async def get_limit(self, ctx):
        if not self.nitro_toggle:
            return await self.bot.respond(ctx, "Nitro commands are disabled.")
        elif not self.active_promo:
            return await self.bot.respond(ctx, no_active_promo_str)
        elif self.new_nitro_system:
            return await self.bot.respond(ctx, "1 promo = 1 nitro credit", False, del_cmd=False)
        await self.bot.respond(ctx, f"Current nitro limit (daily): {self.nitro_limit}, multipliers: 1 boost = {self.b1mult}, 2 boosts = {self.b2mult}", False, del_cmd=False)

    @commands.hybrid_command(name="usage", help="View nitro usage.")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def usage(self, ctx):
        if not self.nitro_toggle:
            return await self.bot.respond(ctx, "Nitro commands are disabled.")
        elif not self.active_promo:
            return await self.bot.respond(ctx, no_active_promo_str)
        elif self.new_nitro_system:
            return await self.bot.respond(ctx, "This command is not available in the new nitro system.")
        member = ctx.author
        today_dt = datetime.datetime.combine(datetime.date.today(), datetime.time(0, 0, 0))
        user_id = member.id
        result = await self.nitro_usage.find_one({'user_id': user_id, 'date': today_dt})
        if not result:
            result = {}
            result['count'] = 0
        if result:
            count = result['count']
            if member.premium_since:
                boost_count = await self.bot.check_boost(ctx.guild.id, member.id)
                if not boost_count:
                    return await ctx.send("There was an error getting your boost count.")
                if boost_count == 1:
                    await ctx.send(f"1 boost. Your usage is {count}/{self.nitro_limit*self.b1mult}.")
                elif boost_count == 2:
                    await ctx.send(f"2 boosts. Your usage is {count}/{self.nitro_limit*self.b2mult}.")
                else:
                    await ctx.send(f"{boost_count} boosts. There are no more perks after 2 boosts. Your usage is {count}/{self.nitro_limit*self.b2mult}.")
            else:
                await ctx.send(f"No boosts. Your usage is {count}/{self.nitro_limit}.")

    @tasks.loop(hours=24)
    async def cleanup_old_usage(self):
        today_dt = dt.combine(datetime.date.today() - datetime.timedelta(days=1), datetime.time(0, 0, 0))
        await self.nitro_usage.delete_many({'date': {'$lt': today_dt}})

    @tasks.loop(hours=2)
    async def check_promos(self):
        try:
            self.active_promo = await self.bot.loop.run_in_executor(None, get_active_promo, self.scraper)
            # self.logger.info(f"Checked promos. Active: {self.active_promo}")
        except Exception as e:
            self.logger.exception("Failed to check promos")

    @tasks.loop(minutes=5)
    async def update_embed(self):
        await self.bot.wait_until_ready()
        try:
            if self.nitro_toggle:
                if self.active_promo:
                    nitro_count = await self.bot.count_lines('nitro.txt')
                    if nitro_count is None: nitro_count = "Error"
                else: nitro_count = "No promo"
            else: nitro_count = "Disabled"
            ping = round(self.bot.latency * 1000)
            guild_count, user_count = len(self.bot.guilds), len(self.bot.users)
            for setting in self.embed_var:
                guild_id = setting['guild_id']
                channel_id = setting['channel_id']
                message_id = setting['message_id']
                channel = self.bot.get_channel(channel_id)
                if channel and isinstance(channel, discord.TextChannel):
                    embed = discord.Embed(title="Bot Status", description="Online 24/7, hosted somewhere...", color=discord.Color.random(), timestamp = datetime.datetime.now())
                    embed.add_field(name="Servers", value=f"{guild_count}")
                    embed.add_field(name="Users", value=f"{user_count}")
                    embed.add_field(name="Ping", value=f"{ping} ms")
                    embed.add_field(name="Nitro stock", value=f"{nitro_count}")
                    embed.add_field(name="Nitro given", value=f"{self.nitro_counter}")
                    embed.set_footer(text="coded by n01b")
                    message = await channel.fetch_message(message_id)
                    await message.edit(embed=embed)
                elif channel:
                    self.logger.warning(f"Channel {channel_id} is not a TextChannel, skipping embed update.")
                else:
                    self.logger.warning(f"Bot does not have access to {channel_id}")
        except discord.NotFound:
            await self.embed_settings.delete_one({'guild_id': guild_id})
            self.embed_var.remove(setting)
        except Exception as e:
            self.logger.exception(f"Failed to update embed: {e}")

    @commands.command(name="embe", help="Enable embed updates in the current channel.")
    @commands.is_owner()
    async def enable_embed(self, ctx):
        existing_entry = await self.embed_settings.find_one({'guild_id': ctx.guild.id})
        if existing_entry:
            return await self.bot.respond(ctx, "Embed updates are already enabled in this channel.")
        embed = discord.Embed(title="Enabled embed updates", description="The main content will be here soon.", color=discord.Color.green())
        message = await ctx.send(embed=embed)
        await self.embed_settings.insert_one({
            'guild_id': ctx.guild.id,
            'channel_id': ctx.channel.id,
            'message_id': message.id
        })
        self.embed_var.append({'guild_id': ctx.guild.id, 'channel_id': ctx.channel.id, 'message_id': message.id})
        await self.bot.respond(ctx, f"Embed updates enabled in {ctx.channel.mention}!")

    @commands.hybrid_command(name="embd", help="Disable embed updates in the current channel.")
    @commands.is_owner()
    async def disable_embed(self,ctx):
        existing_entry = await self.embed_settings.find_one({'guild_id': ctx.guild.id})
        if not existing_entry:
            return await self.bot.respond(ctx, "Embed updates are not enabled in this channel.")
        try:
            message = await ctx.channel.fetch_message(existing_entry['message_id'])
            await message.delete()
        except:
            pass
        await self.embed_settings.delete_one({'guild_id': ctx.guild.id})
        for i in self.embed_var:
            if i['channel_id'] == ctx.channel.id:
                self.embed_var.remove(i)
        await self.bot.respond(ctx, f"Embed updates disabled in {ctx.channel.mention}.")

    @commands.hybrid_command(name='nitrotoggle', help='Toggle nitro related commands.')
    @commands.is_owner()
    async def toggle_nitro(self, ctx, choice = None):
        if choice is None:
            self.nitro_toggle = not self.nitro_toggle
            await self.bot.counter.find_one_and_update({'_id': 'nitro_toggle'}, {'$set': {'state': self.nitro_toggle}}, upsert=True)
            await self.bot.respond(ctx, f"Nitro commands {'enabled' if self.nitro_toggle else 'disabled'}")
        else:
            # toggle the new nitro system
            self.new_nitro_system = not self.new_nitro_system
            await self.bot.counter.find_one_and_update({'_id': 'new_nitro_system'}, {'$set': {'state': self.new_nitro_system}}, upsert=True)
            await self.bot.respond(ctx, f"New nitro system {'enabled' if self.new_nitro_system else 'disabled'}")

async def setup(bot: Bot):
    await bot.add_cog(NitroCog(bot))
