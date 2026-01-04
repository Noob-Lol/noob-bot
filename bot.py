import asyncio
import datetime
import inspect
import logging
import os
from collections.abc import Awaitable
from typing import Any

import aiofiles
import aiohttp
import anyio
import discord
from aiohttp import web
from async_pcloud import AsyncPyCloud
from bson.decimal128 import Decimal128
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
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
load_dotenv()
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
disabled_items = {"type init": set()}
disabled_items.clear()


class CustomContext(commands.Context):
    """Custom commands.Context class with extra stuff"""

    # TODO: add more functions or attributes
    unhandled_error: bool | None = None


Ctx = CustomContext


class GuildOnly(commands.CheckFailure):
    pass


class Bot(commands.Bot):
    """Custom Bot class with extra stuff"""
    def __init__(self):
        self._closers = [client.aclose]
        intents = discord.Intents.all()
        self.prefix = ">"
        super().__init__(command_prefix=commands.when_mentioned_or(self.prefix), intents=intents)
        self.script_path = script_path
        self.db = db
        self.counter = db["counter"]
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
        timeout, headers = aiohttp.ClientTimeout(7), {"User-Agent": f"{bot_name}/1.0"}
        self.session = aiohttp.ClientSession(timeout=timeout, headers=headers, raise_for_status=True)
        self._closers.append(self.session.close)
        pcloud.set_session(self.session)
        global disabled_items
        guild_id = int(os.environ["GUILD_ID"]) if os.getenv("GUILD_ID") else None
        async for item in db["disabled_items"].find():
            if item["thing"] not in disabled_items:
                disabled_items[item["thing"]] = set()
            disabled_items[item["thing"]].add(item["item_id"])
        if await self.path_exists(f"{script_path}/cogs"):
            cogs = [filename[:-3] for filename in os.listdir(f"{script_path}/cogs") if filename.endswith(".py")]
            for cog_name in cogs:
                if cog_name in disabled_items.get("cog", []):
                    continue
                try:
                    await self.load_extension(f"cogs.{cog_name}")
                except commands.ExtensionAlreadyLoaded:
                    pass
        disabled_commands = [self.get_command(cmd) for cmd in disabled_items.get("command", []) if self.get_command(cmd)]
        for command in disabled_commands:
            if command:
                self.logger.info(f"Disabling command: {command.name}")
                command.enabled = False
        target = discord.Object(guild_id) if guild_id else None
        sync_str = "for guild " + str(guild_id) if guild_id else "globally"
        try:
            if await needs_sync(self, target):
                await self.tree.sync(guild=target)
                self.logger.info(f"Successfully synced commands {sync_str}.")
            else:
                self.logger.info(f"Commands already in sync {sync_str}.")
        except discord.Forbidden:
            self.logger.error(f"Bot does not have access to guild {guild_id} for syncing.")
        except Exception as e:
            self.logger.exception(f"Failed to sync commands {sync_str}: {e}")
        app = web.Application()

        def count_values():
            return (
                f"Guilds: {len(self.guilds)}, Users: {len(self.users)}, "
                f"Commands: {len(self.commands)}, Cogs: {len(self.cogs)}, Ping: {round(self.latency * 1000)}ms"
            )

        async def web_status(_):
            return web.Response(text="OK")

        async def bot_info(_):
            return web.Response(text=f"Bot is running as {self.user}, {count_values()}")

        async def rate_limit_info(_):
            """Check Discord API rate limit headers"""
            try:
                # Make a request to Discord to get rate limit info
                url = "https://discord.com/api/v10/users/@me"
                async with self.session.get(url, headers={"authorization": f"Bot {TOKEN}"}) as response:
                    rate_limit_headers = {
                        "Limit": response.headers.get("X-RateLimit-Limit", "N/A"),
                        "Remaining": response.headers.get("X-RateLimit-Remaining", "N/A"),
                        "Reset": response.headers.get("X-RateLimit-Reset", "N/A"),
                        "Reset-After": response.headers.get("X-RateLimit-Reset-After", "N/A"),
                        "Bucket": response.headers.get("X-RateLimit-Bucket", "N/A"),
                    }
                    text = "Discord Rate Limit Headers:\n"
                    for key, value in rate_limit_headers.items():
                        text += f"{key}: {value}\n"
                    return web.Response(text=text)
            except Exception as e:
                return web.Response(text=f"Error checking rate limits: {e}", status=500)

        app.router.add_get("/", web_status)
        app.router.add_get("/info", bot_info)
        app.router.add_get("/ratelimit", rate_limit_info)
        runner = web.AppRunner(app)
        await runner.setup()
        host, port = "0.0.0.0", os.getenv("SERVER_PORT") or os.getenv("PORT") or 8000
        try:
            await web.TCPSite(runner, host, int(port)).start()
        except OSError:
            self.logger.error(f"Port {port} is already in use")

    async def on_ready(self):
        await self.change_presence(activity=discord.CustomActivity(name="I'm cool 😎, '>' prefix"))
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

    async def on_command(self, ctx: Ctx):
        if await self.is_owner(ctx.author) and ctx.command:
            ctx.command.reset_cooldown(ctx)

    async def get_context(self, message, *, cls=None):
        """Use CustomContext so error handlers can safely set attributes like unhandled_error."""
        if cls is None:
            cls = CustomContext
        return await super().get_context(message, cls=cls)

    async def on_command_error(self, ctx: Ctx, error):  # type: ignore | pylance doesnt like type override here
        """Handle command errors with proper type handling"""
        if hasattr(ctx.command, "on_error") and ctx.unhandled_error is None:
            return
        ignored = (commands.CommandNotFound, app_commands.errors.CommandNotFound)
        error = getattr(error, "original", error)
        if isinstance(error, ignored):
            return
        if isinstance(error, commands.CheckFailure):
            if ctx.guild is None or isinstance(error, GuildOnly):
                await ctx.send("You can't use commands in DMs.", ephemeral=True)
                # await ctx.send("This command can only be used in a guild.", ephemeral=True)  # some commands may be allowed in dms
        elif isinstance(error, commands.DisabledCommand):
            await self.respond(ctx, f"{ctx.command} command is disabled.")
        elif isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
            await ctx.send(f"Command {ctx.command} failed, {error}")
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
            self.logger.exception(f"Ignoring exception in command {ctx.command}: {str(error)}", exc_info=error)
            await ctx.send(f"Exception in command {ctx.command}: {str(error)}", ephemeral=True)

    async def close(self):
        await super().close()
        # insanely genius way to close stuff
        coros: list[Awaitable[Any]] = []
        for closer in self._closers:
            try:
                coros.append(closer() if callable(closer) else closer)
            except Exception as e:
                self.logger.error(f"Error creating close coro for {closer}: {e}")
        results = await self.agather(*coros) if coros else []
        for result in results:
            if isinstance(result, Exception):
                self.logger.error(f"Error during closing: {result}")
        self.logger.info("Bye!")

    # custom functions
    async def path_exists(self, path: str):
        """Check if path exists, async version."""
        return await anyio.Path(path).exists()

    async def agather(self, *coros: Awaitable[Any], return_exceptions=True):
        """asyncio.gather for usage in cogs and anywhere with bot import."""
        return await asyncio.gather(*coros, return_exceptions=return_exceptions)

    async def download_file(self, file: str, not_found_ok=False):
        """Download file content from pCloud and return as text.
        not_found_ok=True will not raise an exception if the file is not found."""
        if LOCAL_STORAGE:
            if not await self.path_exists(f"{script_path}/{file}"):
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
        resp = await pcloud.upload_one_file(filename, content, path="/")
        if resp.get("error"):
            raise Exception(resp["error"])

    async def log_to_file(self, text: str, file: str):
        """Append text to a file."""
        try:
            async with self.file_lock:
                rtext = await self.download_file(file, True)
                content = rtext + text + "\n"
                await self.upload_file(file, content)
        except Exception as e:
            self.logger.exception(f"Error for {file}: {e}")

    async def get_lines(self, num_lines: int, file: str):
        """Get and remove the first num_lines from a file."""
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
        """Count the number of lines in a file."""
        try:
            async with self.file_lock:
                text = await self.download_file(file)
                return len(text.splitlines())
        except Exception as e:
            self.logger.exception(f"Error for {file}: {e}")

    async def check_boost(self, guild: discord.Guild, member: discord.Member) -> int:
        """Check how many boosts a member has in a guild, return -1 on error."""
        try:
            if not member.premium_since:
                return 0
            if not RTOKEN:
                raise Exception("RTOKEN not found.")
            url = f"https://discord.com/api/v10/guilds/{guild.id}/premium/subscriptions/a"
            async with await self.session.get(url, headers={"authorization": RTOKEN}) as response:
                resp_json = await response.json()
            if isinstance(resp_json, list):
                boost_count = 0
                for boost in resp_json:
                    user_id = boost["user"]["id"]
                    if int(user_id) == member.id:
                        boost_count += 1
                return boost_count
            else:
                self.logger.error(f"Error for user {member.id}: {resp_json}")
                return -1
        except Exception as e:
            self.logger.error(f"Error for guild {guild.id}, member {member.id}: {e}")
            return -1

    async def respond(self, ctx: Ctx, text: str, delete_after=5, ephemeral=True, del_cmd=True):
        """default respond function (useful)"""
        if ctx.interaction:
            await ctx.send(text, ephemeral=ephemeral)
            return
        if del_cmd:
            await ctx.message.delete()
        if not delete_after:
            await ctx.send(text)
            return
        await ctx.send(text, delete_after=delete_after)

    def verify_guild(self, guild: discord.Guild | None):
        """Check if the command is run in guild"""
        if not guild:
            raise GuildOnly
        return guild

    def verify_guild_user(self, guild: discord.Guild | None, user: discord.Member | discord.User):
        """Check if the command is run in guild and user is a member"""
        if not guild or not isinstance(user, discord.Member):
            raise GuildOnly
        return guild, user

    def verify_guild_channel(self, guild: discord.Guild | None, channel: discord.abc.Messageable):
        """Check if the command is run in guild and channel is a text channel"""
        if not guild or not isinstance(channel, discord.TextChannel):
            raise GuildOnly
        return guild, channel

    def get_env(self, key, default: str | None = None):
        """Get an environment variable."""
        return os.getenv(key, default)

    def now_utc(self):
        """Get the current time in UTC."""
        return datetime.datetime.now(datetime.timezone.utc)

    def to_d128(self, value):
        """Safely converts any numeric type to Decimal128 via string."""
        if value is None:
            return Decimal128("0.0")
        # Rounding to 10 decimal places strips the "0.00000000000004" noise
        # while keeping the intended decimal value.
        cleaned_str = str(round(float(value), 10))
        return Decimal128(cleaned_str)


