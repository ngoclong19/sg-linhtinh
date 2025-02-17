"""Whitelist/Blacklist Suggestion
"""

import argparse
import datetime
import enum
import json
import math
import pathlib
from typing import Any, Callable, NotRequired, TypeAlias, TypedDict, cast

import bs4
import pyrate_limiter
import requests
import requests_ratelimiter

SG_USER = "ngoclong19"
COOKIE_NAME = "PHPSESSID"
COOKIE_VALUE = ""

REQUEST_PER_SECOND = 4
REQUEST_PER_MINUTE = 120
REQUEST_PER_HOUR = 2400
REQUEST_PER_DAY = 14400
REQUEST_TIMEOUT = 8

DEBUG = True
INDENT = 2 if DEBUG else None

TZ_UTC = datetime.UTC

RequestsLimiterSession: TypeAlias = requests_ratelimiter.LimiterSession


class ExtractedArgs:
    no_cache: bool


class BaseUser(TypedDict):
    id: int
    username: str


class User(BaseUser):
    steam_id: str


class Winner(User):
    received: bool | None


class UserData(BaseUser):
    is_creator: NotRequired[bool]
    is_winner: NotRequired[bool]


class UserUpdateMode(enum.Enum):
    DEFAULT = 1
    CREATOR = 2
    WINNER = 3


class UsersData:
    """Data of users."""

    usernames: set[str]
    users: dict[str, UserData]

    def __init__(self):
        self.usernames = set()
        self.users = {}

    def update_user(
        self, user: User, update_mode: UserUpdateMode = UserUpdateMode.DEFAULT
    ):
        user_data: UserData = self.users.setdefault(
            user["steam_id"], cast(Any, {})
        )
        user_data["id"] = user["id"]
        user_data["username"] = user["username"]
        if update_mode == UserUpdateMode.CREATOR:
            user_data["is_creator"] = True
        if update_mode == UserUpdateMode.WINNER:
            user_data["is_winner"] = True

        self.usernames.add(user["username"])


class Giveaway(TypedDict):
    link: str
    end_timestamp: int
    entry_count: int
    received: NotRequired[bool]
    creator: User
    winners: NotRequired[list[Winner]]


class GiveawaysResponse(TypedDict):
    results: list[Giveaway]


def parse_args() -> ExtractedArgs:
    """Construct the argument parser and parse the arguments."""
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable the cache.",
    )
    return ap.parse_args(namespace=ExtractedArgs())


def init_session() -> RequestsLimiterSession:
    session = RequestsLimiterSession(
        REQUEST_PER_SECOND,
        REQUEST_PER_MINUTE,
        REQUEST_PER_HOUR,
        REQUEST_PER_DAY,
        bucket_class=pyrate_limiter.SQLiteBucket,
    )
    session.cookies.set(COOKIE_NAME, COOKIE_VALUE)  # type: ignore
    return session


def fetch_request(
    session: RequestsLimiterSession, url: str, params: dict[str, Any] | None
) -> requests.Response:
    return session.get(url, params=params, timeout=REQUEST_TIMEOUT)


def create_data_dir() -> pathlib.Path:
    data_dir = pathlib.Path("data")
    data_dir.mkdir(exist_ok=True)
    return data_dir


def get_current_time() -> datetime.datetime:
    return datetime.datetime.now(TZ_UTC)


def get_time(timestamp: int) -> datetime.datetime:
    return datetime.datetime.fromtimestamp(timestamp, TZ_UTC)


def fetch_giveaways(
    session: RequestsLimiterSession, fetch_won: bool = False
) -> GiveawaysResponse:
    url = f"https://www.steamgifts.com/user/{SG_USER}"
    params: dict[str, str | int] = {"format": "json"}
    if fetch_won:
        url += "/giveaways/won"
    else:
        params["include_winners"] = 1
    return fetch_request(session, url, params=params).json()


def save_data_to_json(giveaways: Any, filename: str):
    file: pathlib.Path = create_data_dir() / filename
    with open(file, "w", encoding="utf-8") as f:
        json.dump(giveaways, f, indent=INDENT)


