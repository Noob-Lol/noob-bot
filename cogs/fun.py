import io
import json
import random
import time

import discord
import openai
from discord import app_commands
from discord.ext import commands
from noob_gradio import Client

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
        hf_token = bot.get_env("HF_TOKEN")
        base_url = bot.get_env("CHAT_API_BASE_URL")
        api_key = bot.get_env("CHAT_API_KEY")
        self.chat_model = bot.get_env("CHAT_MODEL")
        self.client = None
        if base_url and api_key:
            try:
                self.client = openai.AsyncOpenAI(base_url=base_url, api_key=api_key)
            except Exception as e:
                self.logger.exception(f"Failed to init chat client: {e}")
        else:
            self.logger.warning("CHAT_API_BASE_URL or CHAT_API_KEY not set; chat is disabled")
        self.img_client = Client(hf_token=hf_token, download_files=False)

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
    async def random(self, ctx: Ctx, min: int, max: int):
        if min == max:
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
        prefix = self.bot.prefix
        bot_info = f"Bot User='{self.bot.user}', Server='{guild}', Channel='{channel}', User='{user}', User Owner='{owner_status}'"
        disclaimer = "Never invent Discord Nitro links; free Nitro is only from official Discord promotions."
        return (
            "You are a helpful Discord bot. Keep your answers short and to the point. "
            f"{disclaimer} Context: Bot name (you)='Noob Bot', {bot_info}, {sys_info}. "
            f"Bot command prefix is '{prefix}'. If a line begins with '{prefix}', treat it as a command, not general chat."
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
                    if content.strip().startswith(self.bot.prefix):
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
            # moderation is not required for chat, as the model should handle it itself
            async with ctx.typing():
                msg = await self.generate_message(self.client, self.chat_model, ctx, prompt)
                chunks = split_response(msg)
                for chunk in chunks:
                    await ctx.reply(chunk)
        except Exception as e:
            self.logger.exception(f"Error in ai_chat command: {e}")

    async def moderate_text(self, input_text: str) -> tuple[bool, str]:
        """
        Moderates the prompt using some ai model.
        Returns (is_safe, reason_if_unsafe)
        """
        if not self.client:
            self.logger.warning("Moderation client not configured, skipping moderation")
            return True, ""
        try:
            # this was made for nvidia api and this specific model
            mod_model = "nvidia/llama-3.1-nemotron-safety-guard-8b-v3"
            response = await self.client.chat.completions.create(model=mod_model, messages=[
                {"role": "user", "content": input_text},
            ])
            result = response.choices[0].message.content
            if not result:
                self.logger.error("Empty response from moderation endpoint")
                return False, ""
            try:
                result_json: dict = json.loads(result)
            except json.JSONDecodeError:
                self.logger.error(f"Failed to decode JSON from moderation response: {result}")
                return False, ""
            # Check for unsafe content
            safety = result_json.get("User Safety")
            if safety == "unsafe":
                reason = result_json.get("Safety Categories", "No reason provided")
                return False, reason
            return True, ""
        except Exception as e:
            self.logger.exception(f"Error in prompt moderation: {e}")
            return False, ""

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
            app_commands.Choice(name="krea-dev", value="krea-dev"),
        ])
    async def image(self, ctx: Ctx, *, prompt: str, seed: int = 0, width: int = 1024, height: int = 1024,
                    guidance_scale: float = 3.5, steps: int = 4, model: str = "schnell") -> None:
        await ctx.defer()
        arg_dict: dict = {"prompt": prompt, "api_name": "/infer"}
        # Only add non-default values
        if seed != 0:
            arg_dict.update({"seed": seed, "randomize_seed": False})
        if width != 1024:
            arg_dict["width"] = width
        if height != 1024:
            arg_dict["height"] = height
        if guidance_scale != 3.5 and model != "schnell":
            arg_dict["guidance_scale"] = guidance_scale
        if steps != 4:
            arg_dict["num_inference_steps"] = steps

        arg_names = ["prompt", "seed", "width", "height", "guidance_scale", "steps"]
        # build args for logging without modifying arg_dict; map 'steps' to 'num_inference_steps'
        args = []
        for name in arg_names:
            if name not in arg_dict:
                args.append(None)
            if name == "steps":
                args.append(arg_dict.get("num_inference_steps"))
            else:
                args.append(arg_dict.get(name))
        log_args = ", ".join(f"{name}: {value}" for name, value in zip(arg_names, args, strict=False) if value is not None)
        await self.bot.log_to_file(f"{ctx.author}, {log_args}, model: {model}", "log.txt")
        is_safe, reason = await self.moderate_text(prompt)
        if not is_safe:
            if not reason:
                await ctx.send("Prompt moderation failed, please report to bot owner.")
                return
            await self.bot.log_to_file(f"Moderated prompt from {ctx.author}: {reason}", "log.txt")
            await ctx.send(f"Your prompt was moderated. Reason: {reason}")
            # if moderated - perma-ban or something?
            return
        supported_models = {
            "schnell": "black-forest-labs/FLUX.1-schnell",
            "merged": "multimodalart/FLUX.1-merged",
            "dev": "black-forest-labs/FLUX.1-dev",
            "krea-dev": "black-forest-labs/FLUX.1-Krea-dev",
        }
        chosen_model = supported_models.get(model)
        if not chosen_model:
            await ctx.send(f"Model {model} is not supported.")
            return
        start_time = time.perf_counter()
        try:
            async with self.img_client as client:
                result = await client.predict(src=chosen_model, **arg_dict)
            json_data, seed = result
            async with self.bot.session.get(json_data["url"]) as img_resp:
                # maybe I should make unique file names in the future...
                img_file = discord.File(io.BytesIO(await img_resp.read()), "image.webp")
            gen_time = time.perf_counter() - start_time
            await ctx.send(f"Generated image in {gen_time:.2f} seconds, seed: {seed}", file=img_file)
        except Exception as e:
            self.logger.exception(f"Error in image command during predict: {e}")
            await ctx.send(f"Sorry, there was an issue generating the image. {e}")

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
