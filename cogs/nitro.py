from discord.ext import commands
class NitroCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.file_path = (f'{bot.script_path}/nitro.txt')

    @commands.hybrid_command(name="nitro")
    async def nitro(self, ctx):
        try:
            with open(self.file_path, "r") as file:
                lines = file.readlines()
            if lines:
                first_line = lines[0].strip()
                with open(self.file_path, "w") as file:
                    file.writelines(lines[1:])
                await ctx.send(first_line)
            else:
                await ctx.send("No Nitro codes left.")
        except FileNotFoundError:
            await ctx.send("The file does not exist.")
        except Exception as e:
            await ctx.send(f"An error occurred: {e}")

async def setup(bot):
    await bot.add_cog(NitroCog(bot))
