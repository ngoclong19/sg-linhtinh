"""Fetch Music Brainz
"""

# https://musicbrainz.org/ws/2/recording?fmt=json&query=firstreleasedate:1990%20AND%20tag:rock&limit=100

import datetime
import json
import pathlib
import re
import time
from typing import TypedDict

import requests

MAX_CACHE_LIVE = 1  # days
RATE_LIMITING_DELAY = 1  # seconds
REQUEST_LIMIT = 100
REQUEST_TIMEOUT = 60  # seconds


class MBData(TypedDict):
    timestamp: str
    count: int
    offset: int
    recordings: list[str]


class MBRecording(TypedDict):
    title: str


class MBRecordingResponse(TypedDict):
    created: str
    count: int
    offset: int
    recordings: list[MBRecording]


def fetch_json_data(
    year: int, offset: int, timestamp: datetime.datetime, bypass_cache: bool
) -> MBRecordingResponse:
    now = datetime.datetime.now(tz=datetime.UTC)
    if bypass_cache or now - timestamp > datetime.timedelta(
        days=MAX_CACHE_LIVE
    ):
        offset = 0

    params = {
        "fmt": "json",
        "query": f"firstreleasedate:{year} AND tag:rock",
        "limit": REQUEST_LIMIT,
        "offset": offset,
    }

    r = requests.get(
        "https://musicbrainz.org/ws/2/recording",
        params=params,
        timeout=REQUEST_TIMEOUT,
    )

    if r.status_code != 200:
        raise RuntimeError(f"Cannot fetch Music Brainz. {r.text}")

    return r.json()


def get_current_time() -> str:
    return datetime.datetime.now().isoformat(" ", "seconds")


def init_json_data() -> MBData:
    return {
        "timestamp": datetime.datetime(
            1, 1, 1, tzinfo=datetime.UTC
        ).isoformat(),
        "count": -1,
        "offset": 0,
        "recordings": [],
    }


def load_json_data(file: str) -> MBData:
    json_data: MBData = {}  # type: ignore
    if pathlib.Path(file).exists():
        with open(file, encoding="utf-8") as f:
            json_data = json.load(f)
    return json_data


def save_json_data(file: str, json_data: MBData, debug: bool):
    indent = 2 if debug else None
    with open(file, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=indent)


def update_json_data(
    current_data: MBData, new_data: MBRecordingResponse, pattern: str
) -> MBData:
    if len(new_data) == 0:
        return current_data

    merged_data: MBData = {}  # type: ignore
    merged_data["timestamp"] = new_data["created"]
    merged_data["count"] = new_data["count"]
    merged_data["offset"] = new_data["offset"]
    merged_data["recordings"] = current_data["recordings"]

    regex_sub = re.compile(r"\(.+\)")
    regex_match = re.compile(pattern, re.I)
    recordings = merged_data["recordings"]
    for recording in new_data["recordings"]:
        title = recording["title"]
        title = regex_sub.sub("", title).strip(" /").lower()
        title = title.replace("\u2019", "'")

        if regex_match.match(title) and title not in recordings:
            recordings.append(title)

    return merged_data


def main(
    year: int = 1990,
    pattern: str = r"^[a-z]{4}$",
    bypass_cache: bool = False,
    debug: bool = False,
):
    filename = f"mb_{year}.json"
    print(f"{get_current_time()}|Download data for year {year}.")

    mb_data = load_json_data(filename)
    if len(mb_data) == 0:
        mb_data = init_json_data()

    while True:
        timestamp = datetime.datetime.fromisoformat(mb_data["timestamp"])
        count = mb_data["count"]
        offset = mb_data["offset"] + REQUEST_LIMIT

        if count == -1 or offset < count:
            r_json = fetch_json_data(year, offset, timestamp, bypass_cache)
            progress = "-/-" if count == -1 else f"{offset}/{count}"
            print(f"{get_current_time()}|Downloading {progress}.")
            time.sleep(RATE_LIMITING_DELAY)
        else:
            r_json: MBRecordingResponse = {}  # type: ignore
            print(f"{get_current_time()}|Download completed.")
            break

        mb_data = update_json_data(mb_data, r_json, pattern)

        save_json_data(filename, mb_data, debug)


if __name__ == "__main__":
    main(debug=True)
