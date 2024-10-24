import discord, os, datetime
from discord import app_commands
from discord.ext import commands, tasks

desc1, desc2 = "How many codes. Server booster only!", "Where to send the codes"
def p(desc, default = None):
    return commands.parameter(description=desc, default=default)

class NitroCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.nitro_usage = bot.db['nitro_usage']
        self.embed_settings = bot.db['embed_settings']
        self.embed_var = list(self.embed_settings.find())
        self.count = bot.counter.find_one({'_id': 'nitro_counter'})['count']
        self.update_embed.start()
        self.cleanup_old_limits.start()

    @commands.hybrid_command(name="nitro", help="Sends a free nitro link")
    @commands.cooldown(1, 5, commands.BucketType.guild)
    @app_commands.describe(amount=desc1, place=desc2)
    @app_commands.choices(
        place=[
            app_commands.Choice(name="dm", value="dm"),
            app_commands.Choice(name="channel (here, default)", value="channel")
        ]
    )
    async def nitro(self, ctx, amount: int = p(desc1, 1), place: str = p(desc2, "channel")):
        if os.path.exists(f'{self.bot.script_path}/lock.txt'):
            await ctx.send('The bot is in maintenance, please retry later.', delete_after=5)
            return
        place = place.lower() 
        if place != "dm" and place != "channel":
            await ctx.send("Invalid place. Must be 'dm' or 'channel'.", delete_after=5)
            return
        if amount > 1 and not ctx.author.premium_since:
            await ctx.send("You must be a server booster to get more than 1 code.", delete_after=5)
            return
        lines = self.bot.get_lines(amount, 'nitro.txt')
        if lines:
            if ctx.author.premium_since:
                pass
            else:
                today_dt = datetime.datetime.combine(datetime.date.today(), datetime.time(0, 0, 0))
                user_id = ctx.author.id
                result = self.nitro_usage.find_one({'user_id': user_id, 'date': today_dt})
                if result and result['count'] >= 10:
                    await ctx.send("You have exceeded the free limit. Try again tomorrow or boost the server.", delete_after=10)
                    return
                self.nitro_usage.update_one({'user_id': user_id, 'date': today_dt}, {'$inc': {'count': 1}}, upsert=True)
            if amount > 1:
                if amount > 40:
                    amount = 40
                codes = []  
                count = 0
                for line in lines:
                    if line:
                        codes.append(line[7::])
                        count += 1
                        if count == amount:
                            break
                    else:
                        break
                self.bot.counter.find_one_and_update({'_id': 'nitro_counter'}, {'$inc': {'count': count}}, upsert=True)
                self.count += count
                codes = '\n'.join(codes)
                self.bot.log(f'Booster {ctx.author.name} used {count} nitro codes: {codes}', 'nitro_log.txt')
                if place == "dm":
                    try:
                        await ctx.send(f"Sent {count} codes in dm.")
                        await ctx.author.send(codes)
                    except:
                        await ctx.send("Failed to send dm, sending it here.", ephemeral=True)
                        await ctx.send(codes)
                else:
                    await ctx.send(codes)
            else:
                first_line = lines[0].strip()
                self.bot.counter.find_one_and_update({'_id': 'nitro_counter'}, {'$inc': {'count': 1}}, upsert=True)
                self.count += 1
                self.bot.log(f'{ctx.author.name} used nitro code: {first_line}', 'nitro_log.txt')
                code = first_line[7::]
                if place == "dm":
                    try:
                        await ctx.send("Sent code in dm.")
                        await ctx.author.send(code)
                    except:
                        await ctx.send("Failed to send dm, sending it here.", ephemeral=True)
                        await ctx.send(code)
                else:
                    await ctx.send(code)
        else:
            await ctx.send("No nitro codes left.", delete_after=10)

    @tasks.loop(hours=24)
    async def cleanup_old_limits(self):
        today_dt = datetime.datetime.combine(datetime.date.today() - datetime.timedelta(days=1), datetime.time(0, 0, 0))
        self.nitro_usage.delete_many({'date': {'$lt': today_dt}})

    @tasks.loop(minutes=5)
    async def update_embed(self):
        try:
            for setting in self.embed_var:
                guild_id = setting['guild_id']
                channel_id = setting['channel_id']
                message_id = setting['message_id']
                channel = self.bot.get_channel(channel_id)
                if channel:
                    nitro_count = self.bot.get_lines(0, 'nitro.txt', True)
                    embed = discord.Embed(title="Bot Status", description="Online 24/7, hosted somewhere...", color=discord.Color.random(), timestamp = datetime.datetime.now())
                    embed.add_field(name="Servers", value=f"{len(self.bot.guilds)}")
                    embed.add_field(name="Users", value=f"{len(self.bot.users)}")
                    embed.add_field(name="Ping", value=f"{round (self.bot.latency * 1000)} ms")
                    embed.add_field(name="Nitro stock", value=f"{nitro_count}")
                    embed.add_field(name="Nitro given", value=f"{self.count}")
                    embed.set_footer(text="coded by n01b")
                    message = await channel.fetch_message(message_id)
                    await message.edit(embed=embed)
        except discord.NotFound:
            self.embed_settings.delete_one({'guild_id': guild_id})
            self.embed_var.remove(setting)
        except Exception as e:
            print(f"An error occurred: {e}")

    @commands.command(name="embe", help="Enable embed updates in the current channel.")
    @commands.is_owner()
    async def enable_embed(self, ctx):
        await ctx.message.delete()
        existing_entry = self.embed_settings.find_one({'guild_id': ctx.guild.id})
        if existing_entry:
            await ctx.send("Embed updates are already enabled in this channel.", delete_after=5)
            return
        embed = discord.Embed(title="Enabled embed updates", description="The main content will be here soon.", color=discord.Color.green())
        message = await ctx.send(embed=embed)
        self.embed_settings.insert_one({
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
        existing_entry = self.embed_settings.find_one({'guild_id': ctx.guild.id})
        if not existing_entry:
            await ctx.send("Embed updates are not enabled in this channel.", delete_after=5)
            return
        try:
            message = await ctx.channel.fetch_message(existing_entry['message_id'])
            await message.delete()
        except:
            pass
        self.embed_settings.delete_one({'guild_id': ctx.guild.id})
        for i in self.embed_var:
            if i['channel_id'] == ctx.channel.id:
                self.embed_var.remove(i)
        await ctx.send(f"Embed updates disabled in {ctx.channel.mention}.", delete_after=5)

async def setup(bot):
    await bot.add_cog(NitroCog(bot))
