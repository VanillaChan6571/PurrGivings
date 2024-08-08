import discord
from discord import app_commands
import random
import asyncio
from datetime import datetime, timedelta
import re
import sqlite3
import os

intents = discord.Intents.default()
intents.message_content = True


class GiveawayBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.active_giveaways = {}
        self.conn = sqlite3.connect('giveaways.db')
        self.create_tables()

    async def setup_hook(self):
        await self.tree.sync()

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
    color_hex = "#3EB489"  # Mint green
    duration = parse_time(length)
    end_time = datetime.utcnow() + duration
    giveaway_id = generate_giveaway_id()

    embed = discord.Embed(title=title, description="React with 🎉 to enter!", color=int(color_hex.lstrip('#'), 16))
    embed.add_field(name="Giveaway ID", value=giveaway_id)
    embed.add_field(name="End Time", value=f"<t:{int(end_time.timestamp())}:R>")
    embed.add_field(name="Winners", value=str(winners))
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

    await interaction.response.send_message(f"Giveaway {giveaway_id} created in {channel.mention}!", ephemeral=True)

    await asyncio.sleep(duration.total_seconds())
    await end_giveaway(giveaway_id)


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
        else:
            await giveaway['message'].reply("No one entered the giveaway.")

        # Archive the giveaway
        cursor.execute("SELECT * FROM giveaways WHERE id = ?", (giveaway_id,))
        giveaway_data = cursor.fetchone()
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


@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    if not os.path.exists('giveaways'):
        os.makedirs('giveaways')


# Replace 'YOUR_BOT_TOKEN' with your actual bot token
bot.run('YOUR_BOT_TOKEN')