import platform

import discord
from discord import app_commands
from discord.ext import commands

from bot import Bot, Default_Cog


class MiscCog(Default_Cog):
    def __init__(self, bot: Bot):
        super().__init__(bot)
        # nothing is here, yet

    @commands.hybrid_command(name="add", help="Adds one to the database")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def add(self, ctx):
        counter = self.bot.counter
        result = await counter.find_one_and_update({'_id': 'counter'}, {'$inc': {'count': 1}}, upsert=True)
        await ctx.send(f'Counter incremented to {result["count"] + 1}.')

    @commands.hybrid_command(name="dmme", help="Sends a DM to the author")
    async def dmme(self, ctx, *, text: str):
        try:
            await ctx.author.send(text)
            await self.bot.respond(ctx, "DM was sent", del_cmd=False)
        except Exception as e:
            await self.bot.respond(ctx, f"Could not send DM, {e}", del_cmd=False)

    @commands.hybrid_command(name="cb", help="Check boost count of a user")
    @commands.cooldown(1, 3, commands.BucketType.user)
    @app_commands.describe(user="User to check boost count for")
    async def count_boosts(self, ctx, user: discord.Member | None):
        if user is None:
            user = ctx.author
        if not isinstance(user, discord.Member):
            await ctx.send("Invalid user provided.")
            return
        if user.premium_since:
            boosts = await self.bot.check_boost(ctx.guild.id, user.id)
            if not boosts:
                return await ctx.send("Failed to get boost count.")
            await ctx.send(f"{user.name} has {boosts} boosts.")
        else:
            await ctx.send(f"{user.name} has not boosted the server.")

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
    async def weather(self, ctx: commands.Context, *, city: str):
        headers = {
            # this is not my api key
            "X-RapidAPI-Key": "a3a7d073famsh43a70b10b861ed7p115a35jsnb340981d017b",
            "X-RapidAPI-Host": "weatherapi-com.p.rapidapi.com"
        }
        url = "https://weatherapi-com.p.rapidapi.com/forecast.json"
        async with self.bot.session.get(url, headers=headers, params={"q": city, "days": "3"}) as response:
            if response.status != 200:
                await ctx.send("Failed to fetch weather data.")
                self.logger.error(f"Weather API request failed with status {response.status}")
                return
            weather = await response.json()
        bad_json = {'message': 'This endpoint is disabled for your subscription'}
        if weather == bad_json:
            await ctx.send("This api key is cooked, owner needs to get a new one")
            self.logger.error("Weather API key is cooked")
            return
        title = f"Weather in {weather['location']['name']}, {weather['location']['country']}"
        embed = discord.Embed(title=title, color=discord.Color.blue())
        embed.add_field(name="Local Time", value=weather['location']['localtime'], inline=False)
        embed.add_field(name="Temperature", value=f"{weather['current']['temp_c']}℃")
        embed.add_field(name="Condition", value=weather['current']['condition']['text'])
        embed.add_field(name="Wind Speed", value=f"{weather['current']['wind_kph']} kph")
        embed.add_field(name="Feels like", value=f"{weather['current']['feelslike_c']}℃")
        for i in range(3):
            forecast = weather['forecast']['forecastday'][i]
            temp = f"Temp: {forecast['day']['maxtemp_c']} ~ {forecast['day']['mintemp_c']}℃"
            rain = f"rain chance: {forecast['day']['daily_chance_of_rain']}"
            embed.add_field(name=forecast['date'], value=f"{temp}, {rain}", inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="log", help="Logs a message to the log file")
    @commands.is_owner()
    async def log_text(self, ctx, *, text: str):
        await self.bot.log_to_file(text, "test_log.txt")
        await self.bot.respond(ctx, "Message logged")


async def setup(bot: Bot):
    await bot.add_cog(MiscCog(bot))
