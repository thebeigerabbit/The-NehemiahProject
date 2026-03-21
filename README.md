# Accountability Bot 🤝

A production-ready Telegram accountability bot with daily check-ins, partner notifications, urge reporting, and persistent state across restarts.

---

## Features

- 📅 Daily check-ins at **20:00 SAST** (Africa/Johannesburg)
- 🤝 Same-gender accountability partner system
- 📊 Progress tracking — streaks, failure rates, reflection compliance
- 🚨 Urge reporting with coping strategies and 15-minute follow-ups
- 📝 Mandatory post-failure reflections
- 🔄 Full state persistence — survives bot restarts
- 🛡️ Anti-cheating: one check-in per 24h, immutable responses, anomaly detection
- 📣 Partner alerts for missed check-ins, failures, overdue reflections

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| Bot Framework | python-telegram-bot v21 |
| Database | PostgreSQL |
| ORM | SQLAlchemy 2.0 |
| Migrations | Alembic |
| Scheduler | APScheduler (PostgreSQL job store) |
| Hosting | Railway |
| Timezone | Africa/Johannesburg (SAST) |

---

## Project Structure

```
/
├── Dockerfile                     # Docker build (used by Railway)
├── start.sh                       # Entrypoint: runs migrations then bot
├── main.py                        # Bot entry point, handler registration
├── requirements.txt               # Python dependencies
├── railway.toml                   # Railway deployment config
├── alembic.ini                    # Alembic migration config
├── mise.toml                      # Python version pin for Railway
├── .env.example                   # Environment variable template
│
├── config/
│   └── settings.py                # All config loaded from env vars
│
├── app/
│   ├── database.py                # SQLAlchemy engine + session
│   ├── models/__init__.py         # All 10 ORM models
│   ├── handlers/                  # One file per command group
│   ├── services/                  # Business logic layer
│   ├── jobs/scheduler.py          # APScheduler timed jobs
│   └── utils/                     # Helpers: time, messages, events
│
└── migrations/
    └── versions/0001_initial.py   # Full schema migration
```

---

## Bot Commands

| Command | Description |
|---|---|
| `/start` | Start or resume session |
| `/signup` | Create account (3-step flow) |
| `/login` | Log in with username |
| `/add_partner <username> <id>` | Send partnership request |
| `/accept_partner <id>` | Accept a partnership request |
| `/reject_partner <id>` | Reject a partnership request |
| `/yes` | Report a failure (check-in) |
| `/no` | Report a clean day (check-in) |
| `/reflect` | Submit post-failure reflection |
| `/urge reason: <text>` | Report an urge for support |
| `/report` | View your accountability stats |
| `/help` | Show all commands and formats |

---

## Deploying to Railway

### Step 1 — Create a GitHub Repository

