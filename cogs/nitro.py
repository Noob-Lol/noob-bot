import discord, os, datetime, asyncio
from discord import app_commands
from discord.ext import commands, tasks

desc1, desc2 = "How many codes", "Where to send"
def p(desc, default = None):
    return commands.parameter(description=desc, default=default)

class NitroCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = bot.cog_logger(self.__class__.__name__)
        self.nitro_usage = bot.db['nitro_usage']
        self.eco = bot.db['economy']
        self.embed_settings = bot.db['embed_settings']
        self.cleanup_old_limits.start()

    async def cog_load(self):
        # load variables in async
        self.embed_var = [doc async for doc in self.embed_settings.find()]
        counter_ids = ['nitro_counter', 'nitro_limit', 'b1mult', 'b2mult', 'new_nitro_system', 'nitro_toggle']
        coros = [self.bot.counter.find_one({'_id': counter_id}) for counter_id in counter_ids] # await
        results = await asyncio.gather(*coros)
        # Map results
        for _id, doc in zip(counter_ids, results):
            if doc is None:
                # fallback defaults if no doc found
                if _id in ['new_nitro_system', 'nitro_toggle']:
                    setattr(self, _id, True)
                else:
                    setattr(self, _id, 0)
            else:
                # 'count' for most, 'state' for the last two
                if _id in ['new_nitro_system', 'nitro_toggle']:
                    setattr(self, _id, doc.get('state', True))
                else:
                    setattr(self, _id, doc.get('count', 0))
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
    async def nitro(self, ctx, amount: int = p(desc1, 1), place: str = p(desc2, "dm")):
        if not self.nitro_toggle:
            if not ctx.interaction: await ctx.message.delete()
            return await self.bot.respond(ctx, "Nitro commands are disabled.")
        if os.path.exists(f'{self.bot.script_path}/lock.txt'):
            if not ctx.interaction: await ctx.message.delete()
            return await self.bot.respond(ctx, 'The bot is in maintenance, please retry later.')
        place = place.lower()
        if place != "dm" and place != "channel":
            return await self.bot.respond(ctx, "Invalid place. Must be 'dm' or 'channel'.")
        if amount > 40:
            amount = 40
        if amount < 0:
            return await self.bot.respond(ctx, "Amount can't be negative.")
        try:
            lines = await self.bot.get_lines(0, 'nitro.txt')
            if lines is None:
                return await ctx.send("There was an error checking the code stock.")
            if lines > 0:
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
                            return await ctx.send(f"You don't have enough nitro credits. {user['balance']}/{amount}.")
                        await self.eco.update_one({'_id': user_id}, {'$inc': {'balance': -amount}})
                    else:
                        # old nitro system
                        today_dt = datetime.datetime.combine(datetime.date.today(), datetime.time(0, 0, 0))
                        result = await self.nitro_usage.find_one({'user_id': user_id, 'date': today_dt})
                        limit = self.nitro_limit
                        if result:
                            rcount = result['count']
                            if ctx.author.premium_since:
                                boost_count = self.bot.check_boost(ctx.guild.id, user_id)
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
                    await self.bot.log(f'{ctx.author.name} got {count} nitro codes: {codes}', 'nitro_log.txt')
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
                    await self.bot.log(f'{ctx.author.name} got nitro code: {first_line}', 'nitro_log.txt')
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
            else:
                if not ctx.interaction: await ctx.message.delete()
                await self.bot.respond(ctx, "No nitro codes left.", 10)
        except Exception as e:
            self.logger.exception(f"Error in nitro command")
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
        if not ctx.interaction: await ctx.message.delete()
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
        await ctx.send(f"Updated {limit} to {amount}.")
    
    @commands.hybrid_command(name="what", help="View nitro limit.")
    async def get_limit(self, ctx):
        if not self.nitro_toggle:
            if not ctx.interaction: await ctx.message.delete()
            return await self.bot.respond(ctx, "Nitro commands are disabled.")
        if self.new_nitro_system:
            return await ctx.send("1 promo = 1 nitro credit")
        await ctx.send(f"Current nitro limit (daily): {self.nitro_limit}, multipliers: 1 boost = {self.b1mult}, 2 boosts = {self.b2mult}")

    @commands.hybrid_command(name="usage", help="View nitro usage.")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def usage(self, ctx):
        if not self.nitro_toggle:
            if not ctx.interaction: await ctx.message.delete()
            return await self.bot.respond(ctx, "Nitro commands are disabled.")
        if self.new_nitro_system:
            return await ctx.send("This command is not available in the new nitro system.")
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
    async def cleanup_old_limits(self):
        today_dt = datetime.datetime.combine(datetime.date.today() - datetime.timedelta(days=1), datetime.time(0, 0, 0))
        await self.nitro_usage.delete_many({'date': {'$lt': today_dt}})

    @tasks.loop(minutes=5)
    async def update_embed(self):
        await self.bot.wait_until_ready()
        try:
            for setting in self.embed_var:
                guild_id = setting['guild_id']
                channel_id = setting['channel_id']
                message_id = setting['message_id']
                channel = self.bot.get_channel(channel_id)
                if channel:
                    if self.nitro_toggle:
                        nitro_count = await self.bot.get_lines(0, 'nitro.txt')
                        if nitro_count is None:
                            nitro_count = "Error"
                    else:
                        nitro_count = "N/A"
                    embed = discord.Embed(title="Bot Status", description="Online 24/7, hosted somewhere...", color=discord.Color.random(), timestamp = datetime.datetime.now())
                    embed.add_field(name="Servers", value=f"{len(self.bot.guilds)}")
                    embed.add_field(name="Users", value=f"{len(self.bot.users)}")
                    embed.add_field(name="Ping", value=f"{round (self.bot.latency * 1000)} ms")
                    embed.add_field(name="Nitro stock", value=f"{nitro_count}")
                    embed.add_field(name="Nitro given", value=f"{self.nitro_counter}")
                    embed.set_footer(text="coded by n01b")
                    message = await channel.fetch_message(message_id)
                    await message.edit(embed=embed)
                else:
                    self.logger.warning(f"Bot does not have access to {channel_id}")
        except discord.NotFound:
            await self.embed_settings.delete_one({'guild_id': guild_id})
            self.embed_var.remove(setting)
        except Exception as e:
            self.logger.exception("Failed to update embed")

    @commands.command(name="embe", help="Enable embed updates in the current channel.")
    @commands.is_owner()
    async def enable_embed(self, ctx):
        await ctx.message.delete()
        existing_entry = await self.embed_settings.find_one({'guild_id': ctx.guild.id})
        if existing_entry:
            return await ctx.send("Embed updates are already enabled in this channel.", delete_after=5)
        embed = discord.Embed(title="Enabled embed updates", description="The main content will be here soon.", color=discord.Color.green())
        message = await ctx.send(embed=embed)
        await self.embed_settings.insert_one({
            'guild_id': ctx.guild.id,
            'channel_id': ctx.channel.id,
            'message_id': message.id
        })
        self.embed_var.append({'guild_id': ctx.guild.id, 'channel_id': ctx.channel.id, 'message_id': message.id})
        await ctx.send(f"Embed updates enabled in {ctx.channel.mention}!", delete_after=5)

    @commands.hybrid_command(name="embd", help="Disable embed updates in the current channel.")
    @commands.is_owner()
    async def disable_embed(self,ctx):
        await ctx.message.delete()
        existing_entry = await self.embed_settings.find_one({'guild_id': ctx.guild.id})
        if not existing_entry:
            return await ctx.send("Embed updates are not enabled in this channel.", delete_after=5)
        try:
            message = await ctx.channel.fetch_message(existing_entry['message_id'])
            await message.delete()
        except:
            pass
        await self.embed_settings.delete_one({'guild_id': ctx.guild.id})
        for i in self.embed_var:
            if i['channel_id'] == ctx.channel.id:
                self.embed_var.remove(i)
        await ctx.send(f"Embed updates disabled in {ctx.channel.mention}.", delete_after=5)

    @commands.hybrid_command(name='nitrotoggle', help='Toggle nitro related commands.')
    @commands.is_owner()
    async def toggle_nitro(self, ctx, choice = None):
        if not ctx.interaction: await ctx.message.delete()
        if choice is None:
            self.nitro_toggle = not self.nitro_toggle
            await self.bot.counter.find_one_and_update({'_id': 'nitro_toggle'}, {'$set': {'state': self.nitro_toggle}}, upsert=True)
            await self.bot.respond(ctx, f"Nitro commands {'enabled' if self.nitro_toggle else 'disabled'}")
        else:
            # toggle the new nitro system
            self.new_nitro_system = not self.new_nitro_system
            await self.bot.counter.find_one_and_update({'_id': 'new_nitro_system'}, {'$set': {'state': self.new_nitro_system}}, upsert=True)
            await self.bot.respond(ctx, f"New nitro system {'enabled' if self.new_nitro_system else 'disabled'}")

async def setup(bot):
    await bot.add_cog(NitroCog(bot))
