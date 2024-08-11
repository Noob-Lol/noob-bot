import discord, random, requests, os
from discord.ext import commands
from gradio_client import Client

class FunCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.gradio_client = Client("black-forest-labs/FLUX.1-schnell")

    @commands.hybrid_command(name="cat", help="Sends a random cat image")
    async def cat(self, ctx):
        await ctx.send(requests.get("https://api.thecatapi.com/v1/images/search").json()[0]["url"])
    
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

    @commands.hybrid_command(name="image", help="Generates an image")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def image(self, ctx, *,prompt: str, seed: int = 0):
        await ctx.defer()
        result = await self.bot.loop.run_in_executor(None, self.gradio_client.predict,
        prompt, 0, True, 1024, 1024, 4, "/infer")
        image_path, seed = result
        if os.path.exists(image_path):
            await ctx.send(f'Generated image, seed: {seed}',file=discord.File(image_path))
            try:
                os.remove(image_path)
                folder = os.path.dirname(image_path)
                if not os.listdir(folder):
                    os.rmdir(folder)
            except Exception as e:
                await ctx.send(f"Error while cleaning up: {e}")
        else:
            await ctx.send("Sorry, there was an issue generating the image.")

async def setup(bot):
    await bot.add_cog(FunCog(bot))
