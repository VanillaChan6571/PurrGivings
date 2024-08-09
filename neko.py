import discord
from discord import app_commands
import random
import asyncio
import re
import sqlite3
import os
import json
import sys
import pytz
from datetime import datetime, timedelta
import logging
from aiohttp import web
from discord.ext import tasks

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('discord')
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

intents = discord.Intents.default()
intents.message_content = True

class GiveawayBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.active_giveaways = {}
        self.conn = sqlite3.connect('giveaways.db')
        self.create_tables()
        self.status_config = self.load_status_config()
        self.last_giveaway_end_time = None
        self.last_winner = None
        self.update_interval = 15 * 60  # 15 minutes in seconds

    async def on_ready(self):
        logger.info(f'{self.user} has connected to Discord!')
        if not os.path.exists('giveaways'):
            os.makedirs('giveaways')

    async def on_disconnect(self):
        logger.warning('Bot disconnected from Discord')

    async def on_resume(self):
        logger.info('Bot resumed connection to Discord')

    def create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS giveaways (
            id TEXT PRIMARY KEY,
            title TEXT,
            channel_id INTEGER,
            end_time TEXT,
            winners INTEGER,
            image TEXT
        )
        ''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS participants (
            giveaway_id TEXT,
            user_id INTEGER,
            FOREIGN KEY (giveaway_id) REFERENCES giveaways (id)
        )
        ''')
        self.conn.commit()

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

    async def setup_hook(self):
        await self.tree.sync()
        self.bg_task = self.loop.create_task(self.update_status_loop())

    async def update_status_loop(self):
        await self.wait_until_ready()
        while not self.is_closed():
            await self.update_status()
            if self.active_giveaways:
                await asyncio.sleep(5 * 60)  # Update every 5 minutes if a giveaway is active
            else:
                await asyncio.sleep(self.update_interval)

    async def update_status(self):
        try:
            logger.debug(f"Updating status. Active giveaways: {bool(self.active_giveaways)}")
            logger.debug(f"Last giveaway end time: {self.last_giveaway_end_time}")
            logger.debug(f"Last winner: {self.last_winner}")

            if self.active_giveaways:
                status = random.choice(self.status_config["giveaway_active"])
                logger.info(f"Setting status to: {status} (online)")
                await self.change_presence(activity=discord.Game(name=status), status=discord.Status.online)
            elif self.last_giveaway_end_time and (datetime.utcnow() - self.last_giveaway_end_time) < timedelta(
                    hours=48):
                status = random.choice(self.status_config["giveaway_ended"]).format(username=self.last_winner)
                logger.info(f"Setting status to: {status} (streaming)")
                await self.change_presence(
                    activity=discord.Streaming(name=status, url="https://twitch.tv/vanillachanny"),
                    status=discord.Status.online)
            else:
                status = random.choice(self.status_config["no_giveaways"])
                logger.info(f"Setting status to: {status} (idle)")
                await self.change_presence(activity=discord.Game(name=status), status=discord.Status.idle)
        except discord.errors.HTTPException as e:
            logger.error(f"Failed to update presence: {e}")

    @discord.app_commands.command(name="set_status", description="Manually set the bot's status")
    @discord.app_commands.checks.has_permissions(administrator=True)
    async def set_status(self, interaction: discord.Interaction, status_type: str):
        if status_type not in self.status_config:
            await interaction.response.send_message(f"Invalid status type. Choose from: {', '.join(self.status_config.keys())}", ephemeral=True)
            return

        await self.update_status()
        await interaction.response.send_message(f"Status updated to '{status_type}' type.", ephemeral=True)

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
                status_field = next((field for field in embed.fields if field.name == "Status"), None)
                if not status_field:
                    embed.add_field(name="Status", value="ENDED", inline=False)
                for i, field in enumerate(embed.fields):
                    if field.name == "Time Remaining":
                        embed.set_field_at(i, name="Time Remaining", value="ENDED")
                        break
                await message.edit(embed=embed, view=None)  # Remove the button
                await end_giveaway(giveaway_id)
                self.update_time_remaining.cancel()
                return

            days, remainder = divmod(time_remaining.total_seconds(), 86400)
            hours, remainder = divmod(remainder, 3600)
            minutes, seconds = divmod(remainder, 60)
            time_str = f"{int(days)}d {int(hours)}h {int(minutes)}m {int(seconds)}s"

            embed = message.embeds[0]
            for i, field in enumerate(embed.fields):
                if field.name == "Time Remaining":
                    embed.set_field_at(i, name="Time Remaining", value=time_str)
                    break

            await message.edit(embed=embed)
        except Exception as e:
            logger.error(f"Error in update_time_remaining for giveaway {giveaway_id}: {str(e)}")
            self.update_time_remaining.cancel()

bot = GiveawayBot()

def generate_giveaway_id():
    year = datetime.now().year
    cursor = bot.conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM giveaways WHERE id LIKE ?", (f'%-{year}',))
    count = cursor.fetchone()[0] + 1
    return f'N{count:03d}-{year}'

def parse_time(time_str):
    total_seconds = 0
    time_units = {'w': 7 * 24 * 60 * 60, 'd': 24 * 60 * 60, 'h': 60 * 60, 'm': 60, 's': 1}
    pattern = re.compile(r'(\d+)([wdhms])')

    for value, unit in pattern.findall(time_str):
        total_seconds += int(value) * time_units[unit]

    return timedelta(seconds=total_seconds)

class GiveawayView(discord.ui.View):
    def __init__(self, giveaway_id):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id

    @discord.ui.button(label="Pray for Gods of Nekos", style=discord.ButtonStyle.primary, emoji="<:Peek:1222014873735790644>")
    async def enter_giveaway(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        cursor = bot.conn.cursor()
        cursor.execute("SELECT * FROM participants WHERE giveaway_id = ? AND user_id = ?", (self.giveaway_id, user_id))
        if cursor.fetchone() is None:
            cursor.execute("INSERT INTO participants (giveaway_id, user_id) VALUES (?, ?)", (self.giveaway_id, user_id))
            bot.conn.commit()
            await interaction.response.send_message("You've been entered into the giveaway!", ephemeral=True)
        else:
            await interaction.response.send_message("You're already in the giveaway!", ephemeral=True)

@bot.tree.command(name="create", description="Create a new giveaway")
@app_commands.describe(
    title="Title of the giveaway",
    length="Duration of the giveaway (e.g., 3w 4d 6h 30m 10s)",
    channel="Channel to host the giveaway",
    winners="Number of winners (default: 1)",
    image="URL of the image for the embed (optional)"
)
async def create_giveaway(
        interaction: discord.Interaction,
        title: str,
        length: str,
        channel: discord.TextChannel,
        winners: int = 1,
        image: str = None
):
    await interaction.response.defer(ephemeral=True)
    await create_giveaway_task(bot, interaction, title, length, channel, winners, image)

async def create_giveaway_task(bot, interaction, title, length, channel, winners, image):
    color_hex = "#3EB489"  # Mint green
    duration = parse_time(length)
    start_time = datetime.now(pytz.UTC)
    end_time = start_time + duration
    giveaway_id = generate_giveaway_id()

    # Convert to Unix timestamps
    start_timestamp = int(start_time.timestamp())
    end_timestamp = int(end_time.timestamp())

    embed = discord.Embed(title=title, description="Pray for Gods of Nekos", color=int(color_hex.lstrip('#'), 16))
    embed.add_field(name="Giveaway ID", value=giveaway_id)
    embed.add_field(name="Start Time", value=f"<t:{start_timestamp}:F>")
    embed.add_field(name="End Time", value=f"<t:{end_timestamp}:F>")
    embed.add_field(name="Duration", value=str(duration))
    embed.add_field(name="Ends", value=f"<t:{end_timestamp}:R>")
    embed.add_field(name="How Many Can Win?", value=str(winners))
    embed.add_field(name="Time Remaining", value="Calculating...")

    if image:
        embed.set_image(url=image)

    view = GiveawayView(giveaway_id)
    message = await channel.send(embed=embed, view=view)

    cursor = bot.conn.cursor()
    cursor.execute('''
    INSERT INTO giveaways (id, title, channel_id, end_time, winners, image)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', (giveaway_id, title, channel.id, end_time.isoformat(), winners, image))
    bot.conn.commit()

    bot.active_giveaways[giveaway_id] = {
        'message': message,
        'end_time': end_time,
        'winners': winners,
        'view': view
    }

    await interaction.followup.send(f"Giveaway {giveaway_id} created in {channel.mention}!", ephemeral=True)

    # Update the bot's status when a giveaway starts
    await bot.update_status()

    # Start the background task to update the time remaining
    bot.update_time_remaining.start(giveaway_id, message, end_time)


