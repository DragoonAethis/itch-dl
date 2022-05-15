from enum import Enum

ITCH_BASE = "itch.io"
ITCH_URL = f"https://{ITCH_BASE}"
ITCH_API = f"https://api.{ITCH_BASE}"

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


class ItchDownloadResult(Enum):
    SUCCESS = 0
    FAILURE = 1
    MISSING_DOWNLOAD = 2
    DOWNLOAD_TIMEOUT = 3


# I mean, not really a const but eh
class ItchDownloadError(Exception):
    pass
