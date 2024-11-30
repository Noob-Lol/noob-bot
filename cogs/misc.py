import requests, discord, platform
from discord.ext import commands
from discord import app_commands

class MiscCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="add", help="Adds one to the database")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def add(self, ctx):
        counter = self.bot.counter
        counter.find_one_and_update({'_id': 'counter'}, {'$inc': {'count': 1}}, upsert=True)
        result = counter.find_one({'_id': 'counter'})
        if result:
            await ctx.send(f'Counter incremented to {result["count"]}')

    @commands.hybrid_command(name="dmme", help="Sends a DM to the author")
    async def dmme(self, ctx, *, text: str):
        try:
            await ctx.author.send(text)
            await ctx.send("DM was sent", ephemeral = True)
        except Exception as e:
            await ctx.send(f"Could not send DM, {e}", ephemeral = True)

    @commands.hybrid_command(name="info", help="Displays information about the bot")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def a_bot_info(self, ctx):
        embed = discord.Embed(title="Bot info", color=discord.Color.random())
        embed.add_field(name="Prefix", value=">")
        embed.add_field(name="D.py version", value=discord.__version__)
        embed.add_field(name="Python version", value=platform.python_version())
        embed.add_field(name="Bot owner + dev", value="n01b")
        embed.add_field(name="Source code", value="[GitHub](https://github.com/noob-lol/noob-bot)")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="weather", help="Sends the weather for a city")
    @app_commands.describe(city="City name")
    async def weather(self, ctx, *, city: str):
        await ctx.defer()
        headers = {
             # this is not my api key
            "X-RapidAPI-Key": "f77c5bde9bmsh775458a2f3f1651p175e25jsn8b6a2f52c501",
            "X-RapidAPI-Host": "weatherapi-com.p.rapidapi.com"
        }
        weather = requests.get("https://weatherapi-com.p.rapidapi.com/forecast.json", headers=headers, params={"q":city,"days":"3"}).json()
        embed = discord.Embed(title=f"Weather in {weather['location']['name']}, {weather['location']['country']}", color=discord.Color.blue())
        embed.add_field(name="Local Time", value=weather['location']['localtime'], inline=False)
        embed.add_field(name="Temperature", value=f"{weather['current']['temp_c']}℃")
        embed.add_field(name="Condition", value=weather['current']['condition']['text'])
        embed.add_field(name="Wind Speed", value=f"{weather['current']['wind_kph']} kph")
        embed.add_field(name="Feels like", value=f"{weather['current']['feelslike_c']}℃")
        for i in range(3):
            forecast = weather['forecast']['forecastday'][i]
            embed.add_field(name=forecast['date'], value=f"{forecast['day']['maxtemp_c']} ~ {forecast['day']['mintemp_c']}℃, Rain Chance: {forecast['day']['daily_chance_of_rain']}", inline=False)
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(MiscCog(bot))