def load_data_from_json(filename: str) -> Any | None:
    file: pathlib.Path = create_data_dir() / filename
    if pathlib.Path(file).exists():
        with open(file, encoding="utf-8") as f:
            return json.load(f)


def load_giveaways(
    session: RequestsLimiterSession, no_cache: bool = False
) -> tuple[GiveawaysResponse, GiveawaysResponse]:
    data_ga_created = "created.json"
    data_ga_won = "won.json"
    ga_created: GiveawaysResponse | None = None
    ga_won: GiveawaysResponse | None = None

    if not no_cache:
        # load saved giveaways
        ga_created = load_data_from_json(data_ga_created)
        ga_won = load_data_from_json(data_ga_won)

    if ga_created is None:
        # get and save created giveaways
        ga_created = fetch_giveaways(session)
        save_data_to_json(ga_created, data_ga_created)

    if ga_won is None:
        # get and save won giveaways
        ga_won = fetch_giveaways(session, fetch_won=True)
        save_data_to_json(ga_won, data_ga_won)

    return ga_created, ga_won


def load_ended_giveaways(
    session: RequestsLimiterSession, no_cache: bool = False
) -> list[Giveaway]:
    filename = "giveaways.json"
    giveaways_created: GiveawaysResponse
    giveaways_won: GiveawaysResponse

    giveaways: list[Giveaway] = []

    if not no_cache:
        giveaways = load_data_from_json(filename) or []
    if giveaways:
        return giveaways

    giveaways_created, giveaways_won = load_giveaways(session, no_cache)
    now: datetime.datetime = get_current_time()
    for giveaway in giveaways_created["results"] + giveaways_won["results"]:
        end: datetime.datetime = get_time(giveaway["end_timestamp"])
        if end < now:
            giveaways.append(giveaway)

    save_data_to_json(giveaways, filename)
    return giveaways


def process_giveaway_creator_and_winners(
    giveaway: Giveaway, fn_update_user: Callable[[User, UserUpdateMode], None]
):
    creator = giveaway["creator"]
    if creator["username"] == SG_USER and "winners" in giveaway:
        # gifts sent
        for winner in giveaway["winners"]:
            if winner["received"]:
                fn_update_user(winner, UserUpdateMode.WINNER)
    elif "received" in giveaway:
        # gifts won
        if giveaway["received"]:
            fn_update_user(creator, UserUpdateMode.CREATOR)


def get_giveaway_entries(
    session: RequestsLimiterSession, giveaway: Giveaway
) -> set[str]:
    entries: set[str] = set()
    page_count: int = math.ceil(giveaway["entry_count"] / 25)
    for page in range(1, page_count + 1):
        url: str = giveaway["link"] + "/entries"
        params: dict[str, int] | None = None
        if page > 1:
            url = url + "/search"
            params = {"page": page}
        r: requests.Response = fetch_request(session, url, params)

        soup = bs4.BeautifulSoup(r.text, "html.parser")
        for entry in soup.select("a.table__column__heading"):
            entries.add(entry.text)
    return entries


def load_users(
    session: RequestsLimiterSession,
    giveaways: list[Giveaway],
    no_cache: bool = False,
) -> dict[str, UserData]:
    filename = "users.json"
    users_data = UsersData()

    if not no_cache:
        users_data.users = load_data_from_json(filename) or {}
    # if users_data.users:
    #     return users_data.users

    skip = True
    for giveaway in giveaways:
        # load giveaway creator and winners
        process_giveaway_creator_and_winners(giveaway, users_data.update_user)

        if skip:
            continue
        # load giveaway entries
        users_data.usernames.update(get_giveaway_entries(session, giveaway))
        skip = True

    print(len(users_data.usernames))
    print(len(users_data.users))

    save_data_to_json(users_data.users, filename)
    return users_data.users


def main(no_cache: bool = False):
    session: RequestsLimiterSession = init_session()

    # load user's ended giveaways
    giveaways: list[Giveaway] = load_ended_giveaways(session, no_cache)
    load_users(session, giveaways, no_cache)

    print(len(giveaways))


if __name__ == "__main__":
    args: ExtractedArgs = parse_args()
    main(args.no_cache)
