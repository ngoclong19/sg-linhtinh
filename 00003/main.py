# pyright: reportUnknownMemberType=false
"""SteamGifts Whitelist/Blacklist Suggestion.
"""
import argparse
import datetime
import json
import logging
import math
import sys
from typing import Any, Literal, NotRequired, TypedDict, cast

import bs4
import pyrate_limiter
import requests
import requests_ratelimiter
import tinydb
import urllib3
from tinydb import queries, table
from urllib3 import util

SG_USER = "ngoclong19"
COOKIE_NAME = "PHPSESSID"
COOKIE_VALUE = ""

DEBUG = True
INDENT = 2 if DEBUG else None

REQUEST_PER_SECOND = 4
REQUEST_PER_MINUTE = 120
REQUEST_PER_HOUR = 2400
REQUEST_PER_DAY = 14400
REQUEST_TIMEOUT = 13

CACHE_FILE = "data/cache.json"
CACHE_LIVE_SECONDS = 7 * 24 * 3600
CACHE_GIVEAWAYS = "giveaways"
CACHE_USERNAMES = "usernames"
CACHE_USERS = "users"


RequestMethod = Literal["head", "get"]
UserUpdateMode = Literal["default", "creator", "winner"]


class ExtractedArgs:
    no_cache: bool


class User(TypedDict):
    id: NotRequired[int]
    steam_id: str
    username: str


class Winner(User):
    received: bool


class UserData(User):
    is_creator: NotRequired[bool]
    is_winner: NotRequired[bool]
    timestamp: int


class Giveaway(TypedDict):
    id: int
    link: str
    end_timestamp: int
    entry_count: int
    received: NotRequired[bool]
    creator: User
    winners: NotRequired[list[Winner]]
    entries_page_offset: NotRequired[int]


def parse_args() -> ExtractedArgs:
    """Construct the argument parser and parse the arguments."""
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable the cache.",
    )
    return ap.parse_args(namespace=ExtractedArgs())


def get_cache() -> tinydb.TinyDB:
    return tinydb.TinyDB(CACHE_FILE, create_dirs=True, indent=INDENT)


def get_current_timestamp() -> int:
    return int(datetime.datetime.now(datetime.UTC).timestamp())


def get_log_formatter() -> logging.Formatter:
    # create formatter
    return logging.Formatter(
        "%(asctime)s|%(name)s|%(levelname)s|%(funcName)s() %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )


def get_logger() -> logging.Logger:
    # create logger
    logger: logging.Logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)

    # create console handler and set level to debug
    handler = logging.StreamHandler()
    # handler.setLevel(logging.DEBUG)

    # add formatter to ch
    handler.setFormatter(get_log_formatter())

    # add ch to logger
    if not logger.hasHandlers():
        logger.addHandler(handler)
    return logger


def init_session() -> requests.Session:
    urllib3.add_stderr_logger(logging.WARNING).setFormatter(get_log_formatter())

    retry_strategy = util.Retry(total=500, backoff_factor=5)
    adapter = requests_ratelimiter.LimiterAdapter(
        REQUEST_PER_SECOND,
        REQUEST_PER_MINUTE,
        REQUEST_PER_HOUR,
        REQUEST_PER_DAY,
        bucket_class=pyrate_limiter.SQLiteBucket,
        max_retries=retry_strategy,
    )

    session = requests.Session()
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    session.cookies.set(COOKIE_NAME, COOKIE_VALUE)
    return session


def fetch_request(
    session: requests.Session,
    url: str,
    params: dict[str, Any] | None = None,
    allow_redirects: bool = True,
    *,
    method: RequestMethod = "get",
) -> requests.Response:
    if method == "head":
        return session.head(url, timeout=REQUEST_TIMEOUT)
    return session.get(
        url,
        params=params,
        timeout=REQUEST_TIMEOUT,
        allow_redirects=allow_redirects,
    )


def is_logged_in(session: requests.Session) -> bool:
    r = fetch_request(
        session,
        "https://www.steamgifts.com/account/settings/profile",
        method="head",
    )
    # if logged in, it is not redirected to home page
    return not r.is_redirect


def fetch_giveaways(
    session: requests.Session, *, fetch_won: bool = False
) -> list[Giveaway]:
    """Fetch the latest 100 giveaways."""
    url = f"https://www.steamgifts.com/user/{SG_USER}"
    params: dict[str, str | int] = {"format": "json"}
    if fetch_won:
        url += "/giveaways/won"
    else:
        params["include_winners"] = 1
    return fetch_request(session, url, params).json()["results"]


