import discord, os, json, requests
from discord.ext import commands
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from dotenv import load_dotenv
load_dotenv()
TOKEN = os.environ["TOKEN"]
uri = os.environ["MONGO_URI"]

client = MongoClient(uri, server_api=ServerApi('1'))
db = client['mydatabase']
counter = db['counter']
# Send a ping to confirm a successful connection
try:
    client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(e)

class Bot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        intents.message_content = True
        super().__init__(command_prefix = ">", intents = intents)

    async def on_command_error(self, ctx, error):
        await ctx.reply(error, ephemeral = True)

bot = Bot()

@bot.hybrid_command(name="add", help="Adds one to the database")
async def add(ctx):
    result = counter.find_one_and_update({'_id': 'counter'}, {'$inc': {'count': 1}}, upsert=True)
    await ctx.send(f'Counter incremented to {result["count"]}')

@bot.hybrid_command(name="hybrid")
async def hybrid_command(ctx: commands.Context):
    if ctx.interaction:
        await ctx.send("This is a slash command!")
    else:
        await ctx.send("This is a regular command!")

@bot.hybrid_command(name = "test", with_app_command = True, description = "Testing")
async def test(ctx: commands.Context):
    await ctx.reply("hi!", ephemeral=True)

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
        activity=discord.Game('>help | bot by n01b'))
    await bot.load_extension('cogs.ModCog')
    await bot.load_extension('cogs.WeatherCog')
    print(f'Logged in as {bot.user}')

bot.run(TOKEN)