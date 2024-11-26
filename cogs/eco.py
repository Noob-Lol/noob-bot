import discord, random
from discord.ext import commands

class EconomyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.collection = bot.db["economy"]

    @commands.hybrid_command(name="farm", help="Gives random money (1-1000)")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def farm(self, ctx):
        user_id = ctx.author.id
        amount = random.randint(1, 1000)
        user = self.collection.find_one({"_id": user_id})
        if user:
            new_balance = user["balance"] + amount
            self.collection.update_one({"_id": user_id}, {"$set": {"balance": new_balance}})
        else:
            new_balance = amount
            self.collection.insert_one({"_id": user_id, "balance": new_balance})
        await ctx.send(f"{ctx.author.mention}, you have been given {amount} money! Your new balance is {new_balance}.")

    @commands.hybrid_command(name="give", help="Gives money to another user")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def give(self, ctx, user: discord.User, amount: int):
        if amount < 1:
            await ctx.send("Amount must be at least 1.")
            return
        author_data = self.collection.find_one({"_id": ctx.author.id})
        if not author_data:
            await ctx.send("You don't have any money.")
            return
        if author_data["balance"] < amount:
            await ctx.send("You don't have enough money to give.")
            return
        user_id = user.id
        user_data = self.collection.find_one({"_id": user_id})
        if user_data:
            new_balance = user_data["balance"] + amount
            self.collection.update_one({"_id": user_id}, {"$set": {"balance": new_balance}})
        else:
            new_balance = amount
            self.collection.insert_one({"_id": user_id, "balance": new_balance})
        self.collection.update_one({"_id": ctx.author.id}, {"$inc": {"balance": -amount}})
        await ctx.send(f"**{ctx.author.name}** gave **{user.name}** {amount} money. Their new balance is {new_balance}.")

    @commands.hybrid_command(name="set_money", help="Sets the user's money to a specific amount")
    @commands.has_permissions(administrator=True)
    async def set_money(self, ctx, user: discord.User, amount: int):
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
            balance = 0
            self.collection.insert_one({"_id": user_id, "balance": balance})
        await ctx.send(f"{ctx.author.mention}, your current balance is {balance}.")

    @commands.hybrid_command(name="leaderboard", help="Displays the leaderboard of top users")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def leaderboard(self, ctx):
        await ctx.defer()
        users = self.collection.find({})
        leaderboard = sorted(users, key=lambda x: x.get("balance", 0), reverse=True)[:10]
        if not leaderboard:
            await ctx.send("No users found in the economy system.")
            return
        leaderboard_message = "🏆 **Leaderboard** 🏆\n"
        for index, user in enumerate(leaderboard, start=1):
            user_id = user["_id"]
            balance = user["balance"]
            member = ctx.guild.get_member(user_id)
            username = member.name if member else f"<User ID: {user_id}>"
            leaderboard_message += f"{index}. {username} - {balance} money\n"
        await ctx.send(leaderboard_message)

async def setup(bot):
    await bot.add_cog(EconomyCog(bot))
