import asyncio
import inspect
import logging
import os

import aiofiles
import aiohttp
import discord
import dotenv
from aiohttp import web
from async_pcloud import AsyncPyCloud
from discord import app_commands
from discord.ext import commands
from pymongo import AsyncMongoClient

if os.name == "nt" and not os.getenv("WT_SESSION"):
    try:
        # this fixes logger colors on windows
        from colorama import just_fix_windows_console
        just_fix_windows_console()
        os.environ["WT_SESSION"] = "bruh"
    except ImportError:
        pass
bot_name = "noob_bot"
logging.getLogger("discord").setLevel(logging.INFO)
my_loggers = [bot_name, "bot"]
for logger in my_loggers:
    logging.getLogger(logger).setLevel(logging.INFO)
dotenv.load_dotenv()
script_path = os.path.dirname(__file__)
TOKEN = os.environ["TOKEN"]
RTOKEN = os.getenv("RTOKEN")
PTOKEN = os.getenv("PTOKEN")
LOCAL_STORAGE = True if os.getenv("LOCAL_STORAGE") == "True" else False
folder = "DiscordBotData"
pcloud = AsyncPyCloud(PTOKEN, folder=folder)
uri = os.environ["MONGODB_URI"]
client = AsyncMongoClient(uri)
db = client["discord_bot"]
counter = db["counter"]
unloaded_coll = db["unloaded_cogs"]
disabled_coll = db["disabled_channels"]
disabled_com_coll = db["disabled_commands"]


