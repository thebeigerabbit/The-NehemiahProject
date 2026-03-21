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
    activate_user,
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

    # ââ Step 1: Username ââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    if step == "username":
        if not USERNAME_RE.match(text):
            await reply(update,
                "Invalid username.\n\n"
                "- 3 to 30 characters\n"
                "- Letters, numbers, underscores only\n"
                "- No spaces\n\n"
                "Please try again:"
            )
            return True

        with get_db() as db:
            if username_exists(db, text):
                await reply(update, "That username is already taken. Please choose another:")
                return True
            upsert_temp_signup(db, telegram_id, step="role", username=text)

        await reply(update,
            f"Username {text} is available!\n\n"
            "Step 2 of 3 - Choose your role:\n\n"
            "USER    - You will be held accountable\n"
            "PARTNER - You hold others accountable\n"
            "BOTH    - Both roles\n\n"
            "Reply with: USER, PARTNER, or BOTH"
        )
        return True

    # ââ Step 2: Role ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    if step == "role":
        role = text.upper()
        if role not in VALID_ROLES:
            await reply(update,
                "Invalid role. Please reply with exactly one of:\n"
                "USER, PARTNER, or BOTH"
            )
            return True

        with get_db() as db:
            upsert_temp_signup(db, telegram_id, step="gender", role=role)

        await reply(update,
            f"Role set to {role}.\n\n"
            "Step 3 of 3 - Your gender:\n\n"
            "This is required for same-gender accountability matching.\n\n"
            "Reply with: MALE or FEMALE"
        )
        return True

    # ââ Step 3: Gender ââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    if step == "gender":
        gender = text.upper()
        if gender not in VALID_GENDERS:
            await reply(update,
                "Invalid input. Please reply with exactly:\n"
                "MALE or FEMALE"
            )
            return True

        result = {}
        with get_db() as db:
            ts = get_temp_signup(db, telegram_id)
            if not ts:
                result = {"error": "Your signup session expired. Please use /signup to start again."}
            elif not ts.role or not ts.username:
                delete_temp_signup(db, telegram_id)
                result = {"error": "Signup session was incomplete. Please use /signup to start again."}
            elif get_user_by_telegram_id(db, telegram_id):
                delete_temp_signup(db, telegram_id)
                result = {"error": "An account already exists for your Telegram. Use /start to continue."}
            elif username_exists(db, ts.username):
                saved_username = ts.username
                delete_temp_signup(db, telegram_id)
                upsert_temp_signup(db, telegram_id, step="username")
                result = {"error": f"Sorry, the username {saved_username} was just taken. Please send a new username:"}
            else:
                user = create_user(
                    db,
                    telegram_id=telegram_id,
                    username=ts.username,
                    role=ts.role,
                    gender=gender,
                )
                saved_role = ts.role
                delete_temp_signup(db, telegram_id)

                if saved_role == "PARTNER":
                    activate_user(db, user)

                result = {
                    "success": True,
                    "role": saved_role,
                    "username": user.username,
                    "user_id": user.id,
                }

        if "error" in result:
            await reply(update, result["error"])
            return True

        role = result["role"]
        username = result["username"]
        user_id = result["user_id"]

        if role == "PARTNER":
            await reply(update,
                "Account created successfully!\n\n"
                f"Username: {username}\n"
                f"Role: {role}\n"
                f"Your account ID: {user_id}\n\n"
                "Your account is now active as a partner.\n"
                "Share your username and account ID with anyone who wants to add you.\n\n"
                "Type /help to see all commands."
            )
        else:
            await reply(update,
                "Account created successfully!\n\n"
                f"Username: {username}\n"
                f"Role: {role}\n"
                f"Your account ID: {user_id}\n\n"
                "Next step required:\n"
                "You must add at least 1 accountability partner before your account is activated.\n\n"
                "Use: /add_partner <partner_username> <partner_id>\n\n"
                "Ask your partner to share their username and account ID with you."
            )
        return True

    return False
