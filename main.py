"""
Main entry point for the Accountability Bot.
Registers all handlers, starts scheduler, launches polling or webhook.
"""
import logging
import sys
import os

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters,
)

from config.settings import TELEGRAM_BOT_TOKEN, WEBHOOK_URL, WEBHOOK_PORT, LOG_LEVEL
from app.database import init_db
from app.handlers import (
    start_handler, signup_handler, login_handler,
    add_partner_handler, accept_partner_handler, reject_partner_handler,
    yes_handler, no_handler,
    reflect_handler,
    temptation_handler, temptation_followup_callback,
    report_handler, help_handler,
    message_dispatcher,
)
from app.jobs.scheduler import init_scheduler

# ─── Logging ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def build_application() -> Application:
    # Set defaults: no parse_mode so underscores/asterisks in usernames
    # are never misinterpreted as Markdown entities
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # ── Auth commands ─────────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("signup", signup_handler))
    app.add_handler(CommandHandler("login", login_handler))

    # ── Partner commands ──────────────────────────────────────────────────────
    app.add_handler(CommandHandler("add_partner", add_partner_handler))
    app.add_handler(CommandHandler("accept_partner", accept_partner_handler))
    app.add_handler(CommandHandler("reject_partner", reject_partner_handler))

    # ── Check-in commands ─────────────────────────────────────────────────────
    app.add_handler(CommandHandler("yes", yes_handler))
    app.add_handler(CommandHandler("no", no_handler))

    # ── Reflection command ────────────────────────────────────────────────────
    app.add_handler(CommandHandler("reflect", reflect_handler))

    # ── Temptation command ──────────────────────────────────────────────────────────
    app.add_handler(CommandHandler("temptation", temptation_handler))

    # ── Info commands ─────────────────────────────────────────────────────────
    app.add_handler(CommandHandler("report", report_handler))
    app.add_handler(CommandHandler("help", help_handler))

    # ── Inline button callbacks ───────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(temptation_followup_callback, pattern=r"^temptation_followup:"))

    # ── Fallback: plain text messages ─────────────────────────────────────────
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_dispatcher))

    return app


async def post_init(application: Application):
    """Called after Application is initialized — start scheduler here."""
    logger.info("Post-init: starting scheduler...")
    init_scheduler(application.bot)
    logger.info("Scheduler started.")


def main():
    logger.info("Initializing database...")
    init_db()
    logger.info("Database ready.")

    app = build_application()
    app.post_init = post_init

    if WEBHOOK_URL:
        logger.info(f"Starting webhook on port {WEBHOOK_PORT}...")
        app.run_webhook(
            listen="0.0.0.0",
            port=WEBHOOK_PORT,
            url_path=TELEGRAM_BOT_TOKEN,
            webhook_url=f"{WEBHOOK_URL}/{TELEGRAM_BOT_TOKEN}",
            allowed_updates=Update.ALL_TYPES,
        )
    else:
        logger.info("Starting polling...")
        app.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )


if __name__ == "__main__":
    main()
