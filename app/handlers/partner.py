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

        # Check not already partnered in THIS direction
        existing = get_partnership(db, user.id, partner.id)
        if existing:
            if existing.status == PartnershipStatusEnum.ACCEPTED:
                await reply(update, f" You are already partnered with {partner.username}.")
            elif existing.status == PartnershipStatusEnum.PENDING:
                await reply(update, f"A partnership request to {partner.username} is already pending.")
            else:
                await reply(update, f"A previous request to {partner.username} was rejected. Contact them directly.")
            return

        # Check reverse direction — only block if both directions already exist (mutual max)
        existing_rev = get_partnership(db, partner.id, user.id)
        if existing_rev:
            if existing_rev.status == PartnershipStatusEnum.PENDING:
                await reply(update,
                    f"{partner.username} has already sent YOU a partnership request.\n\n"
                    f"Accept it with /accept_partner instead of creating a duplicate."
                )
                return
            if existing_rev.status == PartnershipStatusEnum.ACCEPTED:
                # Reverse exists and is accepted — allow this direction too (mutual accountability)
                # but only if neither user already has a mutual link in this direction
                pass  # fall through to create the forward partnership

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
            update.get_bot(), user, partner.telegram_id, p.id,
            p.short_id or p.id[:4].upper()
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

    partnership_short_id = args[0].strip().upper()

    with get_db() as db:
        user = get_user_by_telegram_id(db, telegram_id)
        if not user:
            await reply(update, " You need an account first. Use /start.")
            return

        p = db.query(Partnership).filter_by(short_id=partnership_short_id).first()
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

        # Also activate acceptor if they are BOTH role and this is their first accepted partner
        if user.role.value == "BOTH" and not user.is_active:
            if count_accepted_partners(db, user.id) >= 1:
                activate_user(db, user)
                try:
                    await update.get_bot().send_message(
                        chat_id=user.telegram_id,
                        text=(
                            f" Your Account Is Now Active!\n\n"
                            f"You accepted {requester.username}'s partnership request, "
                            f"which has activated your own account.\n"
                            f"Daily check-ins begin at 20:00 SAST.\n\n"
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

    partnership_short_id = args[0].strip().upper()

    with get_db() as db:
        user = get_user_by_telegram_id(db, telegram_id)
        if not user:
            await reply(update, " You need an account first. Use /start.")
            return

        p = db.query(Partnership).filter_by(short_id=partnership_short_id).first()
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