class BaseCog(commands.Cog):
    """Base class for cogs with extra stuff"""
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
descripts = {"thing": "The thing to toggle.", "name": "The name of the thing to toggle."}


async def needs_sync(bot: Bot, guild: discord.Object | None):
    """Check if slash commands need to be synced."""
    remote = await bot.tree.fetch_commands(guild=guild)
    local = bot.tree.get_commands(guild=guild)
    remote_map = {cmd.name: cmd for cmd in remote}
    local_map = {cmd.name: cmd for cmd in local}
    if len(local_map) != len(remote_map):
        return True
    for name, l_cmd in local_map.items():
        r_cmd = remote_map.get(name)
        if not r_cmd:
            return True
        # Only check app commands
        if isinstance(l_cmd, (app_commands.ContextMenu, app_commands.Group)):
            continue
        if l_cmd.description != r_cmd.description:
            return True
        if len(l_cmd.parameters) != len(r_cmd.options):
            return True
        for param, option in zip(l_cmd.parameters, r_cmd.options, strict=False):
            comp_attrs = ["name", "description", "required"]
            if any(getattr(param, attr) != getattr(option, attr) for attr in comp_attrs):
                return True
    return False


def p(desc, default=None):
    return commands.parameter(description=desc, default=default)


@bot.check
async def check_guild(ctx: Ctx):
    if await bot.is_owner(ctx.author):
        return True
    return ctx.guild


