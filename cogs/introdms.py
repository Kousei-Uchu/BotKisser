import discord
from discord import Interaction, app_commands
from discord.ext import commands
import asyncio
from datetime import datetime, date
import openpyxl
import logging

logger = logging.getLogger("QNA")
logging.basicConfig(level=logging.INFO)

# Persistent button IDs
ACCEPT_BUTTON_ID = "qna:accept"
DENY_BUTTON_ID = "qna:deny"
INTERVIEW_BUTTON_ID = "qna:interview"
START_QNA_BUTTON_ID = "qna:start"
SKIP_COMMAND = "q.skip"

class ModerationView(discord.ui.View):
    """Persistent moderation buttons view."""
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog
        self.add_item(AcceptButton())
        self.add_item(DenyButton())
        self.add_item(InterviewButton(cog))

class StartQNAView(discord.ui.View):
    """Persistent start QNA button view."""
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog
        self.add_item(StartQNAButton(cog))

class BaseQNAButton(discord.ui.Button):
    """Base class to handle repeated embed/user logic."""
    async def get_user_from_embed(self, interaction: Interaction):
        embed = interaction.message.embeds[0]
        for field in embed.fields:
            if field.name == "User ID":
                user_id = int(field.value)
                user = interaction.guild.get_member(user_id)
                return user
        return None

class AcceptButton(BaseQNAButton):
    def __init__(self):
        super().__init__(label="Accept", style=discord.ButtonStyle.green, custom_id=ACCEPT_BUTTON_ID)

    async def callback(self, interaction: Interaction):
        cog = self.view.cog
        user = await self.get_user_from_embed(interaction)
        if not user:
            await interaction.response.send_message("Could not identify user.", ephemeral=True)
            return

        role = interaction.guild.get_role(cog.MEMBER_ROLE_ID)
        try:
            await user.add_roles(role)
            await user.send("Your application has been accepted! Enjoy The Den!")
        except discord.Forbidden:
            await interaction.response.send_message("Could not DM or add roles to the user.", ephemeral=True)

        # Action log embed
        embed = interaction.message.embeds[0]
        action_embed = discord.Embed(title="Action Log", color=discord.Color.green())
        action_embed.add_field(name="Accepted", value=f"{interaction.user.mention} accepted {user.mention}.", inline=False)
        await interaction.message.edit(embeds=[embed, action_embed])
        await interaction.response.send_message(f"Accepted {user.display_name}.", ephemeral=True)

class DenyButton(BaseQNAButton):
    def __init__(self):
        super().__init__(label="Deny", style=discord.ButtonStyle.red, custom_id=DENY_BUTTON_ID)

    async def callback(self, interaction: Interaction):
        user = await self.get_user_from_embed(interaction)
        if user:
            try:
                await user.send("We're sorry, your application was not accepted. You may reapply later.")
            except discord.Forbidden:
                pass

        embed = interaction.message.embeds[0]
        action_embed = discord.Embed(title="Action Log", color=discord.Color.red())
        action_embed.add_field(name="Denied", value=f"{interaction.user.mention} denied {user.mention if user else 'user'}.", inline=False)
        await interaction.message.edit(embeds=[embed, action_embed])
        await interaction.response.send_message("Application denied.", ephemeral=True)

class InterviewButton(BaseQNAButton):
    def __init__(self, cog):
        super().__init__(label="Interview", style=discord.ButtonStyle.blurple, custom_id=INTERVIEW_BUTTON_ID)
        self.cog = cog

    async def callback(self, interaction: Interaction):
        user = await self.get_user_from_embed(interaction)
        if not user:
            await interaction.response.send_message("Could not identify user.", ephemeral=True)
            return

        guild = self.cog.bot.get_guild(self.cog.TARGET_SERVER_ID)
        category = discord.utils.get(guild.categories, id=self.cog.INTERVIEW_CATEGORY_ID)
        channel_name = f"interview-{user.name.lower()}"
        interview_channel = await guild.create_text_channel(channel_name, category=category)

        # Log embed
        embed = interaction.message.embeds[0]
        action_embed = discord.Embed(title="Action Log", color=discord.Color.blurple())
        action_embed.add_field(name="Interview Opened", value=f"{interaction.user.mention} started an interview for {user.mention}.", inline=False)
        await interaction.message.edit(embeds=[embed, action_embed])
        await interaction.response.send_message(f"Interview channel created for {user.display_name}.", ephemeral=True)

