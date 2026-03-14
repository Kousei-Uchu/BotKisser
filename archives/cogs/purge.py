import discord
from discord import app_commands
from discord.ext import commands
import re

class PurgeGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="purge", description="Message purge commands")

    @app_commands.command(name="after", description="Delete all messages after the given message ID or link")
    @app_commands.describe(message_id_or_link="Message ID or link to delete after")
    async def purge_after(self, interaction: discord.Interaction, message_id_or_link: str):
        await interaction.response.defer(ephemeral=True)

        def extract_message_id(input_str: str) -> int | None:
            if input_str.isdigit():
                return int(input_str)
            match = re.match(r'https?://(?:canary\.|ptb\.)?discord(?:app)?\.com/channels/\d+/\d+/(\d+)', input_str)
            return int(match.group(1)) if match else None

        message_id = extract_message_id(message_id_or_link)
        if not message_id:
            return await interaction.followup.send("❌ Invalid message ID or link.")

        try:
            anchor = await interaction.channel.fetch_message(message_id)
        except discord.NotFound:
            return await interaction.followup.send(f"⚠️ Message ID `{message_id}` not found in this channel.")

        messages_to_delete = []
        async for msg in interaction.channel.history(after=anchor):
            if msg.id != interaction.id:  # avoid deleting the slash command message itself
                messages_to_delete.append(msg)

        deleted = 0
        try:
            while messages_to_delete:
                batch = messages_to_delete[:100]
                await interaction.channel.delete_messages(batch)
                deleted += len(batch)
                messages_to_delete = messages_to_delete[100:]
        except discord.HTTPException:
            # Fallback to manual delete for older messages
            for msg in messages_to_delete:
                try:
                    await msg.delete()
                    deleted += 1
                except:
                    continue

        await interaction.followup.send(embed=discord.Embed(
            title="Purge Complete",
            description=f"✅ Deleted **{deleted}** messages after ID `{message_id}`",
            color=discord.Color.red()
        ))

    @app_commands.command(name="between", description="Delete all messages between two message IDs or links")
    @app_commands.describe(
        message_id_1="First message ID or link",
        message_id_2="Second message ID or link"
    )
    async def purge_between(self, interaction: discord.Interaction, message_id_1: str, message_id_2: str):
        await interaction.response.defer(ephemeral=True)

        def extract_id(s: str) -> int | None:
            if s.isdigit():
                return int(s)
            match = re.match(r'https?://(?:canary\.|ptb\.)?discord(?:app)?\.com/channels/\d+/\d+/(\d+)', s)
            return int(match.group(1)) if match else None

        id1, id2 = extract_id(message_id_1), extract_id(message_id_2)
        if not id1 or not id2:
            return await interaction.followup.send("❌ Invalid message ID(s) or link(s).")

        start_id, end_id = sorted([id1, id2])
        try:
            start_msg = await interaction.channel.fetch_message(start_id)
            end_msg = await interaction.channel.fetch_message(end_id)
        except discord.NotFound:
            return await interaction.followup.send("⚠️ One or both message IDs were not found in this channel.")

        # Fetch messages between the two (exclusive)
        messages_to_delete = []
        async for msg in interaction.channel.history(after=start_msg, before=end_msg):
            if msg.id != interaction.id:
                messages_to_delete.append(msg)

        deleted = 0
        try:
            while messages_to_delete:
                batch = messages_to_delete[:100]
                await interaction.channel.delete_messages(batch)
                deleted += len(batch)
                messages_to_delete = messages_to_delete[100:]
        except discord.HTTPException:
            for msg in messages_to_delete:
                try:
                    await msg.delete()
                    deleted += 1
                except:
                    continue

        await interaction.followup.send(embed=discord.Embed(
            title="Purge Complete",
            description=f"✅ Deleted **{deleted}** messages between IDs `{start_id}` and `{end_id}`",
            color=discord.Color.orange()
        ))


        @app_commands.command(name="count", description="Delete a number of recent messages")
        @app_commands.describe(number="Number of messages to delete (max 100)")
        async def purge_count(self, interaction: discord.Interaction, number: app_commands.Range[int, 1, 100]):
            await interaction.response.defer(ephemeral=True)

            messages = []
            async for msg in interaction.channel.history(limit=number + 10):  # extra buffer to exclude this command
                if msg.id != interaction.id:
                    messages.append(msg)
                if len(messages) >= number:
                    break

            try:
                await interaction.channel.delete_messages(messages)
                deleted = len(messages)
            except discord.HTTPException:
                deleted = 0
                for msg in messages:
                    try:
                        await msg.delete()
                        deleted += 1
                    except:
                        continue

            await interaction.followup.send(embed=discord.Embed(
                title="Purge Complete",
                description=f"✅ Deleted **{deleted}** messages",
                color=discord.Color.blurple()
            ))

class Purge(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.tree.add_command(PurgeGroup())

async def setup(bot):
    await bot.add_cog(Purge(bot))
