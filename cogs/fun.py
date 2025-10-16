import os
import random
import time

import discord
import openai
from discord import app_commands
from discord.ext import commands
from gradio_client import Client

from bot import BaseCog, Bot, Ctx


def split_response(response: str, max_length=1900):
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


class FunCog(BaseCog):
    def __init__(self, bot: Bot):
        super().__init__(bot)
        self.hf_token = os.getenv("HF_TOKEN")
        base_url = os.getenv("CHAT_API_BASE_URL")
        api_key = os.getenv("CHAT_API_KEY")
        self.chat_model = os.getenv("CHAT_MODEL")
        self.client = None
        if base_url and api_key:
            try:
                self.client = openai.AsyncOpenAI(base_url=base_url, api_key=api_key)
            except Exception as e:
                self.logger.exception(f"Failed to init chat client: {e}")
        else:
            self.logger.warning("CHAT_API_BASE_URL or CHAT_API_KEY not set; chat is disabled")
        self.merged = self.dev = self.schnell = None

    async def cog_load(self):
        if not self.hf_token:
            self.logger.warning("HF_TOKEN not configured; skipping model preloading")
        else:
            await self.bot.loop.run_in_executor(None, self.load_models)

    def load_models(self):
        models = {
            "multimodalart/FLUX.1-merged": "merged",
            "black-forest-labs/FLUX.1-dev": "dev",
            "black-forest-labs/FLUX.1-schnell": "schnell",
        }
        for model, name in models.items():
            self.bot.loop.run_in_executor(None, self.load_one, model, name)

    def load_one(self, model_name, var_name):
        try:
            model = Client(model_name, self.hf_token, verbose=False)
            setattr(self, var_name, model)
        except Exception as e:
            self.logger.error(f"Model {model_name} failed to load: {e}")
            setattr(self, var_name, None)

    @commands.hybrid_command(name="cat", help="Sends a random cat image")
    async def cat(self, ctx: Ctx):
        response = await self.bot.session.get("https://api.thecatapi.com/v1/images/search")
        data = await response.json()
        await ctx.send(data[0]["url"])

    @commands.hybrid_command(name="flip", help="Flips a coin")
    async def flip(self, ctx: Ctx):
        choices = ["Heads", "Tails"]
        await ctx.send(f"**{ctx.author.name}** flipped a coin and it landed on **{random.choice(choices)}**")

    @commands.hybrid_command(name="random", help="Sends a random number")
    async def random(self, ctx: Ctx, min: int | None, max: int | None):
        if min is None or max is None:
            await ctx.send("Input two numbers", delete_after=3)
        elif min == max:
            await ctx.send("Numbers are equal", delete_after=3)
        else:
            if min > max:
                min, max = max, min
            await ctx.send(f"**{ctx.author.name}** rolled a **{random.randint(min, max)}**")

    @commands.hybrid_command(name="joke", help="Sends a random joke")
    async def joke(self, ctx: Ctx):
        flags = "nsfw,religious,political,racist,sexist,explicit"
        response = await self.bot.session.get(f"https://v2.jokeapi.dev/joke/Any?blacklistFlags={flags}")
        joke = await response.json()
        if joke["type"] == "single":
            await ctx.send(joke["joke"])
        else:
            await ctx.send(f"{joke['setup']}\n{joke['delivery']}")

    async def get_sys_prompt(self, ctx: Ctx):
        guild = ctx.guild.name if ctx.guild else "DM"
        channel = getattr(ctx.channel, "name", "DM")
        user = ctx.author.display_name
        sys_info = f"Current time (UTC): {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())}. AI Model: {self.chat_model}"
        if not self.bot.owner_id:
            await self.bot.is_owner(ctx.author)
            assert self.bot.owner_id
        is_owner = ctx.author.id == self.bot.owner_id
        owner_status = "Yes" if is_owner else "No"
        bot_info = f"Bot User='{self.bot.user}', Server='{guild}', Channel='{channel}', User='{user}', User Owner='{owner_status}'"
        disclaimer = "Never invent Discord Nitro links; free Nitro is only from official Discord promotions."
        return (
            "You are a helpful Discord bot. Keep your answers short and to the point. "
            f"{disclaimer} Context: Bot name (you)='Noob Bot', {bot_info}, {sys_info}. "
            "Bot command prefix is '>'. If a line begins with '>', treat it as a command, not general chat."
        )

    async def generate_message(self, client: openai.AsyncOpenAI, chat_model: str, ctx: Ctx, prompt: str):
        """Generates an AI message with channel/user context and returns it. On error return the error message."""
        try:
            start = time.perf_counter()
            sys_prompt = await self.get_sys_prompt(ctx)

            # Build recent message history with authors
            history_messages: list[dict] = []
            try:
                async for m in ctx.channel.history(limit=12, oldest_first=False):
                    if m.id == ctx.message.id:
                        continue
                    content = m.clean_content if hasattr(m, "clean_content") else m.content
                    if not content:
                        continue
                    if content.strip().startswith(">"):
                        continue
                    role = "assistant" if m.author.id == ctx.bot.user.id else "user"
                    author_name = getattr(m.author, "display_name", getattr(m.author, "name", "user"))
                    history_messages.append({"role": role, "content": f"{author_name}: {self._trim(content)}"})
                history_messages.reverse()  # chronological
                # print(history_messages)
            except Exception as e:
                self.logger.warning(f"Failed to fetch message history for context: {e}")

            messages = [
                {"role": "system", "content": sys_prompt},
                *history_messages,
                {"role": "user", "content": f"{ctx.author.display_name}: {prompt}"},
            ]

            completion = await client.chat.completions.create(
                extra_headers={"HTTP-Referer": "https://noob.pics", "X-Title": "NoobNetwork (discord, Noob bot)"},
                model=chat_model,
                messages=messages,
            )
            msg = completion.choices[0].message.content
            if not msg:
                self.logger.error("Empty response from ai_chat command")
                return "Something went wrong, please try again later"
            gen_time = time.perf_counter() - start
            ai_footer = f"\n-# This is AI-generated. Time: {gen_time:.2f}s"
            msg += ai_footer
            return msg
        except openai.RateLimitError:
            self.logger.warning("Api rate limit exceeded")
            return "Api rate limit exceeded, please try again later"
        except Exception as e:
            self.logger.exception(f"Error in ai_chat command while creating completion: {e}")
            return "Something went wrong, please try again later"

    @commands.hybrid_command(name="chat", help="Chat with ai")
    @commands.cooldown(1, 30, commands.BucketType.user)
    @app_commands.describe(prompt="A prompt for the ai")
    async def ai_chat(self, ctx: Ctx, *, prompt: str):
        if not self.client or not self.chat_model:
            self.logger.error("Chat API not configured; missing client or CHAT_MODEL")
            return await ctx.reply("Chat is not configured right now.")
        await ctx.defer()
        try:
            async with ctx.typing():
                msg = await self.generate_message(self.client, self.chat_model, ctx, prompt)
                chunks = split_response(msg)
                for chunk in chunks:
                    await ctx.reply(chunk)
        except Exception as e:
            self.logger.exception(f"Error in ai_chat command: {e}")

    @commands.hybrid_command(name="image", help="Generates an image")
    @commands.cooldown(1, 30, commands.BucketType.user)
    @app_commands.describe(
        prompt="A prompt for the image", seed="default=random", width="default=1024", height="default=1024",
        guidance_scale="default=3.5, not used by schnell", steps="default=4", model="default=schnell",
        )
    @app_commands.choices(
        model=[
            app_commands.Choice(name="schnell", value="schnell"),
            app_commands.Choice(name="merged", value="merged"),
            app_commands.Choice(name="dev", value="dev"),
        ])
    async def image(self, ctx: Ctx, *, prompt: str, seed: int = 0, width: int = 1024, height: int = 1024,
                    guidance_scale: float = 3.5, steps: int = 4, model: str = "schnell"):
        await ctx.defer()
        rand = True
        if seed != 0:
            rand = False
        arg_names = ["prompt", "seed", None, "width", "height", "guidance_scale", "steps"]
        args = [prompt, seed, rand, width, height, guidance_scale, steps]
        log_args = ", ".join(f"{name}: {value}" for name, value in zip(arg_names, args, strict=False) if name is not None)
        # i will manually ban users who type something offensive
        await self.bot.log_to_file(f"{ctx.author}, {log_args}, model: {model}", "log.txt")
        start_time = time.perf_counter()
        if self.dev and model == "dev":
            result = await self.bot.loop.run_in_executor(None, self.dev.predict, *args, "/infer")
        elif self.merged and model == "merged":
            result = await self.bot.loop.run_in_executor(None, self.merged.predict, *args, "/infer")
        elif self.schnell and model == "schnell":
            args.remove(guidance_scale)
            result = await self.bot.loop.run_in_executor(None, self.schnell.predict, *args, "/infer")
        else:
            return await ctx.send(f"Model {model} failed to load, try another one.", delete_after=10)
        image_path, seed = result
        if await self.bot.path_exists(image_path):
            gen_time = time.perf_counter() - start_time
            await ctx.send(f"Generated image in {gen_time:.2f} seconds, seed: {seed}", file=discord.File(image_path))
            try:
                os.remove(image_path)
                folder = os.path.dirname(image_path)
                if not os.listdir(folder):
                    os.rmdir(folder)
            except Exception as e:
                await ctx.send(f"Error while cleaning up: {e}")
        else:
            await ctx.send("Sorry, there was an issue generating the image.")

    def _trim(self, text: str, max_len: int = 500) -> str:
        if not text:
            return ""
        if "\n-# This is AI-generated." in text:
            text = text.split("\n-# This is AI-generated.")[0]
        if len(text) <= max_len:
            return text
        return text[: max_len - 1] + "…"


async def setup(bot: Bot):
    await bot.add_cog(FunCog(bot))
