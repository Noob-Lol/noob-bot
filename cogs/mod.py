import discord, datetime
from discord.ext import commands
from discord import app_commands

class ModCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="admin")
    @commands.has_permissions(administrator=True)
    async def admin_test(self,ctx):
        await ctx.send("You are an admin", ephemeral=True)

    @commands.hybrid_command(name="purge", help="Purges messages")
    @commands.has_permissions(manage_messages=True)
    @app_commands.describe(amount="The number of messages to purge")
    async def purge(self, ctx, amount: int):
        if ctx.interaction:
            await ctx.defer(ephemeral=True)
            await ctx.channel.purge(limit=amount)
            await ctx.send(f'Purged {amount} messages.', ephemeral=True)
        else:
            await ctx.defer()
            await ctx.message.delete()
            await ctx.channel.purge(limit=amount)
            await ctx.send(f'Purged {amount} messages.', delete_after=3)

    @commands.command(name='cleanup', help="Cleans up messages")
    @commands.has_permissions(manage_messages=True)
    @app_commands.describe(msg_limit="The number of messages from the bot to delete")
    async def cleanup(self, ctx, msg_limit: int):
        await ctx.message.delete()
        if msg_limit <= 0:
            await ctx.send("Please specify a number greater than 0.", delete_after=3)
            return
        elif msg_limit > 50:
            msg_limit = 50
        deleted = 0
        async for message in ctx.channel.history(limit=200):
            if message.author == self.bot.user:
                await message.delete()
                deleted += 1
                if deleted >= msg_limit:
                    break
        await ctx.send(f"Deleted {deleted} bot messages.", delete_after=5)

    @commands.hybrid_command(name="ban", help="Bans a user")
    @commands.has_permissions(ban_members=True)
    @app_commands.describe(member="The user to ban",reason="The reason for the ban")
    async def ban(self,ctx, member: discord.Member, *, reason=None):
        await member.ban(reason=reason)
        if not ctx.interaction:
            await ctx.message.delete()
        await ctx.send(f'**{member.name}** has been banned, Reason: {reason}')

    @commands.hybrid_command(name="unban", help="Unbans a user")
    @commands.has_permissions(ban_members=True)
    @app_commands.describe(member_id="The ID of the user to unban")
    async def unban(self,ctx, *, member_id):
        await ctx.guild.unban(discord.Object(id=member_id))
        if not ctx.interaction:
            await ctx.message.delete()
        await ctx.send(f"Unbaned <@{member_id}>")
    
    @commands.hybrid_command(name="kick", help="Kicks a user")
    @commands.has_permissions(ban_members=True)
    async def kick(self,ctx, member: discord.Member, *, reason=None):
        await member.kick(reason=reason)
        if not ctx.interaction:
            await ctx.message.delete()
        await ctx.send(f'**{member.name}** has been kicked, Reason: {reason}')

    @commands.hybrid_command(name="timeout", help="Timeouts a user")
    @commands.has_permissions(ban_members=True)
    async def timeout(self,ctx, member: discord.Member, time: int, *, reason=None):
        await member.timeout(datetime.timedelta(seconds=time), reason=reason)
        if not ctx.interaction:
            await ctx.message.delete()
        await ctx.send(f'**{member.name}** has been timed out, Reason: {reason}')

    @commands.hybrid_command(name="lock", help="Locks a channel")
    @commands.has_permissions(manage_channels=True)
    async def lock(self, ctx, channel: discord.TextChannel):
        await channel.set_permissions(ctx.guild.default_role, send_messages=False)
        if not ctx.interaction:
            await ctx.message.delete()
        await ctx.send(f"Locked {channel.mention}", delete_after=3)

    @commands.hybrid_command(name="unlock", help="Unlocks a channel")
    @commands.has_permissions(manage_channels=True)
    async def unlock(self, ctx, channel: discord.TextChannel):
        await channel.set_permissions(ctx.guild.default_role, send_messages=True)
        if not ctx.interaction:
            await ctx.message.delete()
        await ctx.send(f"Unlocked {channel.mention}", delete_after=3)

async def setup(bot):
    await bot.add_cog(ModCog(bot))
