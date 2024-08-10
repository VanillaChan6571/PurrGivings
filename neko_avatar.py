import discord
from discord import app_commands
import aiohttp


async def set_avatar(bot, interaction: discord.Interaction, avatar_input: str = None):
    if interaction.user.id != bot.owner_id:
        await interaction.response.send_message("This command is only available to the bot owner.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    try:
        avatar_data = None

        if avatar_input:
            # If a URL is provided
            async with aiohttp.ClientSession() as session:
                async with session.get(avatar_input) as resp:
                    if resp.status != 200:
                        await interaction.followup.send("Failed to download the image from the provided URL.",
                                                        ephemeral=True)
                        return
                    avatar_data = await resp.read()
        elif interaction.message.attachments:
            # If an attachment is provided
            attachment = interaction.message.attachments[0]
            avatar_data = await attachment.read()
        else:
            await interaction.followup.send("Please provide either a URL or an image attachment.", ephemeral=True)
            return

        if avatar_data:
            await bot.user.edit(avatar=avatar_data)
            await interaction.followup.send("Avatar updated successfully!", ephemeral=True)
        else:
            await interaction.followup.send("Failed to get image data.", ephemeral=True)
    except discord.errors.HTTPException as e:
        await interaction.followup.send(f"Failed to update avatar: {str(e)}", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"An error occurred: {str(e)}", ephemeral=True)


def setup_avatar_commands(bot):
    @bot.tree.command(name="set_avatar", description="Set a new avatar for the bot (Owner Only)")
    @app_commands.describe(
        avatar_input="URL of the image or upload an image as an attachment"
    )
    async def set_avatar_command(interaction: discord.Interaction, avatar_input: str = None):
        await set_avatar(bot, interaction, avatar_input)