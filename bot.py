import discord, os, json, requests
from discord.ext import commands
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from dotenv import load_dotenv
load_dotenv()
script_path = os.path.dirname(__file__)
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

class Bot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        intents.message_content = True
        super().__init__(command_prefix = ">", intents = intents)
        self.script_path = script_path
        self.db = db
        self.counter = counter

    async def on_command_error(self, ctx, error):
        await ctx.reply(error, ephemeral = True)

bot = Bot()

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

@bot.hybrid_command(name="ping", help="Sends the bot's latency.")
async def ping(ctx):
    await ctx.send(f'Pong! {round (bot.latency * 1000)} ms')

@bot.command(name= 'sync', help="Syncs commands")
@commands.is_owner()
async def sync(ctx):         
    await bot.tree.sync()      
    await ctx.send("Synced!")

@bot.event
async def on_ready():
    await bot.change_presence(
        activity=discord.Game('>help'))
    for filename in os.listdir(f'{script_path}/cogs'):
        if filename.endswith('.py'):
            await bot.load_extension(f'cogs.{filename[:-3]}')
    print(f'Logged in as {bot.user}')

bot.run(TOKEN)
