import discord, os, requests, dotenv
from aiohttp import web
from typing import Optional
from discord.ext import commands
from pymongo.server_api import ServerApi
from pymongo.mongo_client import MongoClient
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
counter = db['counter']
disabled_coll = db["disabled_channels"]
disabled_channels = {channel["channel_id"] for channel in disabled_coll.find()}
try:
    client.admin.command('ping')
    print("Successfully connected to MongoDB!")
except Exception as e:
    print(e)

class Bot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix = commands.when_mentioned_or(">"), intents = intents)
        self.script_path = script_path
        self.db = db
        self.counter = counter
        self.react = False

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
            print(e)
            return 'error'
    
    def get_lines(self, num_lines, file, temp_file='temp2.txt'):
        try:
            response = requests.get(f"{api}/listfolder", params={'path': f'/{folder}', 'auth': PTOKEN}, timeout=5)
            files = response.json().get('metadata', {}).get('contents', [])
            file_info = next((f for f in files if f['name'] == file), None)
            if not file_info:
                print(f"File '{file}' not found in folder '{folder}'.")
                return 'error'
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
            print(e)
            return 'error'
    
    def check_boost(self, guild_id, member_id):
        response = requests.get(f'https://discord.com/api/v10/guilds/{guild_id}/premium/subscriptions', headers={'authorization': RTOKEN}).json()
        if isinstance(response, list):
            boost_count = 0
            for boost in response:
                user_id = boost['user']['id']
                if int(user_id) == member_id:
                    boost_count += 1
            return boost_count
        else:
            print(response)
            return False

bot = Bot()

@bot.check
async def check_guild(ctx):
    return ctx.guild

@bot.check
async def check_channel(ctx):
    if ctx.channel.id in disabled_channels and ctx.command.name != 'enable':
        if ctx.interaction: 
            await ctx.send("This channel is disabled.", ephemeral = True)
        return False
    return True

@bot.event
async def on_command_error(ctx, error):
    if hasattr(ctx.command, 'on_error') and not hasattr(ctx, 'unhandled_error'):
        return
    ignored = (commands.CommandNotFound, )
    error = getattr(error, 'original', error)
    if isinstance(error, ignored):
        return
    if isinstance(error, commands.CheckFailure):
        if ctx.guild is None:
            await ctx.send("You can't use commands in DMs.", ephemeral = True)
    elif isinstance(error, discord.HTTPException) and error.status == 429:
        print(f"Rate limited. Retry in {error.response.headers['Retry-After']} seconds.")
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
        await ctx.send("DM was sent", ephemeral = True)
    except Exception as e:
        await ctx.send(f"Could not send DM, {e}", ephemeral = True)

@bot.hybrid_command(name="msg", help="Sends message as bot")
@commands.is_owner()
async def msg(ctx, channel: Optional[discord.TextChannel] = None, *, text: str):
    if not channel:
        channel = ctx.channel
    if not ctx.interaction:
        await ctx.message.delete()
    message = await ctx.send("Message should be sent", ephemeral = True)
    if channel:
        try:
            await channel.send(text)
        except Exception as e:
            await message.edit(content = f"Could not send message, {e}", ephemeral = True)
    else:
        await message.edit(content = "Channel not found", ephemeral = True)

@bot.hybrid_command(name="enable", help="Enables commands in a channel")
@commands.has_permissions(administrator=True)
async def enable_channel(ctx):
    result = disabled_coll.delete_one({"channel_id": ctx.channel.id})
    if result.deleted_count > 0:
        disabled_channels.remove(ctx.channel.id)
        await ctx.send("This channel has been enabled for bot commands.")
    else:
        await ctx.send("This channel is not disabled.")

@bot.hybrid_command(name="disable", help="Disables commands in a channel")
@commands.has_permissions(administrator=True)
async def disable_channel(ctx):
    if ctx.channel.id in disabled_channels:
        await ctx.send("This channel is already disabled.")
    else:
        disabled_coll.insert_one({"channel_id": ctx.channel.id})
        disabled_channels.add(ctx.channel.id)
        await ctx.send("This channel has been disabled for bot commands.")

@bot.hybrid_command(name="react", help="Toggles reaction")
@commands.is_owner()
async def react(ctx):
    if not ctx.interaction:
        await ctx.message.delete()
    if bot.react:
        bot.react = False
        await ctx.send("Disabled reactions", delete_after=5, ephemeral = True)
    else:
        bot.react = True
        await ctx.send("Enabled reactions", delete_after=5, ephemeral = True)

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
    for filename in os.listdir(f'{script_path}/cogs'):
        if filename.endswith('.py'):
            try:
                await bot.load_extension(f'cogs.{filename[:-3]}')
            except commands.ExtensionAlreadyLoaded:
                pass
    app = web.Application()
    app.router.add_get('/', web_status)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', 8000).start()
    print(f'Logged in as {bot.user}')

bot.run(TOKEN)
