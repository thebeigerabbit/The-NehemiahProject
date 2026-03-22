"""
Partner linking: /add_partner, /accept_partner, /reject_partner
"""
from telegram import Update
from telegram.ext import ContextTypes
from app.database import get_db
from app.services.user_service import (
    get_user_by_telegram_id, get_user_by_username, get_user_by_id,
    get_partnership, create_partnership_request, accept_partnership,
    reject_partnership, count_accepted_partners, activate_user,
)
from app.services.notification_service import send_partnership_request
from app.handlers.base import reply, require_auth
from app.models import PartnershipStatusEnum, Partnership
import logging
from html import escape as h
from telegram.constants import ParseMode

logger = logging.getLogger(__name__)


async def add_partner_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Usage: /add_partner USERNAME PARTNER_ID
    Accessible to inactive users so they can get their first partner.
    """
    telegram_id = str(update.effective_user.id)
    args = context.args

    if not args or len(args) < 2:
        await reply(update,
            " Invalid Format\n\n"
            "Usage: /add_partner USERNAME PARTNER_ID\n\n"
            "Ask your partner to share their username and 4-character account ID."
        )
        return

    partner_username = args[0].strip()
    partner_id_input = args[1].strip().upper()

    with get_db() as db:
        user = get_user_by_telegram_id(db, telegram_id)
        if not user:
            await reply(update, " You need an account first. Use /start.")
            return

        # Validate partner exists
        partner = get_user_by_username(db, partner_username)
        if not partner:
            await reply(update, f"No user found with username: {partner_username}")
            return

        if not partner.short_id or partner.short_id.upper() != partner_id_input:
            await reply(update, " Partner ID does not match. Please double-check the 4-character code.")
            return

        if partner.id == user.id:
            await reply(update, " You cannot add yourself as a partner.")
            return

        # Check not already partnered
        existing = get_partnership(db, user.id, partner.id)
        existing_rev = get_partnership(db, partner.id, user.id)
        if existing or existing_rev:
            p = existing or existing_rev
            if p.status == PartnershipStatusEnum.ACCEPTED:
                await reply(update, f" You are already partnered with {partner.username}.")
            elif p.status == PartnershipStatusEnum.PENDING:
                await reply(update, f"⏳ A partnership request with {partner.username} is already pending.")
            else:
                await reply(update, f"ℹ A previous request with {partner.username} was rejected. Contact them directly.")
            return

        # Gender check — defer final check to acceptance, but warn upfront
        if user.gender != partner.gender:
            await reply(update,
                f" Gender Mismatch\n\n"
                f"Same-gender accountability is required.\n"
                f"Your gender: {user.gender.value}\n"
                f"Partner's gender: {partner.gender.value}\n\n"
                f"You cannot partner with this user."
            )
            return

        # Create partnership request
        p = create_partnership_request(db, user.id, partner.id)

        # Notify partner
        await send_partnership_request(
            update.get_bot(), user, partner.telegram_id, p.id
        )

    await reply(update,
        f" Partnership Request Sent!\n\n"
        f"A request has been sent to {partner.username}.\n"
        f"They must accept and confirm gender compatibility."
    )


async def accept_partner_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Usage: /accept_partner PARTNERSHIP_ID
    """
    telegram_id = str(update.effective_user.id)
    args = context.args

    if not args:
        await reply(update, " Usage: /accept_partner PARTNERSHIP_ID")
        return

    partnership_id = args[0].strip()

    with get_db() as db:
        user = get_user_by_telegram_id(db, telegram_id)
        if not user:
            await reply(update, " You need an account first. Use /start.")
            return

        p = db.query(Partnership).filter_by(id=partnership_id).first()
        if not p:
            await reply(update, " Partnership request not found.")
            return

        if p.partner_id != user.id:
            await reply(update, " This request is not for you.")
            return

        if p.status != PartnershipStatusEnum.PENDING:
            await reply(update, f"This request has already been {p.status.value}")
            return

        requester = get_user_by_id(db, p.user_id)
        if not requester:
            await reply(update, " The requester's account no longer exists.")
            return

        # Enforce same-gender
        if requester.gender != user.gender:
            reject_partnership(db, p)
            await reply(update,
                f" Gender Mismatch — Request Rejected\n\n"
                f"Same-gender accountability is required.\n"
                f"Your gender: {user.gender.value}\n"
                f"Requester's gender: {requester.gender.value}\n\n"
                f"This partnership cannot be formed."
            )
            try:
                await update.get_bot().send_message(
                    chat_id=requester.telegram_id,
                    text=(
                        f" Partnership Rejected — Gender Mismatch\n\n"
                        f"{user.username} could not accept your request due to a gender mismatch."
                    ),
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass
            return

        accept_partnership(db, p)

        # Activate requester if they have role USER or BOTH and no active state
        if requester.role.value in ("USER", "BOTH") and not requester.is_active:
            if count_accepted_partners(db, requester.id) >= 1:
                activate_user(db, requester)
                try:
                    await update.get_bot().send_message(
                        chat_id=requester.telegram_id,
                        text=(
                            f" Account Activated!\n\n"
                            f"{user.username} has accepted your partnership request.\n"
                            f"Your account is now active. Daily check-ins begin at 20:00 SAST.\n\n"
                            f"Type /help for all commands."
                        ),
                        parse_mode=ParseMode.HTML,
                    )
                except Exception:
                    pass

        await reply(update,
            f" Partnership Accepted!\n\n"
            f"You are now the accountability partner of {requester.username}.\n"
            f"You will be notified of their check-ins, failures, and urges."
        )


async def reject_partner_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Usage: /reject_partner PARTNERSHIP_ID
    """
    telegram_id = str(update.effective_user.id)
    args = context.args

    if not args:
        await reply(update, " Usage: /reject_partner PARTNERSHIP_ID")
        return

    partnership_id = args[0].strip()

    with get_db() as db:
        user = get_user_by_telegram_id(db, telegram_id)
        if not user:
            await reply(update, " You need an account first. Use /start.")
            return

        p = db.query(Partnership).filter_by(id=partnership_id).first()
        if not p:
            await reply(update, " Partnership request not found.")
            return

        if p.partner_id != user.id:
            await reply(update, " This request is not for you.")
            return

        if p.status != PartnershipStatusEnum.PENDING:
            await reply(update, f"This request has already been {p.status.value}")
            return

        requester = get_user_by_id(db, p.user_id)
        reject_partnership(db, p)

        if requester:
            try:
                await update.get_bot().send_message(
                    chat_id=requester.telegram_id,
                    text=(
                        f" Partnership Request Rejected\n\n"
                        f"{user.username} has declined your partnership request."
                    ),
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass

    await reply(update, f" Partnership request rejected.")
