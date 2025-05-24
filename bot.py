import discord, os, aiohttp, dotenv, atexit, logging, tempfile
from aiohttp import web
from typing import Optional
from discord import app_commands
from discord.ext import commands
from pymongo.server_api import ServerApi
from pymongo.mongo_client import MongoClient
if os.name == 'nt':
    try:
        from colorama import just_fix_windows_console
        just_fix_windows_console()
        os.environ['WT_SESSION'] = 'bruh'
    except ImportError:
        pass
logger = logging.getLogger('discord.n01b')
bot_name = 'noob_bot'
logger.name = bot_name
dotenv.load_dotenv()
script_path = os.path.dirname(__file__)
TOKEN = os.environ["TOKEN"]
RTOKEN = os.environ["RTOKEN"]
PTOKEN = os.environ['PTOKEN']
folder = "DiscordBotData"
api = 'https://eapi.pcloud.com'
uri = os.environ["MONGODB_URI"]
client = MongoClient(uri, server_api=ServerApi('1'))
db = client["discord_bot"]
unloaded_coll = db['unloaded_cogs']
unloaded_cogs = {cog["cog"] for cog in unloaded_coll.find()}
counter = db['counter']
disabled_coll = db["disabled_channels"]
disabled_channels = {channel["_id"] for channel in disabled_coll.find()}
disabled_com_coll = db["disabled_commands"]
disabled_commands = {command["command"] for command in disabled_com_coll.find()}
# default aiohttp timeout
def_TO = aiohttp.ClientTimeout(total=5, connect=2, sock_connect=2, sock_read=3)

class Bot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix = commands.when_mentioned_or(">"), intents = intents)
        self.script_path = script_path
        self.db = db
        self.counter = counter
        self.react = False

    def cog_logger(self, cog_name: str):
        l = logging.getLogger(f'discord.n01b.{cog_name}')
        l.name = f'bot.{cog_name}' if not bot_name in cog_name else cog_name
        return l

    async def log(self, text, file):
        try:
            temp_file = tempfile.NamedTemporaryFile(delete=False).name
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{api}/listfolder", params={'path': f'/{folder}', 'auth': PTOKEN}, timeout=def_TO) as response:
                    response_json = await response.json()
                    if response_json["result"] != 0:
                        return logger.error(f"Failed to list folder {folder}: {response_json['result']}, error: {response_json.get('error', 'Unknown error')}")
                    files = await response.json()
                file_info = next((f for f in files.get('metadata', {}).get('contents', []) if f['name'] == file), None)
                if file_info:
                    async with session.get(f"{api}/getfilelink", params={'fileid': file_info['fileid'], 'auth': PTOKEN}, timeout=def_TO) as file_url_response:
                        file_url = await file_url_response.json()
                    download_url = file_url['hosts'][0] + file_url['path']
                    async with session.get(f'https://{download_url}', timeout=def_TO) as file_response:
                        content = await file_response.read()
                    with open(temp_file, 'wb') as f:
                        f.write(content)
                with open(temp_file, 'a') as f:
                    f.write(f"{text}\n")
                with open(temp_file, 'rb') as f:
                    form = aiohttp.FormData()
                    form.add_field('filename', f, filename=file)
                    await session.post(f"{api}/uploadfile", data=form, params={'path': f'/{folder}', 'auth': PTOKEN}, timeout=def_TO)
            os.remove(temp_file)
        except Exception as e:
            logger.error(f'Error logging to {file}: {e}')
    
    async def get_lines(self, num_lines, file):
        try:
            temp_file = tempfile.NamedTemporaryFile(delete=False).name
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{api}/listfolder", params={'path': f'/{folder}', 'auth': PTOKEN}, timeout=def_TO) as response:
                    files = await response.json()
                    if files["result"] != 0:
                        return logger.error(f"Failed to list folder {folder}: {files['result']}, error: {files.get('error', 'Unknown error')}")
                file_info = next((f for f in files.get('metadata', {}).get('contents', []) if f['name'] == file), None)
                if not file_info:
                    logger.error(f"File '{file}' not found in folder '{folder}'.")
                    return []
                async with session.get(f"{api}/getfilelink", params={'fileid': file_info['fileid'], 'auth': PTOKEN}, timeout=def_TO) as file_url_response:
                    file_url = await file_url_response.json()
                download_url = file_url['hosts'][0] + file_url['path']
                async with session.get(f'https://{download_url}', timeout=def_TO) as file_response:
                    text = await file_response.text()
                    lines = text.splitlines()
                    if not lines:
                        return 0
                    if num_lines == 0:
                        return len(lines)
                    if num_lines > len(lines):
                        num_lines = len(lines)
                    lines2 = lines[:num_lines]
                    with open(temp_file, 'w') as f: f.write("\n".join(lines[num_lines:]))
                    with open(temp_file, 'rb') as f:
                        data = aiohttp.FormData()
                        data.add_field('filename', f, filename=file)
                        await session.post(f"{api}/uploadfile", data=data, params={'path': f'/{folder}', 'auth': PTOKEN}, timeout=def_TO)
            os.remove(temp_file)
            return lines2
        except Exception as e:
            logger.error(f'Error getting lines from {file}: {e}')
            return []
    
    async def check_boost(self, guild_id, member_id):
        try:
            async with aiohttp.ClientSession() as session:
                response = await session.get(f'https://discord.com/api/v10/guilds/{guild_id}/premium/subscriptions', headers={'authorization': RTOKEN}, timeout=def_TO)
                if response.status != 200:
                    logger.error(f'Error getting boost count for guild {guild_id}: {response.status}')
                    return False
                response = await response.json()
            if isinstance(response, list):
                boost_count = 0
                for boost in response:
                    user_id = boost['user']['id']
                    if int(user_id) == member_id:
                        boost_count += 1
                return boost_count
            else:
                logger.error(f'Error getting boost count for user {member_id}: {response}')
                return False
        except Exception as e:
            logger.error(f'Error checking boost for guild {guild_id}, member {member_id}: {e}')
            return False
        
    async def respond(self, ctx, text, delete_after=5, ephemeral=True):
        # default respond function (saves space)
        if ctx.interaction: await ctx.send(text, ephemeral = ephemeral)
        else: await ctx.send(text, delete_after = delete_after)

