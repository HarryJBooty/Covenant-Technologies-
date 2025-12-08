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

# Roles that are allowed to mark quizzes as pass/fail
QUIZ_REVIEWER_ROLE_IDS = [
    1129557455244902459,  # e.g. High Command, Inquisitors etc.
    # ...
]

# Channel where completed quiz attempts are sent for review
QUIZ_REVIEW_CHANNEL_ID = 1129557456947781649  # REPLACE with real channel ID

# Channel where promotion notifications are sent (can be same as quiz review)
PROMOTION_CHANNEL_ID = 1129557456947781649  # REPLACE with real channel ID

# High Command role ID to ping for promotions
HIGH_COMMAND_ROLE_ID = 1440166465906016306  # REPLACE with HiCom role ID

# =========================
# RANK SYSTEM CONFIGURATION
# =========================

# Define all rank role IDs (REPLACE with actual role IDs)
RANK_ROLE_IDS = {
    "minor_iii": 1129557455211339825,   # Minor III
    "minor_ii": 1129557455211339826,    # Minor II
    "minor_i": 1129557455244902451,     # Minor I
    "major_iii": 1129557455244902452,   # Major III
    "major_ii": 1129557455244902455,    # Major II
    "major_i": 1129557455244902456,     # Major I
    "ultra_iii": 1149841811884486676,   # Ultra III (Officer apps open)
    "ultra_ii": 1155175565171634297,    # Ultra II
    "ultra_i": 1155175631286444143,     # Ultra I
    "champion": 1000000000000000010,    # Champion
}

# Define rank progression and requirements
RANK_REQUIREMENTS = {
    RANK_ROLE_IDS["minor_iii"]: {
        "current_rank": "Minor III",
        "next_rank": "Minor II",
        "requirements": {
            "events": 5,
            "warfare": 0,
            "training": 0,
            "duels": 0,
            "quiz": False
        }
    },
    RANK_ROLE_IDS["minor_ii"]: {
        "current_rank": "Minor II",
        "next_rank": "Minor I",
        "requirements": {
            "events": 7,
            "warfare": 0,
            "training": 0,
            "duels": 0,
            "quiz": False
        }
    },
    RANK_ROLE_IDS["minor_i"]: {
        "current_rank": "Minor I",
        "next_rank": "Major III",
        "requirements": {
            "events": 8,
            "warfare": 0,
            "training": 0,
            "duels": 0,
            "quiz": True
        }
    },
    RANK_ROLE_IDS["major_iii"]: {
        "current_rank": "Major III",
        "next_rank": "Major II",
        "requirements": {
            "events": 0,
            "warfare": 3,
            "training": 3,
            "duels": 0,
            "quiz": False
        }
    },
    RANK_ROLE_IDS["major_ii"]: {
        "current_rank": "Major II",
        "next_rank": "Major I",
        "requirements": {
            "events": 0,
            "warfare": 5,
            "training": 3,
            "duels": 0,
            "quiz": False
        }
    },
    RANK_ROLE_IDS["major_i"]: {
        "current_rank": "Major I",
        "next_rank": "Ultra III",
        "requirements": {
            "events": 0,
            "warfare": 3,
            "training": 2,
            "duels": 1,
            "quiz": False
        }
    },
    RANK_ROLE_IDS["ultra_iii"]: {
        "current_rank": "Ultra III",
        "next_rank": "Ultra II",
        "requirements": {
            "events": 0,
            "warfare": 4,
            "training": 2,
            "duels": 1,
            "quiz": False
        },
        "note": "Officer Applications Open"
    },
    RANK_ROLE_IDS["ultra_ii"]: {
        "current_rank": "Ultra II",
        "next_rank": "Ultra I",
        "requirements": {
            "events": 0,
            "warfare": 3,
            "training": 2,
            "duels": 3,
            "quiz": False
        }
    },
    RANK_ROLE_IDS["ultra_i"]: {
        "current_rank": "Ultra I",
        "next_rank": "Champion",
        "requirements": {
            "events": 0,
            "warfare": 2,
            "training": 2,
            "duels": 5,
            "quiz": False
        }
    },
    RANK_ROLE_IDS["champion"]: {
        "current_rank": "Champion",
        "next_rank": None,
        "requirements": {},
        "note": "Maximum Rank Achieved!"
    }
}