1. Go to [github.com](https://github.com) and log in
2. Click **+** → **New repository**
3. Name it `accountability-bot`
4. Set visibility to **Private**
5. Leave all checkboxes **unticked** (no README, no .gitignore)
6. Click **Create repository**

---

### Step 2 — Upload the Files

Extract `accountability_bot_final.tar.gz` on your computer. You will get a folder containing `Dockerfile`, `main.py`, `requirements.txt`, `app/`, `config/`, `migrations/`, etc.

**Option A — GitHub web interface (no Git needed):**

1. On your new empty repo page, click **uploading an existing file**
2. Drag the **entire contents** of the extracted folder into the upload window
   - Select all files and folders inside the extracted folder
   - Do NOT drag the folder itself — drag what is inside it
3. GitHub will preserve the folder structure automatically
4. Scroll down, write a commit message: `Initial commit`
5. Click **Commit changes**

**Option B — Git command line:**

```bash
# Extract the tarball
tar -xzf accountability_bot_final.tar.gz

# Enter the extracted folder (it extracts as a flat structure)
cd <extracted-folder>

# Push to GitHub
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/accountability-bot.git
git push -u origin main
```

---

### Step 3 — Verify the Repo Structure

After uploading, your GitHub repository root **must** look exactly like this:

```
accountability-bot/          ← repo root on GitHub
├── Dockerfile               ← at ROOT level ✅
├── main.py                  ← at ROOT level ✅
├── requirements.txt         ← at ROOT level ✅
├── start.sh                 ← at ROOT level ✅
├── railway.toml             ← at ROOT level ✅
├── alembic.ini
├── mise.toml
├── app/
├── config/
├── migrations/
└── ...
```

⚠️ **If you see a subfolder** like `bot_clean/` or `accountability_bot/` containing those files, the structure is wrong. You need to move everything up one level.

---

### Step 4 — Create a Railway Project

1. Go to [railway.app](https://railway.app) and log in (create a free account if needed)
2. Click **New Project**
3. Select **Deploy from GitHub repo**
4. Authorise Railway to access GitHub if prompted
5. Select your `accountability-bot` repository
6. Click **Deploy Now**

---

### Step 5 — Add a PostgreSQL Database

1. Inside your Railway project dashboard, click **+ New**
2. Select **Database** → **Add PostgreSQL**
3. Wait ~30 seconds for provisioning
4. Railway automatically injects `DATABASE_URL` into your bot service — nothing extra needed

---

### Step 6 — Set Environment Variables

1. In your Railway project, click on the **bot service** (not the database)
2. Go to the **Variables** tab
3. Click **New Variable** and add:

| Variable | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Your token from @BotFather |
| `LOG_LEVEL` | `INFO` |

**How to get your bot token:**
1. Open Telegram → search `@BotFather` → start a chat
2. Send `/newbot`
3. Choose a display name (e.g. `My Accountability Bot`)
4. Choose a username ending in `bot` (e.g. `myaccountability_bot`)
5. BotFather replies with your token: `1234567890:ABCdefGHI...`
6. Copy that entire token into the Railway variable

---

### Step 7 — Trigger a Deploy

1. Go to the **Deployments** tab
2. If it hasn't auto-deployed, click **Deploy**
3. Click the active deployment to watch the build log

**Expected build output (Docker):**
```
Using Detected Dockerfile
[1/7] FROM python:3.11-slim
[2/7] WORKDIR /app
[3/7] RUN apt-get install gcc libpq-dev
[4/7] COPY requirements.txt .
[5/7] RUN pip install -r requirements.txt   ✅ packages installed here
[6/7] COPY . .
[7/7] RUN chmod +x start.sh
```

**Expected container startup:**
```
Working directory: /app
Python: Python 3.11.x
Running database migrations...
INFO  [alembic] Running upgrade -> 0001_initial
Migrations complete. Starting bot...
```

If you see `Migrations complete. Starting bot...` — the bot is live. ✅

---

### Step 8 — Register Commands with BotFather

1. Open Telegram → `@BotFather` → send `/setcommands`
2. Select your bot from the list
3. Paste this entire block as one message:

```
start - Start or resume your session
signup - Create a new account
login - Log in to your account
add_partner - Link an accountability partner
accept_partner - Accept a partnership request
reject_partner - Reject a partnership request
yes - Report a failure (check-in)
no - Report a clean day (check-in)
reflect - Submit your post-failure reflection
urge - Report an urge for support
report - View your accountability stats
help - Show all commands and formats
```

Your bot is now fully deployed and ready to use.

---

## Environment Variables Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | ✅ | — | From @BotFather |
| `DATABASE_URL` | ✅ | Auto (Railway) | PostgreSQL connection string |
| `TIMEZONE` | No | `Africa/Johannesburg` | Scheduler timezone |
| `LOG_LEVEL` | No | `INFO` | `DEBUG`, `INFO`, or `WARNING` |
| `WEBHOOK_URL` | No | — | Set to use webhook instead of polling |

---

## How It Works

### Daily Check-In Flow
```
20:00 SAST  → Check-in sent to all active users
+10 min     → Reminder if no response
+2 hours    → Partners notified if still no response

/yes → Failure recorded, partners notified, reflection required (5 min)
/no  → Streak incremented, encouragement sent
```

### Urge Reporting Flow
```
/urge reason: ...
  → Partners notified immediately
  → Coping strategy sent to user
  → 15-min follow-up: Fallen / Still tempted / Not tempted
      Fallen        → triggers /yes logic
      Still tempted → repeats urge flow
      Not tempted   → triggers /no logic
```

### Partner Linking Flow
```
/add_partner <username> <id>
  → Gender match validated (same-gender only)
  → Partner receives accept/reject request
  → On accept: gender re-validated
  → If user had no partners: account activated
```

---

## Anti-Cheating Rules

- One valid check-in per **24-hour rolling window**
- Responses **cannot be overwritten** once submitted
- Responses after the 2-hour window are marked **invalid**
- **Reflection must be completed** before any other command works
- Bot restart does **not** reset state — all state lives in PostgreSQL
- Anomaly detection: long clean streak + recent urges → partner alert
- Max **3 urges per hour** — spam triggers partner notification

---

## Troubleshooting

**Bot not responding to messages:**
- Check Railway → Deployments → view logs for errors
- Confirm `TELEGRAM_BOT_TOKEN` is correct in Variables
- Confirm the PostgreSQL service shows as healthy

**"No active check-in" when using /yes or /no:**
- Check-ins are only sent at 20:00 SAST daily
- Your account must have at least one accepted partner
- Your role must be USER or BOTH (not PARTNER-only)

**"Account not yet active":**
- You need at least one accepted accountability partner
- Share your username and account ID with your partner
- Ask them to run `/add_partner <your_username> <your_id>`
- Then you accept with `/accept_partner <partnership_id>`

**Build fails at COPY requirements.txt:**
- Your files are in a subfolder, not the repo root
- Check that `Dockerfile` appears directly in the GitHub repo root
- If not, move all files up one level

**Migrations fail on startup:**
- Confirm PostgreSQL has been added to your Railway project
- Check that `DATABASE_URL` appears in your service's Variables tab (it should be injected automatically)
