import discord, random, os, time, datetime, re, traceback, aiohttp
from discord.ext import commands
from discord import app_commands
from gradio_client import Client
from openai import AsyncOpenAI

def split_response(response, max_length=1900):
    lines = response.splitlines()
    chunks = []
    current_chunk = ""
    for line in lines:
        if len(current_chunk) + len(line) + 1 > max_length:
            chunks.append(current_chunk.strip())
            current_chunk = line
        else:
            current_chunk += "\n" + line if current_chunk else line
    if current_chunk:
        chunks.append(current_chunk.strip())
    return chunks

class FunCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = self.bot.cog_logger(self.__class__.__name__)
        self.hf_token = os.environ['HF_TOKEN']
        self.client = AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.environ['OR_TOKEN'])
        self.merged = self.dev = self.schnell = None
        bot.loop.run_in_executor(None, self.load_models)

    def load_models(self):
        models = {
        "multimodalart/FLUX.1-merged": "merged",
        "black-forest-labs/FLUX.1-dev": "dev",
        "black-forest-labs/FLUX.1-schnell": "schnell"
        }
        for model, name in models.items():
            self.bot.loop.run_in_executor(None, self.load_one, model, name)

    def load_one(self, model_name, var_name):
        try:
            model = Client(model_name, self.hf_token, verbose=False)
            setattr(self, var_name, model)
        except Exception as e:
            self.logger.error(f'Model {model_name} failed to load: {e}')
            setattr(self, var_name, None)

    @commands.hybrid_command(name="cat", help="Sends a random cat image")
    async def cat(self, ctx):
        async with aiohttp.ClientSession() as session:
            response = await session.get("https://api.thecatapi.com/v1/images/search")
            data = await response.json()
        await ctx.send(data[0]["url"])

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

    @commands.hybrid_command(name="joke", help="Sends a random joke")
    async def joke(self, ctx):
        async with aiohttp.ClientSession() as session:
            response = await session.get("https://v2.jokeapi.dev/joke/Any?blacklistFlags=nsfw,religious,political,racist,sexist,explicit")
            joke = await response.json()
        if joke["type"] == "single":
            await ctx.send(joke["joke"])
        else:
            await ctx.send(f"{joke['setup']}\n{joke['delivery']}")

    @commands.hybrid_command(name="chat", help="Chat with ai")
    @commands.cooldown(1, 30, commands.BucketType.user)
    @app_commands.describe(prompt="A prompt for the ai")
    async def ai_chat(self, ctx, *, prompt: str):
        await ctx.defer()
        try:
            async with ctx.typing():
                # TODO: improve this
                completion = await self.client.chat.completions.create(
                    extra_headers={"HTTP-Referer": "http://noobnet.v0x.eu", "X-Title": "NoobNetwork (discord, Noob bot)"},
                    extra_body={},
                    model="deepseek/deepseek-chat-v3-0324:free",
                    messages=[
                        {
                        "role": "user",
                        "content": [
                            {
                            "type": "text",
                            "text": "You are a helpful Discord bot. Keep your answers short and to the point."
                            },
                            {
                            "type": "text",
                            "text": f"{prompt}"
                            },
                            ]}])
                msg = completion.choices[0].message.content
                chunks = split_response(msg)
                for chunk in chunks:
                    await ctx.reply(chunk)
        except Exception as e:
            self.logger.error(f'Error in chat command: {ctx.command.name}')
            print(traceback.format_exc())

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
        await self.bot.log(f'{ctx.author}, prompt: {prompt}, seed: {seed}, width: {width}, height: {height}, guidance_scale: {guidance_scale},steps: {steps}, model: {model}', "log.txt")
        # i will manually ban users who type something offensive
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
            return await ctx.send(f"Model {model} failed to load, try another one.", delete_after=10)
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