# Helper to get user's current rank
def get_user_rank(member: discord.Member) -> Optional[Tuple[int, Dict]]:
    """Returns (role_id, rank_info) for the user's highest rank role, or None"""
    for role in member.roles:
        if role.id in RANK_REQUIREMENTS:
            return (role.id, RANK_REQUIREMENTS[role.id])
    return None


async def check_promotion_eligible(member: discord.Member, stats: Dict[str, int], guild: discord.Guild):
    """Check if user meets requirements for next rank and send notification to HiCom"""
    rank_info = get_user_rank(member)
    if not rank_info:
        return
    
    role_id, rank_data = rank_info
    next_rank = rank_data.get("next_rank")
    
    # No promotion if at max rank
    if not next_rank:
        return
    
    requirements = rank_data["requirements"]
    current_rank = rank_data["current_rank"]
    
    # Check if all requirements are met
    total_att = stats["total_attended"]
    warfare_att = stats["warfare_attended"]
    training_att = stats["training_attended"]
    duels_won = stats["duels_won"]
    quiz_passed = bool(stats["quiz_passed"])
    
    req_events = requirements.get("events", 0)
    req_warfare = requirements.get("warfare", 0)
    req_training = requirements.get("training", 0)
    req_duels = requirements.get("duels", 0)
    req_quiz = requirements.get("quiz", False)
    
    # Check each requirement
    if req_events > 0 and total_att < req_events:
        return
    if req_warfare > 0 and warfare_att < req_warfare:
        return
    if req_training > 0 and training_att < req_training:
        return
    if req_duels > 0 and duels_won < req_duels:
        return
    if req_quiz and not quiz_passed:
        return
    
    # All requirements met! Send promotion notification
    promotion_channel = guild.get_channel(PROMOTION_CHANNEL_ID)
    if promotion_channel:
        hicom_role = guild.get_role(HIGH_COMMAND_ROLE_ID)
        ping_text = hicom_role.mention if hicom_role else "@High Command"
        
        promotion_embed = create_styled_embed(
            "🎉 Promotion Ready!",
            f"{ping_text}\n\n"
            f"**Member:** {member.mention} ({member.display_name})\n"
            f"**Current Rank:** {current_rank}\n"
            f"**Ready for:** {next_rank}\n\n"
            f"**Requirements Met:**",
            UIStyle.COLOR_SUCCESS
        )
        
        # Show what they completed
        requirements_text = []
        if req_events > 0:
            requirements_text.append(f"✅ Events: {total_att}/{req_events}")
        if req_warfare > 0:
            requirements_text.append(f"✅ Warfare: {warfare_att}/{req_warfare}")
        if req_training > 0:
            requirements_text.append(f"✅ Training: {training_att}/{req_training}")
        if req_duels > 0:
            requirements_text.append(f"✅ Duels: {duels_won}/{req_duels}")
        if req_quiz:
            requirements_text.append(f"✅ Quiz: Passed")
        
        promotion_embed.add_field(
            name="Completed Requirements",
            value="\n".join(requirements_text),
            inline=False
        )
        
        promotion_embed.set_thumbnail(url=member.display_avatar.url if member.display_avatar else None)
        
        try:
            await promotion_channel.send(
                content=ping_text,
                embed=promotion_embed
            )
        except Exception as e:
            logger.error(f"Failed to send promotion notification: {e}")

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
        await interaction.response.defer()
        view = DuelReportView(interaction)
        embed = create_styled_embed(
            "⚔️ Report Duel Result",
            "Select the winner and loser from the dropdowns below:",
            UIStyle.COLOR_PRIMARY
        )
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class ChallengeButton(ui.Button):
    def __init__(self):
        super().__init__(
            label="Challenge Player",
            style=discord.ButtonStyle.success,
            emoji="⚔️",
            custom_id="challenge"
        )
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        view = ChallengeSelectView(interaction)
        embed = create_styled_embed(
            "⚔️ Challenge a Player",
            "Select the player you want to challenge from the dropdown below:",
            UIStyle.COLOR_PRIMARY
        )
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


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
        
        # Check if user is eligible for promotion
        if isinstance(interaction.user, discord.Member):
            await check_promotion_eligible(interaction.user, stats, interaction.guild)
        
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
        
        # Check if user has Minor I role
        if not any(r.id == RANK_ROLE_IDS["minor_i"] for r in interaction.user.roles):
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


