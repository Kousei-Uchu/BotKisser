import json
import os
import discord
from discord import Reaction, Member
from discord.ext import commands
from utils.config_manager import ConfigManager  # Assuming your structure
from utils.data_handler import DataHandler
class Fireboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data_handler = DataHandler('data/fireboard.json')
        self.config_manager = ConfigManager('config.json')
        self.config = self.config_manager.load_config()
        self.fire_config = self.config.get('fireboard', {})
        self.posted_messages = self.load_fireboard_data()
    async def fireboard_react_add(self, reaction: Reaction, user: Member):
        try:
            if user.bot:
                return
            if reaction.emoji != '🔥':
                return
            message = reaction.message
            guild = message.guild
            fireboard_channel_id = self.fire_config.get('channel_id')
            fire_threshold = self.fire_config.get('required_reacts', 5)
            fireboard_channel = await self.bot.fetch_channel(fireboard_channel_id)
            if not fireboard_channel:
                print("Fireboard channel not found!")
                return
            # Helper to check if reacting to a repost
            def find_original_message_id(repost_message_id):
                for orig_id, data in self.posted_messages.items():
                    if isinstance(data, dict) and 'repost_id' in data and str(data['repost_id']) == str(repost_message_id):
                        return int(orig_id)
                return None
            original_message_id = find_original_message_id(message.id)
            if original_message_id:
                # Fetch original message from correct original channel
                original_channel_id = self.posted_messages[str(original_message_id)].get('channel_id')
                original_channel = await self.bot.fetch_channel(original_channel_id)
                original_message = await original_channel.fetch_message(original_message_id)
                # Collect reactors from both original and repost
                unique_fire_reactor_ids = set()
                # Reactors from original message
                for react in original_message.reactions:
                    if react.emoji == '🔥':
                        async for reactor in react.users():
                            if not reactor.bot and reactor.id != original_message.author.id:
                                unique_fire_reactor_ids.add(reactor.id)
                # Reactors from reposted message
                for react in message.reactions:
                    if react.emoji == '🔥':
                        async for reactor in react.users():
                            if not reactor.bot and reactor.id != original_message.author.id:
                                unique_fire_reactor_ids.add(reactor.id)
                total_fire_count = len(unique_fire_reactor_ids)
                # Edit repost
                embed = discord.Embed(
                    title=f"🔥 {total_fire_count} Fires!",
                    description=message.content or "*No content*",
                    color=discord.Color.orange()
                )
                embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
                embed.add_field(name="Jump to Message", value=f"[Click Here]({message.jump_url})", inline=False)
                embed.set_footer(text=f"Posted in #{message.channel.name}")
                await message.edit(embed=embed)
            else:
                # Count reactors on the original message only
                fire_reactors = []
                for react in message.reactions:
                    if react.emoji == '🔥':
                        async for reactor in react.users():
                            if not reactor.bot and reactor.id != message.author.id:
                                fire_reactors.append(reactor)
                fire_count = len(set(fire_reactors))
                if str(message.id) in self.posted_messages:
                    # Already posted before, update repost
                    repost_info = self.posted_messages.get(str(message.id), {})
                    if isinstance(repost_info, dict) and 'repost_id' in repost_info:
                        fireboard_msg = await fireboard_channel.fetch_message(repost_info['repost_id'])
                        embed = discord.Embed(
                            title=f"🔥 {fire_count} Fires!",
                            description=message.content or "*No content*",
                            color=discord.Color.orange()
                        )
                        embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
                        embed.add_field(name="Jump to Message", value=f"[Click Here]({message.jump_url})", inline=False)
                        embed.set_footer(text=f"Posted in #{message.channel.name}")

                        await fireboard_msg.edit(embed=embed)

                elif fire_count >= fire_threshold:
                    # New post to fireboard
                    embed = discord.Embed(
                        title=f"🔥 {fire_count} Fires!",
                        description=message.content or "*No content*",
                        color=discord.Color.orange()
                    )
                    embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
                    embed.add_field(name="Jump to Message", value=f"[Click Here]({message.jump_url})", inline=False)
                    embed.set_footer(text=f"Posted in #{message.channel.name}")

                    post = await fireboard_channel.send(embed=embed)
                    await post.add_reaction('🔥')
                    # Save with extra info: repost ID and original channel ID
                    self.posted_messages[str(message.id)] = {
                        "repost_id": post.id,
                        "channel_id": message.channel.id
                    }
                    self.save_fireboard_data()
        except Exception as e:
            print(f"Error in Fireboard on_reaction_add: {e}")
    def load_fireboard_data(self):
        # Ensure proper loading of data
        if os.path.exists('data/fireboard.json'):
            try:
                data = self.data_handler.load_data()
                return data.get('posted_messages', {})
            except json.JSONDecodeError:
                print("Error decoding fireboard.json, resetting data.")
                return {}
        else:
            print("No fireboard data file found, initializing new one.")
            return {}
    def save_fireboard_data(self):
        self.data_handler.save_data({"posted_messages": self.posted_messages})
async def setup(bot):
    await bot.add_cog(Fireboard(bot))