bot = Bot()

# # this is cool, but i dont log anything in commands. will be commented out for now
# @bot.before_invoke
# async def command_logger(ctx):
#     if ctx.cog:
#         ctx.logger = bot.cog_logger(f'{ctx.cog.qualified_name}.{ctx.command.name}')
#     else:
#         ctx.logger = bot.cog_logger(f'{bot_name}.{ctx.command.name}')

@atexit.register
def on_exit():
    logger.info("Stopped.")

def p(desc, default = None):
    return commands.parameter(description=desc, default=default)

descripts = {'type': 'The type of thing to toggle.', 'name': 'The name of the thing to toggle.'}

@bot.check
async def check_guild(ctx):
    return ctx.guild

@bot.check
async def check_channel(ctx):
    if ctx.channel.id in disabled_channels and ctx.command.name != 'toggle':
        if ctx.interaction: 
            await ctx.send("This channel is disabled.", ephemeral = True)
        return False
    return True

@bot.event
async def on_command(ctx):
    if await bot.is_owner(ctx.author):
        ctx.command.reset_cooldown(ctx)

@bot.event
async def on_command_error(ctx, error):
    if hasattr(ctx.command, 'on_error') and not hasattr(ctx, 'unhandled_error'):
        return
    ignored = (commands.CommandNotFound, app_commands.errors.CommandNotFound, )
    error = getattr(error, 'original', error)
    if isinstance(error, ignored):
        return
    if isinstance(error, commands.CheckFailure):
        if ctx.guild is None:
            await ctx.send("You can't use commands in DMs.", ephemeral = True)
    elif isinstance(error, discord.HTTPException) and error.status == 429:
        logger.warning(f"Rate limited. Retry in {error.response.headers['Retry-After']} seconds.")
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"This command is on cooldown. Please wait {error.retry_after:.2f}s", ephemeral = True, delete_after = 5)
    else: await ctx.send(error, ephemeral = True)

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    if '>nitro' in message.content.lower():
        if not bot.react:
            pass
        else:
            await message.add_reaction('☠️')
    await bot.process_commands(message)

@bot.hybrid_command(name="hi", help="Says hello")
async def hi(ctx):
    await ctx.send(f'Hello!')

@bot.hybrid_command(name="ping", help="Sends bot's latency.")
async def ping(ctx):
    await ctx.send(f'Pong! {round (bot.latency * 1000)} ms')

@bot.hybrid_command(name="dm", help="Sends a DM to a user")
@commands.is_owner()
async def dm(ctx, member:discord.Member, *, content):
    try:
        await member.send(content)
        await bot.respond(ctx, "DM was sent")
    except Exception as e:
        await bot.respond(ctx, f"Could not send DM, {e}")

