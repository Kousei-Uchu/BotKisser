import discord
from discord import Interaction, app_commands
import discord.abc
from discord.ext import commands
import asyncio
from datetime import datetime, date
import openpyxl

# Constants for persistent button IDs
ACCEPT_BUTTON_ID = "qna:accept"
DENY_BUTTON_ID = "qna:deny"
INTERVIEW_BUTTON_ID = "qna:interview"
START_QNA_BUTTON_ID = "qna:start"

class ModerationView(discord.ui.View):
    """Persistent view for QNA moderation buttons"""
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog
        self.add_item(AcceptButton())
        self.add_item(DenyButton())
        self.add_item(InterviewButton(cog))

class StartQNAView(discord.ui.View):
    """Persistent view for the start QNA button"""
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog
        self.add_item(StartQNAButton(cog))

class AcceptButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Accept",
            style=discord.ButtonStyle.green,
            custom_id=ACCEPT_BUTTON_ID
        )

    async def callback(self, interaction: discord.Interaction):
        cog = self.view.cog
        embed = interaction.message.embeds[0]
        user_id = None
        
        # Try to find user ID in embed fields
        for field in embed.fields:
            if field.name == "User ID":
                user_id = int(field.value)
                break
        
        # Fallback to parsing from title
        if user_id is None:
            user_display = embed.title.split("for ")[-1].strip()
            user = discord.utils.get(interaction.guild.members, name=user_display.split('#')[0])
            if user:
                user_id = user.id
        
        if not user_id:
            await interaction.response.send_message("Could not identify user from the application.", ephemeral=True)
            return

        # Get the target channel
        channel = interaction.client.get_channel(1071601576252289158)
        if not channel:
            await interaction.response.send_message("Target channel not found.", ephemeral=True)
            return

        # Send DM to applicant
        guild = interaction.client.get_guild(1071601574616498248)
        user = guild.get_member(user_id)
        if user:
            try:
                await user.send(f"Your application has been accepted! You can now access the rest of The Den! Have fun!")
                role = interaction.guild.get_role(1388159784221413472)
                await user.add_roles(role)
                bot = cog.bot
                intro_cog = bot.get_cog('IntroSystem')


                if intro_cog:
                    await intro_cog.on_member_approve(user)

            except discord.Forbidden:
                await interaction.response.send_message(f"Could not DM the user (they might have DMs disabled).", ephemeral=True)
        else:
            await interaction.response.send_message(f"User not found in server.", ephemeral=True)

        # Create action log embed
        action_embed = discord.Embed(title="Action Log", color=discord.Color.green())
        action_embed.add_field(
            name="Accepted",
            value=f"{interaction.user.mention} accepted the user.",
            inline=False
        )

        await interaction.message.edit(embeds=[embed, action_embed])
        await interaction.response.send_message(f"Accepted {user.display_name if user else user_id}.", ephemeral=True)

class DenyButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Deny",
            style=discord.ButtonStyle.red,
            custom_id=DENY_BUTTON_ID
        )

    async def callback(self, interaction: discord.Interaction):
        embed = interaction.message.embeds[0]
        user_id = None
        
        for field in embed.fields:
            if field.name == "User ID":
                user_id = int(field.value)
                break
        
        if user_id:
            guild = interaction.client.get_guild(1071601574616498248)
            user = guild.get_member(user_id)
            if user:
                try:
                    await user.send("We're sorry, but your application was not accepted, you may choose to reapply later.")
                except discord.Forbidden:
                    pass
        
        action_embed = discord.Embed(title="Action Log", color=discord.Color.red())
        action_embed.add_field(
            name="Denied",
            value=f"{interaction.user.mention} denied the user.",
            inline=False
        )
        
        await interaction.message.edit(embeds=[embed, action_embed])
        await interaction.response.send_message("Application denied.", ephemeral=True)

class InterviewButton(discord.ui.Button):
    def __init__(self, cog):
        super().__init__(
            label="Interview",
            style=discord.ButtonStyle.blurple,
            custom_id=INTERVIEW_BUTTON_ID
        )
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        cog = self.view.cog
        embed = interaction.message.embeds[0]
        user_display = embed.title.split("for ")[-1]
        guild = cog.bot.get_guild(cog.TARGET_SERVER_ID)
        category = discord.utils.get(guild.categories, id=cog.INTERVIEW_CATEGORY_ID)
        
        interview_channel = await guild.create_text_channel(
            f"interview-{user_display}",
            category=category
        )
        
        action_embed = discord.Embed(title="Action Log", color=discord.Color.blurple())
        action_embed.add_field(
            name="Interview Opened",
            value=f"{interaction.user.mention} started an interview.",
            inline=False
        )
        
        await interaction.message.edit(embeds=[embed, action_embed])
        await interaction.response.send_message(f"Interview channel created for {user_display}.", ephemeral=True)

