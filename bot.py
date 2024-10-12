import discord, os, requests, subprocess, dotenv, socket, time
from aiohttp import web
from discord.ext import commands
from pymongo.server_api import ServerApi
from pymongo.mongo_client import MongoClient
dotenv.load_dotenv()
script_path = os.path.dirname(__file__)
try:
    server2 = os.environ['SERVER2']
    while True:
        try:
            response = requests.get(f"http://{server2}/status", timeout=2)
            if response.status_code == 200:
                print("Bot is online, waiting...")
                time.sleep(30)
            else:
                print("Something went wrong.")
                break
        except requests.ConnectionError:
            break
except KeyError:
    print("Second server not configured, skipping.")

def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(('8.8.8.8', 80))
    return s.getsockname()[0]

try:
    ip = os.environ['SERVER_IP']
    port = os.environ['SERVER_PORT']
except KeyError:
    ip = get_ip()
    port = 6969

TOKEN = os.environ["TOKEN"]
uri = os.environ["MONGODB_URI"]
client = MongoClient(uri, server_api=ServerApi('1'))
db = client["discord_bot"]
counter = db['counter']
try:
    client.admin.command('ping')
    print("Successfully connected to MongoDB!")
except Exception as e:
    print(e)

response = requests.get("https://discord.com/api/v10/users/@me", headers={"Authorization": f"Bot {TOKEN}"})
if response.status_code == 429:
    retry_after = response.headers["Retry-After"]
    print(f"Rate limited. Restart in {retry_after} seconds.")
    proxy = "http://127.0.0.1:8080"
    subprocess.Popen(f"{script_path}/proxies/opera-proxy -country EU -bind-address {proxy.split('/')[2]}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    while True:
        try:
            requests.head(proxy, timeout=1)
            print('Proxy started')
            break
        except requests.ConnectionError:
            pass
else:
    response.raise_for_status()
    proxy = None

class Bot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        intents.message_content = True
        intents.presences = True
        intents.guilds = True
        intents.members = True
        intents.messages = True
        intents.reactions = True
        intents.typing = True
        super().__init__(command_prefix = ">", intents = intents, proxy = proxy)
        self.script_path = script_path
        self.db = db
        self.counter = counter

bot = Bot()

@bot.check
async def check_guild(ctx):
    return ctx.guild

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        if ctx.guild is None:
            await ctx.send("You can't use commands in DMs.", ephemeral = True)
        return
    await ctx.reply(error, ephemeral = True)

@bot.hybrid_command(name="add", help="Adds one to the database")
@commands.cooldown(1, 5, commands.BucketType.user)
async def add(ctx):
    counter.find_one_and_update({'_id': 'counter'}, {'$inc': {'count': 1}}, upsert=True)
    result = counter.find_one({'_id': 'counter'})
    if result:
        await ctx.send(f'Counter incremented to {result["count"]}')

@bot.hybrid_command(name="hybrid", help="Hybrid test")
async def hybrid_command(ctx: commands.Context):
    if ctx.interaction:
        await ctx.send("This is a slash command!")
    else:
        await ctx.send("This is a regular command!")

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
        await ctx.send("Could not send DM, {e}", ephemeral = True)

@bot.hybrid_command(name="msg", help="Sends message as bot")
@commands.is_owner()
async def msg(ctx, content):
    if not ctx.interaction:
        await ctx.message.delete()
    await ctx.send(content)

@bot.hybrid_command(name="dmme", help="Sends a DM to the author")
async def dmme(ctx, *, content):
    try:
        await ctx.author.send(content)
        await ctx.send("DM was sent", ephemeral = True)
    except Exception as e:
        await ctx.send(f"Could not send DM, {e}", ephemeral = True)

@bot.command(name= 'sync', help="Syncs commands")
@commands.is_owner()
async def sync(ctx):
    await ctx.message.delete()         
    await bot.tree.sync()      
    await ctx.send("Synced!", delete_after=3)

async def web_status(self):
    return web.Response(text='OK')

@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.CustomActivity(name='im cool 😎, ">" prefix'))
    for filename in os.listdir(f'{script_path}/cogs'):
        if filename.endswith('.py'):
            await bot.load_extension(f'cogs.{filename[:-3]}')
    app = web.Application()
    app.router.add_get('/status', web_status)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', int(port)).start()
    print(f'Started at http://{ip}:{port}/status')
    print(f'Logged in as {bot.user}')

bot.run(TOKEN)
