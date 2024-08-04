import discord, random, requests
from discord.ext import commands

class FunCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.hybrid_command(name="joke", help="Sends a joke")
    async def joke(self, ctx):
        await ctx.send('your fatherless')

    @commands.hybrid_command(name="flip", help="Flips a coin")
    async def flip(self, ctx):
        choices = ["Heads", "Tails"]
        await ctx.send(f"**{ctx.author.name}** flipped a coin and it landed on **{random.choice(choices)}**")

    @commands.hybrid_command(name="random", help="Sends a random number")
    async def random(self, ctx, min: int|None, max: int|None):
        if min is None or max is None:
            await ctx.send("Input two numbers")
        elif min == max:
            await ctx.send("Numbers are equal")
        else:
            if min > max:
                min, max = max, min
            await ctx.send(f"**{ctx.author.name}** rolled a **{random.randint(min, max)}**")

    @commands.hybrid_command(name="cat", help="Sends a random cat image")
    async def cat(self, ctx):
        await ctx.send(requests.get("https://api.thecatapi.com/v1/images/search").json()[0]["url"])

async def setup(bot):
    await bot.add_cog(FunCog(bot))
