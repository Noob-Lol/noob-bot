import discord, random, datetime
from discord.ext import commands, tasks
from discord.ui import View, Button

class EconomyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.collection = bot.db["economy"]
        self.farm_usage = bot.db["farm_usage"]
        self.cleanup_old_farm.start()

    @commands.hybrid_command(name="farm", help="Gives some nitro credits")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def farm(self, ctx):
        today_dt = datetime.datetime.combine(datetime.date.today(), datetime.time(0, 0, 0))
        user_id = ctx.author.id
        result = self.farm_usage.find_one({'_id': user_id})
        if result:
            last_farm = result['last_farm']
            if last_farm >= today_dt:
                return await ctx.send("You have already farmed today.")
            self.farm_usage.update_one({'_id': user_id}, {'$set': {'last_farm': today_dt}})
        else:
            self.farm_usage.insert_one({'_id': user_id, 'last_farm': today_dt})
        amount = 0.5
        user = self.collection.find_one({"_id": user_id})
        if user:
            new_balance = user["balance"] + amount
            if new_balance % 1 == 0:
                new_balance = int(new_balance)
            self.collection.update_one({"_id": user_id}, {"$set": {"balance": new_balance}})
        else:
            new_balance = amount
            self.collection.insert_one({"_id": user_id, "balance": new_balance})
        await ctx.send(f"{ctx.author.mention}, you have been given {amount} nitro credits! Your new balance is {new_balance}.")

    @commands.hybrid_command(name="give", help="Gives nitro credits to another user")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def give(self, ctx, user: discord.User, amount: float):
        if amount < 1:
            return await ctx.send("Amount must be at least 1.")
        author_data = self.collection.find_one({"_id": ctx.author.id})
        if not author_data:
            return await ctx.send("You don't have any nitro credits.")
        if author_data["balance"] < amount:
            return await ctx.send("You don't have enough nitro credits to give.")
        user_id = user.id
        user_data = self.collection.find_one({"_id": user_id})
        if user_data:
            new_balance = user_data["balance"] + amount
            self.collection.update_one({"_id": user_id}, {"$set": {"balance": new_balance}})
        else:
            new_balance = amount
            self.collection.insert_one({"_id": user_id, "balance": new_balance})
        self.collection.update_one({"_id": ctx.author.id}, {"$inc": {"balance": -amount}})
        await ctx.send(f"**{ctx.author.name}** gave **{user.name}** {amount} nitro credits. Their new balance is {new_balance}.")

    @commands.hybrid_command(name="set_balance", help="Sets the user's nitro credits to a specific amount")
    @commands.has_permissions(administrator=True)
    async def set_balance(self, ctx, user: discord.User, amount: float):
        user_id = user.id
        self.collection.update_one({"_id": user_id}, {"$set": {"balance": amount}}, upsert=True)
        await ctx.send(f"{user.mention}'s balance has been set to {amount}.")

    @commands.hybrid_command(name="balance", help="Displays your current balance")
    async def balance(self, ctx):
        user_id = ctx.author.id
        user = self.collection.find_one({"_id": user_id})
        if user:
            balance = user["balance"]
        else:
            return await ctx.send("You are not in database. (no nitro credits)")
        await ctx.send(f"{ctx.author.mention}, your current balance is {balance}.")

    @commands.hybrid_command(name="leaderboard", help="Displays the leaderboard of top users")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def leaderboard(self, ctx):
        await ctx.defer(ephemeral=True)
        users = self.collection.find({})
        this_guild = []
        for user in users:
            user_id = user["_id"]
            member = ctx.guild.get_member(user_id)
            if member:
                user["member"] = member
                this_guild.append(user)
        leaderboard = sorted(this_guild, key=lambda x: x.get("balance", 0), reverse=True)
        if not leaderboard:
            await ctx.send("No users found in the economy system.")
            return
        page_size, current_page = 5, 0
        total_pages = (len(leaderboard) // page_size) + (1 if len(leaderboard) % page_size > 0 else 0)
        def build_embed(page):
            start = page * page_size
            end = start + page_size
            page_data = leaderboard[start:end]
            embed = discord.Embed(title="🏆 **Leaderboard** 🏆", description="Top Users:", color=discord.Color.yellow())
            for index, user in enumerate(page_data, start=start+1):
                member = user["member"]
                balance = user["balance"]
                if balance == 0:
                    continue
                username = member.name
                embed.add_field(name=f"{index}. {username}", value=f"{balance} nitro credits", inline=False)
            embed.set_footer(text=f"Page {page+1}/{total_pages}, timeouts in 60 seconds")
            return embed
        async def update_embed(interaction, page):
            await interaction.response.edit_message(embed=build_embed(page), view=build_view(page))
        def build_view(page):
            prev_button = Button(label="Previous", style=discord.ButtonStyle.primary, disabled=page == 0)
            next_button = Button(label="Next", style=discord.ButtonStyle.primary, disabled=page == total_pages - 1)
            async def prev_callback(interaction):
                nonlocal current_page
                if current_page > 0:
                    current_page -= 1
                await update_embed(interaction, current_page)
            async def next_callback(interaction):
                nonlocal current_page
                if current_page < total_pages - 1:
                    current_page += 1
                await update_embed(interaction, current_page)
            prev_button.callback, next_button.callback = prev_callback, next_callback
            return View(timeout=60).add_item(prev_button).add_item(next_button)
        await ctx.send(embed=build_embed(current_page), view=build_view(current_page))

    @tasks.loop(hours=24)
    async def cleanup_old_farm(self):
        today_dt = datetime.datetime.combine(datetime.date.today() - datetime.timedelta(days=1), datetime.time(0, 0, 0))
        self.farm_usage.delete_many({'last_farm': {'$lt': today_dt}})

async def setup(bot):
    await bot.add_cog(EconomyCog(bot))
