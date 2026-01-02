import discord
from discord.ext import commands
import asyncio
import logging
from neko_giveaway import GiveawayCog
from neko_database import create_connection, create_tables
from neko_utils import get_token
from neko_status import StatusManager
from colorama import Fore, Back, Style, init

# Initialize colorama for cross-platform color support
init(autoreset=True)

# Custom colored formatter
class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors for different log levels."""

    COLORS = {
        'DEBUG': Fore.CYAN,
        'INFO': Fore.GREEN,
        'WARNING': Fore.YELLOW,
        'ERROR': Fore.RED,
        'CRITICAL': Fore.RED + Back.WHITE + Style.BRIGHT,
    }

    ICONS = {
        'DEBUG': '🔍',
        'INFO': '✅',
        'WARNING': '⚠️',
        'ERROR': '❌',
        'CRITICAL': '🚨',
    }

    def format(self, record):
        # Color the level name
        levelname = record.levelname
        if levelname in self.COLORS:
            record.levelname = f"{self.COLORS[levelname]}{self.ICONS.get(levelname, '')} {levelname}{Style.RESET_ALL}"

        # Color the logger name
        record.name = f"{Fore.MAGENTA}{record.name}{Style.RESET_ALL}"

        # Color timestamps
        if hasattr(record, 'asctime'):
            record.asctime = f"{Fore.BLUE}{record.asctime}{Style.RESET_ALL}"

        return super().format(record)

# Set up logging with colors
handler = logging.StreamHandler()
handler.setFormatter(ColoredFormatter('%(asctime)s │ %(levelname)s │ %(name)s │ %(message)s', datefmt='%H:%M:%S'))

# Configure root logger
logging.basicConfig(level=logging.INFO, handlers=[handler])

# Set discord.py logging to WARNING to reduce noise
logging.getLogger('discord').setLevel(logging.WARNING)
logging.getLogger('discord.http').setLevel(logging.WARNING)
logging.getLogger('discord.gateway').setLevel(logging.WARNING)

logger = logging.getLogger('neko')
logger.setLevel(logging.INFO)

# Print startup banner
print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
print(f"{Fore.GREEN}{Style.BRIGHT}           🐱 PurrGivings Bot Starting... 🎁{Style.RESET_ALL}")
print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")


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
        print(f"\n{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.GREEN}{Style.BRIGHT}✨ Bot Connected Successfully!{Style.RESET_ALL}")
        print(f"{Fore.CYAN}   Username: {Fore.WHITE}{self.user}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}   User ID:  {Fore.WHITE}{self.user.id}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}   Servers:  {Fore.WHITE}{len(self.guilds)}{Style.RESET_ALL}")
        print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}\n")
        logger.info(f'Ready! Logged in as {self.user} (ID: {self.user.id})')
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