from datetime import datetime
from typing import TypedDict, Dict, List, Any, Tuple, Optional

from bs4 import BeautifulSoup


class InfoboxMetadata(TypedDict, total=False):
    pass


def parse_date_block(td: BeautifulSoup) -> datetime:
    raise NotImplementedError("Not yet!")


def parse_links(td: BeautifulSoup) -> Dict[str, str]:
    """Parses blocks of comma-separated <a> blocks, returns a dict
    of link text -> URL it points at."""
    pass


def parse_text_from_links(td: BeautifulSoup) -> List[str]:
    return list(parse_links(td).keys())


def parse_tr(name: str, content: BeautifulSoup) -> Optional[Tuple[str, Any]]:
    if name == "Updated":
        pass


def parse_infobox(infobox: BeautifulSoup) -> dict:
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
            meta[parsed_block[0]] = parsed_block[1]

    return meta
