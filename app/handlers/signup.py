"""
Multi-step signup flow via message handler (not ConversationHandler,
so it survives restarts via TempSignup table).
"""
import re
from telegram import Update
from telegram.ext import ContextTypes
from app.database import get_db
from app.services.user_service import (
    get_temp_signup, upsert_temp_signup, delete_temp_signup,
    get_user_by_telegram_id, username_exists, create_user,
)
from app.handlers.base import reply
import logging

logger = logging.getLogger(__name__)

USERNAME_RE = re.compile(r'^[a-zA-Z0-9_]{3,30}$')
VALID_ROLES = ["USER", "PARTNER", "BOTH"]
VALID_GENDERS = ["MALE", "FEMALE"]


async def handle_signup_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Returns True if the message was consumed by signup flow.
    Called by the main message dispatcher.
    """
    telegram_id = str(update.effective_user.id)
    text = update.message.text.strip() if update.message.text else ""

    with get_db() as db:
        ts = get_temp_signup(db, telegram_id)
        if not ts:
            return False

        step = ts.step

        # ââ Step 1: Username ââââââââââââââââââââââââââââââââââââââââââââââââââ
        if step == "username":
            if not USERNAME_RE.match(text):
                await reply(update,
                    "â Invalid username.\n\n"
                    "â¢ 3â30 characters\n"
                    "â¢ Letters, numbers, underscores only\n"
                    "â¢ No spaces\n\n"
                    "Please try again:"
                )
                return True

            if username_exists(db, text):
                await reply(update,
                    "â That username is already taken. Please choose another:"
                )
                return True

            upsert_temp_signup(db, telegram_id, step="role", username=text)
            await reply(update,
                f"â Username *{text}* is available!\n\n"
                "ð *Step 2 of 3 â Choose your role:*\n\n"
                "â¢ `USER` â You will be held accountable\n"
                "â¢ `PARTNER` â You hold others accountable\n"
                "â¢ `BOTH` â Both roles\n\n"
                "Reply with: `USER`, `PARTNER`, or `BOTH`"
            )
            return True

        # ââ Step 2: Role ââââââââââââââââââââââââââââââââââââââââââââââââââââââ
        elif step == "role":
            role = text.upper()
            if role not in VALID_ROLES:
                await reply(update,
                    "â Invalid role. Please reply with exactly one of:\n"
                    "`USER`, `PARTNER`, or `BOTH`"
                )
                return True

            upsert_temp_signup(db, telegram_id, step="gender", role=role)
            await reply(update,
                f"â Role set to *{role}*.\n\n"
                "ð *Step 3 of 3 â Your gender:*\n\n"
                "â ï¸ This is required for same-gender accountability matching.\n\n"
                "Reply with: `MALE` or `FEMALE`"
            )
            return True

        # ââ Step 3: Gender ââââââââââââââââââââââââââââââââââââââââââââââââââââ
        elif step == "gender":
            gender = text.upper()
            if gender not in VALID_GENDERS:
                await reply(update,
                    "â Invalid gender. Please reply with exactly:\n"
                    "`MALE` or `FEMALE`"
                )
                return True

            # Create the user
            existing = get_user_by_telegram_id(db, telegram_id)
            if existing:
                delete_temp_signup(db, telegram_id)
                await reply(update, "â Account already exists. Use /start to continue.")
                return True

            if username_exists(db, ts.username):
                delete_temp_signup(db, telegram_id)
                upsert_temp_signup(db, telegram_id, step="username")
                await reply(update,
                    "â That username was taken while you were signing up.\n"
                    "Please send a new username:"
                )
                return True

            user = create_user(
                db,
                telegram_id=telegram_id,
                username=ts.username,
                role=ts.role,
                gender=gender,
            )
            delete_temp_signup(db, telegram_id)

            if ts.role == "PARTNER":
                # Partners don't need to add users â activate immediately
                from app.services.user_service import activate_user
                activate_user(db, user)
                await reply(update,
                    f"ð *Account Created!*\n\n"
                    f"Username: *{user.username}*\n"
                    f"Role: *{ts.role}*\n"
                    f"Your ID: `{user.id}`\n\n"
                    f"â Your account is active as a partner. Share your username and ID with those who want to add you.\n\n"
                    f"Type /help to see all commands."
                )
            else:
                await reply(update,
                    f"ð *Account Created!*\n\n"
                    f"Username: *{user.username}*\n"
                    f"Role: *{ts.role}*\n"
                    f"Your ID: `{user.id}`\n\n"
                    f"â³ *Next Step Required:*\n"
                    f"You must add at least 1 accountability partner before your account is activated.\n\n"
                    f"Use: `/add_partner <username> <partner_id>`\n\n"
                    f"Ask your partner to share their username and account ID."
                )
            return True

    return False