@bot.check
async def check_channel(ctx: Ctx):
    if await bot.is_owner(ctx.author):
        return True
    if ctx.channel.id in disabled_items.get("channel", []) and ctx.command and ctx.command.name != "toggle":
        if ctx.interaction:
            await ctx.send("Bot commands are restricted in this channel.", ephemeral=True)
        return False
    return True


@bot.check
async def check_user(ctx: Ctx):
    if await bot.is_owner(ctx.author):
        return True
    if ctx.author.id in disabled_items.get("user", []) and ctx.command and ctx.command.name != "toggle":
        if ctx.interaction:
            await ctx.send("Your access to bot commands is currently restricted.", ephemeral=True)
        return False
    return True


@bot.hybrid_command(name="hi", help="Says hello")
async def hi(ctx: Ctx):
    await ctx.send("Hello!")


@bot.hybrid_command(name="ping", help="Sends bot's latency.")
async def ping(ctx: Ctx):
    await ctx.send(f"Pong! {round(bot.latency * 1000)} ms")


@bot.hybrid_command(name="dm", help="Sends a DM to a user")
@commands.is_owner()
async def dm(ctx: Ctx, member: discord.Member, *, content: str):
    try:
        await member.send(content)
        await bot.respond(ctx, "DM was sent")
    except Exception as e:
        await bot.respond(ctx, f"Could not send DM, {e}")


@bot.hybrid_command(name="msg", help="Sends message as bot")
@commands.is_owner()
async def msg(ctx: Ctx, channel: discord.TextChannel | None, *, text: str):
    if not channel:
        if isinstance(ctx.channel, discord.TextChannel):
            channel = ctx.channel
        else:
            await bot.respond(ctx, "Cannot send messages in DMs")
            return
    try:
        await channel.send(text)
        await bot.respond(ctx, "Message sent")
    except Exception as e:
        await bot.respond(ctx, f"Could not send message, {e}")


