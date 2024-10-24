import discord, random, requests, os, time, datetime
from discord.ext import commands
from discord import app_commands
from gradio_client import Client

banned_words = ['gay', "sex", 'nigg', 'porn', 'nude']
class FunCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        bot.loop.run_in_executor(None, self.load_merged)
        bot.loop.run_in_executor(None, self.load_dev)
        bot.loop.run_in_executor(None, self.load_schnell)

    def load_merged(self):
        try:
            self.merged = Client("multimodalart/FLUX.1-merged")
        except Exception as e:
            print(f'Merged model failed to load: {e}')
            self.merged = None

    def load_dev(self):
        try:
            self.dev = Client("black-forest-labs/FLUX.1-dev")
        except Exception as e:
            print(f'Dev model failed to load: {e}')
            self.dev = None

    def load_schnell(self):
        try:
            self.schnell = Client("black-forest-labs/FLUX.1-schnell")
        except Exception as e:
            print(f'Schnell model failed to load: {e}')
            self.schnell = None

    @commands.hybrid_command(name="cat", help="Sends a random cat image")
    async def cat(self, ctx):
        await ctx.send(requests.get("https://api.thecatapi.com/v1/images/search").json()[0]["url"])

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
    @commands.cooldown(1, 30, commands.BucketType.user)
    @app_commands.describe(prompt="A prompt for the image", seed="default=random", width="default=1024", height="default=1024", guidance_scale="default=3.5, not used by schnell",steps="default=4", model="default=schnell")
    @app_commands.choices(
        model=[
            app_commands.Choice(name="schnell", value="schnell"),
            app_commands.Choice(name="merged", value="merged"),
            app_commands.Choice(name="dev", value="dev")
        ])
    async def image(self, ctx, *, prompt: str, seed: int = 0, width: int = 1024, height: int = 1024, guidance_scale: float = 3.5, steps: int = 4, model: str = "schnell"):
        await ctx.defer()
        self.bot.log(f'{ctx.author}, prompt: {prompt}, seed: {seed}, width: {width}, height: {height}, guidance_scale: {guidance_scale},steps: {steps}, model: {model}', "log.txt")
        if any(word in prompt.lower() for word in banned_words):
            duration = datetime.timedelta(seconds=120)
            await ctx.author.timeout(duration,reason="Banned word used")
            await ctx.send("Banned word used, you have been timed out.")
            return
        rand = True
        if seed != 0:
            rand = False
        start_time = time.time()
        if self.dev and model == "dev":
            result = await self.bot.loop.run_in_executor(None,self.dev.predict,prompt,seed,rand,width,height,guidance_scale,steps,"/infer")
        elif self.merged and model == "merged":
            result = await self.bot.loop.run_in_executor(None,self.merged.predict,prompt,seed,rand,width,height,guidance_scale,steps,"/infer")
        elif self.schnell and model == "schnell":
            result = await self.bot.loop.run_in_executor(None, self.schnell.predict,prompt,seed,rand,width,height,steps,"/infer")
        else:
            await ctx.send("Error, this model failed to load.", delete_after=10)
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
