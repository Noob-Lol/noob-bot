import discord
from discord.ext import commands
class NitroCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.file_path = (f'{bot.script_path}/nitro.txt')
        self.nitro_db = bot.counter

    @commands.hybrid_command(name="nitro", help="Sends a free nitro link")
    async def nitro(self, ctx):
        with open(self.file_path, "r") as file:
            lines = file.readlines()
        if lines:
            first_line = lines[0].strip()
            with open(self.file_path, "w") as file:
                file.writelines(lines[1:])
            self.nitro_db.find_one_and_update({'_id': 'nitro_counter'}, {'$inc': {'count': 1}}, upsert=True)
            count = self.nitro_db.find_one({'_id': 'nitro_counter'})
            if count:
                await ctx.send(f'Here is your nitro! :arrow_down:   Total nitro used: **{count["count"]}** \n{first_line}')
        else:
            await ctx.send("No nitro codes left.")

    @commands.hybrid_command(name="status", help="Sends some info about the bot")
    async def status(self, ctx):
        count = self.nitro_db.find_one({'_id': 'nitro_counter'})['count']
        with open(self.file_path, 'r') as f:
            nitro_count=sum(1 for _ in f)
        embed = discord.Embed(title="Bot Status", description="Online 24/7, hosted somewhere...", color=discord.Color.blue())
        embed.add_field(name="Nitro available:", value=f"{nitro_count}", inline=False)
        embed.add_field(name="Total nitro used:", value=f"{count}", inline=False)
        embed.set_footer(text="coded by n01b")
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(NitroCog(bot))