class StartQNAButton(discord.ui.Button):
    def __init__(self, cog):
        super().__init__(
            label="Start Q&A in DMs",
            style=discord.ButtonStyle.green,
            custom_id=START_QNA_BUTTON_ID
        )
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.client.get_guild(1071601574616498248)
        role = guild.get_role(1388159784221413472)
        member = guild.get_member(interaction.user.id)
        if role in member.roles:
            await interaction.response.send_message("You are already in The Den!", ephemeral=True)
            return

        try:
            await interaction.response.send_message("DM sent, please check for a message request from this bot.", ephemeral=True)
            await self.cog.run_qna(interaction.user)
        except discord.Forbidden:
            await interaction.response.send_message("I can't DM you, make sure your DMs are open!", ephemeral=True)

class QNACog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.TARGET_CHANNEL_ID = 1071601578181664910
        self.TARGET_SERVER_ID = 1071601574616498248
        self.INTERVIEW_CATEGORY_ID = 1369630301235445820
        self.MAX_FIELD_LENGTH = 1024

        # Define all questions and their metadata
        self.QUESTION_DATA = [
            {
                "question": "**What's your preferred name?**",
                "column": "Preferred Name",
                "mapping": "Mandatory",
                "validator": self.type(str)
            },
            {
                "question": "**What pronouns do you feel comfortable with?**",
                "column": "Pronouns",
                "mapping": "Mandatory",
                "validator": self.type(str)
            },
            {
                "question": "**What is your Reddit Username? (Mandatory if you have a reddit account, optional if you don't. Include 'u/' in your answer.)**",
                "column": "Reddit Username",
                "mapping": "Optional",
                "validator": self.mustcontain("u/")
            },
            {
                "question": "**Please link your pronouns page! If you don't have one, create one at https://pronouns.page. (Optional but preferred)**",
                "column": "Pronouns Page",
                "mapping": "Optional",
                "validator": self.mustcontain("https://")
            },
            {
                "question": "**Tell me more about you! Give me as much as you can while staying under 1024 characters (I'll let you know if you've put too much).**",
                "column": "About",
                "mapping": "Mandatory",
                "validator": self.type(str)
            },
            {
                "question": "**How old are you? (We use this only for safety!)**",
                "column": "Age",
                "mapping": "Mandatory",
                "validator": self.type(int)
            },
            {
                "question": "**When is your birthday? If you choose to answer, you'll get a special announcement on your special day! (Optional - Format 'DD/MM/YYYY')**",
                "column": "Birthday",
                "mapping": "Optional",
                "validator": self.type(date)
            },
            {
                "question": "**What is your favourite quote? (Optional)**",
                "column": "Favourite Quote",
                "mapping": "Optional",
                "validator": self.type(str)
            },
            {
                "question": "**What is your fursona's name?**",
                "column": "Fursona Name",
                "mapping": "Mandatory",
                "validator": self.type(str)
            },
            {
                "question": "**What species is your fursona?**",
                "column": "Fursona Species",
                "mapping": "Mandatory",
                "validator": self.type(str)
            },
            {
                "question": "**Tell me more about your fursona! Again, give me as much as you can while staying under 1024 characters (I'll let you know if you've put too much).**",
                "column": "About Fursona",
                "mapping": "Mandatory",
                "validator": self.type(str)
            },
            {
                "question": "**What are you hoping to get out of joining?**",
                "column": "Join Goals",
                "mapping": "Mandatory",
                "validator": self.type(str)
            },
            {
                "question": "**Where did you find out about us?**",
                "column": "Discovery Source",
                "mapping": "Optional",
                "validator": self.type(str)
            }
        ]

        # Derived lists for easier access
        self.questions = [q["question"] for q in self.QUESTION_DATA]
        self.questionmappings = [q["mapping"] for q in self.QUESTION_DATA]
        self.questionformat = [q["validator"] for q in self.QUESTION_DATA]
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

    async def run_qna(self, user: discord.User):
        responses = {}
        def check(m):
            return m.author == user and isinstance(m.channel, discord.DMChannel)

        try:
            await user.send("Hi! Let's begin the Intro form. Please answer the following questions! You may choose to skip optional questions by saying simply 'q.skip'.")
        except discord.Forbidden:
            return

        for i, qdata in enumerate(self.QUESTION_DATA):
            await user.send(qdata["question"])
            while True:
                try:
                    msg = await self.bot.wait_for("message", check=check, timeout=300)
                    if len(msg.content) > self.MAX_FIELD_LENGTH:
                        await user.send(f"Your answer is too long! Please provide a shorter response (max {self.MAX_FIELD_LENGTH} characters).")
                        continue

                    if qdata["mapping"] == "Optional" and msg.content.strip().lower() == "q.skip":
                        responses[qdata["column"]] = "Skipped"
                        break

                    if qdata["mapping"] == "Mandatory" and msg.content.strip().lower() == "q.skip":
                        await user.send(f"You may not skip this question.")
                        continue

                    valid = qdata["validator"](msg.content.strip())
                    if valid:
                        responses[qdata["column"]] = msg.content.strip()
                        break
                    else:
                        await user.send(f"Please provide your answer in the specified format.")
                        continue

                except asyncio.TimeoutError:
                    await user.send("You took too long to respond. Ending the session. Please re-attempt by pressing the button again!")
                    return

        embed = discord.Embed(title=f"Intro Post for {user}", description="Here are their responses:", color=discord.Color.blue())
        embed.add_field(name="User ID", value=str(user.id), inline=False)  # Add user ID for reference
        
        for qdata in self.QUESTION_DATA:
            answer = responses.get(qdata["column"], "skipped")
            embed.add_field(name=qdata["question"], value=answer, inline=False)

        mod_channel = self.bot.get_channel(self.TARGET_CHANNEL_ID)
        message = await mod_channel.send(content='@everyone', embed=embed)
        self.save_to_excel(user, responses)

        view = ModerationView(self)
        await message.edit(view=view)
        await user.send("Thank you for applying! Your responses have been recorded and are now under review.")

    def save_to_excel(self, user: discord.User, responses: dict):
        try:
            workbook = openpyxl.load_workbook("responses.xlsx")
        except FileNotFoundError:
            workbook = openpyxl.Workbook()
            sheet = workbook.active
            sheet.append(self.column_headers)

        sheet = workbook.active
        
        # Prepare the row data
        row_data = [user.name]  # Start with username
        for qdata in self.QUESTION_DATA:
            answer = responses.get(qdata["column"], "N/A")
            row_data.append(answer)

        sheet.append(row_data)
        workbook.save("responses.xlsx")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.bot.user:
            return

        if isinstance(message.channel, discord.TextChannel):
            if message.channel.category and message.channel.category.id == self.INTERVIEW_CATEGORY_ID:
                user_name = message.channel.name.replace("interview-", "")
                user = discord.utils.get(self.bot.users, name=user_name)
                if user:
                    try:
                        await user.send(f"Staff Message: {message.content}")
                    except discord.Forbidden:
                        await message.channel.send(f"Could not send the message to {user_name}'s DM.")
        
        if isinstance(message.channel, discord.DMChannel):
            interview_channel_name = f"interview-{message.author.name}"
            guild = self.bot.get_guild(self.TARGET_SERVER_ID)
            interview_channel = discord.utils.get(guild.text_channels, name=interview_channel_name)
            if interview_channel:
                try:
                    await interview_channel.send(f"{message.author.name}: {message.content}")
                except discord.Forbidden:
                    await message.channel.send("I don't have permission to send messages in the interview channel.")
        
        await self.bot.process_commands(message)

    @app_commands.command(name="post_qna_button", description="Post a Q&A start button in this channel.")
    async def post_qna_button(self, interaction: discord.Interaction):
        await interaction.channel.send(
            "Press the button below to start the intro process to gain access to the rest of The Den. Please DM a staff member if you have any questions or need any help!",
            view=StartQNAView(self)
        )
        await interaction.response.send_message("Sent", ephemeral=True)

    @app_commands.command(name="interview_close", description="Close interview channel, can be run by staff or applicant.")
    async def interview_close(self, interaction: discord.Interaction):
        guild = self.bot.get_guild(self.TARGET_SERVER_ID)
        if not guild:
            await interaction.response.send_message("Server not found.", ephemeral=True)
            return

        if not interaction.channel.name.startswith("interview-"):
            await interaction.response.send_message("Please use this command in an interview channel.", ephemeral=True)
            return

        user = interaction.channel.name.split("interview-")[-1]
        await interaction.channel.send(f"Closing interview for {user}.")
        await interaction.response.send_message(f"Interview channel closed for {user}.", ephemeral=True)
        await interaction.channel.delete()

async def setup(bot):
    await bot.add_cog(QNACog(bot))