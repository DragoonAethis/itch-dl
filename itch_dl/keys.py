import logging
from typing import Dict

from .api import ItchApiClient


def get_download_keys(client: ItchApiClient) -> Dict[int, str]:
    logging.info("Fetching all download keys...")
    download_keys: Dict[int, str] = {}
    page = 1

    while True:
        logging.info(f"Downloading page {page} (found {len(download_keys)} keys total)")
        r = client.get("/profile/owned-keys", data={"page": page}, timeout=15)
        if not r.ok:
            break

        data = r.json()
        if 'owned_keys' not in data:
            break  # Assuming we're out of keys already...

        for key in data['owned_keys']:
            download_keys[key['game_id']] = key['id']

        if len(data['owned_keys']) == data['per_page']:
            page += 1
        else:
            break

    logging.info(f"Fetched {len(download_keys)} download keys.")
    return download_keys
