import discord, os, time, datetime
from discord.ext import commands, tasks
CHANNEL_ID = 1282133552699277342
MESSAGE_ID = 1282133957239902249

class NitroCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot_path = bot.script_path
        self.file_path = (f'{self.bot_path}/nitro.txt')
        self.nitro_db = bot.counter
        self.update_embed.start()

    @commands.hybrid_command(name="nitro", help="Sends a free nitro link")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def nitro(self, ctx):
        if os.path.exists(f'{self.bot_path}/lock.txt'):
            await ctx.send('More nitro codes are being added, please retry later.', delete_after=5)
            return
        with open(self.file_path, "r") as file:
            lines = file.readlines()
        if lines:
            first_line = lines[0].strip()
            with open(self.file_path, "w") as file:
                file.writelines(lines[1:])
            self.nitro_db.find_one_and_update({'_id': 'nitro_counter'}, {'$inc': {'count': 1}}, upsert=True)
            await ctx.send(first_line)
        else:
            await ctx.send("No nitro codes left.")

    @tasks.loop(minutes=5)
    async def update_embed(self):
        channel = self.bot.get_channel(CHANNEL_ID)
        if isinstance(channel, discord.TextChannel):
            message = await channel.fetch_message(MESSAGE_ID)
        else:
            return
        count = self.nitro_db.find_one({'_id': 'nitro_counter'})['count']
        with open(self.file_path, 'r') as f:
            nitro_count=sum(1 for _ in f)
        embed = discord.Embed(title="Bot Status", description="Online 24/7, hosted somewhere...", color=discord.Color.random(), timestamp = datetime.datetime.now())
        embed.add_field(name="Servers", value=f"{len(self.bot.guilds)}")
        embed.add_field(name="Users", value=f"{len(self.bot.users)}")
        embed.add_field(name="Ping", value=f"{round (self.bot.latency * 1000)} ms")
        embed.add_field(name="Nitro stock", value=f"{nitro_count}")
        embed.add_field(name="Nitro given", value=f"{count}")
        embed.set_footer(text="coded by n01b")
        await message.edit(embed=embed)

async def setup(bot):
    await bot.add_cog(NitroCog(bot))
