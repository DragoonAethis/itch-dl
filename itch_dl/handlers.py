import json
import os.path
import logging
import urllib.parse
from typing import List, Set, Optional

from bs4 import BeautifulSoup

from .api import ItchApiClient
from .utils import ItchDownloadError, get_int_after_marker_in_json
from .consts import ITCH_BASE, ITCH_URL, ITCH_BROWSER_TYPES
from .config import Settings


def get_jobs_for_game_jam_json(game_jam_json: dict) -> List[str]:
    if 'jam_games' not in game_jam_json:
        raise Exception("Provided JSON is not a valid itch.io jam JSON.")

    return [g['game']['url'] for g in game_jam_json['jam_games']]


def get_game_jam_json(jam_url: str, client: ItchApiClient) -> dict:
    r = client.get(jam_url)
    if not r.ok:
        raise ItchDownloadError(f"Could not download the game jam site: {r.status_code} {r.reason}")

    jam_id: Optional[int] = get_int_after_marker_in_json(r.text, "I.ViewJam", "id")
    if jam_id is None:
        raise ItchDownloadError("Provided site did not contain the Game Jam ID. Provide "
                                "the path to the game jam entries JSON file instead, or "
                                "create an itch-dl issue with the Game Jam URL.")

    logging.info(f"Extracted Game Jam ID: {jam_id}")
    r = client.get(f"{ITCH_URL}/jam/{jam_id}/entries.json")
    if not r.ok:
        raise ItchDownloadError(f"Could not download the game jam entries list: {r.status_code} {r.reason}")

    return r.json()


def get_jobs_for_browse_url(url: str, client: ItchApiClient) -> List[str]:
    """
    Every browser page has a hidden RSS feed that can be accessed by
    appending .xml to its URL. An optional "page" argument lets us
    iterate over their contents. When no more elements are available,
    the last returned <channel> has no <item> children.

    The input URL is cleaned in the main URL handler, so append the
    .xml?page=N suffix and iterate until we've caught 'em all.
    """
    page = 1
    found_urls: Set[str] = set()
    logging.info(f"Scraping game URLs from RSS feeds for %s", url)

    while True:
        logging.info(f"Downloading page {page} (found {len(found_urls)} URLs total)")
        r = client.get(f"{url}.xml?page={page}", append_api_key=False)
        if not r.ok:
            logging.info("RSS feed returned %s, finished.", r.reason)
            break

        soup = BeautifulSoup(r.text, features="xml")
        rss_items = soup.find_all("item")
        if len(rss_items) < 1:
            logging.info("No more items, finished.")
            break

        logging.info(f"Found {len(rss_items)} items.")
        for item in rss_items:
            link_node = item.find("link")
            if link_node is None:
                continue

            node_url = link_node.text.strip()
            if len(node_url) > 0:
                found_urls.add(node_url)

        page += 1

    if len(found_urls) == 0:
        raise ItchDownloadError("No game URLs found to download.")

    return list(found_urls)


def get_jobs_for_itch_url(url: str, client: ItchApiClient) -> List[str]:
    if url.startswith("http://"):
        logging.info("HTTP link provided, upgrading to HTTPS")
        url = "https://" + url[7:]

    if url.startswith(f"https://www.{ITCH_BASE}/"):
        logging.info(f"Correcting www.{ITCH_BASE} to {ITCH_BASE}")
        url = ITCH_URL + '/' + url[20:]

    url_parts = urllib.parse.urlparse(url)
    url_path_parts: List[str] = [x for x in str(url_parts.path).split('/') if len(x) > 0]

    if url_parts.netloc == ITCH_BASE:
        if len(url_path_parts) == 0:
            raise NotImplementedError("itch-dl cannot download the entirety of itch.io.")
        # (yet) (also leafo would not be happy with the bandwidth bill)

        site = url_path_parts[0]

        if site == "jam":  # Game jams
            if len(url_path_parts) < 2:
                raise ValueError(f"Incomplete game jam URL: {url}")

            logging.info("Fetching Game Jam JSON...")
            clean_game_jam_url = f"{ITCH_URL}/jam/{url_path_parts[1]}"
            game_jam_json = get_game_jam_json(clean_game_jam_url, client)
            return get_jobs_for_game_jam_json(game_jam_json)

        elif site in ITCH_BROWSER_TYPES:  # Browser
            clean_browse_url = '/'.join([ITCH_URL, *url_path_parts])
            return get_jobs_for_browse_url(clean_browse_url, client)

        elif site in ("b", "bundle"):  # Bundles
            raise NotImplementedError("itch-dl cannot download bundles yet.")

        elif site in ("j", "jobs"):  # Jobs...
            raise ValueError("itch-dl cannot download a job.")

        elif site in ("t", "board", "community"):  # Forums
            raise ValueError("itch-dl cannot download forums.")

        elif site == "profile":  # Forum Profile
            if len(url_path_parts) >= 2:
                username = url_path_parts[1]
                logging.info("Correcting user profile to creator page for %s", username)
                return get_jobs_for_itch_url(f"https://{username}.{ITCH_BASE}", client)

            raise ValueError("itch-dl expects a username in profile links.")

        # Something else?
        raise NotImplementedError(f"itch-dl does not understand \"{site}\" URLs. Please file a new issue.")

    elif url_parts.netloc.endswith(f".{ITCH_BASE}"):
        if len(url_path_parts) == 0:  # Author
            # TODO: Find I.UserPage, regex for "user_id": [0-9]+, find the responsible API?
            raise NotImplementedError("itch-dl cannot download author pages yet.")

        else:  # Single game
            # Just clean and return the URL:
            return [f"https://{url_parts.netloc}/{url_path_parts[0]}"]

    else:
        raise ValueError(f"Unknown domain: {url_parts.netloc}")


def get_jobs_for_path(path: str) -> List[str]:
    try:  # Game Jam Entries JSON?
        with open(path, "rb") as f:
            json_data = json.load(f)

        if not isinstance(json_data, dict):
            raise ValueError(f"File does not contain a JSON dict: {path}")

        if 'jam_games' in json_data:
            logging.info("Parsing provided file as a Game Jam Entries JSON...")
            return get_jobs_for_game_jam_json(json_data)
    except json.JSONDecodeError:
        pass  # Not a valid JSON, okay...

    url_list = []
    with open(path) as f:  # Plain job list?
        for line in f:
            line = line.strip()
            if line.startswith("https://") or line.startswith("http://"):
                url_list.append(line)

    if len(url_list) > 0:
        logging.info("Parsing provided file as a list of URLs to fetch...")
        return url_list

    raise ValueError(f"File format is unknown - cannot read URLs to download.")


def get_jobs_for_url_or_path(path_or_url: str, settings: Settings) -> List[str]:
    """Returns a list of Game URLs for a given itch.io URL or file."""
    path_or_url = path_or_url.strip()

    if path_or_url.startswith("http://"):
        logging.info("HTTP link provided, upgrading to HTTPS")
        path_or_url = "https://" + path_or_url[7:]

    if path_or_url.startswith("https://"):
        client = ItchApiClient(settings.api_key, settings.user_agent)
        return get_jobs_for_itch_url(path_or_url, client)
    elif os.path.isfile(path_or_url):
        return get_jobs_for_path(path_or_url)
    else:
        raise NotImplementedError(f"Cannot handle path or URL: {path_or_url}")
