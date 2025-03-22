import logging

from .api import ItchApiClient

KEYS_CACHED: bool = False
DOWNLOAD_KEYS: dict[int, str] = {}
GAME_URLS: list[str] = []


def load_keys_and_urls(client: ItchApiClient) -> None:
    global KEYS_CACHED  # noqa: PLW0603 (whatever, I'll move all this to a class one day)
    logging.info("Fetching all download keys...")
    page = 1

    while True:
        logging.info("Downloading page %d (found %d keys total)", page, len(DOWNLOAD_KEYS))
        r = client.get("/profile/owned-keys", data={"page": page}, timeout=15)
        if not r.ok:
            break

        data = r.json()
        if "owned_keys" not in data:
            break  # Assuming we're out of keys already...

        for key in data["owned_keys"]:
            DOWNLOAD_KEYS[key["game_id"]] = key["id"]
            GAME_URLS.append(key["game"]["url"])

        if len(data["owned_keys"]) == data["per_page"]:
            page += 1
        else:
            break

    logging.info("Fetched %d download keys.", len(DOWNLOAD_KEYS))
    KEYS_CACHED = True


def get_owned_keys(client: ItchApiClient) -> tuple[dict[int, str], list[str]]:
    if not KEYS_CACHED:
        load_keys_and_urls(client)

    return DOWNLOAD_KEYS, GAME_URLS


def get_download_keys(client: ItchApiClient) -> dict[int, str]:
    if not KEYS_CACHED:
        load_keys_and_urls(client)

    return DOWNLOAD_KEYS


def get_owned_games(client: ItchApiClient) -> list[str]:
    if not KEYS_CACHED:
        load_keys_and_urls(client)

    return GAME_URLS
