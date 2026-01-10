import secrets

import discord
from discord.ext import commands, tasks
from discord.ui import Button, View

from bot import BaseCog, Bot, Ctx


class EconomyCog(BaseCog):
    def __init__(self, bot: Bot):
        super().__init__(bot)
        self.eco = bot.db["economy"]
        self.farm_usage = bot.db["farm_usage"]
        self.auth_tokens_coll = bot.db["auth_tokens"]
        self.dash_url = bot.get_env("DASH_URL", "")
        self.logger.info("Dashboard link: %s", self.dash_url)
        self.cleanup_old_farm.start()

    @commands.hybrid_command(name="farm", help="Gives some currency once a day")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def farm(self, ctx: Ctx):
        today_dt = self.bot.now_utc(combine=True)
        user_id = ctx.author.id
        result = await self.farm_usage.find_one({"_id": user_id})
        if result:
            last_farm = result["last_farm"]
            if last_farm >= today_dt:
                await ctx.send("You have already farmed today.")
                return
            await self.farm_usage.update_one({"_id": user_id}, {"$set": {"last_farm": today_dt}})
        else:
            await self.farm_usage.insert_one({"_id": user_id, "last_farm": today_dt})
        amount = 0.5
        user = await self.eco.find_one({"_id": user_id})
        if user:
            new_bal = self.to_d129(user["balance"]) + amount
            if new_bal % 1 == 0:
                new_bal = round(new_bal)
            await self.eco.update_one({"_id": user_id}, {"$set": {"balance": new_bal}})
        else:
            new_bal = self.to_d129(amount)
            await self.eco.insert_one({"_id": user_id, "balance": new_bal})
        amount_cur = f"{amount:g} {self.bot.currency}"
        await ctx.send(f"{ctx.author.mention}, you have been given {amount_cur}! Your new balance is {new_bal!s}.")

    @commands.hybrid_command(name="dash", help="Get your personal dashboard login link")
    async def dashboard(self, ctx: Ctx):
        if not self.dash_url:
            await ctx.send("Dashboard link is not set.")
            return
        if not ctx.interaction:
            await ctx.send("For security, you must use slash version of this command.")
            return
        token = secrets.token_urlsafe(16)
        discord_id = ctx.author.id
        await self.auth_tokens_coll.insert_one({
            "_id": token,
            "discord_id": discord_id,
            "created_at": self.bot.now_utc(),
        })
        url = f"{self.dash_url}/{token}"
        await ctx.respond(f"Here is your dashboard login link: [Click](<{url}>)")

    @commands.hybrid_command(name="give", help="Give currency to another user")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def give(self, ctx: Ctx, user: discord.Member, amount: float):
        if amount < 0:
            await ctx.send("Amount must be positive.")
            return
        if amount < 1 and not await self.bot.is_owner(ctx.author):
            await ctx.send("Amount must be at least 1.")
            return
        author = ctx.author
        user_id = user.id
        # you can't give yourself, lol
        if author.id == user_id:
            await ctx.send("You can't give yourself currency.")
            return
        author_data = await self.eco.find_one({"_id": author.id})
        if not author_data:
            await ctx.send(f"You don't have any {self.bot.currency}.")
            return
        amount_decimal = self.to_d129(amount)
        if self.to_d129(author_data["balance"]) < amount_decimal:
            await ctx.send(f"You don't have enough {self.bot.currency} to give.")
            return
        # Perform both updates in parallel, convert float to Decimal128
        update_recipient = self.eco.update_one({"_id": user_id}, {"$inc": {"balance": amount_decimal}}, upsert=True)
        update_sender = self.eco.update_one({"_id": author.id}, {"$inc": {"balance": -amount_decimal}}, upsert=True)
        await self.bot.agather(update_recipient, update_sender)
        recipient_data = await self.eco.find_one({"_id": user_id})
        if not recipient_data:
            self.logger.error("User %s not found in database", user_id)
            await ctx.send(f"Something went wrong. User {user.name} not found in database.")
            return
        new_bal = self.to_d129(recipient_data["balance"])
        amount_cur = f"{amount:g} {self.bot.currency}"
        await ctx.send(f"**{author.name}** gave **{user.name}** {amount_cur}. Their new balance is {new_bal!s}.")

    @commands.hybrid_command(name="set_balance", help="Sets the user's balance to a specific amount")
    @commands.is_owner()
    async def set_balance(self, ctx, user: discord.User, amount: float):
        await self.eco.update_one({"_id": user.id}, {"$set": {"balance": self.to_d129(amount)}}, upsert=True)
        await ctx.respond(f"{user.name}'s balance has been set to {amount:g}.")

    @commands.hybrid_command(name="remove_user", help="Removes a user from the economy database")
    @commands.is_owner()
    async def remove_user(self, ctx, user: discord.User):
        await self.eco.delete_one({"_id": user.id})
        await ctx.respond(f"{user.name}'s data has been removed from the database.")

    @commands.hybrid_command(name="balance", help="Displays your current balance")
    async def balance(self, ctx: Ctx):
        user = await self.eco.find_one({"_id": ctx.author.id})
        if not user:
            await ctx.send(f"You are not in database. (no {self.bot.currency})")
            return
        balance = self.to_d129(user["balance"])
        await ctx.send(f"{ctx.author.mention}, your current balance is {balance!s}.")

    @commands.hybrid_command(name="leaderboard", help="Displays the leaderboard of top users")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def leaderboard(self, ctx: Ctx):
        guild = self.bot.verify_guild(ctx.guild)
        await ctx.defer(ephemeral=True)

        member_ids = [m.id for m in guild.members]
        cursor = self.eco.find({"_id": {"$in": member_ids}}).sort("balance", -1)
        users = await cursor.to_list(100)

        leaderboard_data = []
        for user in users:
            balance = self.to_d129(user.get("balance", 0))
            if balance > 0:
                leaderboard_data.append({"id": user["_id"], "balance": balance})

        if not leaderboard_data:
            await ctx.send("No users with balance found in this server.")
            return

        page_size = 5
        total_pages = max(1, (len(leaderboard_data) + page_size - 1) // page_size)
        current_page = 0

        def build_embed(page: int):
            start = page * page_size
            end = start + page_size
            page_data = leaderboard_data[start:end]
            embed = discord.Embed(title="🏆 **Leaderboard** 🏆", description="Top Users:", color=discord.Color.yellow())
            for index, entry in enumerate(page_data, start=start + 1):
                member = guild.get_member(entry["id"])
                username = member.name if member else "Unknown User"
                embed.add_field(name=f"{index}. {username}", value=f"{entry['balance']!s} {self.bot.currency}", inline=False)
            embed.set_footer(text=f"Page {page + 1}/{total_pages}, timeouts in 60 seconds")
            return embed

        async def update_embed(interaction: discord.Interaction, page):
            await interaction.response.edit_message(embed=build_embed(page), view=build_view(page))

        def build_view(page: int):
            prev_button = Button(label="Previous", style=discord.ButtonStyle.primary, disabled=page == 0)
            next_button = Button(label="Next", style=discord.ButtonStyle.primary, disabled=page == total_pages - 1)

            async def prev_callback(interaction):
                nonlocal current_page
                current_page -= 1
                await update_embed(interaction, current_page)

            async def next_callback(interaction):
                nonlocal current_page
                current_page += 1
                await update_embed(interaction, current_page)

            prev_button.callback, next_button.callback = prev_callback, next_callback
            return View(timeout=60).add_item(prev_button).add_item(next_button)

        await ctx.send(embed=build_embed(current_page), view=build_view(current_page))

    @tasks.loop(hours=24)
    async def cleanup_old_farm(self):
        yesterday_dt = self.bot.now_utc(combine=True, days=-1)
        await self.farm_usage.delete_many({"last_farm": {"$lt": yesterday_dt}})


async def setup(bot: Bot):
    await bot.add_cog(EconomyCog(bot))
