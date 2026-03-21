import os
from dotenv import load_dotenv
import pytz

load_dotenv()

# Bot
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

# Database
DATABASE_URL = os.environ["DATABASE_URL"]
# Ensure psycopg2 dialect for SQLAlchemy
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Timezone
TIMEZONE_STR = os.getenv("TIMEZONE", "Africa/Johannesburg")
TIMEZONE = pytz.timezone(TIMEZONE_STR)

# Check-in schedule
CHECKIN_HOUR = 20
CHECKIN_MINUTE = 0

# Timeouts (in minutes)
REMINDER_MINUTES = 10
CHECKIN_TIMEOUT_MINUTES = 120  # 2 hours
REFLECTION_TIMEOUT_MINUTES = 5
URGE_FOLLOWUP_MINUTES = 15

# Validation
MIN_REFLECTION_LENGTH = 20
MAX_TEXT_LENGTH = 500
MIN_URGE_REASON_LENGTH = 10

# Anti-spam
MAX_URGES_PER_HOUR = 3

# Random partner checks
PARTNER_CHECK_MIN_PCT = 0.20
PARTNER_CHECK_MAX_PCT = 0.30

# Anomaly detection
ANOMALY_NO_STREAK_THRESHOLD = 5

# Webhook
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "8443"))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