@bot.hybrid_command(name="msg", help="Sends message as bot")
@commands.is_owner()
async def msg(ctx, channel: Optional[discord.TextChannel] = None, *, text: str):
    if not channel:
        channel = ctx.channel
        if not channel: return
    if not ctx.interaction:
        await ctx.message.delete()
    try:
        await channel.send(text)
        await bot.respond(ctx, "Message sent")
    except Exception as e:
        await bot.respond(ctx, f"Could not send message, {e}")

@bot.hybrid_command(name="toggle", help="Toggles alot of things (owner only)")
@commands.is_owner()
@app_commands.describe(type=descripts['type'], name=descripts['name'])
@app_commands.choices(
    type = [
        app_commands.Choice(name = 'cog', value = 'cog'),
        app_commands.Choice(name = 'channel', value = 'channel'),
        app_commands.Choice(name = 'command', value = 'command'),
        app_commands.Choice(name = 'react', value = 'react')
    ]
)
async def toggle_thing(ctx, type: str = p(descripts['type']), name: Optional[str] = p(descripts['name'])):
    if not ctx.interaction:
        await ctx.message.delete()
    if type == 'cog':
        cog = name
        if not cog:
            await bot.respond(ctx, "Please provide a cog name.")
            return
        try:
            cog_name = ''
            for key, _ in bot.cogs.items():
                if cog.lower() in key.lower():
                    cog_name = key
                    break
            if cog_name in bot.cogs:
                await bot.unload_extension(f'cogs.{cog}')
                unloaded_coll.insert_one({"cog": cog})
                await bot.respond(ctx, f"Disabled {cog}")
            elif cog in unloaded_cogs:
                await bot.load_extension(f'cogs.{cog}')
                unloaded_coll.delete_one({"cog": cog})
                await bot.respond(ctx, f"Enabled {cog}")
            else:
                await bot.respond(ctx, f"Cog not found: {cog}")
        except Exception as e:
            await bot.respond(ctx, f"Error: {e}", 10)
    elif type == 'channel':
        if ctx.channel.id in disabled_channels:
            result = disabled_coll.delete_one({"_id": ctx.channel.id})
            if result.deleted_count > 0:
                disabled_channels.remove(ctx.channel.id)
                await ctx.send("This channel has been enabled for bot commands.")
        else:
            disabled_coll.insert_one({"_id": ctx.channel.id})
            disabled_channels.add(ctx.channel.id)
            await ctx.send("This channel has been disabled for bot commands.")
    elif type == 'react':
        bot.react = not bot.react
        await bot.respond(ctx, f"Reactions are now {'enabled' if bot.react else 'disabled'}")
    elif type == 'command':
        command = name
        if not command:
            await bot.respond(ctx, "Please provide a command name.")
            return
        found = bot.get_command(command)
        if ctx.command == found:
            await bot.respond(ctx, "You can't disable the toggle command.")
            return
        if not found:
            await bot.respond(ctx, "Command not found.")
            return
        result = found.enabled = not found.enabled
        if result:
            disabled_com_coll.delete_one({"command": command})
        else:
            disabled_com_coll.insert_one({"command": command})
        await bot.respond(ctx, f"Command {command} is now {'enabled' if result else 'disabled'}")

@bot.command(name="sync", help="Syncs commands")
@commands.is_owner()
async def sync(ctx):
    await ctx.message.delete()         
    await bot.tree.sync()      
    await ctx.send("Synced!", delete_after=3)

async def web_status(_):
    return web.Response(text='OK')

@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.CustomActivity(name='im cool 😎, ">" prefix'))
    cogs = [filename[:-3] for filename in os.listdir(f'{script_path}/cogs') if filename.endswith('.py')]
    for cog_name in cogs:
        if cog_name in unloaded_cogs:
            continue
        try:
            await bot.load_extension(f'cogs.{cog_name}')
        except commands.ExtensionAlreadyLoaded:
            pass
    app = web.Application()
    app.router.add_get('/', web_status)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', 8000).start()
    logger.info(f'Logged in as {bot.user}')
    disabled_commands_list = [bot.get_command(command) for command in disabled_commands if (_ := bot.get_command(command)) is not None]
    for command in disabled_commands_list:
        if command:
            logger.info(f'Disabling command: {command.name}')
            command.enabled = False

bot.run(TOKEN)