class SupervisorSelectView(ui.View):
    """Select supervising officer for duel"""
    
    def __init__(self, opponent: discord.Member, challenger: discord.User, channel: discord.TextChannel, duel_link: str):
        super().__init__(timeout=180)
        self.opponent = opponent
        self.challenger = challenger
        self.channel = channel
        self.duel_link = duel_link
        self.supervisor = None
        
        self.add_item(SupervisorSelect())
        
        no_supervisor_btn = ui.Button(label="No Supervisor (Optional)", style=discord.ButtonStyle.secondary)
        no_supervisor_btn.callback = self.no_supervisor_callback
        self.add_item(no_supervisor_btn)
    
    async def no_supervisor_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self.proceed_with_challenge(interaction)
    
    async def proceed_with_challenge(self, interaction: discord.Interaction):
        # Send challenge to the channel
        def response_check(m: discord.Message):
            return (
                m.author.id == self.opponent.id
                and m.channel == self.channel
                and m.content.lower() in ("yes", "no", "y", "n", "accept", "decline")
            )

        supervisor_text = f"\n**Supervising Officer:** {self.supervisor.mention}" if self.supervisor else ""
        
        challenge_embed = create_styled_embed(
            "⚔️ Duel Challenge!",
            f"{self.opponent.mention}, you have been challenged to a duel by {self.challenger.mention}!{supervisor_text}\n\n"
            "**Respond with:**\n"
            "• `yes` or `accept` to accept the challenge\n"
            "• `no` or `decline` to decline\n\n"
            f"⏱️ You have 60 seconds to respond...",
            UIStyle.COLOR_WARNING
        )
        challenge_embed.set_thumbnail(url=self.challenger.display_avatar.url if self.challenger.display_avatar else None)
        
        await self.channel.send(embed=challenge_embed)

        try:
            reply = await bot.wait_for("message", check=response_check, timeout=60)
        except asyncio.TimeoutError:
            timeout_embed = create_styled_embed(
                "⏱️ Challenge Expired",
                f"{self.opponent.mention} did not respond in time.\n\n"
                f"The duel challenge has been cancelled.",
                UIStyle.COLOR_ERROR
            )
            await self.channel.send(embed=timeout_embed)
            return

        answer = reply.content.lower()
        if answer in ("no", "n", "decline"):
            declined_embed = create_styled_embed(
                "❌ Challenge Declined",
                f"{self.opponent.mention} has declined the duel challenge.",
                UIStyle.COLOR_ERROR
            )
            await self.channel.send(embed=declined_embed)
            return

        # Accepted
        accepted_embed = create_styled_embed(
            "✅ Challenge Accepted!",
            f"{self.opponent.mention} has accepted the duel!\n\n"
            "📨 Both players and the supervising officer will receive a DM with the duel link.",
            UIStyle.COLOR_SUCCESS
        )
        await self.channel.send(embed=accepted_embed)

        # Send DM to participants and supervisor
        recipients = [self.challenger, self.opponent]
        if self.supervisor:
            recipients.append(self.supervisor)
        
        for user in recipients:
            try:
                dm = await user.create_dm()
                
                if user == self.supervisor:
                    # Special message for supervisor
                    dm_embed = create_styled_embed(
                        "👁️ Duel Supervision Request",
                        f"You have been selected to supervise a duel!\n\n"
                        f"**Challenger:** {self.challenger.mention}\n"
                        f"**Challenged:** {self.opponent.mention}\n\n"
                        f"**Duel Link:** {self.duel_link}\n\n"
                        "Please join to observe and ensure fair play. 🛡️",
                        UIStyle.COLOR_INFO
                    )
                else:
                    # Message for participants
                    supervisor_info = f"\n**Supervising Officer:** {self.supervisor.mention}" if self.supervisor else ""
                    dm_embed = create_styled_embed(
                        "⚔️ Duel Information",
                        f"**Match:** {self.challenger.mention} vs {self.opponent.mention}{supervisor_info}\n\n"
                        f"**Duel Link:** {self.duel_link}\n\n"
                        "Good luck! May the best player win! 🎮",
                        UIStyle.COLOR_PRIMARY
                    )
                
                dm_embed.add_field(
                    name="📋 After the Duel",
                    value="An officer will use the menu to report the results.",
                    inline=False
                )
                await dm.send(embed=dm_embed)
            except Exception:
                pass


