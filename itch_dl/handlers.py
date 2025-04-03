import json
import os.path
import logging
import urllib.parse

from http.client import responses
from bs4 import BeautifulSoup

from .api import ItchApiClient
from .utils import ItchDownloadError, get_int_after_marker_in_json, should_skip_item_by_glob, should_skip_item_by_regex
from .consts import ITCH_API, ITCH_BASE, ITCH_URL, ITCH_BROWSER_TYPES
from .config import Settings
from .keys import get_owned_games


def get_jobs_for_game_jam_json(game_jam_json: dict) -> list[str]:
    if "jam_games" not in game_jam_json:
        raise Exception("Provided JSON is not a valid itch.io jam JSON.")

    return [g["game"]["url"] for g in game_jam_json["jam_games"]]


def get_game_jam_json(jam_url: str, client: ItchApiClient) -> dict:
    r = client.get(jam_url)
    if not r.ok:
        raise ItchDownloadError(f"Could not download the game jam site: {r.status_code} {r.reason}")

    jam_id: int | None = get_int_after_marker_in_json(r.text, "I.ViewJam", "id")
    if jam_id is None:
        raise ItchDownloadError(
            "Provided site did not contain the Game Jam ID. Provide "
            "the path to the game jam entries JSON file instead, or "
            "create an itch-dl issue with the Game Jam URL.",
        )

    logging.info("Extracted Game Jam ID: %d", jam_id)
    r = client.get(f"{ITCH_URL}/jam/{jam_id}/entries.json")
    if not r.ok:
        raise ItchDownloadError(f"Could not download the game jam entries list: {r.status_code} {r.reason}")

    return r.json()


def get_jobs_for_browse_url(url: str, client: ItchApiClient) -> list[str]:
    """
    Every browser page has a hidden RSS feed that can be accessed by
    appending .xml to its URL. An optional "page" argument lets us
    iterate over their contents. When no more elements are available,
    the last returned <channel> has no <item> children.

    The input URL is cleaned in the main URL handler, so append the
    .xml?page=N suffix and iterate until we've caught 'em all.
    """
    page = 1
    found_urls: set[str] = set()
    logging.info("Scraping game URLs from RSS feeds for %s", url)

    while True:
        logging.info("Downloading page %d (found %d URLs total)", page, len(found_urls))
        r = client.get(f"{url}.xml?page={page}", append_api_key=False)
        if not r.ok:
            logging.info("RSS feed returned %s, finished.", r.reason)
            break

        soup = BeautifulSoup(r.text, features="xml")
        rss_items = soup.find_all("item")
        if len(rss_items) < 1:
            logging.info("No more items, finished.")
            break

        logging.info("Found %d items.", len(rss_items))
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


def get_jobs_for_collection_json(url: str, client: ItchApiClient) -> list[str]:
    page = 1
    found_urls: set[str] = set()

    while True:
        logging.info("Downloading page %d (found %d URLs total)", page, len(found_urls))
        r = client.get(url, data={"page": page}, timeout=15)
        if not r.ok:
            logging.info("Collection page %d returned %d %s, finished.", page, r.status_code, r.reason)
            break

        data = r.json()

        if len(data["collection_games"]) < 1:
            logging.info("No more items, finished.")
            break

        for item in data["collection_games"]:
            found_urls.add(item["game"]["url"])

        if len(data["collection_games"]) == data["per_page"]:
            page += 1
        else:
            break

    if len(found_urls) == 0:
        raise ItchDownloadError("No game URLs found to download.")

    return list(found_urls)


def get_jobs_for_creator(creator: str, client: ItchApiClient) -> list[str]:
    logging.info("Downloading public games for creator %s", creator)
    r = client.get(f"https://{ITCH_BASE}/profile/{creator}", append_api_key=False)
    if not r.ok:
        raise ItchDownloadError(f"Could not fetch the creator page: HTTP {r.status_code} {responses[r.status_code]}")

    prefix = f"https://{creator}.{ITCH_BASE}/"
    game_links = set()

    soup = BeautifulSoup(r.text, features="xml")
    for link in soup.select("a.game_link"):
        link_url = link.attrs.get("href")
        if not link_url:
            continue

        if link_url.startswith(prefix):
            game_links.add(link_url)

    return sorted(game_links)


