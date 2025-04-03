import re
import logging
from fnmatch import fnmatch

from typing import Literal


class ItchDownloadError(Exception):
    pass


def get_int_after_marker_in_json(text: str, marker: str, key: str) -> int | None:
    """
    Many itch.io sites use a pattern like this: Most of the HTML page
    is prerendered, but certain interactive objects are handled with
    JavaScript initialized with `I.WidgetHandler({"id": 123, ...})`
    somewhere near the end of each page. Those config blocks often
    contain metadata like game/page IDs that we want to extract.
    """
    marker_line: str | None = None
    for line in reversed(text.splitlines()):
        marker_index = line.find(marker)
        if marker_index != -1:
            marker_line = line[marker_index:]
            break

    if marker_line is None:
        return None

    # Notice double-slashes in the f-string (not r-string)!
    pattern = f'\\"{key}\\":\\s?(\\d+)'

    found_ints = re.findall(pattern, marker_line)
    if len(found_ints) != 1:
        return None

    return int(found_ints[0])


def should_skip_item_by_glob(kind: Literal["File"] | Literal["URL"], item: str, glob: str) -> bool:
    if glob and not fnmatch(item, glob):
        logging.info("%s '%s' does not match the glob filter '%s', skipping", kind, item, glob)
        return True

    return False


def should_skip_item_by_regex(kind: Literal["File"] | Literal["URL"], item: str, regex: str) -> bool:
    if regex and not re.fullmatch(regex, item):
        logging.info("%s '%s' does not match the regex filter '%s', skipping", kind, item, regex)
        return True

    return False
