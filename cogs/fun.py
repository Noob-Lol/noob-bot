import discord
from discord.ext import commands

class FunCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.hybrid_command(name="joke", help="Sends a joke")
    async def joke(self, ctx):
        await ctx.send('your fatherless')

async def setup(bot):
    await bot.add_cog(FunCog(bot))