@bot.hybrid_command(name="toggle", help="Toggles a lot of things (owner only)")
@commands.is_owner()
@app_commands.describe(thing=descripts["thing"], name=descripts["name"])
@app_commands.choices(
    thing=[
        app_commands.Choice(name="cog", value="cog"),
        app_commands.Choice(name="channel", value="channel"),
        app_commands.Choice(name="command", value="command"),
        app_commands.Choice(name="react", value="react"),
        app_commands.Choice(name="user", value="user"),
    ],
)
async def toggle_thing(ctx: Ctx, thing: str = p(descripts["thing"]), name: str | None = p(descripts["name"])):
    if thing == "cog":
        await handle_toggle_cog(ctx, name)
    elif thing == "channel":
        await handle_toggle_channel(ctx)
    elif thing == "react":
        bot.react = not bot.react
        await bot.respond(ctx, f"Reactions are now {'enabled' if bot.react else 'disabled'}")
    elif thing == "command":
        await handle_toggle_command(ctx, name)
    elif thing == "user":
        await handle_toggle_user(ctx, name)
    else:
        await bot.respond(ctx, "Invalid thing choice.")


async def disable_item(ctx: Ctx, thing: str, item_id: str | int):
    bot.logger.info(f"{thing} {item_id} by {ctx.author}")
    doc = {"thing": thing, "item_id": item_id, "disabled_at": bot.now_utc(), "disabled_by": ctx.author.id}
    await db["disabled_items"].insert_one(doc)
    if thing not in disabled_items:
        disabled_items[thing] = set()
    disabled_items[thing].add(item_id)


async def enable_item(ctx: Ctx, thing: str, item_id: str | int):
    bot.logger.info(f"{thing} {item_id} by {ctx.author}")
    res = await db["disabled_items"].delete_one({"thing": thing, "item_id": item_id})
    if thing in disabled_items and item_id in disabled_items[thing]:
        disabled_items[thing].remove(item_id)
    return res.deleted_count


async def handle_toggle_cog(ctx: Ctx, cog: str | None):
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
            await disable_item(ctx, "cog", cog)
            await bot.respond(ctx, f"Disabled {cog}")
        elif cog in disabled_items.get("cog", []):
            await bot.load_extension(f"cogs.{cog}")
            await enable_item(ctx, "cog", cog)
            await bot.respond(ctx, f"Enabled {cog}")
        else:
            await bot.respond(ctx, f"Cog not found: {cog}")
    except Exception as e:
        await bot.respond(ctx, f"Error: {e}", 10)


async def handle_toggle_channel(ctx: Ctx):
    if ctx.channel.id in disabled_items.get("channel", []):
        result = await enable_item(ctx, "channel", ctx.channel.id)
        if result:
            await ctx.send("This channel has been enabled for bot commands.")
    else:
        await disable_item(ctx, "channel", ctx.channel.id)
        await ctx.send("This channel has been disabled for bot commands.")


async def handle_toggle_command(ctx: Ctx, command):
    if not command:
        return await bot.respond(ctx, "Please provide a command name.")
    found = bot.get_command(command)
    if ctx.command == found:
        return await bot.respond(ctx, "You can't disable the toggle command.")
    if not found:
        return await bot.respond(ctx, "Command not found.")
    result = found.enabled = not found.enabled
    if result:
        await enable_item(ctx, "command", command)
    else:
        await disable_item(ctx, "command", command)
    await bot.respond(ctx, f"Command {command} is now {'enabled' if result else 'disabled'}")


async def handle_toggle_user(ctx: Ctx, user_id_or_mention: str | None):
    if not user_id_or_mention:
        return await bot.respond(ctx, "Please provide a user (mention or ID).")
    uid = None
    try:
        if user_id_or_mention.isdigit():
            uid = int(user_id_or_mention)
        elif user_id_or_mention.startswith("<@") and user_id_or_mention.endswith(">"):
            uid = int(user_id_or_mention.strip("<@!>"))
    except Exception:
        uid = None
    if uid is None:
        return await bot.respond(ctx, "Invalid user. Provide a mention or numeric ID.")
    if uid in disabled_items.get("user", []):
        result = await enable_item(ctx, "user", uid)
        if result:
            return await bot.respond(ctx, f"User <@{uid}> can now use bot commands.")
    else:
        await disable_item(ctx, "user", uid)
        return await bot.respond(ctx, f"User <@{uid}> can no longer use bot commands.")


@bot.command(name="sync", help="Syncs commands")
@commands.is_owner()
async def sync(ctx: Ctx):
    await ctx.message.delete()
    await bot.tree.sync()
    await ctx.send("Synced!", delete_after=3)


def run_bot():
    """Run the bot."""
    bot.run(TOKEN, log_level=logging.WARNING, root_logger=True)


if __name__ == "__main__":
    run_bot()
