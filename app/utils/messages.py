import random

ENCOURAGEMENTS = [
    "Excellent! Another clean day. Keep building that streak!",
    "Well done! You are proving your commitment every single day.",
    "Stay strong! Each clean day is a victory worth celebrating.",
    "Amazing work! You are becoming the person you want to be.",
    "Brilliant! Discipline today, freedom tomorrow.",
    "Outstanding! Your accountability partner is proud of you.",
    "Another day of integrity. You are building something beautiful.",
    "Clean day locked in! The momentum is yours to keep.",
]

COPING_STRATEGIES = [
    "Try the 5-4-3-2-1 grounding method: name 5 things you see, 4 you can touch, 3 you hear, 2 you smell, 1 you taste.",
    "Take a cold shower immediately. It is a proven pattern interrupt.",
    "Call or text a trusted friend right now. Do not be alone with this.",
    "Go for a brisk walk or do 20 push-ups. Physical movement breaks the urge cycle.",
    "Read your 'why'. Write it now if you have not: why do you want to be free?",
    "Pray or meditate for 5 minutes. Breathe deeply and focus on your values.",
    "Write out exactly what you are feeling. Naming the emotion weakens it.",
    "Ride the wave. Temptations peak and pass in 15 to 20 minutes. You can outlast it.",
    "Put on uplifting music and change your environment immediately.",
    "Drink a full glass of water slowly and focus entirely on the sensation.",
]


def random_encouragement() -> str:
    return random.choice(ENCOURAGEMENTS)


def random_coping_strategy() -> str:
    return random.choice(COPING_STRATEGIES)
