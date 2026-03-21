"""
/report and /help handlers.
"""
from telegram import Update
from telegram.ext import ContextTypes
from app.database import get_db
from app.services.user_service import get_user_by_telegram_id
from app.services.checkin_service import get_stats
from app.utils.time_utils import format_local
from app.utils.messages import HELP_TEXT
from app.handlers.base import reply, require_auth, require_no_pending_reflection
import logging

logger = logging.getLogger(__name__)


@require_auth
@require_no_pending_reflection
async def report_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)

    with get_db() as db:
        user = get_user_by_telegram_id(db, telegram_id)
        stats = get_stats(db, user)

    streak_bar = "🔥" * min(stats["streak"], 10) or "—"
    last_failure = format_local(stats["last_failure_at"]) if stats["last_failure_at"] else "Never"

    await reply(update,
        f"📊 *Your Accountability Report*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *{user.username}* | {user.role.value} | {user.gender.value}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 Days active: *{stats['days_active']}*\n"
        f"✅ Total check-ins: *{stats['total_checkins']}*\n"
        f"❌ Total failures: *{stats['total_failures']}*\n"
        f"📈 Success rate: *{stats['success_rate']}%*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔥 Current streak: *{stats['streak']} day{'s' if stats['streak'] != 1 else ''}*\n"
        f"{streak_bar}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🕐 Last failure: *{last_failure}*\n"
        f"🆘 Urges reported: *{stats['urge_count']}*\n"
        f"📝 Reflection compliance: *{stats['reflection_compliance']}%*\n"
        f"⚠️ Missed check-ins: *{stats['missed_checkins']}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"_Keep going. Every clean day matters._ 💪"
    )


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(update, HELP_TEXT)
