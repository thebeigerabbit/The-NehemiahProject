"""
/report and /help handlers.
"""
from telegram import Update
from telegram.ext import ContextTypes
from app.database import get_db
from app.services.user_service import get_user_by_telegram_id
from app.services.checkin_service import get_stats
from app.utils.time_utils import format_local
from app.handlers.base import reply, require_auth, require_no_pending_reflection
import logging

logger = logging.getLogger(__name__)

HELP_TEXT = """Accountability Bot - Command Reference

--- Authentication ---
/start       - Begin or resume your session
/signup      - Create a new account
/login       - Log in with username

--- Daily Check-In (20:00 SAST) ---
/yes         - Report a failure (relapse)
/no          - Report a clean day

--- Reflection (required after /yes) ---
/reflect
trigger: what triggered it
failure: what happened
prevention: what you will do differently
Each field: 20 to 500 characters. Be specific.

--- Urge Reporting ---
/urge reason: your reason here
- Reason must be at least 10 characters
- Max 3 urges per hour
- Partners notified immediately
- Follow-up check in 15 minutes

--- Reports ---
/report      - Your full accountability stats
/help        - This message

--- Important Rules ---
- Only ONE check-in valid per 24-hour window
- Check-in responses cannot be overwritten
- Reflection MUST be completed before other commands
- Late responses are marked invalid
- Accountability partners must be the same gender
- At least 1 partner required before account activation"""


@require_auth
@require_no_pending_reflection
async def report_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)

    with get_db() as db:
        user = get_user_by_telegram_id(db, telegram_id)
        stats = get_stats(db, user)
        # Read all user attributes inside session to avoid DetachedInstanceError
        username = user.username.replace('_', '-')
        role = user.role.value
        gender = user.gender.value

    last_failure = format_local(stats["last_failure_at"]) if stats["last_failure_at"] else "Never"
    streak_display = f"{stats['streak']} day{'s' if stats['streak'] != 1 else ''}"

    await reply(update,
        f"Your Accountability Report\n"
        f"---\n"
        f"User: {username} | {role} | {gender}\n"
        f"---\n"
        f"Days active:          {stats['days_active']}\n"
        f"Total check-ins:      {stats['total_checkins']}\n"
        f"Total failures:       {stats['total_failures']}\n"
        f"Success rate:         {stats['success_rate']}%\n"
        f"---\n"
        f"Current streak:       {streak_display}\n"
        f"---\n"
        f"Last failure:         {last_failure}\n"
        f"Urges reported:       {stats['urge_count']}\n"
        f"Reflection rate:      {stats['reflection_compliance']}%\n"
        f"Missed check-ins:     {stats['missed_checkins']}\n"
        f"---\n"
        f"Keep going. Every clean day matters."
    )


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(update, HELP_TEXT)
