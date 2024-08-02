import discord
from discord.ext import commands
import random
import os
from pymongo import MongoClient
from pymongo.server_api import ServerApi

uri = os.environ["MONGODB_URI"]
client = MongoClient(uri, server_api=ServerApi('1'))
db = client["discord_bot"]
collection = db["economy"]

class EconomyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="farm", help="Gives random money (1-1000)")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def farm(self, ctx):
        user_id = ctx.author.id
        amount = random.randint(1, 1000)
        user = collection.find_one({"_id": user_id})
        if user:
            new_balance = user["balance"] + amount
            collection.update_one({"_id": user_id}, {"$set": {"balance": new_balance}})
        else:
            new_balance = amount
            collection.insert_one({"_id": user_id, "balance": new_balance})

        await ctx.send(f"{ctx.author.mention}, you have been given {amount} money! Your new balance is {new_balance}.")


    @commands.hybrid_command(name="set_money", help="Sets the user's money to a specific amount")
    @commands.has_permissions(administrator=True)
    async def set_money(self, ctx, user: discord.User, amount: int):
        user_id = user.id
        collection.update_one({"_id": user_id}, {"$set": {"balance": amount}}, upsert=True)
        await ctx.send(f"{user.mention}'s balance has been set to {amount}.")


    @commands.hybrid_command(name="balance", help="Displays your current balance")
    async def balance(self, ctx):
        user_id = ctx.author.id
        user = collection.find_one({"_id": user_id})
        if user:
            balance = user["balance"]
        else:
            balance = 0
            collection.insert_one({"_id": user_id, "balance": balance})
        await ctx.send(f"{ctx.author.mention}, your current balance is {balance}.")

    @commands.hybrid_command(name="leaderboard", help="Displays the top 10 users with the most money")
    async def leaderboard(self, ctx):
        top_users = collection.find().sort("balance", -1).limit(10)  # Get top 10 users by balance
        leaderboard = "Leaderboard:\n"
        rank = 1
        for user in top_users:
            user_id = user["_id"]
            balance = user["balance"]
            user_mention = f"<@{user_id}>"  # Format user ID as a mention
            leaderboard += f"{rank}. {user_mention}: {balance} money\n"
            rank += 1
        if not leaderboard:
            leaderboard = "No users found in the leaderboard."
        await ctx.send(leaderboard)

async def setup(bot):
    await bot.add_cog(EconomyCog(bot))
