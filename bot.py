import datetime
import inspect
import logging
import os
from collections.abc import Awaitable
from decimal import Decimal
from typing import TypeVar

import aiohttp
import anyio
import discord
from aiohttp import web
from anyio import Path
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
T = TypeVar("T")
bot_name = "noob_bot"
logging.getLogger("discord").setLevel(logging.INFO)
my_loggers = [bot_name, "bot"]
for logger in my_loggers:
    logging.getLogger(logger).setLevel(logging.INFO)
load_dotenv()
script_path = Path(__file__).parent
TOKEN = os.environ["TOKEN"]
RTOKEN = os.getenv("RTOKEN")
PTOKEN = os.getenv("PTOKEN")
LOCAL_STORAGE = os.getenv("LOCAL_STORAGE") == "True"
DC_API_BASE = "https://discord.com/api/v10"
folder = "DiscordBotData"
pcloud = AsyncPyCloud(PTOKEN, folder=folder)
uri = os.environ["MONGODB_URI"]
client = AsyncMongoClient(uri)
db = client["discord_bot"]
disabled_items = {"type init": set()}
disabled_items.clear()


async def do_nothing(*args, **kwargs) -> None:
    """Does nothing, async."""


class Decimal129(Decimal128):
    """A Decimal128 with math."""

    @staticmethod
    def _to_py(obj):
        """Helper to accept int, float, str, or Decimal128"""
        if isinstance(obj, Decimal128):
            return obj.to_decimal()
        if isinstance(obj, Decimal):
            return obj
        return Decimal(str(obj))

    # short aliases
    def _dec(self): return self.to_decimal()
    # Math
    def __add__(self, other): return Decimal129(self._dec() + self._to_py(other))
    def __radd__(self, other): return Decimal129(self._to_py(other) + self._dec())
    def __sub__(self, other): return Decimal129(self._dec() - self._to_py(other))
    def __rsub__(self, other): return Decimal129(self._to_py(other) - self._dec())
    def __mul__(self, other): return Decimal129(self._dec() * self._to_py(other))
    def __rmul__(self, other): return Decimal129(self._to_py(other) * self._dec())
    def __pow__(self, other): return Decimal129(self._dec() ** self._to_py(other))
    def __rpow__(self, other): return Decimal129(self._to_py(other) ** self._dec())
    def __truediv__(self, other): return Decimal129(self._dec() / self._to_py(other))
    def __rtruediv__(self, other): return Decimal129(self._to_py(other) / self._dec())
    def __floordiv__(self, other): return Decimal129(self._dec() // self._to_py(other))
    def __rfloordiv__(self, other): return Decimal129(self._to_py(other) // self._dec())
    def __mod__(self, other): return Decimal129(self._dec() % self._to_py(other))
    def __rmod__(self, other): return Decimal129(self._to_py(other) % self._dec())
    # Comparison
    def __lt__(self, other): return self._dec() < self._to_py(other)
    def __le__(self, other): return self._dec() <= self._to_py(other)
    def __gt__(self, other): return self._dec() > self._to_py(other)
    def __ge__(self, other): return self._dec() >= self._to_py(other)
    def __eq__(self, other): return self._dec() == self._to_py(other)
    # Type formatting
    def __int__(self): return int(self._dec())
    def __float__(self): return float(self._dec())
    def __str__(self): return s.rstrip("0").rstrip(".") if "." in (s := f"{self._dec():f}") else s
    def __repr__(self): return f"Decimal129('{self._dec()}')"
    def __format__(self, fmt): return self._dec().__format__(fmt)
    # Some ops
    def __neg__(self): return Decimal129(-self._dec())
    def __abs__(self): return Decimal129(abs(self._dec()))
    def __pos__(self): return Decimal129(+self._dec())
    def __round__(self, *, ndigits=None): return Decimal129(round(self._dec(), ndigits))


def to_d129(value: str | float | Decimal128 | Decimal129 | None):
    """Safely converts any numeric type to Decimal129 via string."""
    if value is None:
        return Decimal129("0.0")
    if isinstance(value, Decimal129):
        return value
    if isinstance(value, Decimal128):
        return Decimal129(value.to_decimal())
    # Rounding to 10 decimal places strips the "0.00000000000004" noise
    # while keeping the intended decimal value.
    cleaned_str = str(round(float(value), 10))
    return Decimal129(cleaned_str)


class CustomContext(commands.Context):
    """Custom commands.Context class with extra stuff."""

    # TODO: add more functions or attributes
    unhandled_error: bool | None = None

    async def respond(self, text: str, delete_after=5, *, ephemeral=True, del_cmd=True) -> None:
        """Sends a message. By default, the message is ephemeral, and the command message is deleted. Returns None."""
        if self.interaction:
            await self.send(text, ephemeral=ephemeral)
            return
        if del_cmd:
            await self.message.delete()
        if not delete_after:
            await self.send(text)
            return
        await self.send(text, delete_after=delete_after)
        return


Ctx = CustomContext


class BotError(Exception):
    """Base class for bot errors."""


class GuildOnly(commands.CheckFailure):
    """Guild only error."""


class Bot(commands.Bot):
    """Custom Bot class with extra stuff."""

    def __init__(self) -> None:
        self._closers = [client.aclose]
        intents = discord.Intents.all()
        self.prefix = ">"
        super().__init__(command_prefix=commands.when_mentioned_or(self.prefix), intents=intents)
        self.script_path = script_path
        self.db = db
        self.counter = db["counter"]
        self.react = False
        self.file_lock = anyio.Lock()
        self.currency = "noob credits"

    @property
    def logger(self) -> logging.Logger:
        """Logs things with logger name like 'bot.cog.func' or {bot_name}.func ."""
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
        for item in await db["disabled_items"].find().to_list():
            if item["thing"] not in disabled_items:
                disabled_items[item["thing"]] = set()
            disabled_items[item["thing"]].add(item["item_id"])
        cogs_path = script_path / "cogs"
        if await cogs_path.is_dir():
            cogs = [path.stem async for path in cogs_path.glob("*.py") if path.stem != "__init__"]
            for cog_name in cogs:
                if cog_name in disabled_items.get("cog", []):
                    continue
                try:
                    await self.load_extension(f"cogs.{cog_name}")
                except commands.ExtensionAlreadyLoaded:
                    self.logger.info("Cog already loaded: %s", cog_name)
        disabled_commands = [self.get_command(cmd) for cmd in disabled_items.get("command", []) if self.get_command(cmd)]
        for command in disabled_commands:
            if command:
                self.logger.info("Disabling command: %s", command.qualified_name)
                command.enabled = False
        target = discord.Object(guild_id) if guild_id else None
        sync_str = "for guild " + str(guild_id) if guild_id else "globally"
        try:
            if await needs_sync(self, target):
                await self.tree.sync(guild=target)
                self.logger.info("Successfully synced commands %s.", sync_str)
            else:
                self.logger.info("Commands already in sync %s.", sync_str)
        except discord.Forbidden:
            self.logger.exception("Bot does not have access to guild %s for syncing.", guild_id)
        except Exception:
            self.logger.exception("Failed to sync commands %s:", sync_str)
        app = web.Application()

        def count_values():
            return (
                f"Guilds: {len(self.guilds)}, Users: {len(self.users)}, "
                f"Commands: {len(self.commands)}, Cogs: {len(self.cogs)}, Ping: {round(self.latency * 1000)}ms"
            )

        async def web_status(_):
            await do_nothing()
            return web.Response(text="OK")

        async def bot_info(_):
            await do_nothing()
            return web.Response(text=f"Bot is running as {self.user}, {count_values()}")

        async def rate_limit_info(_):
            """Check Discord API rate limit headers."""
            try:
                # Make a request to Discord to get rate limit info
                url = f"{DC_API_BASE}/users/@me"
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
            except Exception:
                self.logger.exception("Error checking rate limits")
                return web.Response(text="Error checking rate limits", status=500)

        app.router.add_get("/", web_status)
        app.router.add_get("/info", bot_info)
        app.router.add_get("/ratelimit", rate_limit_info)
        runner = web.AppRunner(app)
        await runner.setup()
        host, port = "0.0.0.0", os.getenv("SERVER_PORT") or os.getenv("PORT") or 8000
        try:
            await web.TCPSite(runner, host, int(port)).start()
        except OSError:
            self.logger.warning("Port %s is already in use", port)

    async def on_ready(self):
        await self.change_presence(activity=discord.CustomActivity(name="I'm cool 😎, '>' prefix"))
        self.logger.info("Logged in as %s", self.user)

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

    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.premium_since != after.premium_since and before.guild and after.guild:
            guild = before.guild
            self.logger.info("Member %s changed boost status in guild %s (%s)", after, guild.name, guild.id)
            # clear boost count cache in memory and redis for this guild (WIP)

    async def get_context(self, message, *, cls=None):
        """Use CustomContext so error handlers can safely set attributes like unhandled_error."""
        if cls is None:
            cls = CustomContext
        return await super().get_context(message, cls=cls)

    async def on_command_error(self, ctx: Ctx, error):  # type: ignore | pylance doesnt like type override here
        """Handle command errors with proper type handling."""
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
            await ctx.respond(f"{ctx.command} command is disabled.")
        elif isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
            await ctx.send(f"Command {ctx.command} failed, {error}")
        elif isinstance(error, discord.HTTPException) and error.status == 429:
            self.logger.warning("Rate limited. Retry in %s seconds.", error.response.headers["Retry-After"], exc_info=error)
        elif isinstance(error, discord.HTTPException) and error.status == 400:
            self.logger.error("Bad request: %s", error.text, exc_info=error)
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.respond(f"This command is on cooldown. Please wait {error.retry_after:.2f}s")
        elif (isinstance(error, app_commands.CommandInvokeError) and isinstance(error.original, discord.NotFound)) or isinstance(error, (discord.NotFound, discord.Forbidden)):
            self.logger.error(error, exc_info=error)
        else:
            self.logger.error("Ignoring exception in command %s:", ctx.command, exc_info=error)
            await ctx.send(f"Exception in command {ctx.command}: {error!s}", ephemeral=True)

    async def close(self):
        await super().close()
        # insanely genius way to close stuff
        coros: list[Awaitable[None]] = []
        for closer in self._closers:
            try:
                coros.append(closer() if callable(closer) else closer)
            except Exception:
                self.logger.exception("Error creating close coro for %s:", closer)
        results = await self.agather(*coros) if coros else []
        for result in results:
            if isinstance(result, Exception):
                self.logger.error("Error during closing: %s", result)
        self.logger.info("Bye!")

    # custom functions
    @staticmethod
    async def agather(*coros: Awaitable[T], return_exceptions=True):
        """asyncio.gather alternative using anyio with error handling and typing."""
        results: list[T | Exception | None] = [None] * len(coros)
        errors: list[Exception] = []
        async with anyio.create_task_group() as tg:
            for i, coro in enumerate(coros):
                async def runner(i=i, coro=coro):
                    try:
                        results[i] = await coro
                    except Exception as e:
                        if return_exceptions:
                            results[i] = e
                        else:
                            errors.append(e)
                tg.start_soon(runner)
        if errors and not return_exceptions:
            raise errors[0]
        return results

    @staticmethod
    async def download_file(file: str, *, not_found_ok=False) -> str:
        """Download file content from pCloud and return as text. not_found_ok=True will not raise an exception if the file is not found."""
        if LOCAL_STORAGE:
            file_path = script_path / file
            if not await file_path.exists():
                if not_found_ok:
                    return ""
                msg = "Not found in local storage."
                raise FileNotFoundError(msg)
            return await file_path.read_text("utf-8")
        file_text = await pcloud.gettextfile(not_found_ok=not_found_ok, path=file)
        if file_text is None:
            if not_found_ok:
                return ""
            msg = f"Not found in folder '{folder}'."
            raise FileNotFoundError(msg)
        return file_text

    @staticmethod
    async def upload_file(filename: str, content: str) -> None:
        """Upload content to a file in pCloud. Or write to file."""
        if LOCAL_STORAGE:
            await (script_path / filename).write_text(content, "utf-8")
            return
        resp = await pcloud.upload_one_file(filename, content, path="/")
        if resp.get("error"):
            raise BotError(resp["error"])

    async def log_to_file(self, text: str, file: str):
        """Append text to a file."""
        try:
            async with self.file_lock:
                rtext = await self.download_file(file, not_found_ok=True)
                content = rtext + text + "\n"
                await self.upload_file(file, content)
        except Exception:
            self.logger.exception("Error for %s:", file)

    async def get_lines(self, num_lines: int, file: str):
        """Get and remove the first num_lines from a file."""
        try:
            async with self.file_lock:
                text = await self.download_file(file)
                lines = text.splitlines()
                if not lines:
                    return None
                num_lines = min(num_lines, len(lines))
                lines_list = lines[:num_lines]
                content = "\n".join(lines[num_lines:])
                await self.upload_file(file, content)
                return lines_list
        except Exception:
            self.logger.exception("Error for %s:", file)

    async def count_lines(self, file: str):
        """Count the number of lines in a file."""
        try:
            async with self.file_lock:
                text = await self.download_file(file)
                return len(text.splitlines())
        except Exception:
            self.logger.exception("Error for %s:", file)

    async def check_boost(self, guild: discord.Guild, member: discord.Member) -> int:
        """Check how many boosts a member has in a guild, return -1 on error."""
        try:
            if not member.premium_since:
                return 0
            auth_token = self.check_var(RTOKEN)
            url = f"{DC_API_BASE}/guilds/{guild.id}/premium/subscriptions"
            async with await self.session.get(url, headers={"authorization": auth_token}) as response:
                resp_json = await response.json()
            if not isinstance(resp_json, list):
                self.logger.error("Error for user %s: %s", member.id, resp_json)
                return -1
            boost_count = 0
            for boost in resp_json:
                user_id = boost["user"]["id"]
                if int(user_id) == member.id:
                    boost_count += 1
        except Exception:
            self.logger.exception("Error for guild %s, member %s:", guild.id, member.id)
            return -1
        return boost_count

    @staticmethod
    def verify_guild(guild: discord.Guild | None):
        """Check if the command is run in guild"""
        if not guild:
            raise GuildOnly
        return guild

    @staticmethod
    def verify_guild_user(guild: discord.Guild | None, user: discord.Member | discord.User):
        """Check if the command is run in guild and user is a member"""
        if not guild or not isinstance(user, discord.Member):
            raise GuildOnly
        return guild, user

    @staticmethod
    def verify_guild_channel(guild: discord.Guild | None, channel: discord.abc.Messageable):
        """Check if the command is run in guild and channel is a text channel"""
        if not guild or not isinstance(channel, discord.TextChannel):
            raise GuildOnly
        return guild, channel

    @staticmethod
    def get_env(key: str, default: T = None) -> str | T:
        """Get an environment variable."""
        return os.getenv(key, default)

    @staticmethod
    def now_utc(*, combine=False, days=0):
        """Get the current time in UTC. Can combine with days to get a specific date, 00:00."""
        now_dt = datetime.datetime.now(datetime.UTC)
        if days and not combine:
            raise NotImplementedError
        if combine:
            return datetime.datetime.combine(now_dt.date() + datetime.timedelta(days=days), datetime.time(0, 0, 0, 0))
        return now_dt

    @staticmethod
    def check_var(var: T | None) -> T:
        if var is None:
            msg = f"Variable is None! ({var=})"
            raise ValueError(msg)
        return var


class BaseCog(commands.Cog):
    """Base class for cogs with extra stuff."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.bot_path = bot.script_path
        self._ready = False
        self.to_d129 = to_d129
        self.do_nothing = do_nothing

    async def cog_on_ready(self) -> None:
        """Called when the cog is loaded. Custom function."""

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if not self._ready:
            await self.cog_on_ready()
            self._ready = True

    @property
    def logger(self) -> logging.Logger:
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
        await ctx.respond("DM was sent")
    except Exception as e:
        await ctx.respond(f"Could not send DM, {e}")


@bot.hybrid_command(name="msg", help="Sends message as bot")
@commands.is_owner()
async def msg(ctx: Ctx, channel: discord.TextChannel | None, *, text: str):
    if not channel:
        if isinstance(ctx.channel, discord.TextChannel):
            channel = ctx.channel
        else:
            await ctx.respond("Cannot send messages in DMs")
            return
    try:
        await channel.send(text)
        await ctx.respond("Message sent")
    except Exception as e:
        await ctx.respond(f"Could not send message, {e}")


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
        await ctx.respond(f"Reactions are now {'enabled' if bot.react else 'disabled'}")
    elif thing == "command":
        await handle_toggle_command(ctx, name)
    elif thing == "user":
        await handle_toggle_user(ctx, name)
    else:
        await ctx.respond("Invalid thing choice.")


async def disable_item(ctx: Ctx, thing: str, item_id: str | int):
    # "%s %s by %s", thing, item_id, ctx.author
    bot.logger.info("%s %s by %s", thing, item_id, ctx.author)
    doc = {"thing": thing, "item_id": item_id, "disabled_at": bot.now_utc(), "disabled_by": ctx.author.id}
    await db["disabled_items"].insert_one(doc)
    if thing not in disabled_items:
        disabled_items[thing] = set()
    disabled_items[thing].add(item_id)


async def enable_item(ctx: Ctx, thing: str, item_id: str | int):
    bot.logger.info("%s %s by %s", thing, item_id, ctx.author)
    res = await db["disabled_items"].delete_one({"thing": thing, "item_id": item_id})
    if thing in disabled_items and item_id in disabled_items[thing]:
        disabled_items[thing].remove(item_id)
    return res.deleted_count


async def handle_toggle_cog(ctx: Ctx, cog: str | None):
    if not cog:
        return await ctx.respond("Please provide a cog name.")
    try:
        cog_name = ""
        for key in bot.cogs:
            if cog.lower() in key.lower():
                cog_name = key
                break
        if cog_name in bot.cogs:
            await bot.unload_extension(f"cogs.{cog}")
            await disable_item(ctx, "cog", cog)
            await ctx.respond(f"Disabled {cog}")
        elif cog in disabled_items.get("cog", []):
            await bot.load_extension(f"cogs.{cog}")
            await enable_item(ctx, "cog", cog)
            await ctx.respond(f"Enabled {cog}")
        else:
            await ctx.respond(f"Cog not found: {cog}")
    except Exception as e:
        await ctx.respond(f"Error: {e}", 10)


async def handle_toggle_channel(ctx: Ctx):
    if ctx.channel.id in disabled_items.get("channel", []):
        result = await enable_item(ctx, "channel", ctx.channel.id)
        if result:
            await ctx.send("This channel has been enabled for bot commands.")
    else:
        await disable_item(ctx, "channel", ctx.channel.id)
        await ctx.send("This channel has been disabled for bot commands.")


async def handle_toggle_command(ctx: Ctx, command: str | None):
    if not command:
        return await ctx.respond("Please provide a command name.")
    found = bot.get_command(command)
    if ctx.command == found:
        return await ctx.respond("You can't disable the toggle command.")
    if not found:
        return await ctx.respond("Command not found.")
    result = found.enabled = not found.enabled
    if result:
        await enable_item(ctx, "command", command)
    else:
        await disable_item(ctx, "command", command)
    await ctx.respond(f"Command {command} is now {'enabled' if result else 'disabled'}")
    return None


async def handle_toggle_user(ctx: Ctx, user_id_or_mention: str | None):
    if not user_id_or_mention:
        return await ctx.respond("Please provide a user (mention or ID).")
    uid = None
    try:
        if user_id_or_mention.isdigit():
            uid = int(user_id_or_mention)
        elif user_id_or_mention.startswith("<@") and user_id_or_mention.endswith(">"):
            uid = int(user_id_or_mention.strip("<@!>"))
    except Exception:
        uid = None
    if uid is None:
        return await ctx.respond("Invalid user. Provide a mention or numeric ID.")
    if uid in disabled_items.get("user", []):
        result = await enable_item(ctx, "user", uid)
        if result:
            return await ctx.respond(f"User <@{uid}> can now use bot commands.")
    else:
        await disable_item(ctx, "user", uid)
        return await ctx.respond(f"User <@{uid}> can no longer use bot commands.")
    return None


@bot.command(name="sync", help="Syncs commands")
@commands.is_owner()
async def sync(ctx: Ctx):
    await ctx.message.delete()
    await bot.tree.sync()
    await ctx.send("Synced!", delete_after=3)


def run_bot() -> None:
    """Run the bot."""
    bot.run(TOKEN, log_level=logging.WARNING, root_logger=True)


if __name__ == "__main__":
    run_bot()