class StartQNAButton(discord.ui.Button):
    def __init__(self, cog):
        super().__init__(label="Start Q&A in DMs", style=discord.ButtonStyle.green, custom_id=START_QNA_BUTTON_ID)
        self.cog = cog

    async def callback(self, interaction: Interaction):
        guild = self.cog.bot.get_guild(self.cog.TARGET_SERVER_ID)
        member = guild.get_member(interaction.user.id)
        if self.cog.MEMBER_ROLE_ID in [r.id for r in member.roles]:
            await interaction.response.send_message("You are already in The Den!", ephemeral=True)
            return

        try:
            await interaction.response.send_message("DM sent, please check your messages.", ephemeral=True)
            await self.cog.run_qna(member)
        except discord.Forbidden:
            await interaction.response.send_message("I can't DM you. Open your DMs and try again.", ephemeral=True)

class QNACog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.TARGET_CHANNEL_ID = 1071601578181664910
        self.TARGET_SERVER_ID = 1071601574616498248
        self.INTERVIEW_CATEGORY_ID = 1369630301235445820
        self.MEMBER_ROLE_ID = 1388159784221413472
        self.MAX_FIELD_LENGTH = 1024

        # Questions setup
        self.QUESTION_DATA = [
            {"question": "**What's your preferred name?**", "column": "Preferred Name", "mapping": "Mandatory", "validator": self.type(str)},
            {"question": "**What pronouns do you feel comfortable with?**", "column": "Pronouns", "mapping": "Mandatory", "validator": self.type(str)},
            {"question": "**What is your Reddit Username? Include 'u/'**", "column": "Reddit Username", "mapping": "Optional", "validator": self.mustcontain("u/")},
            {"question": "**Please link your pronouns page!**", "column": "Pronouns Page", "mapping": "Optional", "validator": self.mustcontain("https://")},
            {"question": "**Tell me about you! Max 1024 chars**", "column": "About", "mapping": "Mandatory", "validator": self.type(str)},
            {"question": "**How old are you?**", "column": "Age", "mapping": "Mandatory", "validator": self.type(int)},
            {"question": "**Birthday? Format 'DD/MM/YYYY' (optional)**", "column": "Birthday", "mapping": "Optional", "validator": self.type(date)},
            {"question": "**Favourite Quote (optional)**", "column": "Favourite Quote", "mapping": "Optional", "validator": self.type(str)},
            {"question": "**Fursona's name?**", "column": "Fursona Name", "mapping": "Mandatory", "validator": self.type(str)},
            {"question": "**Fursona species?**", "column": "Fursona Species", "mapping": "Mandatory", "validator": self.type(str)},
            {"question": "**About your fursona? Max 1024 chars**", "column": "About Fursona", "mapping": "Mandatory", "validator": self.type(str)},
            {"question": "**What are you hoping to get out of joining?**", "column": "Join Goals", "mapping": "Mandatory", "validator": self.type(str)},
            {"question": "**Where did you find out about us?**", "column": "Discovery Source", "mapping": "Optional", "validator": self.type(str)}
        ]

        self.column_headers = ["Username"] + [q["column"] for q in self.QUESTION_DATA]

        # Register persistent views
        self.bot.add_view(StartQNAView(self))
        self.bot.add_view(ModerationView(self))

    def mustcontain(self, substring):
        def validator(value):
            return substring in value
        return validator

    def type(self, t):
        def validator(value):
            try:
                if t == int:
                    int(value)
                    return True
                elif t == date:
                    datetime.strptime(value, "%d/%m/%Y")
                    return True
                return isinstance(value, t)
            except ValueError:
                return False
        return validator

    async def run_qna(self, member: discord.Member):
        responses = {}
        check = lambda m: m.author == member and isinstance(m.channel, discord.DMChannel)

        try:
            await member.send("Hi! Let's start the Q&A. Type `q.skip` to skip optional questions.")
        except discord.Forbidden:
            return

        for qdata in self.QUESTION_DATA:
            await member.send(qdata["question"])
            while True:
                try:
                    msg = await self.bot.wait_for("message", check=check, timeout=300)
                    content = msg.content.strip()
                    if len(content) > self.MAX_FIELD_LENGTH:
                        await member.send(f"Answer too long! Max {self.MAX_FIELD_LENGTH} characters.")
                        continue

                    if qdata["mapping"] == "Optional" and content.lower() == SKIP_COMMAND:
                        responses[qdata["column"]] = "Skipped"
                        break
                    if qdata["mapping"] == "Mandatory" and content.lower() == SKIP_COMMAND:
                        await member.send("You may not skip this question.")
                        continue

                    if qdata["validator"](content):
                        responses[qdata["column"]] = content
                        break
                    else:
                        await member.send("Invalid format, please try again.")
                except asyncio.TimeoutError:
                    await member.send("Timed out. Please restart the Q&A with the button.")
                    return

        # Build embed
        embed = discord.Embed(title=f"Intro Post for {member}", description="Here are their responses:", color=discord.Color.blue())
        embed.add_field(name="User ID", value=str(member.id), inline=False)
        for qdata in self.QUESTION_DATA:
            answer = responses.get(qdata["column"], "Skipped")
            embed.add_field(name=qdata["question"], value=answer[:self.MAX_FIELD_LENGTH], inline=False)

        # Send to moderation channel
        mod_channel = self.bot.get_channel(self.TARGET_CHANNEL_ID)
        message = await mod_channel.send(content='@everyone', embed=embed, view=ModerationView(self))

        # Save responses asynchronously
        await asyncio.to_thread(self.save_to_excel, member, responses)

        await member.send("Thank you! Your responses are now under review.")

    def save_to_excel(self, member: discord.Member, responses: dict):
        try:
            workbook = openpyxl.load_workbook("responses.xlsx")
        except FileNotFoundError:
            workbook = openpyxl.Workbook()
            sheet = workbook.active
            sheet.title = "Responses"
            sheet.append(self.column_headers)

        sheet = workbook["Responses"]

        row_data = [member.name]
        for qdata in self.QUESTION_DATA:
            row_data.append(responses.get(qdata["column"], "N/A"))

        sheet.append(row_data)
        workbook.save("responses.xlsx")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        guild = self.bot.get_guild(self.TARGET_SERVER_ID)
        # DM to staff in interview channels
        if isinstance(message.channel, discord.DMChannel):
            interview_channel_name = f"interview-{message.author.name.lower()}"
            interview_channel = discord.utils.get(guild.text_channels, name=interview_channel_name)
            if interview_channel:
                try:
                    await interview_channel.send(f"{message.author.name}: {message.content}")
                except discord.Forbidden:
                    logger.warning(f"Cannot send DM to {message.author.id}")
        # Staff to DM
        elif isinstance(message.channel, discord.TextChannel):
            if message.channel.category and message.channel.category.id == self.INTERVIEW_CATEGORY_ID:
                user_name = message.channel.name.replace("interview-", "")
                user = discord.utils.get(guild.members, name=user_name)
                if user:
                    try:
                        await user.send(f"Staff Message: {message.content}")
                    except discord.Forbidden:
                        await message.channel.send(f"Could not send message to {user_name}'s DM.")

        await self.bot.process_commands(message)

    @app_commands.command(name="post_qna_button", description="Post a Q&A start button in this channel.")
    async def post_qna_button(self, interaction: Interaction):
        await interaction.channel.send(
            "Press the button below to start the intro process to gain access to The Den.",
            view=StartQNAView(self)
        )
        await interaction.response.send_message("Sent", ephemeral=True)

    @app_commands.command(name="interview_close", description="Close interview channel.")
    async def interview_close(self, interaction: Interaction):
        if not interaction.channel.name.startswith("interview-"):
            await interaction.response.send_message("Use this command inside an interview channel.", ephemeral=True)
            return

        user_name = interaction.channel.name.replace("interview-", "")
        await interaction.channel.send(f"Closing interview for {user_name}.")
        await interaction.response.send_message(f"Interview channel closed for {user_name}.", ephemeral=True)
        await interaction.channel.delete()

async def setup(bot):
    await bot.add_cog(QNACog(bot))