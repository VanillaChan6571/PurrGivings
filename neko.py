import discord
from discord.ext import commands
import asyncio
import logging
from neko_giveaway import GiveawayCog
from neko_database import create_connection, create_tables
from neko_utils import get_token
from neko_status import StatusManager

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')
logger = logging.getLogger('neko')


class NekoBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='!', intents=intents)
        self.conn = None
        self.status_manager = None

    async def setup_hook(self):
        self.conn = create_connection("giveaways.db")
        create_tables(self.conn)
        self.status_manager = StatusManager(self)
        await self.add_cog(GiveawayCog(self))
        await self.tree.sync()
        logger.info("Bot setup completed")

    async def on_ready(self):
        logger.info(f'Logged in as {self.user} (ID: {self.user.id})')
        self.loop.create_task(self.status_manager.start_status_loop())


bot = NekoBot()


@bot.tree.command(name="sync", description="Manually sync commands (Owner only)")
async def sync(interaction: discord.Interaction):
    if interaction.user.id != bot.owner_id:
        await interaction.response.send_message("Only the bot owner can use this command.", ephemeral=True)
        return
    try:
        synced = await bot.tree.sync()
        await interaction.response.send_message(f"Synced {len(synced)} commands.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Failed to sync commands: {e}", ephemeral=True)


@bot.tree.command(name="debug", description="Toggle debug mode (Owner only)")
async def debug_mode(interaction: discord.Interaction):
    if interaction.user.id != bot.owner_id:
        await interaction.response.send_message("Only the bot owner can use this command.", ephemeral=True)
        return

    if logging.getLogger().level == logging.DEBUG:
        logging.getLogger().setLevel(logging.INFO)
        await interaction.response.send_message("Debug mode disabled.", ephemeral=True)
    else:
        logging.getLogger().setLevel(logging.DEBUG)
        await interaction.response.send_message("Debug mode enabled. Check console for detailed logs.", ephemeral=True)


async def main():
    token = get_token()
    if not token:
        raise ValueError("No token provided. Please run the script again and enter your bot token.")

    async with bot:
        await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())