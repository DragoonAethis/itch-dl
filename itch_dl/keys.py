import logging
from typing import Dict, List, Optional, Tuple

from .api import ItchApiClient


cached_owned_keys: Optional[Tuple[Dict[int, str], List[str]]] = None


def get_owned_keys(client: ItchApiClient) -> Tuple[Dict[int, str], List[str]]:
    global cached_owned_keys
    if cached_owned_keys is not None:
        logging.debug(f"Fetched {len(cached_owned_keys[0])} download keys from cache.")
        return cached_owned_keys

    logging.info("Fetching all download keys...")
    download_keys: Dict[int, str] = {}
    game_urls: List[str] = []
    page = 1

    while True:
        logging.info(f"Downloading page {page} (found {len(download_keys)} keys total)")
        r = client.get("/profile/owned-keys", data={"page": page}, timeout=15)
        if not r.ok:
            break

        data = r.json()
        if "owned_keys" not in data:
            break  # Assuming we're out of keys already...

        for key in data["owned_keys"]:
            download_keys[key["game_id"]] = key["id"]
            game_urls.append(key["game"]["url"])

        if len(data["owned_keys"]) == data["per_page"]:
            page += 1
        else:
            break

    logging.info(f"Fetched {len(download_keys)} download keys.")

    cached_owned_keys = (download_keys, game_urls)
    return cached_owned_keys


def get_download_keys(client: ItchApiClient) -> Dict[int, str]:
    (download_keys, _) = get_owned_keys(client)
    return download_keys


def get_owned_games(client: ItchApiClient) -> List[str]:
    (_, game_urls) = get_owned_keys(client)
    return game_urls
