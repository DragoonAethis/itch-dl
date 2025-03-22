from datetime import datetime
from typing import TypedDict, Any

from bs4 import BeautifulSoup


class InfoboxMetadata(TypedDict, total=False):
    updated_at: datetime
    released_at: datetime
    published_at: datetime
    status: str
    platforms: list[str]  # Windows/macOS/Linux/etc
    publisher: str
    author: dict[str, str]  # See impl below!
    authors: dict[str, str]  # Links
    genre: dict[str, str]  # Links
    tools: dict[str, str]  # Links
    license: dict[str, str]  # Links
    asset_license: dict[str, str]  # Links
    tags: dict[str, str]  # Links
    length: str
    multiplayer: dict[str, str]  # Links
    player_count: str
    accessibility: dict[str, str]  # Links
    inputs: dict[str, str]  # Links
    links: dict[str, str]  # Links
    mentions: dict[str, str]  # Links
    category: dict[str, str]  # Links


def parse_date_block(td: BeautifulSoup) -> datetime | None:
    abbr = td.find("abbr")
    if not abbr or "title" not in abbr.attrs:
        return None

    date_str, time_str = abbr["title"].split("@")
    date = datetime.strptime(date_str.strip(), "%d %B %Y")
    time = datetime.strptime(time_str.strip(), "%H:%M UTC")
    return datetime(date.year, date.month, date.day, time.hour, time.minute)


def parse_links(td: BeautifulSoup) -> dict[str, str]:
    """Parses blocks of comma-separated <a> blocks, returns a dict
    of link text -> URL it points at."""
    return {link.text.strip(): link["href"] for link in td.find_all("a")}


def parse_text_from_links(td: BeautifulSoup) -> list[str]:
    return list(parse_links(td).keys())


def parse_tr(name: str, content: BeautifulSoup) -> tuple[str, Any] | None:
    if name == "Updated":
        return "updated_at", parse_date_block(content)
    elif name == "Release date":
        return "released_at", parse_date_block(content)
    elif name == "Published":
        return "published_at", parse_date_block(content)
    elif name == "Status":
        return "status", parse_text_from_links(content)[0]
    elif name == "Platforms":
        return "platforms", parse_text_from_links(content)
    elif name == "Publisher":
        return "publisher", content.text.strip()
    elif name == "Rating":
        return None  # Read the AggregatedRating block instead!
    elif name == "Author":
        author, author_url = parse_links(content).popitem()
        return "author", {"author": author, "author_url": author_url}
    elif name == "Authors":
        return "authors", parse_links(content)
    elif name == "Genre":
        return "genre", parse_links(content)
    elif name == "Made with":
        return "tools", parse_links(content)
    elif name == "License":
        return "license", parse_links(content)
    elif name == "Code license":
        return "code_license", parse_links(content)
    elif name == "Asset license":
        return "asset_license", parse_links(content)
    elif name == "Tags":
        return "tags", parse_links(content)
    elif name == "Average session":
        return "length", parse_text_from_links(content)[0]
    elif name == "Languages":
        return "languages", parse_links(content)
    elif name == "Multiplayer":
        return "multiplayer", parse_links(content)
    elif name == "Player count":
        return "player_count", content.text.strip()
    elif name == "Accessibility":
        return "accessibility", parse_links(content)
    elif name == "Inputs":
        return "inputs", parse_links(content)
    elif name == "Links":
        return "links", parse_links(content)
    elif name == "Mentions":
        return "mentions", parse_links(content)
    elif name == "Category":
        return "category", parse_links(content)
    else:
        # Oops, you need to extend this with something new. Sorry.
        # Make sure to add the block name to InfoboxMetadata as well!
        raise NotImplementedError(f"Unknown infobox block name '{name}' - please file a new itch-dl issue.")


def parse_infobox(infobox: BeautifulSoup) -> InfoboxMetadata:
    """Feed it <div class="game_info_panel_widget">, out goes a dict
    of parsed metadata blocks."""
    meta = InfoboxMetadata()

    for tr in infobox.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue

        name_td, content_td = tds[0], tds[1]
        name = name_td.text.strip()

        parsed_block = parse_tr(name, content_td)
        if parsed_block:
            meta[parsed_block[0]] = parsed_block[1]  # noqa: PyTypedDict (non-literal TypedDict keys)

    return meta
