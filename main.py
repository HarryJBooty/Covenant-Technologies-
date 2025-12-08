import os
import asyncio
import logging
from typing import List, Optional, Dict, Tuple
from enum import Enum

import discord
from discord.ext import commands
from discord import ui
import asyncpg

# =========================
# CONFIG SECTION (EDIT ME)
# =========================

# Discord bot token (set in Railway as env var)
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# Railway Postgres URL (Railway usually sets DATABASE_URL)
DATABASE_URL = os.getenv("DATABASE_URL")

# Allowed roles for logging events (officer roles)
OFFICER_ROLE_IDS = [
    1283223363980103702,  # REPLACE with real officer role IDs
    # ...
]

# Role ID for "Minor I" (allowed to start the quiz)
MINOR_I_ROLE_ID = 1129557455244902451  # REPLACE with real role ID

# Roles that are allowed to mark quizzes as pass/fail
QUIZ_REVIEWER_ROLE_IDS = [
    1129557455244902459,  # e.g. High Command, Inquisitors etc.
    # ...
]

# Channel where completed quiz attempts are sent for review
QUIZ_REVIEW_CHANNEL_ID = 1129557456947781649  # REPLACE with real channel ID

# Placeholder link for duel DM
DUEL_PLACEHOLDER_LINK = "https://example.com/your-duel-link"  # EDIT this later

# Default requirements used for !progress bars (edit to match next-rank target)
DEFAULT_REQUIREMENTS = {
    "events": 7,       # e.g. 7 events
    "warfare": 3,      # e.g. 3 warfare events
    "training": 2,     # e.g. 2 trainings
    "duels": 2,        # e.g. 2 duels
}

# Events that count as warfare (for hosted/attended warfare stats)
WARFARE_EVENT_TYPES = {"raid", "defense", "scrim"}

# Events that count as training
TRAINING_EVENT_TYPES = {"training"}

# Quiz questions (placeholders – edit texts as you like)
QUIZ_QUESTIONS = [
    "Question 1 placeholder – edit me.",
    "Question 2 placeholder – edit me.",
    "Question 3 placeholder – edit me.",
    "Question 4 placeholder – edit me.",
    "Question 5 placeholder – edit me.",
]

# =========================
# LOGGING
# =========================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("halo_group_bot")

# =========================
# DISCORD SETUP
# =========================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.reactions = True

bot = commands.Bot(
    command_prefix=("!", "?"),  # supports both ! and ?
    intents=intents,
    help_command=None,  # you can implement custom help later
)

# =========================
# POSTGRES / ASYNCPG
# =========================

pool: Optional[asyncpg.Pool] = None


async def init_db():
    global pool
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL environment variable not set.")

    # On Railway, this should work directly. If SSL is required:
    # pool = await asyncpg.create_pool(DATABASE_URL, ssl="require")
    pool = await asyncpg.create_pool(DATABASE_URL)

    async with pool.acquire() as conn:
        # Users table
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                discord_id BIGINT UNIQUE NOT NULL,
                roblox_user_id BIGINT,
                quiz_passed BOOLEAN DEFAULT FALSE
            );
            """
        )

        # Events table
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id SERIAL PRIMARY KEY,
                event_type TEXT NOT NULL,
                host_discord_id BIGINT NOT NULL,
                cohost_discord_id BIGINT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

        # Attendance table
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS event_attendance (
                id SERIAL PRIMARY KEY,
                event_id INTEGER REFERENCES events(id) ON DELETE CASCADE,
                user_discord_id BIGINT NOT NULL
            );
            """
        )

        # Duels table
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS duels (
                id SERIAL PRIMARY KEY,
                winner_discord_id BIGINT NOT NULL,
                loser_discord_id BIGINT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

    logger.info("Postgres database initialized.")


# =========================
# DATABASE HELPERS
# =========================

async def ensure_user(discord_id: int):
    """Ensure a user row exists for this Discord ID."""
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users (discord_id)
            VALUES ($1)
            ON CONFLICT (discord_id) DO NOTHING;
            """,
            discord_id,
        )


async def set_quiz_passed(discord_id: int, passed: bool):
    await ensure_user(discord_id)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE users
            SET quiz_passed = $1
            WHERE discord_id = $2;
            """,
            passed,
            discord_id,
        )