def upsert_user(
    user: User,
    no_cache: bool = False,
    *,
    update_mode: UserUpdateMode = "default",
):
    """Update users, if they exist, insert them otherwise."""
    with get_cache() as db:
        users: table.Table = db.table(CACHE_USERS)
        usernames: table.Table = db.table(CACHE_USERNAMES)

        now: int = get_current_timestamp()

        user_query: queries.QueryInstance = (
            tinydb.Query()["steam_id"] == user["steam_id"]
        )
        user_new_query: queries.QueryInstance = (
            tinydb.Query()["timestamp"] >= now - CACHE_LIVE_SECONDS
        )
        username_query: queries.QueryInstance = (
            tinydb.Query()["username"] == user["username"]
        )

        if user["steam_id"]:
            if not no_cache and users.contains(user_query & user_new_query):
                # skip this user
                return
            user_data: UserData = {
                "id": user["id"],
                "steam_id": user["steam_id"],
                "username": user["username"],
                "timestamp": int(now),
            }
            if update_mode == "creator":
                user_data["is_creator"] = True
            if update_mode == "winner":
                user_data["is_winner"] = True
            users.upsert(user_data, user_query)
        elif usernames.contains(username_query):
            # skip this username
            return

        usernames.upsert({"username": user["username"]}, username_query)


def process_giveaway_entry_page(
    session: requests.Session, giveaway: Giveaway, page: int
) -> list[str]:
    logger: logging.Logger = get_logger()
    page_count: int = math.ceil(giveaway["entry_count"] / 25)
    url: str = giveaway["link"] + "/entries"
    params: dict[str, int] | None = None

    logger.info(
        "Retrieving giveaway (ID: %d) entry page %d out of %d...",
        giveaway["id"],
        page,
        page_count,
    )
    if page > 1:
        url = url + "/search"
        params = {"page": page}
    r: requests.Response = fetch_request(session, url, params)

    soup = bs4.BeautifulSoup(r.text, "html.parser")
    logger.info(
        # pylint: disable-next=line-too-long
        "Finished retrieving giveaway (ID: %d) entry page %d out of %d.",
        giveaway["id"],
        page,
        page_count,
    )
    return [entry.text for entry in soup.select("a.table__column__heading")]


def get_giveaway_entries(
    session: requests.Session, giveaway: Giveaway, no_cache: bool = False
) -> list[str]:
    logger: logging.Logger = get_logger()
    entries: list[str] = []
    page_offset = 1 if no_cache else giveaway.get("entries_page_offset", 0) + 1
    page_count: int = math.ceil(giveaway["entry_count"] / 25)

    with get_cache() as db:
        logger.info(
            "Retrieving a total of %d giveaway entry pages...",
            page_count,
        )
        giveaways: table.Table = db.table(CACHE_GIVEAWAYS)
        for page in range(page_offset, page_count + 1):
            entries.extend(process_giveaway_entry_page(session, giveaway, page))
            giveaways.update(
                {"entries_page_offset": page},
                tinydb.Query()["id"] == giveaway["id"],
            )
        logger.info(
            "Finished retrieving a total of %d giveaway entry pages.",
            page_count,
        )
    return entries


def filter_ended_giveaways(
    session: requests.Session, no_cache: bool = False
) -> list[Giveaway]:
    with get_cache() as db:
        giveaways: table.Table = db.table(CACHE_GIVEAWAYS)
        now: int = get_current_timestamp()
        # filter new giveaways
        cond: queries.QueryInstance = (
            tinydb.Query()["end_timestamp"] >= now - CACHE_LIVE_SECONDS
        )
        if no_cache or not giveaways.contains(cond):
            # there are only outdated giveaways
            giveaways.truncate()
        if not giveaways:
            # get created and won giveaways
            giveaways.insert_multiple(fetch_giveaways(session))
            giveaways.insert_multiple(fetch_giveaways(session, fetch_won=True))

        # filter ended giveaways
        cond = tinydb.Query()["end_timestamp"] < now
        return cast(list[Giveaway], giveaways.search(cond))


