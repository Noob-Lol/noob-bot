import discord, os, requests, dotenv, atexit, logging
from aiohttp import web
from typing import Optional
from discord import app_commands
from discord.ext import commands
from pymongo.server_api import ServerApi
from pymongo.mongo_client import MongoClient
logger = logging.getLogger('discord.n01b')
logger.name = 'bot.main'
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
disabled_channels = {channel["channel_id"] for channel in disabled_coll.find()}
disabled_com_coll = db["disabled_commands"]
disabled_commands = {command["command"] for command in disabled_com_coll.find()}
try:
    client.admin.command('ping')
    logger.info("Successfully connected to MongoDB!")
except Exception as e:
    logger.error('Error connecting to MongoDB:', e)

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
        l.name = f'bot.{cog_name}'
        return l

    def log(self, text, file, temp_file='temp.txt'):
        try:
            response = requests.get(f"{api}/listfolder", params={'path': f'/{folder}', 'auth': PTOKEN}, timeout=5)
            files = response.json().get('metadata', {}).get('contents', [])
            file_info = next((f for f in files if f['name'] == file), None)
            if file_info:
                file_url = requests.get(f"{api}/getfilelink", params={'fileid': file_info['fileid'], 'auth': PTOKEN}, timeout=5).json()
                download_url = file_url['hosts'][0] + file_url['path']
                with open(temp_file, 'wb') as f:
                    f.write(requests.get(f'https://{download_url}', timeout=5).content)
            with open(temp_file, 'a') as f: f.write(f"{text}\n")
            with open(temp_file, 'rb') as f:
                requests.post(f"{api}/uploadfile", files={'filename': (file, f)}, data={'path': f'/{folder}', 'auth': PTOKEN}, timeout=5)
            os.remove(temp_file)
        except Exception as e:
            logger.error(f'Error logging to {file}: {e}')
    
    def get_lines(self, num_lines, file, temp_file='temp2.txt'):
        try:
            response = requests.get(f"{api}/listfolder", params={'path': f'/{folder}', 'auth': PTOKEN}, timeout=5)
            files = response.json().get('metadata', {}).get('contents', [])
            file_info = next((f for f in files if f['name'] == file), None)
            if not file_info:
                logger.error(f"File '{file}' not found in folder '{folder}'.")
                return []
            file_url = requests.get(f"{api}/getfilelink", params={'fileid': file_info['fileid'], 'auth': PTOKEN}, timeout=5).json()
            download_url = file_url['hosts'][0] + file_url['path']
            response = requests.get(f'https://{download_url}', timeout=5)
            response.raise_for_status()
            lines = response.text.splitlines()
            if not lines:
                return 0
            if num_lines == 0:
                return len(lines)
            if num_lines > len(lines):
                num_lines = len(lines)
            lines2 = lines[:num_lines]
            with open(temp_file, 'w') as f: f.write("\n".join(lines[num_lines:]))
            with open(temp_file, 'rb') as f:
                requests.post(f"{api}/uploadfile", files={'filename': (file, f)}, data={'path': f'/{folder}', 'auth': PTOKEN}, timeout=5)
            os.remove(temp_file)
            return lines2
        except Exception as e:
            logger.error(f'Error getting lines from {file}: {e}')
            return []
    
    def check_boost(self, guild_id, member_id):
        response = requests.get(f'https://discord.com/api/v10/guilds/{guild_id}/premium/subscriptions', headers={'authorization': RTOKEN}, timeout=5).json()
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
        
    async def respond(self, ctx, text, delete_after=5, ephemeral=True):
        # default respond function (saves space)
        if ctx.interaction: await ctx.send(text, ephemeral = ephemeral)
        else: await ctx.send(text, delete_after = delete_after)

bot = Bot()

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
            result = disabled_coll.delete_one({"channel_id": ctx.channel.id})
            if result.deleted_count > 0:
                disabled_channels.remove(ctx.channel.id)
                await ctx.send("This channel has been enabled for bot commands.")
        else:
            disabled_coll.insert_one({"channel_id": ctx.channel.id})
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
    skipped_cogs, dis_cmds = [], []
    for filename in os.listdir(f'{script_path}/cogs'):
        if filename.endswith('.py') and filename != '__init__.py':
            cog_name = filename[:-3]
            if cog_name in unloaded_cogs:
                skipped_cogs.append(cog_name)
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
    if skipped_cogs:
        logger.info(f'Unloaded cogs: {", ".join(skipped_cogs)}')
    for command in disabled_commands:
        cmd = bot.get_command(command)
        if cmd: cmd.enabled = False
        dis_cmds.append(command)
    if dis_cmds:
        logger.info(f'Disabled commands: {", ".join(dis_cmds)}')

bot.run(TOKEN)