async def get_quiz_passed(discord_id: int) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT quiz_passed
            FROM users
            WHERE discord_id = $1;
            """,
            discord_id,
        )

    if not row:
        return False
    return bool(row["quiz_passed"])


async def log_event(
    event_type: str,
    host_id: int,
    cohost_id: Optional[int],
    attendee_ids: List[int],
) -> int:
    """Create an event and event_attendance rows. Returns event_id."""
    # Deduplicate attendees
    unique_attendees = list(dict.fromkeys(attendee_ids))

    async with pool.acquire() as conn:
        # Ensure host/cohost/users exist
        await ensure_user(host_id)
        if cohost_id:
            await ensure_user(cohost_id)
        for uid in unique_attendees:
            await ensure_user(uid)

        row = await conn.fetchrow(
            """
            INSERT INTO events (event_type, host_discord_id, cohost_discord_id)
            VALUES ($1, $2, $3)
            RETURNING id;
            """,
            event_type,
            host_id,
            cohost_id,
        )
        event_id = row["id"]

        for uid in unique_attendees:
            await conn.execute(
                """
                INSERT INTO event_attendance (event_id, user_discord_id)
                VALUES ($1, $2);
                """,
                event_id,
                uid,
            )

    return event_id


async def log_duel_result(winner_id: int, loser_id: int):
    async with pool.acquire() as conn:
        await ensure_user(winner_id)
        await ensure_user(loser_id)
        await conn.execute(
            """
            INSERT INTO duels (winner_discord_id, loser_discord_id)
            VALUES ($1, $2);
            """,
            winner_id,
            loser_id,
        )


async def get_user_stats(discord_id: int) -> Dict[str, int]:
    await ensure_user(discord_id)

    async with pool.acquire() as conn:
        # Total hosted
        total_hosted = await conn.fetchval(
            """
            SELECT COUNT(*) FROM events
            WHERE host_discord_id = $1 OR cohost_discord_id = $1;
            """,
            discord_id,
        )

        # Warfare hosted
        warfare_hosted = await conn.fetchval(
            """
            SELECT COUNT(*) FROM events
            WHERE (host_discord_id = $1 OR cohost_discord_id = $1)
              AND event_type = ANY($2::text[]);
            """,
            discord_id,
            list(WARFARE_EVENT_TYPES),
        )

        # Total attended
        total_attended = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM event_attendance
            WHERE user_discord_id = $1;
            """,
            discord_id,
        )

        # Warfare attended
        warfare_attended = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM event_attendance ea
            JOIN events e ON ea.event_id = e.id
            WHERE ea.user_discord_id = $1
              AND e.event_type = ANY($2::text[]);
            """,
            discord_id,
            list(WARFARE_EVENT_TYPES),
        )

        # Training attended
        training_attended = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM event_attendance ea
            JOIN events e ON ea.event_id = e.id
            WHERE ea.user_discord_id = $1
              AND e.event_type = ANY($2::text[]);
            """,
            discord_id,
            list(TRAINING_EVENT_TYPES),
        )

        # Duels won
        duels_won = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM duels
            WHERE winner_discord_id = $1;
            """,
            discord_id,
        )

    quiz_passed = await get_quiz_passed(discord_id)

    return {
        "total_hosted": total_hosted or 0,
        "warfare_hosted": warfare_hosted or 0,
        "total_attended": total_attended or 0,
        "warfare_attended": warfare_attended or 0,
        "training_attended": training_attended or 0,
        "duels_won": duels_won or 0,
        "quiz_passed": int(quiz_passed),
    }


def make_progress_bar(current: int, required: int, length: int = 10) -> str:
    if required <= 0:
        return "[──────────]"
    ratio = max(0.0, min(1.0, current / required))
    filled = int(round(ratio * length))
    bar = "█" * filled + "─" * (length - filled)
    return f"[{bar}]"


# =========================
# ENHANCED UI COMPONENTS
# =========================

class UIStyle:
    """Centralized styling for all UI components"""
    COLOR_PRIMARY = discord.Color.from_rgb(138, 43, 226)  # Purple
    COLOR_SUCCESS = discord.Color.green()
    COLOR_ERROR = discord.Color.red()
    COLOR_INFO = discord.Color.blue()
    COLOR_WARNING = discord.Color.orange()
    
    EMOJI_SUCCESS = "✅"
    EMOJI_ERROR = "❌"
    EMOJI_WARNING = "⚠️"
    EMOJI_INFO = "ℹ️"
    EMOJI_LOADING = "⏳"
    EMOJI_BACK = "◀️"
    EMOJI_FORWARD = "▶️"
    EMOJI_HOME = "🏠"
    EMOJI_NUMBERS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


class MainMenuView(ui.View):
    """Main menu with buttons for all major features"""
    
    def __init__(self, ctx: commands.Context):
        super().__init__(timeout=300)
        self.ctx = ctx
        self.is_officer = isinstance(ctx.author, discord.Member) and is_officer(ctx.author)
        
        # Add buttons conditionally based on permissions
        if self.is_officer:
            self.add_item(LogEventButton())
            self.add_item(ReportDuelButton())
        
        self.add_item(ChallengeButton())
        self.add_item(ProgressButton())
        self.add_item(QuizButton())
        self.add_item(HelpButton())
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.ctx.author.id
    
    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            await self.message.edit(view=self)
        except:
            pass


class LogEventButton(ui.Button):
    def __init__(self):
        super().__init__(
            label="Log Event",
            style=discord.ButtonStyle.primary,
            emoji="📋",
            custom_id="log_event"
        )
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        view = EventTypeSelectView(interaction)
        embed = create_styled_embed(
            "📋 Log Event",
            "Select the type of event you want to log:",
            UIStyle.COLOR_PRIMARY
        )
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class ReportDuelButton(ui.Button):
    def __init__(self):
        super().__init__(
            label="Report Duel",
            style=discord.ButtonStyle.primary,
            emoji="⚔️",
            custom_id="report_duel"
        )
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=create_styled_embed(
                "⚔️ Report Duel Result",
                "Use the command: `!report_duel @winner @loser`\n\n"
                "Example: `!report_duel @John @Jane`",
                UIStyle.COLOR_INFO
            ),
            ephemeral=True
        )


class ChallengeButton(ui.Button):
    def __init__(self):
        super().__init__(
            label="Challenge Player",
            style=discord.ButtonStyle.success,
            emoji="⚔️",
            custom_id="challenge"
        )
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=create_styled_embed(
                "⚔️ Challenge a Player",
                "Use the command: `!challenge @opponent`\n\n"
                "Example: `!challenge @PlayerName`\n\n"
                "They will receive a notification to accept or decline!",
                UIStyle.COLOR_INFO
            ),
            ephemeral=True
        )


class ProgressButton(ui.Button):
    def __init__(self):
        super().__init__(
            label="View Progress",
            style=discord.ButtonStyle.success,
            emoji="📊",
            custom_id="progress"
        )
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        stats = await get_user_stats(interaction.user.id)
        embed = create_progress_embed(interaction.user, stats)
        await interaction.followup.send(embed=embed, ephemeral=True)


class QuizButton(ui.Button):
    def __init__(self):
        super().__init__(
            label="Start Quiz",
            style=discord.ButtonStyle.success,
            emoji="📝",
            custom_id="quiz"
        )
    
    async def callback(self, interaction: discord.Interaction):
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                embed=create_styled_embed(
                    "Error",
                    "This command must be used in a server.",
                    UIStyle.COLOR_ERROR
                ),
                ephemeral=True
            )
            return
        
        if not any(r.id == MINOR_I_ROLE_ID for r in interaction.user.roles):
            await interaction.response.send_message(
                embed=create_styled_embed(
                    "Permission Denied",
                    "Only Minor I members may start this quiz.",
                    UIStyle.COLOR_ERROR
                ),
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        await start_quiz_flow(interaction.user, interaction.guild)
        await interaction.followup.send(
            embed=create_styled_embed(
                "Quiz Started",
                "Check your DMs! The quiz has been sent to you.",
                UIStyle.COLOR_SUCCESS
            ),
            ephemeral=True
        )


class HelpButton(ui.Button):
    def __init__(self):
        super().__init__(
            label="Help",
            style=discord.ButtonStyle.secondary,
            emoji="❓",
            custom_id="help"
        )
    
    async def callback(self, interaction: discord.Interaction):
        embed = create_help_embed()
        await interaction.response.send_message(embed=embed, ephemeral=True)


class EventTypeSelectView(ui.View):
    """Interactive event type selection with buttons"""
    
    def __init__(self, interaction: discord.Interaction):
        super().__init__(timeout=180)
        self.interaction = interaction
        self.selected_type = None
        
        event_types = [
            ("Raid", "⚔️", discord.ButtonStyle.danger),
            ("Defense", "🛡️", discord.ButtonStyle.primary),
            ("Scrim", "🎯", discord.ButtonStyle.primary),
            ("Training", "🏋️", discord.ButtonStyle.success),
            ("Gamenight", "🎮", discord.ButtonStyle.secondary),
            ("Recruitment", "📢", discord.ButtonStyle.secondary),
            ("Other", "📝", discord.ButtonStyle.secondary),
        ]
        
        for name, emoji, style in event_types:
            button = ui.Button(label=name, emoji=emoji, style=style)
            button.callback = self.create_callback(name.lower())
            self.add_item(button)
    
    def create_callback(self, event_type: str):
        async def callback(interaction: discord.Interaction):
            self.selected_type = event_type
            await interaction.response.defer()
            await self.proceed_to_cohost(interaction)
        return callback
    
    async def proceed_to_cohost(self, interaction: discord.Interaction):
        view = CoHostSelectView(self.interaction, self.selected_type)
        embed = create_styled_embed(
            "👥 Select Co-Host",
            f"Event Type: **{self.selected_type.capitalize()}**\n\n"
            "Click below to select a co-host, or choose 'No Co-Host':",
            UIStyle.COLOR_PRIMARY
        )
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.interaction.user.id


class CoHostSelectView(ui.View):
    """Select co-host with user select menu"""
    
    def __init__(self, interaction: discord.Interaction, event_type: str):
        super().__init__(timeout=180)
        self.interaction = interaction
        self.event_type = event_type
        self.cohost = None
        
        self.add_item(CoHostSelect())
        
        no_cohost_btn = ui.Button(label="No Co-Host", style=discord.ButtonStyle.secondary)
        no_cohost_btn.callback = self.no_cohost_callback
        self.add_item(no_cohost_btn)
    
    async def no_cohost_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self.proceed_to_attendees(interaction)
    
    async def proceed_to_attendees(self, interaction: discord.Interaction):
        view = AttendeeSelectView(self.interaction, self.event_type, self.cohost)
        cohost_text = f"@{self.cohost.display_name}" if self.cohost else "None"
        embed = create_styled_embed(
            "👥 Select Attendees",
            f"Event Type: **{self.event_type.capitalize()}**\n"
            f"Co-Host: **{cohost_text}**\n\n"
            "Select all attendees from the dropdown, then click 'Finish':",
            UIStyle.COLOR_PRIMARY
        )
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.interaction.user.id


class CoHostSelect(ui.UserSelect):
    def __init__(self):
        super().__init__(
            placeholder="Select co-host...",
            min_values=1,
            max_values=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        view: CoHostSelectView = self.view
        view.cohost = self.values[0]
        await interaction.response.defer()
        await view.proceed_to_attendees(interaction)


class AttendeeSelectView(ui.View):
    """Select multiple attendees"""
    
    def __init__(self, interaction: discord.Interaction, event_type: str, cohost: Optional[discord.Member]):
        super().__init__(timeout=300)
        self.interaction = interaction
        self.event_type = event_type
        self.cohost = cohost
        self.attendees = []
        
        self.add_item(AttendeeSelect())
        
        finish_btn = ui.Button(label="Finish & Log Event", style=discord.ButtonStyle.success, emoji="✅")
        finish_btn.callback = self.finish_callback
        self.add_item(finish_btn)
    
    async def finish_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        if not self.attendees:
            await interaction.followup.send(
                embed=create_styled_embed(
                    "No Attendees",
                    "Please select at least one attendee before finishing.",
                    UIStyle.COLOR_WARNING
                ),
                ephemeral=True
            )
            return
        
        # Log the event
        attendee_ids = [a.id for a in self.attendees]
        attendee_ids.append(interaction.user.id)  # Host
        if self.cohost:
            attendee_ids.append(self.cohost.id)
        
        event_id = await log_event(
            self.event_type,
            interaction.user.id,
            self.cohost.id if self.cohost else None,
            attendee_ids
        )
        
        cohost_text = f"Co-Host: {self.cohost.mention}" if self.cohost else "No Co-Host"
        attendee_list = ", ".join([a.mention for a in self.attendees[:10]])
        if len(self.attendees) > 10:
            attendee_list += f" and {len(self.attendees) - 10} more"
        
        embed = create_styled_embed(
            "✅ Event Logged Successfully",
            f"**Event ID:** {event_id}\n"
            f"**Type:** {self.event_type.capitalize()}\n"
            f"**Host:** {interaction.user.mention}\n"
            f"**{cohost_text}**\n"
            f"**Attendees ({len(self.attendees)}):** {attendee_list}",
            UIStyle.COLOR_SUCCESS
        )
        await interaction.followup.send(embed=embed)
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.interaction.user.id


class AttendeeSelect(ui.UserSelect):
    def __init__(self):
        super().__init__(
            placeholder="Select attendees (you can select multiple times)...",
            min_values=1,
            max_values=25
        )
    
    async def callback(self, interaction: discord.Interaction):
        view: AttendeeSelectView = self.view
        
        # Add new attendees
        for user in self.values:
            if user not in view.attendees:
                view.attendees.append(user)
        
        attendee_names = ", ".join([a.display_name for a in view.attendees[:20]])
        if len(view.attendees) > 20:
            attendee_names += f" and {len(view.attendees) - 20} more"
        
        await interaction.response.send_message(
            embed=create_styled_embed(
                "Attendees Updated",
                f"**Total selected:** {len(view.attendees)}\n"
                f"**Members:** {attendee_names}\n\n"
                "Select more or click 'Finish & Log Event' when done.",
                UIStyle.COLOR_SUCCESS
            ),
            ephemeral=True
        )


def create_styled_embed(title: str, description: str, color: discord.Color) -> discord.Embed:
    """Create a consistently styled embed"""
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=discord.utils.utcnow()
    )
    embed.set_footer(text="Covenant Technologies • Halo Group Bot")
    return embed


def create_main_menu_embed(member: discord.Member, is_officer: bool) -> discord.Embed:
    """Create the main menu embed"""
    embed = discord.Embed(
        title="🎮 Halo Group Management System",
        description=f"Welcome, {member.mention}!\n\nSelect an option below to get started:",
        color=UIStyle.COLOR_PRIMARY,
        timestamp=discord.utils.utcnow()
    )
    
    # Add fields for available actions
    if is_officer:
        embed.add_field(
            name="📋 Officer Actions",
            value="• Log Event\n• Report Duel Results",
            inline=False
        )
    
    embed.add_field(
        name="⚔️ Player Actions",
        value="• Challenge Player\n• View Progress\n• Start Quiz (Minor I only)",
        inline=False
    )
    
    embed.add_field(
        name="❓ Need Help?",
        value="Click the Help button for detailed command information.",
        inline=False
    )
    
    embed.set_footer(text="Covenant Technologies • Halo Group Bot")
    embed.set_thumbnail(url=member.display_avatar.url if member.display_avatar else None)
    
    return embed


def create_help_embed() -> discord.Embed:
    """Create comprehensive help embed"""
    embed = discord.Embed(
        title="❓ Help & Commands",
        description="Here's everything you can do with this bot:",
        color=UIStyle.COLOR_INFO,
        timestamp=discord.utils.utcnow()
    )
    
    embed.add_field(
        name="📋 Log Event (Officers Only)",
        value="Log raids, defenses, scrims, trainings, and more. "
              "Select event type, co-host, and attendees through an interactive menu.",
        inline=False
    )
    
    embed.add_field(
        name="⚔️ Challenge Player",
        value="Challenge another player to a duel.\n"
              "Command: `!challenge @opponent`",
        inline=False
    )
    
    embed.add_field(
        name="⚔️ Report Duel (Officers Only)",
        value="Report duel results after completion.\n"
              "Command: `!report_duel @winner @loser`",
        inline=False
    )
    
    embed.add_field(
        name="📊 View Progress",
        value="Check your stats, including events attended, duels won, and quiz status.\n"
              "Shows progress bars for rank requirements.",
        inline=False
    )
    
    embed.add_field(
        name="📝 Quiz (Minor I Only)",
        value="Start the rank-up quiz. Questions will be sent via DM, "
              "and your answers will be reviewed by staff.",
        inline=False
    )
    
    embed.add_field(
        name="🏠 Main Menu",
        value="Use `!menu` or `?menu` to open this interactive menu anytime!",
        inline=False
    )
    
    embed.set_footer(text="Covenant Technologies • Halo Group Bot")
    
    return embed


def create_progress_embed(member: discord.Member, stats: Dict[str, int]) -> discord.Embed:
    """Create enhanced progress embed"""
    total_att = stats["total_attended"]
    warfare_att = stats["warfare_attended"]
    training_att = stats["training_attended"]
    duels_won = stats["duels_won"]
    quiz_passed = bool(stats["quiz_passed"])

    req_events = DEFAULT_REQUIREMENTS.get("events", 0)
    req_warfare = DEFAULT_REQUIREMENTS.get("warfare", 0)
    req_training = DEFAULT_REQUIREMENTS.get("training", 0)
    req_duels = DEFAULT_REQUIREMENTS.get("duels", 0)

    embed = discord.Embed(
        title=f"📊 Progress Report: {member.display_name}",
        description="Your current stats and progress towards next rank:",
        color=UIStyle.COLOR_PRIMARY,
        timestamp=discord.utils.utcnow()
    )
    
    embed.set_thumbnail(url=member.display_avatar.url if member.display_avatar else None)

    # Calculate completion percentage
    total_progress = 0
    total_items = 4
    
    if total_att >= req_events:
        total_progress += 1
    if warfare_att >= req_warfare:
        total_progress += 1
    if training_att >= req_training:
        total_progress += 1
    if duels_won >= req_duels:
        total_progress += 1
    
    completion = int((total_progress / total_items) * 100)
    
    embed.add_field(
        name="🎯 Overall Completion",
        value=f"**{completion}%** ({total_progress}/{total_items} requirements met)\n"
              f"{make_progress_bar(total_progress, total_items, 15)}",
        inline=False
    )

    # Events Attended
    status = "✅" if total_att >= req_events else "⏳"
    embed.add_field(
        name=f"{status} Events Attended",
        value=f"**{total_att}/{req_events}** events\n{make_progress_bar(total_att, req_events, 12)}",
        inline=True
    )

    # Warfare Events
    status = "✅" if warfare_att >= req_warfare else "⏳"
    embed.add_field(
        name=f"{status} Warfare Events",
        value=f"**{warfare_att}/{req_warfare}** raids/defenses/scrims\n{make_progress_bar(warfare_att, req_warfare, 12)}",
        inline=True
    )

    # Training Events
    status = "✅" if training_att >= req_training else "⏳"
    embed.add_field(
        name=f"{status} Training Events",
        value=f"**{training_att}/{req_training}** trainings\n{make_progress_bar(training_att, req_training, 12)}",
        inline=True
    )

    # Duels Won
    status = "✅" if duels_won >= req_duels else "⏳"
    embed.add_field(
        name=f"{status} Duels Won",
        value=f"**{duels_won}/{req_duels}** duels\n{make_progress_bar(duels_won, req_duels, 12)}",
        inline=True
    )

    # Hosted stats
    embed.add_field(
        name="🎯 Events Hosted",
        value=f"Total: **{stats['total_hosted']}**\nWarfare: **{stats['warfare_hosted']}**",
        inline=True
    )

    # Quiz Status
    embed.add_field(
        name="📝 Quiz Status",
        value="✅ **Passed**" if quiz_passed else "❌ **Not Completed**",
        inline=True
    )

    embed.set_footer(text="Covenant Technologies • Keep up the great work!")
    
    return embed


async def start_quiz_flow(user: discord.Member, guild: discord.Guild):
    """Enhanced quiz flow with better UI"""
    try:
        dm = await user.create_dm()
    except Exception:
        return
    
    # Welcome message
    welcome_embed = create_styled_embed(
        "📝 Minor I → Major III Quiz",
        "Welcome to the rank-up quiz!\n\n"
        "**Instructions:**\n"
        "• You will be asked 5 questions\n"
        "• Type your answer and confirm it\n"
        "• You can re-answer before confirming\n"
        "• Your answers will be reviewed by staff\n\n"
        "**Ready? Let's begin!**",
        UIStyle.COLOR_PRIMARY
    )
    await dm.send(embed=welcome_embed)
    
    answers: List[str] = []

    def dm_msg_check(m: discord.Message):
        return m.author.id == user.id and isinstance(m.channel, discord.DMChannel)

    for index, question in enumerate(QUIZ_QUESTIONS, start=1):
        while True:
            question_embed = create_styled_embed(
                f"Question {index}/{len(QUIZ_QUESTIONS)}",
                question,
                UIStyle.COLOR_INFO
            )
            question_embed.set_footer(text=f"Question {index} of {len(QUIZ_QUESTIONS)} • Type your answer below")
            
            try:
                await dm.send(embed=question_embed)
                answer_msg = await bot.wait_for("message", check=dm_msg_check, timeout=300)
            except asyncio.TimeoutError:
                timeout_embed = create_styled_embed(
                    "⏱️ Quiz Timed Out",
                    "The quiz has timed out. Please run `!menu` and try again when ready.",
                    UIStyle.COLOR_ERROR
                )
                await dm.send(embed=timeout_embed)
                return

            answer_text = answer_msg.content.strip()
            
            confirm_embed = create_styled_embed(
                "Confirm Your Answer",
                f"**Your answer:**\n```{answer_text}```\n\n"
                "React with ✅ to confirm or ❌ to re-answer this question.",
                UIStyle.COLOR_WARNING
            )
            confirm_msg = await dm.send(embed=confirm_embed)

            def reaction_check(reaction: discord.Reaction, reactor: discord.User):
                return (
                    reactor.id == user.id
                    and reaction.message.id == confirm_msg.id
                    and str(reaction.emoji) in ("✅", "❌")
                )

            try:
                await confirm_msg.add_reaction("✅")
                await confirm_msg.add_reaction("❌")
            except Exception:
                pass

            try:
                reaction, reactor = await bot.wait_for(
                    "reaction_add", check=reaction_check, timeout=120
                )
            except asyncio.TimeoutError:
                timeout_embed = create_styled_embed(
                    "⏱️ Quiz Timed Out",
                    "The quiz has timed out. Please run `!menu` and try again.",
                    UIStyle.COLOR_ERROR
                )
                await dm.send(embed=timeout_embed)
                return

            if str(reaction.emoji) == "✅":
                answers.append(answer_text)
                if index < len(QUIZ_QUESTIONS):
                    progress_embed = create_styled_embed(
                        "✅ Answer Confirmed",
                        f"Moving to question {index + 1}...",
                        UIStyle.COLOR_SUCCESS
                    )
                    await dm.send(embed=progress_embed)
                break
            else:
                retry_embed = create_styled_embed(
                    "↩️ Re-answer",
                    "Please type your new answer for this question:",
                    UIStyle.COLOR_INFO
                )
                await dm.send(embed=retry_embed)

    # Send quiz to review channel
    review_channel = guild.get_channel(QUIZ_REVIEW_CHANNEL_ID)
    if review_channel is None:
        error_embed = create_styled_embed(
            "Configuration Error",
            "The review channel is not configured. Please contact an administrator.",
            UIStyle.COLOR_ERROR
        )
        await dm.send(embed=error_embed)
        return

    embed = discord.Embed(
        title=f"📝 Quiz Submission",
        description=f"**Candidate:** {user.mention} ({user.display_name})\n"
                   f"**Rank Path:** Minor I ➜ Major III\n"
                   f"**Submitted:** {discord.utils.format_dt(discord.utils.utcnow(), 'R')}",
        color=UIStyle.COLOR_PRIMARY,
        timestamp=discord.utils.utcnow()
    )
    
    for i, (q, a) in enumerate(zip(QUIZ_QUESTIONS, answers), start=1):
        embed.add_field(
            name=f"📌 Question {i}",
            value=f"*{q}*",
            inline=False
        )
        embed.add_field(
            name="💬 Answer",
            value=f"```{a}```",
            inline=False
        )

    embed.set_footer(text=f"User ID: {user.id}")
    embed.set_thumbnail(url=user.display_avatar.url if user.display_avatar else None)

    msg = await review_channel.send(
        content="@here New quiz submission for review!",
        embed=embed
    )
    try:
        await msg.add_reaction("✅")  # pass
        await msg.add_reaction("❌")  # fail
    except Exception:
        pass

    completion_embed = create_styled_embed(
        "🎉 Quiz Complete!",
        "Your quiz has been submitted for review by staff.\n\n"
        "You will receive a DM notification once your quiz has been reviewed.\n\n"
        "Thank you for your patience!",
        UIStyle.COLOR_SUCCESS
    )
    await dm.send(embed=completion_embed)


# =========================
# PERMISSION HELPERS
# =========================

def has_any_role(member: discord.Member, role_ids: List[int]) -> bool:
    return any(r.id in role_ids for r in member.roles)


def is_officer(member: discord.Member) -> bool:
    return has_any_role(member, OFFICER_ROLE_IDS)


# =========================
# BOT EVENTS
# =========================

@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    logger.info("Bot is ready with enhanced UI system!")
    logger.info("------")
    
    # Set bot status
    activity = discord.Activity(
        type=discord.ActivityType.watching,
        name="for !menu | Enhanced UI System"
    )
    await bot.change_presence(activity=activity)


@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    """
    Handles quiz review reactions in the review channel.
    ✅ = pass
    ❌ = fail
    """
    if payload.user_id == bot.user.id:
        return

    if payload.channel_id != QUIZ_REVIEW_CHANNEL_ID:
        return

    emoji = str(payload.emoji)
    if emoji not in ("✅", "❌"):
        return

    guild = bot.get_guild(payload.guild_id)
    if guild is None:
        return

    member = guild.get_member(payload.user_id)
    if member is None:
        try:
            member = await guild.fetch_member(payload.user_id)
        except Exception:
            return

    if not has_any_role(member, QUIZ_REVIEWER_ROLE_IDS):
        # Remove unauthorized reaction
        channel = bot.get_channel(payload.channel_id)
        if isinstance(channel, discord.TextChannel):
            try:
                msg = await channel.fetch_message(payload.message_id)
                await msg.remove_reaction(payload.emoji, member)
            except Exception:
                pass
        return

    channel = bot.get_channel(payload.channel_id)
    if not isinstance(channel, discord.TextChannel):
        return

    try:
        message = await channel.fetch_message(payload.message_id)
    except Exception:
        return

    if not message.embeds:
        return
    embed = message.embeds[0]

    # We encode the user id in the footer like "User ID: 123456789"
    if not embed.footer or not embed.footer.text:
        return

    footer_text = embed.footer.text
    if "User ID:" not in footer_text:
        return

    try:
        user_id_str = footer_text.split("User ID:")[-1].strip()
        target_user_id = int(user_id_str)
    except ValueError:
        return

    # Apply result
    passed = emoji == "✅"
    await set_quiz_passed(target_user_id, passed)

    target_user = guild.get_member(target_user_id)
    status_str = "PASSED" if passed else "FAILED"

    try:
        if passed:
            review_embed = create_styled_embed(
                "✅ Quiz Approved",
                f"**Candidate:** <@{target_user_id}>\n"
                f"**Reviewed by:** {member.mention}\n"
                f"**Result:** PASSED ✅\n\n"
                "Congratulations to the candidate!",
                UIStyle.COLOR_SUCCESS
            )
        else:
            review_embed = create_styled_embed(
                "❌ Quiz Not Approved",
                f"**Candidate:** <@{target_user_id}>\n"
                f"**Reviewed by:** {member.mention}\n"
                f"**Result:** FAILED ❌\n\n"
                "The candidate may retake the quiz.",
                UIStyle.COLOR_ERROR
            )
        await message.reply(embed=review_embed)
    except Exception:
        pass

    # Notify user via DM
    if target_user:
        try:
            dm = await target_user.create_dm()
            if passed:
                dm_embed = create_styled_embed(
                    "🎉 Quiz Passed!",
                    f"Congratulations! Your quiz has been reviewed and **PASSED**!\n\n"
                    f"**Reviewed by:** {member.mention}\n\n"
                    "You are one step closer to your next rank! 🚀",
                    UIStyle.COLOR_SUCCESS
                )
            else:
                dm_embed = create_styled_embed(
                    "Quiz Result",
                    f"Your quiz has been reviewed and did not pass this time.\n\n"
                    f"**Reviewed by:** {member.mention}\n\n"
                    "Don't worry! You can retake the quiz when you're ready. "
                    "Use `!menu` and select 'Start Quiz' to try again.",
                    UIStyle.COLOR_WARNING
                )
            await dm.send(embed=dm_embed)
        except Exception:
            pass


# =========================
# COMMANDS
# =========================

@bot.command(name="menu")
async def menu_command(ctx: commands.Context):
    """
    !menu or ?menu
    Opens the main interactive menu with all bot features.
    """
    if not isinstance(ctx.author, discord.Member):
        await ctx.send("This command must be used in a server.")
        return
    
    is_officer_user = is_officer(ctx.author)
    view = MainMenuView(ctx)
    embed = create_main_menu_embed(ctx.author, is_officer_user)
    
    message = await ctx.send(embed=embed, view=view)
    view.message = message


@bot.command(name="help")
async def help_command(ctx: commands.Context):
    """
    !help or ?help
    Shows comprehensive help information.
    """
    embed = create_help_embed()
    await ctx.send(embed=embed)


@bot.command(name="stats")
async def stats_command(ctx: commands.Context, member: Optional[discord.Member] = None):
    """
    !stats [@member]
    Alias for !progress - shows user statistics and progress.
    """
    await progress_command(ctx, member)


@bot.command(name="log_event")
async def log_event_command(ctx: commands.Context):
    """
    !log_event
    Now redirects to the enhanced menu system for a better experience.
    Officers can use the interactive menu to log events.
    """
    if not isinstance(ctx.author, discord.Member) or not is_officer(ctx.author):
        embed = create_styled_embed(
            "🔒 Permission Denied",
            "Only officers can log events.",
            UIStyle.COLOR_ERROR
        )
        await ctx.reply(embed=embed)
        return
    
    # Redirect to menu for better UX
    redirect_embed = create_styled_embed(
        "📋 Enhanced Event Logging",
        "Event logging is now available through our interactive menu system!\n\n"
        "Use `!menu` or `?menu` to access the new interface with:\n"
        "• Visual event type selection\n"
        "• Easy co-host selection\n"
        "• Multi-select attendee picker\n"
        "• Instant confirmation\n\n"
        "**Or continue with the text-based version below...**",
        UIStyle.COLOR_INFO
    )
    await ctx.send(embed=redirect_embed)
    
    # Continue with legacy flow if they prefer
    if not isinstance(ctx.author, discord.Member) or not is_officer(ctx.author):
        return

    event_types = [
        "raid",
        "defense",
        "scrim",
        "training",
        "gamenight",
        "recruitment",
        "other",
    ]

    def msg_check(m: discord.Message):
        return m.author == ctx.author and m.channel == ctx.channel

    # Step 1: choose event type
    type_list = "\n".join(
        f"{i+1}. {name.capitalize()}" for i, name in enumerate(event_types)
    )
    await ctx.send(
        "Select event type by number or name:\n" + type_list
    )

    try:
        reply = await bot.wait_for("message", check=msg_check, timeout=60)
    except asyncio.TimeoutError:
        await ctx.send("Timed out waiting for event type.")
        return

    content = reply.content.strip().lower()

    selected_type: Optional[str] = None
    if content.isdigit():
        idx = int(content) - 1
        if 0 <= idx < len(event_types):
            selected_type = event_types[idx]
    else:
        if content in event_types:
            selected_type = content

    if not selected_type:
        await ctx.send("Invalid event type. Aborting.")
        return

    # Step 2: co-host
    await ctx.send("Mention your co-host, or type `none` if there is no co-host.")

    try:
        reply = await bot.wait_for("message", check=msg_check, timeout=60)
    except asyncio.TimeoutError:
        await ctx.send("Timed out waiting for co-host.")
        return

    cohost_id: Optional[int] = None
    if reply.content.strip().lower() != "none":
        if reply.mentions:
            cohost_id = reply.mentions[0].id
        else:
            await ctx.send("No valid mention detected. Assuming no co-host.")

    # Step 3: attendees
    await ctx.send(
        "Now mention all attendees.\n"
        "You can mention multiple people per message.\n"
        "Type `done` when finished."
    )

    attendee_ids: List[int] = []

    while True:
        try:
            msg = await bot.wait_for("message", check=msg_check, timeout=180)
        except asyncio.TimeoutError:
            await ctx.send("Timed out waiting for attendees. Aborting.")
            return

        if msg.content.strip().lower() == "done":
            break

        if msg.mentions:
            for m in msg.mentions:
                attendee_ids.append(m.id)
        else:
            await ctx.send("No mentions in that message – try again or type `done`.")

    # Ensure host and cohost also count as attendees
    attendee_ids.append(ctx.author.id)
    if cohost_id:
        attendee_ids.append(cohost_id)

    event_id = await log_event(
        selected_type,
        ctx.author.id,
        cohost_id,
        attendee_ids,
    )

    await ctx.send(
        f"Event logged (ID: `{event_id}`) "
        f"type: **{selected_type.capitalize()}**, "
        f"host: {ctx.author.mention}."
    )


@bot.command(name="challenge")
async def challenge_command(ctx: commands.Context, opponent: Optional[discord.Member] = None):
    """
    !challenge @user
    Asks the opponent to accept/decline with an enhanced UI.
    If accepted, DM both users with a placeholder link.
    """
    if opponent is None:
        embed = create_styled_embed(
            "⚔️ Challenge Command",
            "You need to mention someone to challenge!\n\n"
            "**Usage:** `!challenge @user`\n"
            "**Example:** `!challenge @PlayerName`",
            UIStyle.COLOR_ERROR
        )
        await ctx.send(embed=embed)
        return

    if opponent.bot:
        embed = create_styled_embed(
            "Invalid Target",
            "You cannot challenge a bot!",
            UIStyle.COLOR_ERROR
        )
        await ctx.send(embed=embed)
        return

    if opponent.id == ctx.author.id:
        embed = create_styled_embed(
            "Invalid Target",
            "You cannot challenge yourself!",
            UIStyle.COLOR_ERROR
        )
        await ctx.send(embed=embed)
        return

    def response_check(m: discord.Message):
        return (
            m.author.id == opponent.id
            and m.channel == ctx.channel
            and m.content.lower() in ("yes", "no", "y", "n", "accept", "decline")
        )

    challenge_embed = create_styled_embed(
        "⚔️ Duel Challenge!",
        f"{opponent.mention}, you have been challenged to a duel by {ctx.author.mention}!\n\n"
        "**Respond with:**\n"
        "• `yes` or `accept` to accept the challenge\n"
        "• `no` or `decline` to decline\n\n"
        f"⏱️ You have 60 seconds to respond...",
        UIStyle.COLOR_WARNING
    )
    challenge_embed.set_thumbnail(url=ctx.author.display_avatar.url if ctx.author.display_avatar else None)
    
    await ctx.send(embed=challenge_embed)

    try:
        reply = await bot.wait_for("message", check=response_check, timeout=60)
    except asyncio.TimeoutError:
        timeout_embed = create_styled_embed(
            "⏱️ Challenge Expired",
            f"{opponent.mention} did not respond in time.\n\n"
            f"The duel challenge has been cancelled.",
            UIStyle.COLOR_ERROR
        )
        await ctx.send(embed=timeout_embed)
        return

    answer = reply.content.lower()
    if answer in ("no", "n", "decline"):
        declined_embed = create_styled_embed(
            "❌ Challenge Declined",
            f"{opponent.mention} has declined the duel challenge.",
            UIStyle.COLOR_ERROR
        )
        await ctx.send(embed=declined_embed)
        return

    # Accepted
    accepted_embed = create_styled_embed(
        "✅ Challenge Accepted!",
        f"{opponent.mention} has accepted the duel!\n\n"
        "📨 Both players will receive a DM with the duel link.",
        UIStyle.COLOR_SUCCESS
    )
    await ctx.send(embed=accepted_embed)

    for user in (ctx.author, opponent):
        try:
            dm = await user.create_dm()
            dm_embed = create_styled_embed(
                "⚔️ Duel Information",
                f"**Match:** {ctx.author.mention} vs {opponent.mention}\n\n"
                f"**Duel Link:** {DUEL_PLACEHOLDER_LINK}\n\n"
                "Good luck! May the best player win! 🎮",
                UIStyle.COLOR_PRIMARY
            )
            dm_embed.add_field(
                name="📋 After the Duel",
                value="An officer will use `!report_duel` to log the results.",
                inline=False
            )
            await dm.send(embed=dm_embed)
        except Exception:
            pass


@bot.command(name="report_duel")
async def report_duel_command(
    ctx: commands.Context,
    winner: Optional[discord.Member] = None,
    loser: Optional[discord.Member] = None,
):
    """
    !report_duel @winner @loser
    Logs the duel winner to the database (+1 duel for winner).
    Restricted to officers.
    """
    if not isinstance(ctx.author, discord.Member) or not is_officer(ctx.author):
        embed = create_styled_embed(
            "🔒 Permission Denied",
            "Only officers can report duel results.",
            UIStyle.COLOR_ERROR
        )
        await ctx.reply(embed=embed)
        return

    if not winner or not loser:
        embed = create_styled_embed(
            "⚔️ Report Duel Result",
            "You need to mention both the winner and loser!\n\n"
            "**Usage:** `!report_duel @winner @loser`\n"
            "**Example:** `!report_duel @John @Jane`",
            UIStyle.COLOR_ERROR
        )
        await ctx.send(embed=embed)
        return

    if winner.id == loser.id:
        embed = create_styled_embed(
            "Invalid Result",
            "Winner and loser cannot be the same person!",
            UIStyle.COLOR_ERROR
        )
        await ctx.send(embed=embed)
        return

    await log_duel_result(winner.id, loser.id)
    
    result_embed = create_styled_embed(
        "✅ Duel Result Recorded",
        f"**Winner:** {winner.mention} 🏆\n"
        f"**Loser:** {loser.mention}\n\n"
        f"Recorded by: {ctx.author.mention}",
        UIStyle.COLOR_SUCCESS
    )
    result_embed.set_thumbnail(url=winner.display_avatar.url if winner.display_avatar else None)
    
    await ctx.send(embed=result_embed)
    
    # Notify participants
    for user, is_winner in [(winner, True), (loser, False)]:
        try:
            dm = await user.create_dm()
            if is_winner:
                dm_embed = create_styled_embed(
                    "🏆 Duel Victory!",
                    f"Congratulations! Your duel victory has been recorded.\n\n"
                    f"**Opponent:** {loser.mention}\n"
                    f"**Recorded by:** {ctx.author.mention}",
                    UIStyle.COLOR_SUCCESS
                )
            else:
                dm_embed = create_styled_embed(
                    "⚔️ Duel Result",
                    f"Your duel result has been recorded.\n\n"
                    f"**Opponent:** {winner.mention}\n"
                    f"**Recorded by:** {ctx.author.mention}",
                    UIStyle.COLOR_INFO
                )
            await dm.send(embed=dm_embed)
        except Exception:
            pass


@bot.command(name="quiz")
async def quiz_command(ctx: commands.Context):
    """
    ?quiz (or !quiz)
    Can only be run by the Minor I role (MINOR_I_ROLE_ID).
    DMs the caller a 5-question quiz with enhanced UI.
    Quiz is then posted to review channel where staff mark pass/fail via reactions.
    """
    if not isinstance(ctx.author, discord.Member):
        embed = create_styled_embed(
            "Server Only",
            "This command must be used in a server.",
            UIStyle.COLOR_ERROR
        )
        await ctx.send(embed=embed)
        return

    if not any(r.id == MINOR_I_ROLE_ID for r in ctx.author.roles):
        embed = create_styled_embed(
            "🔒 Permission Denied",
            "Only Minor I members may start this quiz.",
            UIStyle.COLOR_ERROR
        )
        await ctx.send(embed=embed)
        return

    user = ctx.author
    try:
        dm = await user.create_dm()
    except Exception:
        embed = create_styled_embed(
            "DM Error",
            "Unable to send you a DM. Please enable DMs from this server in your privacy settings.",
            UIStyle.COLOR_ERROR
        )
        await ctx.send(embed=embed)
        return

    notification_embed = create_styled_embed(
        "📨 Quiz Started!",
        f"{user.mention}, check your DMs!\n\n"
        "The quiz has been sent to you privately.",
        UIStyle.COLOR_SUCCESS
    )
    await ctx.send(embed=notification_embed)
    
    await start_quiz_flow(user, ctx.guild)


@bot.command(name="progress")
async def progress_command(
    ctx: commands.Context,
    member: Optional[discord.Member] = None,
):
    """
    !progress [@member]
    Shows attendance / duel / quiz stats with enhanced UI and progress bars
    against DEFAULT_REQUIREMENTS.
    """
    if member is None:
        if isinstance(ctx.author, discord.Member):
            member = ctx.author
        else:
            embed = create_styled_embed(
                "Member Required",
                "Specify a member when using this command outside a server.",
                UIStyle.COLOR_ERROR
            )
            await ctx.send(embed=embed)
            return

    # Send loading message
    loading_embed = create_styled_embed(
        "⏳ Loading Progress...",
        f"Fetching stats for {member.mention}...",
        UIStyle.COLOR_INFO
    )
    loading_msg = await ctx.send(embed=loading_embed)
    
    stats = await get_user_stats(member.id)
    embed = create_progress_embed(member, stats)
    
    await loading_msg.edit(embed=embed)


# =========================
# MAIN ENTRY
# =========================

async def main():
    await init_db()

    if not DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKEN environment variable not set.")

    await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())