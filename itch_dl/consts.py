ITCH_BASE = "itch.io"
ITCH_URL = f"https://{ITCH_BASE}"
ITCH_API = f"https://api.{ITCH_BASE}"

# Extracts https://user.itch.io/name to {'author': 'user', 'game': 'name'}
ITCH_GAME_URL_REGEX = r"^https:\/\/(?P<author>[\w\d\-_]+).itch.io\/(?P<game>[\w\d\-_]+)$"

ITCH_BROWSER_TYPES = [
    "games",
    "tools",
    "game-assets",
    "comics",
    "books",
    "physical-games",
    "soundtracks",
    "game-mods",
    "misc",
]
