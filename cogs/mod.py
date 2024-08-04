import discord
from discord.ext import commands

class ModCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="admin")
    @commands.has_permissions(administrator=True)
    async def admin_test(self,ctx):
        await ctx.send("You are an admin", ephemeral=True)

    @commands.hybrid_command(name="purge", help="Purges messages")
    @commands.has_permissions(manage_messages=True)
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

    @commands.hybrid_command(name="ban", with_app_command = True, help="Bans a user")
    @commands.has_permissions(ban_members=True)
    async def ban(self,ctx, member: discord.Member, *, reason=None):
        await member.ban(reason=reason)
        if not ctx.interaction:
            await ctx.message.delete()
        await ctx.send(f'**{member.name}** has been banned, Reason: {reason}')

    @commands.hybrid_command(name="unban", help="Unbans a user")
    @commands.has_permissions(ban_members=True)
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

async def setup(bot):
    await bot.add_cog(ModCog(bot))