class SupervisorSelect(ui.UserSelect):
    def __init__(self):
        super().__init__(
            placeholder="Select supervising officer (optional)...",
            min_values=1,
            max_values=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        view: SupervisorSelectView = self.view
        view.supervisor = self.values[0]
        
        await interaction.response.send_message(
            embed=create_styled_embed(
                "Supervisor Selected",
                f"Supervising Officer: {view.supervisor.mention}\n\n"
                "Proceeding with challenge...",
                UIStyle.COLOR_SUCCESS
            ),
            ephemeral=True
        )
        
        await view.proceed_with_challenge(interaction)


class DuelLinkModal(ui.Modal, title="Enter Duel Link"):
    """Modal for entering custom Roblox private server link"""
    
    duel_link = ui.TextInput(
        label="Roblox Private Server Link",
        placeholder="https://www.roblox.com/games/...",
        required=True,
        style=discord.TextStyle.short,
        max_length=500
    )
    
    def __init__(self, opponent: discord.Member, challenger: discord.User, channel: discord.TextChannel):
        super().__init__()
        self.opponent = opponent
        self.challenger = challenger
        self.channel = channel
    
    async def on_submit(self, interaction: discord.Interaction):
        duel_link = self.duel_link.value.strip()
        
        # Validate it's a URL
        if not (duel_link.startswith("http://") or duel_link.startswith("https://")):
            await interaction.response.send_message(
                embed=create_styled_embed(
                    "Invalid Link",
                    "Please provide a valid URL starting with http:// or https://",
                    UIStyle.COLOR_ERROR
                ),
                ephemeral=True
            )
            return
        
        # Now ask for supervising officer
        await interaction.response.defer()
        view = SupervisorSelectView(self.opponent, self.challenger, self.channel, duel_link)
        embed = create_styled_embed(
            "👁️ Select Supervising Officer",
            "Select an officer to supervise this duel, or click 'No Supervisor' to continue without one.\n\n"
            "The supervising officer will receive the duel link and can observe the match.",
            UIStyle.COLOR_INFO
        )
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class ChallengeSelectView(ui.View):
    """Select opponent for challenge"""
    
    def __init__(self, interaction: discord.Interaction):
        super().__init__(timeout=180)
        self.interaction = interaction
        self.add_item(OpponentSelect())
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.interaction.user.id


class OpponentSelect(ui.UserSelect):
    def __init__(self):
        super().__init__(
            placeholder="Select opponent to challenge...",
            min_values=1,
            max_values=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        opponent = self.values[0]
        challenger = interaction.user
        
        if opponent.bot:
            await interaction.response.send_message(
                embed=create_styled_embed(
                    "Invalid Target",
                    "You cannot challenge a bot!",
                    UIStyle.COLOR_ERROR
                ),
                ephemeral=True
            )
            return

        if opponent.id == challenger.id:
            await interaction.response.send_message(
                embed=create_styled_embed(
                    "Invalid Target",
                    "You cannot challenge yourself!",
                    UIStyle.COLOR_ERROR
                ),
                ephemeral=True
            )
            return
        
        # Open modal for duel link input
        modal = DuelLinkModal(opponent, challenger, interaction.channel)
        await interaction.response.send_modal(modal)


class DuelReportView(ui.View):
    """Report duel results with winner/loser selection"""
    
    def __init__(self, interaction: discord.Interaction):
        super().__init__(timeout=180)
        self.interaction = interaction
        self.winner = None
        self.loser = None
        
        self.add_item(WinnerSelect())
        self.add_item(LoserSelect())
        
        submit_btn = ui.Button(label="Submit Result", style=discord.ButtonStyle.success, emoji="✅")
        submit_btn.callback = self.submit_callback
        self.add_item(submit_btn)
    
    async def submit_callback(self, interaction: discord.Interaction):
        if not self.winner or not self.loser:
            await interaction.response.send_message(
                embed=create_styled_embed(
                    "Missing Information",
                    "Please select both winner and loser before submitting.",
                    UIStyle.COLOR_WARNING
                ),
                ephemeral=True
            )
            return
        
        if self.winner.id == self.loser.id:
            await interaction.response.send_message(
                embed=create_styled_embed(
                    "Invalid Result",
                    "Winner and loser cannot be the same person!",
                    UIStyle.COLOR_ERROR
                ),
                ephemeral=True
            )
            return
        
        await interaction.response.defer()
        
        await log_duel_result(self.winner.id, self.loser.id)
        
        result_embed = create_styled_embed(
            "✅ Duel Result Recorded",
            f"**Winner:** {self.winner.mention} 🏆\n"
            f"**Loser:** {self.loser.mention}\n\n"
            f"Recorded by: {interaction.user.mention}",
            UIStyle.COLOR_SUCCESS
        )
        result_embed.set_thumbnail(url=self.winner.display_avatar.url if self.winner.display_avatar else None)
        
        await interaction.channel.send(embed=result_embed)
        
        # Notify participants
        for user, is_winner in [(self.winner, True), (self.loser, False)]:
            try:
                dm = await user.create_dm()
                if is_winner:
                    dm_embed = create_styled_embed(
                        "🏆 Duel Victory!",
                        f"Congratulations! Your duel victory has been recorded.\n\n"
                        f"**Opponent:** {self.loser.mention}\n"
                        f"**Recorded by:** {interaction.user.mention}",
                        UIStyle.COLOR_SUCCESS
                    )
                else:
                    dm_embed = create_styled_embed(
                        "⚔️ Duel Result",
                        f"Your duel result has been recorded.\n\n"
                        f"**Opponent:** {self.winner.mention}\n"
                        f"**Recorded by:** {interaction.user.mention}",
                        UIStyle.COLOR_INFO
                    )
                await dm.send(embed=dm_embed)
            except Exception:
                pass
        
        await interaction.followup.send(
            embed=create_styled_embed(
                "✅ Complete",
                "Duel result has been recorded and participants have been notified!",
                UIStyle.COLOR_SUCCESS
            ),
            ephemeral=True
        )
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.interaction.user.id


class WinnerSelect(ui.UserSelect):
    def __init__(self):
        super().__init__(
            placeholder="Select winner...",
            min_values=1,
            max_values=1,
            row=0
        )
    
    async def callback(self, interaction: discord.Interaction):
        view: DuelReportView = self.view
        view.winner = self.values[0]
        await interaction.response.send_message(
            embed=create_styled_embed(
                "Winner Selected",
                f"Winner: {view.winner.mention}\n\n"
                "Now select the loser and click 'Submit Result'.",
                UIStyle.COLOR_SUCCESS
            ),
            ephemeral=True
        )


class LoserSelect(ui.UserSelect):
    def __init__(self):
        super().__init__(
            placeholder="Select loser...",
            min_values=1,
            max_values=1,
            row=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        view: DuelReportView = self.view
        view.loser = self.values[0]
        await interaction.response.send_message(
            embed=create_styled_embed(
                "Loser Selected",
                f"Loser: {view.loser.mention}\n\n"
                "Click 'Submit Result' to record the duel.",
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
        name="🏠 Main Menu - `!menu`",
        value="Opens the interactive menu system where you can access all features:\n"
              "• Log Events (Officers)\n"
              "• Report Duels (Officers)\n"
              "• Challenge Players\n"
              "• View Progress\n"
              "• Start Quiz (Minor I)\n\n"
              "**All major features are accessed through the menu!**",
        inline=False
    )
    
    embed.add_field(
        name="📊 View Progress - `!progress` or `!stats`",
        value="Check your stats, including events attended, duels won, and quiz status.\n"
              "Shows progress bars for rank requirements.\n"
              "Usage: `!progress [@member]`",
        inline=False
    )
    
    embed.add_field(
        name="❓ Help - `!help`",
        value="Shows this help message with all available commands.",
        inline=False
    )
    
    embed.add_field(
        name="💡 Quick Start",
        value="New to the bot? Just type `!menu` to get started!\n"
              "The interactive menu guides you through all features.",
        inline=False
    )
    
    embed.set_footer(text="Covenant Technologies • Halo Group Bot")
    
    return embed


def create_progress_embed(member: discord.Member, stats: Dict[str, int]) -> discord.Embed:
    """Create enhanced progress embed with rank-specific requirements"""
    total_att = stats["total_attended"]
    warfare_att = stats["warfare_attended"]
    training_att = stats["training_attended"]
    duels_won = stats["duels_won"]
    quiz_passed = bool(stats["quiz_passed"])

    # Get user's current rank and requirements
    rank_info = get_user_rank(member)
    
    if rank_info:
        role_id, rank_data = rank_info
        current_rank = rank_data["current_rank"]
        next_rank = rank_data["next_rank"]
        requirements = rank_data["requirements"]
        note = rank_data.get("note", "")
    else:
        # Default fallback if no rank role found
        current_rank = "Unranked"
        next_rank = "Minor III"
        requirements = {"events": 0, "warfare": 0, "training": 0, "duels": 0, "quiz": False}
        note = "Join us to start your journey!"

    req_events = requirements.get("events", 0)
    req_warfare = requirements.get("warfare", 0)
    req_training = requirements.get("training", 0)
    req_duels = requirements.get("duels", 0)
    req_quiz = requirements.get("quiz", False)

    # Build description
    if next_rank:
        description = f"**Current Rank:** {current_rank}\n**Next Rank:** {next_rank}\n"
        if note:
            description += f"*{note}*\n"
        description += "\nYour progress towards the next rank:"
    else:
        description = f"**Current Rank:** {current_rank}\n{note}"

    embed = discord.Embed(
        title=f"📊 Progress Report: {member.display_name}",
        description=description,
        color=UIStyle.COLOR_PRIMARY,
        timestamp=discord.utils.utcnow()
    )
    
    embed.set_thumbnail(url=member.display_avatar.url if member.display_avatar else None)

    # Calculate completion percentage (only if there's a next rank)
    if next_rank:
        total_items = 0
        total_progress = 0
        
        if req_events > 0:
            total_items += 1
            if total_att >= req_events:
                total_progress += 1
        
        if req_warfare > 0:
            total_items += 1
            if warfare_att >= req_warfare:
                total_progress += 1
        
        if req_training > 0:
            total_items += 1
            if training_att >= req_training:
                total_progress += 1
        
        if req_duels > 0:
            total_items += 1
            if duels_won >= req_duels:
                total_progress += 1
        
        if req_quiz:
            total_items += 1
            if quiz_passed:
                total_progress += 1
        
        if total_items > 0:
            completion = int((total_progress / total_items) * 100)
            
            embed.add_field(
                name="🎯 Overall Completion",
                value=f"**{completion}%** ({total_progress}/{total_items} requirements met)\n"
                      f"{make_progress_bar(total_progress, total_items, 15)}",
                inline=False
            )

        # Events Attended (only show if required)
        if req_events > 0:
            status = "✅" if total_att >= req_events else "⏳"
            embed.add_field(
                name=f"{status} Events Attended",
                value=f"**{total_att}/{req_events}** events\n{make_progress_bar(total_att, req_events, 12)}",
                inline=True
            )

        # Warfare Events (only show if required)
        if req_warfare > 0:
            status = "✅" if warfare_att >= req_warfare else "⏳"
            embed.add_field(
                name=f"{status} Warfare Events",
                value=f"**{warfare_att}/{req_warfare}** raids/defenses/scrims\n{make_progress_bar(warfare_att, req_warfare, 12)}",
                inline=True
            )

        # Training Events (only show if required)
        if req_training > 0:
            status = "✅" if training_att >= req_training else "⏳"
            embed.add_field(
                name=f"{status} Training Events",
                value=f"**{training_att}/{req_training}** trainings\n{make_progress_bar(training_att, req_training, 12)}",
                inline=True
            )

        # Duels Won (only show if required)
        if req_duels > 0:
            status = "✅" if duels_won >= req_duels else "⏳"
            embed.add_field(
                name=f"{status} Duels Won",
                value=f"**{duels_won}/{req_duels}** duels\n{make_progress_bar(duels_won, req_duels, 12)}",
                inline=True
            )

        # Quiz Status (only show if required)
        if req_quiz:
            status = "✅" if quiz_passed else "⏳"
            embed.add_field(
                name=f"{status} Quiz Status",
                value="✅ **Passed**" if quiz_passed else "❌ **Not Completed**",
                inline=True
            )

    # Always show overall stats
    embed.add_field(
        name="📈 Overall Statistics",
        value=f"**Total Events:** {total_att}\n"
              f"**Warfare Events:** {warfare_att}\n"
              f"**Training Events:** {training_att}\n"
              f"**Duels Won:** {duels_won}\n"
              f"**Events Hosted:** {stats['total_hosted']}",
        inline=False
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
    
    # Check if user is eligible for promotion
    await check_promotion_eligible(member, stats, ctx.guild)
    
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