async def end_giveaway(giveaway_id):
    if giveaway_id in bot.active_giveaways:
        giveaway = bot.active_giveaways[giveaway_id]
        cursor = bot.conn.cursor()
        cursor.execute("SELECT user_id FROM participants WHERE giveaway_id = ?", (giveaway_id,))
        participants = [row[0] for row in cursor.fetchall()]

        if participants:
            winners = random.sample(participants, min(giveaway['winners'], len(participants)))
            winner_mentions = ', '.join(f"<@{winner}>" for winner in winners)
            await giveaway['message'].reply(f"Congratulations {winner_mentions}! You won the giveaway!")

            winner_user = bot.get_user(winners[0])
            if winner_user:
                bot.last_winner = winner_user.name
            else:
                bot.last_winner = f"Unknown (ID: {winners[0]})"
        else:
            await giveaway['message'].reply("No one entered the giveaway.")
            bot.last_winner = "Nobody"

        # Update the giveaway message
        embed = giveaway['message'].embeds[0]
        status_field = next((field for field in embed.fields if field.name == "Status"), None)
        if not status_field:
            embed.add_field(name="Status", value="ENDED", inline=False)
        for i, field in enumerate(embed.fields):
            if field.name == "Time Remaining" and field.value != "ENDED":
                embed.set_field_at(i, name="Time Remaining", value="ENDED")
                break
        await giveaway['message'].edit(embed=embed, view=None)  # Remove the button

        # Archive the giveaway
        cursor.execute("SELECT * FROM giveaways WHERE id = ?", (giveaway_id,))
        giveaway_data = cursor.fetchone()
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
        cursor.execute("DELETE FROM giveaways WHERE id = ?", (giveaway_id,))
        cursor.execute("DELETE FROM participants WHERE giveaway_id = ?", (giveaway_id,))
        bot.conn.commit()

        del bot.active_giveaways[giveaway_id]

        bot.last_giveaway_end_time = datetime.utcnow()

        # Update the bot's status when a giveaway ends, but only if there are no more active giveaways
        if not bot.active_giveaways:
            await bot.update_status()

    else:
        print(f"Warning: Attempted to end non-existent giveaway with ID {giveaway_id}")

