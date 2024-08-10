import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import pytz
from datetime import datetime
import logging
import random
from neko_database import get_participants, add_participant, get_giveaway, add_giveaway, delete_giveaway
from neko_utils import parse_time, generate_giveaway_id, format_time_remaining

logger = logging.getLogger('neko.giveaway')


class GiveawayCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_giveaways = {}

    async def cog_load(self):
        self.reload_active_giveaways.start()

    @tasks.loop(minutes=1)
    async def update_time_remaining(self, giveaway_id, message, end_time):
        try:
            if giveaway_id not in self.active_giveaways:
                self.update_time_remaining.cancel()
                return

            now = datetime.now(pytz.UTC)
            time_remaining = end_time - now

            if time_remaining.total_seconds() <= 0:
                embed = message.embeds[0]
                embed.add_field(name="Status", value="ENDED", inline=False)
                for i, field in enumerate(embed.fields):
                    if field.name == "Time Remaining":
                        embed.set_field_at(i, name="Time Remaining", value="ENDED")
                        break
                await message.edit(embed=embed, view=None)  # Remove the button
                await self.end_giveaway(giveaway_id)
                self.update_time_remaining.cancel()
                return

            time_str = format_time_remaining(time_remaining)

            embed = message.embeds[0]
            for i, field in enumerate(embed.fields):
                if field.name == "Time Remaining":
                    embed.set_field_at(i, name="Time Remaining", value=time_str)
                    break

            await message.edit(embed=embed)
        except Exception as e:
            logger.error(f"Error in update_time_remaining for giveaway {giveaway_id}: {str(e)}")
            self.update_time_remaining.cancel()

    @tasks.loop(minutes=5)
    async def reload_active_giveaways(self):
        logger.info("Reloading active giveaways")
        cursor = self.bot.conn.cursor()
        cursor.execute("SELECT id, channel_id, end_time, winners FROM giveaways WHERE end_time > ?",
                       (datetime.now(pytz.UTC).isoformat(),))
        active_giveaways = cursor.fetchall()

        for giveaway in active_giveaways:
            giveaway_id, channel_id, end_time, winners = giveaway
            channel = self.bot.get_channel(channel_id)
            if channel:
                try:
                    message = await channel.fetch_message(int(giveaway_id))
                    end_time = datetime.fromisoformat(end_time)
                    view = GiveawayView(giveaway_id, self)
                    self.active_giveaways[giveaway_id] = {
                        'message': message,
                        'end_time': end_time,
                        'winners': winners,
                        'view': view
                    }
                    self.update_time_remaining.start(giveaway_id, message, end_time)
                    logger.info(f"Reloaded giveaway: {giveaway_id}")
                except discord.errors.NotFound:
                    logger.warning(f"Could not find message for giveaway {giveaway_id}. Removing from database.")
                    delete_giveaway(self.bot.conn, giveaway_id)
            else:
                logger.warning(f"Could not find channel for giveaway {giveaway_id}. Removing from database.")
                delete_giveaway(self.bot.conn, giveaway_id)

    @app_commands.command(name="create", description="Create a new giveaway")
    @app_commands.describe(
        title="Title of the giveaway",
        length="Duration of the giveaway (e.g., 3w 4d 6h 30m 10s)",
        channel="Channel to host the giveaway",
        winners="Number of winners (default: 1)",
        image="URL of the image for the embed (optional)"
    )
    async def create_giveaway(
            self, interaction: discord.Interaction, title: str, length: str,
            channel: discord.TextChannel, winners: int = 1, image: str = None
    ):
        await interaction.response.defer(ephemeral=True)
        await self.create_giveaway_task(interaction, title, length, channel, winners, image)

    @app_commands.command(name="giveaway-view", description="View participants of a giveaway")
    @app_commands.describe(giveaway_id="ID of the giveaway to view")
    async def view_giveaway(self, interaction: discord.Interaction, giveaway_id: str):
        giveaway = get_giveaway(self.bot.conn, giveaway_id)

        if giveaway is None:
            await interaction.response.send_message("Giveaway not found.", ephemeral=True)
            return

        participants = get_participants(self.bot.conn, giveaway_id)

        embed = discord.Embed(title=f"Giveaway {giveaway_id}", color=int("#3EB489".lstrip('#'), 16))
        embed.add_field(name="Title", value=giveaway[1])
        embed.add_field(name="End Time", value=giveaway[3])
        embed.add_field(name="Winners", value=giveaway[4])
        embed.add_field(name="Participants", value=len(participants))

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="giveaway-list", description="List all giveaways")
    async def list_giveaways(self, interaction: discord.Interaction):
        cursor = self.bot.conn.cursor()
        cursor.execute("SELECT id, title, end_time FROM giveaways ORDER BY end_time DESC")
        giveaways = cursor.fetchall()

        if not giveaways:
            await interaction.response.send_message("No giveaways found.", ephemeral=True)
            return

        embed = discord.Embed(title="Giveaway List", color=int("#3EB489".lstrip('#'), 16))
        for giveaway in giveaways:
            embed.add_field(name=f"ID: {giveaway[0]}", value=f"Title: {giveaway[1]}\nEnds: {giveaway[2]}", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def create_giveaway_task(self, interaction, title, length, channel, winners, image):
        logger.info(f"Creating new giveaway: {title}")
        color_hex = "#3EB489"  # Mint green
        duration = parse_time(length)
        start_time = datetime.now(pytz.UTC)
        end_time = start_time + duration
        giveaway_id = generate_giveaway_id(self.bot.conn)

        # Convert to Unix timestamps
        start_timestamp = int(start_time.timestamp())
        end_timestamp = int(end_time.timestamp())

        embed = discord.Embed(title=title, description="React to enter!", color=int(color_hex.lstrip('#'), 16))
        embed.add_field(name="Giveaway ID", value=giveaway_id)
        embed.add_field(name="Start Time", value=f"<t:{start_timestamp}:F>")
        embed.add_field(name="End Time", value=f"<t:{end_timestamp}:F>")
        embed.add_field(name="Duration", value=str(duration))
        embed.add_field(name="Ends", value=f"<t:{end_timestamp}:R>")
        embed.add_field(name="Winners", value=str(winners))
        embed.add_field(name="Time Remaining", value="Calculating...")

        if image:
            embed.set_image(url=image)

        view = GiveawayView(giveaway_id, self)
        message = await channel.send(embed=embed, view=view)

        add_giveaway(self.bot.conn, giveaway_id, title, channel.id, end_time, winners, image)

        self.active_giveaways[giveaway_id] = {
            'message': message,
            'end_time': end_time,
            'winners': winners,
            'view': view
        }

        await interaction.followup.send(f"Giveaway {giveaway_id} created in {channel.mention}!", ephemeral=True)

        # Update the bot's status when a giveaway starts
        if self.bot.status_manager:
            await self.bot.status_manager.update_status()
        else:
            logger.error("Status manager is not initialized")

        # Start the background task to update the time remaining
        self.update_time_remaining.start(giveaway_id, message, end_time)

    async def end_giveaway(self, giveaway_id):
        logger.info(f"Ending giveaway: {giveaway_id}")
        if giveaway_id in self.active_giveaways:
            giveaway = self.active_giveaways[giveaway_id]
            participants = get_participants(self.bot.conn, giveaway_id)

            if participants:
                winners = random.sample(participants, min(giveaway['winners'], len(participants)))
                winner_mentions = ', '.join(f"<@{winner}>" for winner in winners)
                await giveaway['message'].reply(f"Congratulations {winner_mentions}! You won the giveaway!")

                winner_user = self.bot.get_user(winners[0])
                if winner_user:
                    winner_name = winner_user.name
                else:
                    winner_name = f"Unknown (ID: {winners[0]})"
            else:
                await giveaway['message'].reply("No one entered the giveaway.")
                winner_name = "Nobody"

            # Update the giveaway message
            embed = giveaway['message'].embeds[0]
            embed.add_field(name="Status", value="ENDED", inline=False)
            for i, field in enumerate(embed.fields):
                if field.name == "Time Remaining" and field.value != "ENDED":
                    embed.set_field_at(i, name="Time Remaining", value="ENDED")
                    break
            await giveaway['message'].edit(embed=embed, view=None)  # Remove the button

            # Archive the giveaway
            giveaway_data = get_giveaway(self.bot.conn, giveaway_id)
            if giveaway_data:
                with open(f"giveaways/{giveaway_id}.txt", "w") as f:
                    f.write(f"Giveaway ID: {giveaway_id}\n")
                    f.write(f"Title: {giveaway_data[1]}\n")
                    f.write(f"Channel ID: {giveaway_data[2]}\n")
                    f.write(f"End Time: {giveaway_data[3]}\n")
                    f.write(f"Winners: {giveaway_data[4]}\n")
                    f.write(f"Image: {giveaway_data[5]}\n")
                    f.write("Participants:\n")
                    for participant in participants:
                        f.write(f"- {participant}\n")
                    f.write(f"Winners: {', '.join(map(str, winners))}\n")

            # Remove the giveaway from the database
            delete_giveaway(self.bot.conn, giveaway_id)

            del self.active_giveaways[giveaway_id]

            # Update the status manager with the last giveaway info
            if self.bot.status_manager:
                self.bot.status_manager.set_last_giveaway_info(datetime.utcnow(), winner_name)
                await self.bot.status_manager.update_status()
            else:
                logger.error("Status manager is not initialized")

        else:
            logger.warning(f"Attempted to end non-existent giveaway with ID {giveaway_id}")


class GiveawayView(discord.ui.View):
    def __init__(self, giveaway_id, cog):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id
        self.cog = cog

    @discord.ui.button(label="Enter Giveaway", style=discord.ButtonStyle.primary, emoji="🎉", custom_id="enter_giveaway")
    async def enter_giveaway(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Get the cog if it's not set (for persistent views)
        if self.cog is None:
            self.cog = interaction.client.get_cog('GiveawayCog')

        # Get the giveaway_id from the message if it's not set
        if self.giveaway_id is None:
            for embed in interaction.message.embeds:
                for field in embed.fields:
                    if field.name == "Giveaway ID":
                        self.giveaway_id = field.value
                        break
                if self.giveaway_id:
                    break

        user_id = interaction.user.id
        cursor = self.cog.bot.conn.cursor()
        cursor.execute("SELECT * FROM participants WHERE giveaway_id = ? AND user_id = ?", (self.giveaway_id, user_id))
        if cursor.fetchone() is None:
            add_participant(self.cog.bot.conn, self.giveaway_id, user_id)
            await interaction.response.send_message("You've been entered into the giveaway!", ephemeral=True)
        else:
            await interaction.response.send_message("You're already in the giveaway!", ephemeral=True)


async def setup(bot):
    await bot.add_cog(GiveawayCog(bot))