def get_jobs_for_itch_url(url: str, client: ItchApiClient) -> list[str]:
    if url.startswith("http://"):
        logging.info("HTTP link provided, upgrading to HTTPS")
        url = "https://" + url[7:]

    if url.startswith(f"https://www.{ITCH_BASE}/"):
        logging.info("Correcting www.%s to %s", ITCH_BASE, ITCH_BASE)
        url = ITCH_URL + "/" + url[20:]

    url_parts = urllib.parse.urlparse(url)
    url_path_parts: list[str] = [x for x in str(url_parts.path).split("/") if len(x) > 0]

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
            clean_browse_url = "/".join([ITCH_URL, *url_path_parts])
            return get_jobs_for_browse_url(clean_browse_url, client)

        elif site in ("b", "bundle"):  # Bundles
            raise NotImplementedError("itch-dl cannot download bundles yet.")

        elif site in ("j", "jobs"):  # Jobs...
            raise ValueError("itch-dl cannot download a job.")

        elif site in ("t", "board", "community"):  # Forums
            raise ValueError("itch-dl cannot download forums.")

        elif site == "profile":  # Forum Profile
            if len(url_path_parts) >= 2:
                return get_jobs_for_creator(url_path_parts[1], client)

            raise ValueError("itch-dl expects a username in profile links.")

        elif site == "my-purchases":  # User Purchased Games
            return get_owned_games(client)

        elif site == "c":  # Collections
            collection_id = url_path_parts[1]
            clean_collection_url = f"{ITCH_API}/collections/{collection_id}/collection-games"
            return get_jobs_for_collection_json(clean_collection_url, client)

        # Something else?
        raise NotImplementedError(f'itch-dl does not understand "{site}" URLs. Please file a new issue.')

    elif url_parts.netloc.endswith(f".{ITCH_BASE}"):
        if len(url_path_parts) == 0:  # Author
            return get_jobs_for_creator(url_parts.netloc.split(".")[0], client)

        else:  # Single game
            # Just clean and return the URL:
            return [f"https://{url_parts.netloc}/{url_path_parts[0]}"]

    else:
        raise ValueError(f"Unknown domain: {url_parts.netloc}")


def get_jobs_for_path(path: str) -> list[str]:
    try:  # Game Jam Entries JSON?
        with open(path, "rb") as f:
            json_data = json.load(f)

        if not isinstance(json_data, dict):
            raise ValueError(f"File does not contain a JSON dict: {path}")

        if "jam_games" in json_data:
            logging.info("Parsing provided file as a Game Jam Entries JSON...")
            return get_jobs_for_game_jam_json(json_data)
    except json.JSONDecodeError:
        pass  # Not a valid JSON, okay...

    url_list = []
    with open(path) as f:  # Plain job list?
        for line in f:
            link = line.strip()
            if link.startswith("https://") or link.startswith("http://"):
                url_list.append(link)

    if len(url_list) > 0:
        logging.info("Parsing provided file as a list of URLs to fetch...")
        return url_list

    raise ValueError("File format is unknown - cannot read URLs to download.")


def get_jobs_for_url_or_path(path_or_url: str, settings: Settings) -> list[str]:
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


def preprocess_job_urls(jobs: list[str], settings: Settings) -> list[str]:
    cleaned_jobs = set()
    for base_job in jobs:
        job = base_job.strip()

        if should_skip_item_by_glob("URL", job, settings.filter_urls_glob):
            continue

        if should_skip_item_by_regex("URL", job, settings.filter_urls_regex):
            continue

        cleaned_jobs.add(job)

    return list(cleaned_jobs)
