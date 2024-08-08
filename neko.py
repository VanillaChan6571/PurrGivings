import discord
from discord import app_commands
import random
import asyncio
from datetime import datetime, timedelta
import re
import sqlite3
import os
import json
import sys
import pytz
from datetime import datetime, timedelta

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

    async def setup_hook(self):
        await self.tree.sync()
        self.bg_task = self.loop.create_task(self.update_status())

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
                    "Nekos has choosen {username}!"
                ]
            }

    async def update_status(self):
        await self.wait_until_ready()
        while not self.is_closed():
            if self.active_giveaways:
                status = random.choice(self.status_config["giveaway_active"])
                await self.change_presence(activity=discord.Game(name=status), status=discord.Status.online)
            elif self.last_giveaway_end_time and (datetime.utcnow() - self.last_giveaway_end_time) < timedelta(hours=48):
                status = random.choice(self.status_config["giveaway_ended"]).format(username=self.last_winner)
                await self.change_presence(activity=discord.Streaming(name=status, url="https://twitch.tv/vanillachanny"), status=discord.Status.streaming)
            else:
                status = random.choice(self.status_config["no_giveaways"])
                await self.change_presence(activity=discord.Game(name=status), status=discord.Status.idle)
            await asyncio.sleep(300)  # Update every 5 minutes

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

    @discord.ui.button(label="Enter Giveaway", style=discord.ButtonStyle.primary, emoji="🎉")
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

    embed = discord.Embed(title=title, description="React with 🎉 to enter!", color=int(color_hex.lstrip('#'), 16))
    embed.add_field(name="Giveaway ID", value=giveaway_id)
    embed.add_field(name="Start Time", value=f"<t:{start_timestamp}:F>")
    embed.add_field(name="End Time", value=f"<t:{end_timestamp}:F>")
    embed.add_field(name="Duration", value=str(duration))
    embed.add_field(name="Ends", value=f"<t:{end_timestamp}:R>")
    embed.add_field(name="Winners", value=str(winners))

    # Add a field to show the time remaining in a user-friendly format
    time_remaining = end_time - start_time
    days, remainder = divmod(time_remaining.total_seconds(), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    time_str = f"{int(days)}d {int(hours)}h {int(minutes)}m {int(seconds)}s"
    embed.add_field(name="Time Remaining", value=time_str)

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

    # Schedule the giveaway to end
    bot.loop.create_task(schedule_giveaway_end(giveaway_id, duration))
async def schedule_giveaway_end(giveaway_id, duration):
    print(f"Debug: Scheduling giveaway end for {giveaway_id}")
    print(f"Debug: Duration: {duration}")
    await asyncio.sleep(duration.total_seconds())
    print(f"Debug: Ending giveaway {giveaway_id}")
    await end_giveaway(giveaway_id)

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
            bot.last_winner = bot.get_user(winners[0]).name if winners else "Unknown"
        else:
            await giveaway['message'].reply("No one entered the giveaway.")
            bot.last_winner = "Nobody"

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

        if not bot.active_giveaways:
            bot.last_giveaway_end_time = datetime.utcnow()

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

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    if not os.path.exists('giveaways'):
        os.makedirs('giveaways')

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

if __name__ == "__main__":
    token = get_token()
    if not token:
        raise ValueError("No token provided. Please run the script again and enter your bot token.")
    bot.run(token)