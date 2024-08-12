import discord, random, requests, os, time
from discord.ext import commands
from discord import app_commands
from gradio_client import Client
HF_TOKEN = os.environ["HF_TOKEN"]
class FunCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.schnell = Client("black-forest-labs/FLUX.1-schnell", HF_TOKEN)
        time.sleep(3)
        self.dev = Client("black-forest-labs/FLUX.1-dev", HF_TOKEN)
        self.log_path = (f'{bot.script_path}/log.txt')

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
            await ctx.send("Input two numbers", delete_after=3)
        elif min == max:
            await ctx.send("Numbers are equal", delete_after=3)
        else:
            if min > max:
                min, max = max, min
            await ctx.send(f"**{ctx.author.name}** rolled a **{random.randint(min, max)}**")

    @commands.hybrid_command(name="image", help="Generates an image")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def image(self, ctx, *, prompt: str, seed: int = 0, width: int = 1024, height: int = 1024, steps: int = 4, client: str = "schnell"):
        await ctx.defer()
        with open(self.log_path, 'a') as f:
            f.write(f"{ctx.author}, prompt: {prompt}, seed: {seed}, width: {width}, height: {height}, steps: {steps}, client: {client}\n")
        rand = True
        if seed != 0:
            rand = False
        start_time = time.time()
        if client == "schnell":
            result = await self.bot.loop.run_in_executor(None, self.schnell.predict,prompt,seed,rand,width,height,steps,"/infer")
        elif client == "dev":
            result = await self.bot.loop.run_in_executor(None,self.dev.predict,prompt,seed,rand,width,height,3.5,steps,"/infer")
        else:
            await ctx.send("Invalid client. Please use 'schnell' or 'dev'.", delete_after=5)
            return
        image_path, seed = result
        if os.path.exists(image_path):
            gen_time = time.time() - start_time
            await ctx.send(f'Generated image in {gen_time:.2f} seconds, seed: {seed}',file=discord.File(image_path))
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
