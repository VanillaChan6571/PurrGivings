import os
import json
import random
import discord
from datetime import datetime, timedelta
import logging
import asyncio

logger = logging.getLogger('neko.status')


class StatusManager:
    def __init__(self, bot):
        self.bot = bot
        self.status_config = self.load_status_config()
        self.last_giveaway_end_time = None
        self.last_winner = None
        self.update_interval = 1 * 60  # 1 minute for testing

    def load_status_config(self):
        if os.path.exists('status.json'):
            with open('status.json', 'r') as f:
                return json.load(f)
        else:
            return {
                "no_giveaways": [
                    "Just Chilling like a cat",
                    "Meowing at life",
                    "Purrin Along.."
                ],
                "giveaway_active": [
                    "I see the Nekos are Giving a wish!",
                    "A Giveaway is in progress nya!",
                    "Nya! Something is cooking!~"
                ],
                "giveaway_ended": [
                    "Nya~! {username} won!",
                    "OwO! {username} wish has been granted!",
                    "Nekos has chosen {username}!"
                ]
            }

    async def update_status(self):
        try:
            giveaway_cog = self.bot.get_cog('GiveawayCog')
            active_giveaways = getattr(giveaway_cog, 'active_giveaways', {}) if giveaway_cog else {}

            logger.info(f"Updating status. Active giveaways: {bool(active_giveaways)}")
            logger.info(f"Last giveaway end time: {self.last_giveaway_end_time}")
            logger.info(f"Last winner: {self.last_winner}")

            if active_giveaways:
                status = random.choice(self.status_config["giveaway_active"])
                logger.info(f"Setting status to: {status} (online)")
                await self.bot.change_presence(activity=discord.Game(name=status), status=discord.Status.online)
            elif self.last_giveaway_end_time and (datetime.utcnow() - self.last_giveaway_end_time) < timedelta(
                    hours=48):
                status = random.choice(self.status_config["giveaway_ended"]).format(username=self.last_winner)
                logger.info(f"Setting status to: {status} (streaming)")
                await self.bot.change_presence(
                    activity=discord.Streaming(name=status, url="https://twitch.tv/vanillachanny"),
                    status=discord.Status.online)
            else:
                status = random.choice(self.status_config["no_giveaways"])
                logger.info(f"Setting status to: {status} (idle)")
                await self.bot.change_presence(activity=discord.Game(name=status), status=discord.Status.idle)
        except Exception as e:
            logger.error(f"Failed to update presence: {e}", exc_info=True)

    async def start_status_loop(self):
        await self.bot.wait_until_ready()
        logger.info("StatusManager: Bot is ready, starting status loop")
        while not self.bot.is_closed():
            await self.update_status()
            await asyncio.sleep(self.update_interval)

    def set_last_giveaway_info(self, end_time, winner):
        self.last_giveaway_end_time = end_time
        self.last_winner = winner


def setup(bot):
    return StatusManager(bot)