class Bot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix=commands.when_mentioned_or(">"), intents=intents)
        self.script_path = script_path
        self.db = db
        self.counter = counter
        self.react = False
        self.file_lock = asyncio.Lock()
        self.currency = "noob credits"

    @property
    def logger(self):
        """Logs things with logger name like 'bot.cog.func' or {bot_name}.func"""
        stack = inspect.stack()
        for frame_info in stack[1:]:
            func_name = frame_info.function
            if func_name == "logger":
                continue
            self_obj = frame_info.frame.f_locals.get("self")
            cls_name = self_obj.__class__.__name__.lower()
            if self_obj and cls_name != "bot":
                return logging.getLogger(f"bot.{cls_name}.{func_name}")
            return logging.getLogger(f"{bot_name}.{func_name}")
        return logging.getLogger(bot_name)

    # bot events
    async def setup_hook(self):
        await pcloud.connect()
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(7), raise_for_status=True)
        global unloaded_cogs, disabled_channels, disabled_commands
        unloaded_cogs = {cog["cog"] async for cog in unloaded_coll.find()}
        disabled_channels = {channel["_id"] async for channel in disabled_coll.find()}
        disabled_commands = {command["command"] async for command in disabled_com_coll.find()}
        cogs = [filename[:-3] for filename in os.listdir(f"{script_path}/cogs") if filename.endswith(".py")]
        for cog_name in cogs:
            if cog_name in unloaded_cogs:
                continue
            try:
                await self.load_extension(f"cogs.{cog_name}")
            except commands.ExtensionAlreadyLoaded:
                pass
        disabled_commands_list = [self.get_command(cmd) for cmd in disabled_commands if self.get_command(cmd)]
        for command in disabled_commands_list:
            if command:
                self.logger.info(f"Disabling command: {command.name}")
                command.enabled = False
        app = web.Application()

        def count_values():
            return (f"Guilds: {len(self.guilds)}, Users: {len(self.users)}, "
                    f"Commands: {len(self.commands)}, Cogs: {len(self.cogs)}, Ping: {round(self.latency * 1000)}ms")

        async def web_status(_):
            return web.Response(text=f"Bot is running as {self.user}, {count_values()}")
        app.router.add_get("/", web_status)
        runner = web.AppRunner(app)
        await runner.setup()
        host, port = "0.0.0.0", os.getenv("SERVER_PORT") or os.getenv("PORT") or 8000
        try:
            await web.TCPSite(runner, host, int(port)).start()
        except OSError:
            self.logger.error(f"Port {port} is already in use")

    async def on_ready(self):
        await self.change_presence(activity=discord.CustomActivity(name='im cool 😎, ">" prefix'))
        self.logger.info(f"Logged in as {self.user}")

    async def on_message(self, message: discord.Message):
        if message.author == self.user:
            return
        if ">nitro" in message.content.lower():
            if not self.react:
                pass
            else:
                await message.add_reaction("☠️")
        await self.process_commands(message)

    async def on_command(self, ctx: commands.Context):
        if await self.is_owner(ctx.author) and ctx.command:
            ctx.command.reset_cooldown(ctx)

    async def on_command_error(self, ctx: commands.Context, error):
        if hasattr(ctx.command, "on_error") and not hasattr(ctx, "unhandled_error"):
            return
        ignored = (commands.CommandNotFound, app_commands.errors.CommandNotFound)
        error = getattr(error, "original", error)
        if isinstance(error, ignored):
            return
        if isinstance(error, commands.CheckFailure):
            if ctx.guild is None:
                await ctx.send("You can't use commands in DMs.", ephemeral=True)
        elif isinstance(error, discord.HTTPException) and error.status == 429:
            self.logger.warning(f"Rate limited. Retry in {error.response.headers['Retry-After']} seconds.", exc_info=error)
        elif isinstance(error, discord.HTTPException) and error.status == 400:
            self.logger.exception(f"Bad request: {error.text}", exc_info=error)
        elif isinstance(error, commands.CommandOnCooldown):
            await self.respond(ctx, f"This command is on cooldown. Please wait {error.retry_after:.2f}s")
        elif isinstance(error, app_commands.CommandInvokeError) and isinstance(error.original, discord.NotFound):
            self.logger.exception(error, exc_info=error)
        elif isinstance(error, (discord.NotFound, discord.Forbidden)):
            self.logger.exception(error, exc_info=error)
        else:
            self.logger.exception(f"Ignoring exception in command {ctx.command}:", exc_info=error)
            await ctx.send(f"Exception in command {ctx.command}: {str(error)}", ephemeral=True)

    async def close(self):
        await super().close()
        await self.session.close()
        await pcloud.disconnect()
        self.logger.info("Stopped.")
        await client.aclose()

    # custom functions
    async def download_file(self, file: str, not_found_ok=False):
        """Download file content from pCloud and return as text.
        not_found_ok=True will not raise an exception if the file is not found."""
        if LOCAL_STORAGE:
            if not os.path.exists(f"{script_path}/{file}"):
                if not_found_ok:
                    return ""
                raise Exception("Not found in local storage.")
            async with aiofiles.open(f"{script_path}/{file}") as f:
                return await f.read()
        file_text = await pcloud.gettextfile(not_found_ok, path=file)
        if file_text is None:
            if not_found_ok:
                return ""
            raise Exception(f"Not found in folder '{folder}'.")
        return file_text

    async def upload_file(self, filename: str, content: str):
        """Upload content to a file in pCloud. Or write to file."""
        if LOCAL_STORAGE:
            async with aiofiles.open(f"{script_path}/{filename}", "w") as f:
                await f.write(content)
            return
        r = await pcloud.upload_one_file(filename, content, path="/")
        if r.get("error"):
            raise Exception(r["error"])

    async def log_to_file(self, text: str, file: str):
        try:
            async with self.file_lock:
                rtext = await self.download_file(file, True)
                content = rtext + text + "\n"
                await self.upload_file(file, content)
        except Exception as e:
            self.logger.exception(f"Error for {file}: {e}")

    async def get_lines(self, num_lines: int, file: str):
        try:
            async with self.file_lock:
                text = await self.download_file(file)
                lines = text.splitlines()
                if not lines:
                    return
                if num_lines > len(lines):
                    num_lines = len(lines)
                lines_list = lines[:num_lines]
                content = "\n".join(lines[num_lines:])
                await self.upload_file(file, content)
                return lines_list
        except Exception as e:
            self.logger.exception(f"Error for {file}: {e}")

    async def count_lines(self, file: str):
        try:
            async with self.file_lock:
                text = await self.download_file(file)
                return len(text.splitlines())
        except Exception as e:
            self.logger.exception(f"Error for {file}: {e}")

    async def check_boost(self, guild_id: int, member_id: int):
        try:
            if not RTOKEN:
                raise Exception("RTOKEN not found.")
            url = f"https://discord.com/api/v10/guilds/{guild_id}/premium/subscriptions"
            response = await self.session.get(url, headers={"authorization": RTOKEN})
            if response.status != 200:
                self.logger.error(f"Error getting boost count for guild {guild_id}: {response.status}")
                return False
            response = await response.json()
            if isinstance(response, list):
                boost_count = 0
                for boost in response:
                    user_id = boost["user"]["id"]
                    if int(user_id) == member_id:
                        boost_count += 1
                return boost_count
            else:
                self.logger.error(f"Error getting boost count for user {member_id}: {response}")
                return False
        except Exception as e:
            self.logger.error(f"Error checking boost for guild {guild_id}, member {member_id}: {e}")
            return False

    async def respond(self, ctx: commands.Context, text: str, delete_after=5, ephemeral=True, del_cmd=True):
        """default respond function (useful)"""
        if ctx.interaction:
            await ctx.send(text, ephemeral=ephemeral)
        else:
            if del_cmd:
                await ctx.message.delete()
            if not delete_after:
                return await ctx.send(text)
            await ctx.send(text, delete_after=delete_after)

    def get_env(self, key, default: str | None = None):
        """Get an environment variable."""
        return os.getenv(key, default)

    def lock_exists(self):
        """Check if the lock file exists."""
        return os.path.exists(f"{self.script_path}/lock.txt")