@bot.tree.command(name="giveaway-view", description="View participants of a giveaway")
@app_commands.describe(giveaway_id="ID of the giveaway to view")
async def view_giveaway(interaction: discord.Interaction, giveaway_id: str):
    cursor = bot.conn.cursor()
    cursor.execute("SELECT * FROM giveaways WHERE id = ?", (giveaway_id,))
    giveaway = cursor.fetchone()

    if giveaway is None:
        await interaction.response.send_message("Giveaway not found.", ephemeral=True)
        return

    cursor.execute("SELECT user_id FROM participants WHERE giveaway_id = ?", (giveaway_id,))
    participants = [row[0] for row in cursor.fetchall()]

    embed = discord.Embed(title=f"Giveaway {giveaway_id}", color=int("#3EB489".lstrip('#'), 16))
    embed.add_field(name="Title", value=giveaway[1])
    embed.add_field(name="End Time", value=giveaway[3])
    embed.add_field(name="Winners", value=giveaway[4])
    embed.add_field(name="Participants", value=len(participants))

    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="giveaway-list", description="List all giveaways")
async def list_giveaways(interaction: discord.Interaction):
    cursor = bot.conn.cursor()
    cursor.execute("SELECT id, title, end_time FROM giveaways ORDER BY end_time DESC")
    giveaways = cursor.fetchall()

    if not giveaways:
        await interaction.response.send_message("No giveaways found.", ephemeral=True)
        return

    embed = discord.Embed(title="Giveaway List", color=int("#3EB489".lstrip('#'), 16))
    for giveaway in giveaways:
        embed.add_field(name=f"ID: {giveaway[0]}", value=f"Title: {giveaway[1]}\nEnds: {giveaway[2]}", inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)

def get_token():
    config_file = 'bot-config.json'
    if os.path.exists(config_file):
        with open(config_file, 'r') as f:
            config = json.load(f)
            return config.get('token')
    else:
        while True:
            sys.stdout.write("Please enter your Discord bot token: ")
            sys.stdout.flush()
            token = input().strip()

            if len(token) < 50:
                print("Error: Token is too short. Discord bot tokens are usually 50+ characters long. Please try again.")
            else:
                with open(config_file, 'w') as f:
                    json.dump({'token': token}, f)
                print(f"Token saved to {config_file}")
                return token

async def keep_alive(request):
    return web.Response(text="I'm alive!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", keep_alive)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, 'localhost', 8080)
    await site.start()
    return runner

async def main():
    token = get_token()
    if not token:
        raise ValueError("No token provided. Please run the script again and enter your bot token.")

    web_runner = await start_web_server()

    try:
        await bot.start(token)
    except KeyboardInterrupt:
        await bot.close()
    finally:
        await web_runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())