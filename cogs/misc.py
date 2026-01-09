import platform

import discord
from discord import app_commands
from discord.ext import commands

from bot import BaseCog, Bot, Ctx


class MiscCog(BaseCog):
    def __init__(self, bot: Bot):
        super().__init__(bot)
        # nothing is here, yet

    @commands.hybrid_command(name="add", help="Adds one to the database")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def add(self, ctx: Ctx):
        counter = self.bot.counter
        result = await counter.find_one_and_update({"_id": "counter"}, {"$inc": {"count": 1}}, upsert=True)
        await ctx.send(f'Counter incremented to {result["count"] + 1}.')

    @commands.hybrid_command(name="dmme", help="Sends a DM to the author")
    async def dmme(self, ctx: Ctx, *, text: str):
        await self.do_nothing()
        try:
            await ctx.author.send(text)
            await ctx.respond("DM was sent", del_cmd=False)
        except Exception as e:
            await ctx.respond(f"Could not send DM, {e}", del_cmd=False)

    @commands.hybrid_command(name="cb", help="Check boost count of a user")
    @commands.cooldown(1, 3, commands.BucketType.user)
    @app_commands.describe(user="User to check boost count for")
    async def count_boosts(self, ctx: Ctx, user: discord.Member | None):
        guild, user = self.bot.verify_guild_user(ctx.guild, ctx.author if user is None else user)
        boosts = await self.bot.check_boost(guild, user)
        if boosts == -1:
            await ctx.send("Failed to get boost count.")
            return
        if boosts == 0:
            await ctx.send(f"{user.name} has not boosted the server.")
        else:
            await ctx.send(f"{user.name} has {boosts} boosts.")

    @commands.hybrid_command(name="info", help="Displays information about the bot")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def a_bot_info(self, ctx: Ctx):
        embed = discord.Embed(title="Bot info", color=discord.Color.random())
        embed.add_field(name="Prefix", value=f"/ (Slash) or {self.bot.prefix}")
        embed.add_field(name="D.py version", value=discord.__version__)
        embed.add_field(name="Python version", value=platform.python_version())
        embed.add_field(name="Bot owner + dev", value="n01b")
        embed.add_field(name="Source code", value="[GitHub](https://github.com/noob-lol/noob-bot)")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="serverinfo", description="Get some useful (or not) information about the server.")
    async def serverinfo(self, ctx: Ctx):
        guild = self.bot.verify_guild(ctx.guild)
        roles = [role.name for role in guild.roles]
        num_roles = len(roles)
        if num_roles > 50:
            roles = roles[:50]
            roles.append(f">>>> Displaying [50/{num_roles}] Roles")
        roles = ", ".join(roles)
        embed = discord.Embed(title="**Server Name:**", description=guild, color=0xBEBEFE)
        if guild.icon is not None:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="Server ID", value=guild.id)
        embed.add_field(name="Member Count", value=guild.member_count)
        embed.add_field(name="Text/Voice Channels", value=f"{len(guild.channels)}")
        embed.add_field(name=f"Roles ({len(guild.roles)})", value=roles)
        embed.set_footer(text=f"Created at: {guild.created_at}")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="feedback", description="Submit a feedback for the owners of the bot")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def feedback(self, ctx: Ctx, *, text: str | None = None):
        app_owner = (await self.bot.application_info()).owner
        await app_owner.send(
            embed=discord.Embed(
                title="New Feedback",
                description=f"{ctx.author} (<@{ctx.author.id}>) has submitted a new feedback:\n```\n{text}\n```",
                color=0xBEBEFE),
        )
        await ctx.respond("Feedback submitted")

    @commands.hybrid_command(name="weather", help="Sends the weather for a city")
    @app_commands.describe(city="City name")
    async def weather(self, ctx: Ctx, *, city: str):
        headers = {
            # this is not my api key
            "X-RapidAPI-Key": "a3a7d073famsh43a70b10b861ed7p115a35jsnb340981d017b",
            "X-RapidAPI-Host": "weatherapi-com.p.rapidapi.com",
        }
        url = "https://weatherapi-com.p.rapidapi.com/forecast.json"
        try:
            async with self.bot.session.get(url, headers=headers, params={"q": city, "days": "3"}) as response:
                weather: dict = await response.json()
            bad_json = {"message": "This endpoint is disabled for your subscription"}
            if weather == bad_json:
                await ctx.send("This api key is cooked, owner needs to get a new one")
                self.logger.error("Weather API key is cooked")
                return
            title = f"Weather in {weather['location']['name']}, {weather['location']['country']}"
            embed = discord.Embed(title=title, color=discord.Color.blue())
            embed.add_field(name="Local Time", value=weather["location"]["localtime"], inline=False)
            embed.add_field(name="Temperature", value=f"{weather['current']['temp_c']}℃")
            embed.add_field(name="Condition", value=weather["current"]["condition"]["text"])
            embed.add_field(name="Wind Speed", value=f"{weather['current']['wind_kph']} kph")
            embed.add_field(name="Feels like", value=f"{weather['current']['feelslike_c']}℃")
            for i in range(3):
                forecast = weather["forecast"]["forecastday"][i]
                temp = f"Temp: {forecast['day']['maxtemp_c']} ~ {forecast['day']['mintemp_c']}℃"
                rain = f"rain chance: {forecast['day']['daily_chance_of_rain']}"
                embed.add_field(name=forecast["date"], value=f"{temp}, {rain}", inline=False)
            await ctx.send(embed=embed)
        except Exception as e:
            self.logger.exception("Failed to get data:")
            await ctx.send(f"Failed to get weather data: {e}")

    @commands.hybrid_command(name="log", help="Logs a message to the log file")
    @commands.is_owner()
    async def log_text(self, ctx: Ctx, *, text: str):
        await self.bot.log_to_file(text, "test_log.txt")
        await ctx.respond("Message logged")

    @commands.hybrid_command(name="crash", help="Crashes the bot (for testing)")
    @commands.is_owner()
    async def crash_bot(self, ctx: Ctx, error_message: str = "crash"):
        self.logger.info("Crashing bot...")
        raise discord.DiscordException(error_message)


async def setup(bot: Bot):
    await bot.add_cog(MiscCog(bot))