class Default_Cog(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot
        self._ready = False

    async def cog_on_ready(self):
        """Called when the cog is loaded. Custom function."""
        pass

    @commands.Cog.listener()
    async def on_ready(self):
        if self._ready:
            return
        await self.cog_on_ready()
        self._ready = True

    @property
    def logger(self):
        """The custom logger for cogs."""
        return self.bot.logger


bot = Bot()
descripts = {"type": "The type of thing to toggle.", "name": "The name of the thing to toggle."}


def p(desc, default=None):
    return commands.parameter(description=desc, default=default)


@bot.check
async def check_guild(ctx):
    return ctx.guild


@bot.check
async def check_channel(ctx):
    if ctx.channel.id in disabled_channels and ctx.command.name != "toggle":
        if ctx.interaction:
            await ctx.send("This channel is disabled.", ephemeral=True)
        return False
    return True

# TODO: add this
# @bot.check
# async def check_user(ctx):
#     if ctx.author.id in disabled_users and ctx.command.name != 'toggle':
#         if ctx.interaction:
#             await ctx.send("You are disabled.", ephemeral = True)
#         return False
#     return True


@bot.hybrid_command(name="hi", help="Says hello")
async def hi(ctx):
    await ctx.send("Hello!")


@bot.hybrid_command(name="ping", help="Sends bot's latency.")
async def ping(ctx):
    await ctx.send(f"Pong! {round(bot.latency * 1000)} ms")


@bot.hybrid_command(name="dm", help="Sends a DM to a user")
@commands.is_owner()
async def dm(ctx, member: discord.Member, *, content):
    try:
        await member.send(content)
        await bot.respond(ctx, "DM was sent")
    except Exception as e:
        await bot.respond(ctx, f"Could not send DM, {e}")


@bot.hybrid_command(name="msg", help="Sends message as bot")
@commands.is_owner()
async def msg(ctx, channel: discord.TextChannel | None, *, text: str):
    if not channel:
        channel = ctx.channel
        if not channel:
            return
    try:
        await channel.send(text)
        await bot.respond(ctx, "Message sent")
    except Exception as e:
        await bot.respond(ctx, f"Could not send message, {e}")


@bot.hybrid_command(name="toggle", help="Toggles alot of things (owner only)")
@commands.is_owner()
@app_commands.describe(type=descripts["type"], name=descripts["name"])
@app_commands.choices(
    type=[
        app_commands.Choice(name="cog", value="cog"),
        app_commands.Choice(name="channel", value="channel"),
        app_commands.Choice(name="command", value="command"),
        app_commands.Choice(name="react", value="react"),
    ],
)
async def toggle_thing(ctx, type: str = p(descripts["type"]), name: str | None = p(descripts["name"])):
    if type == "cog":
        await handle_toggle_cog(ctx, name)
    elif type == "channel":
        await handle_toggle_channel(ctx)
    elif type == "react":
        bot.react = not bot.react
        await bot.respond(ctx, f"Reactions are now {'enabled' if bot.react else 'disabled'}")
    elif type == "command":
        await handle_toggle_command(ctx, name)
    else:
        await bot.respond(ctx, "Invalid type.")


async def handle_toggle_cog(ctx, cog):
    if not cog:
        return await bot.respond(ctx, "Please provide a cog name.")
    try:
        cog_name = ""
        for key, _ in bot.cogs.items():
            if cog.lower() in key.lower():
                cog_name = key
                break
        if cog_name in bot.cogs:
            await bot.unload_extension(f"cogs.{cog}")
            await unloaded_coll.insert_one({"cog": cog})
            await bot.respond(ctx, f"Disabled {cog}")
        elif cog in unloaded_cogs:
            await bot.load_extension(f"cogs.{cog}")
            await unloaded_coll.delete_one({"cog": cog})
            await bot.respond(ctx, f"Enabled {cog}")
        else:
            await bot.respond(ctx, f"Cog not found: {cog}")
    except Exception as e:
        await bot.respond(ctx, f"Error: {e}", 10)


async def handle_toggle_channel(ctx):
    if ctx.channel.id in disabled_channels:
        result = await disabled_coll.delete_one({"_id": ctx.channel.id})
        if result.deleted_count > 0:
            disabled_channels.remove(ctx.channel.id)
            await ctx.send("This channel has been enabled for bot commands.")
    else:
        await disabled_coll.insert_one({"_id": ctx.channel.id})
        disabled_channels.add(ctx.channel.id)
        await ctx.send("This channel has been disabled for bot commands.")


async def handle_toggle_command(ctx, command):
    if not command:
        return await bot.respond(ctx, "Please provide a command name.")
    found = bot.get_command(command)
    if ctx.command == found:
        return await bot.respond(ctx, "You can't disable the toggle command.")
    if not found:
        return await bot.respond(ctx, "Command not found.")
    result = found.enabled = not found.enabled
    if result:
        await disabled_com_coll.delete_one({"command": command})
    else:
        await disabled_com_coll.insert_one({"command": command})
    await bot.respond(ctx, f"Command {command} is now {'enabled' if result else 'disabled'}")


@bot.command(name="sync", help="Syncs commands")
@commands.is_owner()
async def sync(ctx):
    await ctx.message.delete()
    await bot.tree.sync()
    await ctx.send("Synced!", delete_after=3)


if __name__ == "__main__":
    bot.run(TOKEN, log_level=logging.WARNING, root_logger=True)