def process_giveaway(
    session: requests.Session, giveaway: Giveaway, no_cache: bool = False
):
    # load giveaway creator and winners
    creator: User = giveaway["creator"]
    if creator["username"] == SG_USER and "winners" in giveaway:
        # gifts sent
        for winner in giveaway["winners"]:
            if winner["received"]:
                upsert_user(winner, no_cache, update_mode="winner")
    elif "received" in giveaway:
        # gifts won
        if giveaway["received"]:
            upsert_user(creator, no_cache, update_mode="creator")

    # load giveaway entries
    for entry in get_giveaway_entries(session, giveaway, no_cache):
        upsert_user({"username": entry, "steam_id": ""}, no_cache)


def load_giveaways(session: requests.Session, no_cache: bool = False):
    """Fetch created and won giveaways."""
    logger: logging.Logger = get_logger()
    giveaways_ended: list[Giveaway] = filter_ended_giveaways(session, no_cache)

    # loop over ended giveaways
    giveaways_ended.sort(key=lambda ga: ga["end_timestamp"])
    giveaway_count: int = len(giveaways_ended)
    logger.info(
        "Retrieving a total of %d end giveaways...",
        giveaway_count,
    )
    for index, giveaway in enumerate(giveaways_ended, start=1):
        if (
            giveaway.get("entries_page_offset", 0) * 25
            >= giveaway["entry_count"]
        ):
            # skipped
            continue
        logger.info(
            "Retrieving end giveaway %d out of %d (ID: %d)...",
            index,
            giveaway_count,
            giveaway["id"],
        )
        process_giveaway(session, giveaway, no_cache)
        logger.info(
            "Finished retrieving end giveaway %d out of %d (ID: %d).",
            index,
            giveaway_count,
            giveaway["id"],
        )
    logger.info(
        "Finished retrieving a total of %d end giveaways.",
        giveaway_count,
    )


def load_user_infos(session: requests.Session):
    with get_cache() as db:
        usernames = db.table(CACHE_USERNAMES)

        for doc in usernames:
            username = cast(str, doc["username"])
            r = fetch_request(
                session,
                f"https://www.steamgifts.com/user/{username}",
                allow_redirects=False,
            )
            if r.is_redirect:
                # invalid username
                continue

            user_stats = {}
            soup = bs4.BeautifulSoup(r.text, "html.parser")
            rows = soup.select(".featured__table__row")
            for row in rows:
                row_left = row.select_one(".featured__table__row__left")
                row_right = row.select_one(".featured__table__row__right")
                if not (row_left and row_right):
                    continue
                match row_left.text:
                    case "Role":
                        user_stats["role"] = row_right.text.lower()
                    case "Last Online":
                        if row_right.span:
                            user_stats["last_online"] = row_right.span.get(
                                "data-timestamp", str(get_current_timestamp())
                            )
                    case "Registered":
                        if row_right.span:
                            user_stats["registered"] = row_right.span[
                                "data-timestamp"
                            ]
                    case "Comments":
                        user_stats["comments"] = row_right.text
                    case "Giveaways Entered":
                        user_stats["entered"] = row_right.text
                    case "Gifts Won":
                        if row_right.span and row_right.span.span:
                            # tooltip_data = cast(
                            #     str, row_right.span.span["data-ui-tooltip"]
                            # )
                            tooltip_data = json.loads(
                                cast(
                                    str, row_right.span.span["data-ui-tooltip"]
                                )
                            )["rows"]
                            print(tooltip_data)
                        user_stats["won"] = {
                            "count": 0,
                            "full": 0,
                            "reduced": 0,
                            "zero": 0,
                            "not_received": 0,
                            "value": 0,
                            "real_value": 0,
                        }
                    case "Gifts Sent":
                        user_stats["sent"] = {
                            "count": 0,
                            "full": 0,
                            "reduced": 0,
                            "zero": 0,
                            "awaiting_feedback": 0,
                            "not_received": 0,
                            "value": 0,
                            "real_value": 0,
                        }
                    case "Contributor Level":
                        user_stats["level"] = 0
                    case _:
                        pass
            print(username)
            print(user_stats)
            break


def main(no_cache: bool = False):
    session: requests.Session = init_session()
    if not is_logged_in(session):
        print("Logged out. Please update PHPSESSID cookie value.")
        sys.exit(1)
    load_giveaways(session, no_cache)
    load_user_infos(session)


if __name__ == "__main__":
    args: ExtractedArgs = parse_args()
    main(args.no_cache)
