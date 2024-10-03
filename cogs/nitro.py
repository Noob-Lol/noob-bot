import discord, os, datetime
from discord.ext import commands, tasks

class NitroCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.start_time = datetime.datetime.now()
        self.embed_settings = bot.db['embed_settings']
        self.update_embed.start()

    @commands.hybrid_command(name="nitro", help="Sends a free nitro link")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def nitro(self, ctx):
        if os.path.exists(f'{self.bot.script_path}/lock.txt'):
            await ctx.send('The bot is in maintenance, please retry later.', delete_after=5)
            return
        with open(f'{self.bot.script_path}/nitro.txt', "r") as file:
            lines = file.readlines()
        if lines:
            first_line = lines[0].strip()
            with open(f'{self.bot.script_path}/nitro.txt', "w") as file:
                file.writelines(lines[1:])
            self.bot.counter.find_one_and_update({'_id': 'nitro_counter'}, {'$inc': {'count': 1}}, upsert=True)
            with open(f'{self.bot.script_path}/nitro_log.txt', 'a') as file:
                file.write(f'{ctx.author.name} used nitro code: {first_line}\n')
            await ctx.send(first_line)
        else:
            await ctx.send("No nitro codes left.", delete_after=10)

    @tasks.loop(minutes=5)
    async def update_embed(self):
        try:
            settings = self.embed_settings.find()
            for setting in settings:
                guild_id = setting['guild_id']
                channel_id = setting['channel_id']
                message_id = setting['message_id']
                channel = self.bot.get_channel(channel_id)
                if channel:
                    count = self.bot.counter.find_one({'_id': 'nitro_counter'})['count']
                    with open(f'{self.bot.script_path}/nitro.txt', 'r') as f:
                        nitro_count=sum(1 for _ in f)
                    embed = discord.Embed(title="Bot Status", description="Online 24/7, hosted somewhere...", color=discord.Color.random(), timestamp = datetime.datetime.now())
                    embed.add_field(name="Servers", value=f"{len(self.bot.guilds)}")
                    embed.add_field(name="Users", value=f"{len(self.bot.users)}")
                    embed.add_field(name="Ping", value=f"{round (self.bot.latency * 1000)} ms")
                    embed.add_field(name="Nitro stock", value=f"{nitro_count}")
                    embed.add_field(name="Nitro given", value=f"{count}")
                    uptime = datetime.datetime.now() - self.start_time
                    hours, remainder = divmod(uptime.seconds, 3600)
                    minutes, _ = divmod(remainder, 60)
                    embed.add_field(name="Uptime", value=f"{hours} h, {minutes} m")
                    embed.set_footer(text="coded by n01b")
                    message = await channel.fetch_message(message_id)
                    await message.edit(embed=embed)
        except discord.NotFound:
            self.embed_settings.delete_one({'guild_id': guild_id})
        except discord.HTTPException as e:
            print(f"HTTP exception occurred: {e}")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")

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
        await ctx.send(f"Embed updates disabled in {ctx.channel.mention}.", delete_after=5)

async def setup(bot):
    await bot.add_cog(NitroCog(bot))
