import os
import asyncio
import logging
from typing import List, Optional, Dict

import discord
from discord.ext import commands
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
    logger.info("------")


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
        await message.reply(
            f"Quiz for <@{target_user_id}> marked as **{status_str}** by {member.mention}."
        )
    except Exception:
        pass

    # Notify user via DM
    if target_user:
        try:
            dm = await target_user.create_dm()
            await dm.send(f"Your quiz has been reviewed: **{status_str}**.")
        except Exception:
            pass


# =========================
# COMMANDS
# =========================

@bot.command(name="log_event")
async def log_event_command(ctx: commands.Context):
    """
    !log_event
    Only officers (OFFICER_ROLE_IDS) can run.
    Interactive flow:
      1) Pick event type
      2) Co-host mention or none
      3) Attendees via mentions until 'done'
    """
    if not isinstance(ctx.author, discord.Member) or not is_officer(ctx.author):
        await ctx.reply("You do not have permission to log events.")
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
    Asks the opponent to accept/decline.
    If accepted, DM both users with a placeholder link.
    """
    if opponent is None:
        await ctx.send("Mention the person you want to challenge. Usage: `!challenge @user`")
        return

    if opponent.bot:
        await ctx.send("You cannot challenge a bot.")
        return

    if opponent.id == ctx.author.id:
        await ctx.send("You cannot challenge yourself.")
        return

    def response_check(m: discord.Message):
        return (
            m.author.id == opponent.id
            and m.channel == ctx.channel
            and m.content.lower() in ("yes", "no", "y", "n")
        )

    await ctx.send(
        f"{opponent.mention}, {ctx.author.mention} has challenged you to a duel.\n"
        "Reply with `yes` or `no`."
    )

    try:
        reply = await bot.wait_for("message", check=response_check, timeout=60)
    except asyncio.TimeoutError:
        await ctx.send(f"{opponent.mention} did not respond in time. Duel cancelled.")
        return

    answer = reply.content.lower()
    if answer in ("no", "n"):
        await ctx.send("Duel declined.")
        return

    # Accepted
    await ctx.send("Duel accepted! Sending DM with duel link.")

    for user in (ctx.author, opponent):
        try:
            dm = await user.create_dm()
            await dm.send(
                f"You have a duel between {ctx.author.mention} and {opponent.mention}.\n"
                f"Use this link to set up the duel: {DUEL_PLACEHOLDER_LINK}"
            )
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
        await ctx.reply("You do not have permission to report duels.")
        return

    if not winner or not loser:
        await ctx.send("Usage: `!report_duel @winner @loser`")
        return

    if winner.id == loser.id:
        await ctx.send("Winner and loser cannot be the same.")
        return

    await log_duel_result(winner.id, loser.id)
    await ctx.send(
        f"Duel result recorded: Winner {winner.mention}, Loser {loser.mention}."
    )


@bot.command(name="quiz")
async def quiz_command(ctx: commands.Context):
    """
    ?quiz (or !quiz)
    Can only be run by the Minor I role (MINOR_I_ROLE_ID).
    DMs the caller a 5-question quiz with reaction-based answer confirmation.
    Quiz is then posted to review channel where staff mark pass/fail via reactions.
    """
    if not isinstance(ctx.author, discord.Member):
        await ctx.send("This command must be used in a server.")
        return

    if not any(r.id == MINOR_I_ROLE_ID for r in ctx.author.roles):
        await ctx.send("Only Minor I may start this quiz.")
        return

    user = ctx.author
    try:
        dm = await user.create_dm()
    except Exception:
        await ctx.send("Unable to DM you. Please enable DMs from this server.")
        return

    await ctx.send(f"{user.mention}, check your DMs for the quiz.")
    answers: List[str] = []

    def dm_msg_check(m: discord.Message):
        return m.author.id == user.id and isinstance(m.channel, discord.DMChannel)

    for index, question in enumerate(QUIZ_QUESTIONS, start=1):
        while True:
            try:
                await dm.send(f"**Question {index}**:\n{question}")
                answer_msg = await bot.wait_for("message", check=dm_msg_check, timeout=300)
            except asyncio.TimeoutError:
                await dm.send("Quiz timed out. Please run the command again if needed.")
                return

            answer_text = answer_msg.content.strip()
            confirm_msg = await dm.send(
                f"Your answer:\n```{answer_text}```\n"
                "React with ✅ to confirm or ❌ to re-answer."
            )

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
                await dm.send("Timed out waiting for confirmation. Quiz cancelled.")
                return

            if str(reaction.emoji) == "✅":
                answers.append(answer_text)
                break
            else:
                await dm.send("Okay, re-answer this question.")

    # Send quiz to review channel
    guild = ctx.guild
    review_channel = guild.get_text_channel(QUIZ_REVIEW_CHANNEL_ID)
    if review_channel is None:
        await dm.send(
            "Quiz finished, but the review channel is not configured correctly. "
            "Please contact an administrator."
        )
        return

    embed = discord.Embed(
        title=f"Quiz Submission - {user} ({user.id})",
        description=f"Rank path: Minor I ➜ Major III",
        color=discord.Color.purple(),
    )
    for i, (q, a) in enumerate(zip(QUIZ_QUESTIONS, answers), start=1):
        field_name = f"Q{i}: {q}"
        field_value = f"```{a}```"
        embed.add_field(name=field_name, value=field_value, inline=False)

    embed.set_footer(text=f"User ID: {user.id}")

    msg = await review_channel.send(embed=embed)
    try:
        await msg.add_reaction("✅")  # pass
        await msg.add_reaction("❌")  # fail
    except Exception:
        pass

    await dm.send(
        "Your quiz has been submitted for review. You will be notified once it is marked."
    )


@bot.command(name="progress")
async def progress_command(
    ctx: commands.Context,
    member: Optional[discord.Member] = None,
):
    """
    !progress [@member]
    Shows attendance / duel / quiz stats, plus simple progress bars
    against DEFAULT_REQUIREMENTS.
    """
    if member is None:
        if isinstance(ctx.author, discord.Member):
            member = ctx.author
        else:
            await ctx.send("Specify a member when using this command outside a server.")
            return

    stats = await get_user_stats(member.id)

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
        title=f"Progress for {member.display_name}",
        color=discord.Color.dark_purple(),
    )

    # Attendance (as participant)
    embed.add_field(
        name="Events Attended",
        value=(
            f"**{total_att}/{req_events}** events\n"
            f"{make_progress_bar(total_att, req_events)}"
        ),
        inline=False,
    )

    embed.add_field(
        name="Warfare Events Attended (Raids/Defences/Scrims)",
        value=(
            f"**{warfare_att}/{req_warfare}** warfare events\n"
            f"{make_progress_bar(warfare_att, req_warfare)}"
        ),
        inline=False,
    )

    embed.add_field(
        name="Training Events Attended",
        value=(
            f"**{training_att}/{req_training}** trainings\n"
            f"{make_progress_bar(training_att, req_training)}"
        ),
        inline=False,
    )

    embed.add_field(
        name="Duels Won",
        value=(
            f"**{duels_won}/{req_duels}** duels\n"
            f"{make_progress_bar(duels_won, req_duels)}"
        ),
        inline=False,
    )

    # Hosted stats (informational)
    embed.add_field(
        name="Events Hosted (Info)",
        value=(
            f"Total hosted: **{stats['total_hosted']}**\n"
            f"Warfare hosted: **{stats['warfare_hosted']}**"
        ),
        inline=False,
    )

    embed.add_field(
        name="Quiz Status",
        value="✅ Passed" if quiz_passed else "❌ Not passed yet",
        inline=False,
    )

    await ctx.send(embed=embed)


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