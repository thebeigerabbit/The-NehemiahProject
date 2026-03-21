import random

ENCOURAGEMENTS = [
    "💪 Excellent! Another clean day. Keep building that streak!",
    "🌟 Well done! You're proving your commitment every single day.",
    "🔥 Stay strong! Each clean day is a victory worth celebrating.",
    "✅ Amazing work! You're becoming the person you want to be.",
    "🏆 Brilliant! Discipline today, freedom tomorrow.",
    "🙌 Outstanding! Your accountability partner is proud of you.",
    "💎 Another day of integrity. You're building something beautiful.",
    "🚀 Clean day locked in! The momentum is yours to keep.",
]

COPING_STRATEGIES = [
    "🧘 Try the 5-4-3-2-1 grounding method: name 5 things you see, 4 you can touch, 3 you hear, 2 you smell, 1 you taste.",
    "🚿 Take a cold shower immediately — it's a proven pattern interrupt.",
    "📞 Call or text a trusted friend right now. Don't be alone with this.",
    "🏃 Go for a brisk walk or do 20 push-ups. Physical movement breaks the urge cycle.",
    "📖 Read your 'why' — write it now if you haven't: why do you want to be free?",
    "🙏 Pray or meditate for 5 minutes. Breathe deeply and focus on your values.",
    "📝 Write out exactly what you're feeling. Naming the emotion weakens it.",
    "🌊 Ride the wave — urges peak and pass in 15–20 minutes. You can outlast it.",
    "🎵 Put on uplifting music and change your environment immediately.",
    "💧 Drink a full glass of water slowly and focus entirely on the sensation.",
]

REFLECTION_FORMAT = """📝 *Reflection Format Required*

Please use *exactly* this format:

```
/reflect
trigger: <what triggered the urge/failure>
failure: <describe what happened>
prevention: <what will you do differently>
```

*Rules:*
• Each field must be ≥20 characters
• Each field must be ≤500 characters
• All three fields are required
• Be specific — vague responses will be rejected"""

HELP_TEXT = """📋 *Accountability Bot — Command Reference*

━━━━━━━━━━━━━━━━━━━━
*Authentication*
━━━━━━━━━━━━━━━━━━━━
/start — Begin or resume your session
/signup — Create a new account
/login — Log in with username + ID

━━━━━━━━━━━━━━━━━━━━
*Daily Check-In (20:00 SAST)*
━━━━━━━━━━━━━━━━━━━━
/yes — Report a failure (relapse)
/no — Report a clean day (success)

━━━━━━━━━━━━━━━━━━━━
*Reflection (required after /yes)*
━━━━━━━━━━━━━━━━━━━━
```
/reflect
trigger: <what triggered it>
failure: <what happened>
prevention: <what you'll do differently>
```
Each field: 20–500 characters. Be specific.

━━━━━━━━━━━━━━━━━━━━
*Urge Reporting*
━━━━━━━━━━━━━━━━━━━━
/urge reason: <why you're struggling>
• Reason must be ≥10 characters
• Max 3 urges per hour (anti-spam)
• Partners notified immediately
• Follow-up check in 15 minutes

━━━━━━━━━━━━━━━━━━━━
*Reports & Info*
━━━━━━━━━━━━━━━━━━━━
/report — Your full accountability stats
/help — This message

━━━━━━━━━━━━━━━━━━━━
⚠️ *Important Limitations*
━━━━━━━━━━━━━━━━━━━━
• Only ONE check-in valid per 24-hour window
• Check-in responses cannot be overwritten
• Reflection MUST be completed before other commands
• Late responses are marked invalid
• Accountability partners must be the *same gender*
• At least 1 partner required before account activation
• All state persists across restarts — no shortcuts"""


def random_encouragement() -> str:
    return random.choice(ENCOURAGEMENTS)


def random_coping_strategy() -> str:
    return random.choice(COPING_STRATEGIES)
