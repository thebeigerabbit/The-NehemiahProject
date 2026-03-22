"""
Notification service. All methods are async and receive a bot instance.
Separated from handlers to keep business logic testable.
"""
from html import escape as h
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError
from app.models import User
from app.utils.time_utils import format_local
import logging

logger = logging.getLogger(__name__)


async def send_safe(bot: Bot, chat_id: str, text: str, **kwargs):
    """Send message using HTML parse mode, log errors without raising."""
    try:
        kwargs.pop("parse_mode", None)
        await bot.send_message(
            chat_id=chat_id,
            text=h(text),
            parse_mode=ParseMode.HTML,
            **kwargs
        )
    except TelegramError as e:
        logger.error(f"Failed to send message to {chat_id}: {e}")


async def notify_partners_failure(bot: Bot, user: User, partners: list[User]):
    msg = (
        f" Partner Alert\n\n"
        f"{user.username} has just reported a FAILURE for today's check-in.\n"
        f"Please reach out and offer support. "
    )
    for partner in partners:
        await send_safe(bot, partner.telegram_id, msg)


async def notify_partners_urge(bot: Bot, user: User, partners: list[User], reason: str):
    msg = (
        f" Urge Alert\n\n"
        f"{user.username} is reporting an urge right now.\n"
        f"Reason: {reason}\n\n"
        f"Please check in with them immediately. "
    )
    for partner in partners:
        await send_safe(bot, partner.telegram_id, msg)


async def notify_partners_no_checkin(bot: Bot, user: User, partners: list[User]):
    msg = (
        f"⏰ Missed Check-In Alert\n\n"
        f"{user.username} has not responded to their daily check-in within 2 hours.\n"
        f"Please reach out to verify their status."
    )
    for partner in partners:
        await send_safe(bot, partner.telegram_id, msg)


async def notify_partners_no_reflection(bot: Bot, user: User, partners: list[User]):
    msg = (
        f" Reflection Overdue\n\n"
        f"{user.username} reported a failure but has not completed their reflection in time.\n"
        f"Please follow up with them."
    )
    for partner in partners:
        await send_safe(bot, partner.telegram_id, msg)


async def notify_partners_anomaly(bot: Bot, user: User, partners: list[User]):
    msg = (
        f" Behaviour Anomaly Detected\n\n"
        f"{user.username} has a long clean streak but has recently reported urges.\n"
        f"This may indicate an inconsistency. Please check in carefully."
    )
    for partner in partners:
        await send_safe(bot, partner.telegram_id, msg)


async def notify_partners_urge_spam(bot: Bot, user: User, partners: list[User]):
    msg = (
        f" Urge Spam Alert\n\n"
        f"{user.username} has submitted more than 3 urge reports in the past hour.\n"
        f"Please reach out — this may indicate a serious struggle."
    )
    for partner in partners:
        await send_safe(bot, partner.telegram_id, msg)


async def send_partner_check_notification(bot: Bot, user: User, partners: list[User]):
    msg = (
        f" Random Partner Check\n\n"
        f"You have been selected to manually check on {user.username} today.\n"
        f"Please reach out and verify how they're doing."
    )
    for partner in partners:
        await send_safe(bot, partner.telegram_id, msg)


async def send_partnership_request(bot: Bot, requester: User, partner_telegram_id: str, partnership_id: str):
    msg = (
        f" Partnership Request\n\n"
        f"{requester.username} wants to add you as their accountability partner.\n\n"
        f"To accept, reply:\n/accept_partner {partnership_id}\n\n"
        f"To reject, reply:\n/reject_partner {partnership_id}\n\n"
        f" Note: You must be the same gender as the person you're partnering with."
    )
    await send_safe(bot, partner_telegram_id, msg)
