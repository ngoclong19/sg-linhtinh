"""Suggest a list of users to remove from your whitelist.
"""

import configparser
import json
import pathlib
import pickle
import re
import time
import zipfile
from typing import Any, cast

import bs4
import numpy as np
import requests
import requests.adapters
import urllib3.util


def add_sent_won_ratio(profile: dict[str, float]):
    profile["ratio"] = (
        profile["sent_count"] / profile["won_count"]
        if profile["won_count"]
        else 0
    )
    profile["ratio_full"] = (
        profile["sent_full"] / profile["won_full"] if profile["won_full"] else 0
    )
    profile["ratio_reduced"] = (
        profile["sent_reduced"] / profile["won_reduced"]
        if profile["won_reduced"]
        else 0
    )
    profile["ratio_zero"] = (
        profile["sent_zero"] / profile["won_zero"] if profile["won_zero"] else 0
    )
    profile["ratio_cv"] = (
        profile["sent_cv"] / profile["won_cv"] if profile["won_cv"] else 0
    )
    profile["ratio_real_cv"] = (
        profile["sent_real_cv"] / profile["won_real_cv"]
        if profile["won_real_cv"]
        else 0
    )


def calculate_iqr(data: list[int]) -> tuple[np.floating[Any], np.floating[Any]]:
    """Calculate Interquartile Range (IQR) using numpy.

    Returns: `tuple(q1, q3)`
    """
    q1 = np.percentile(data, 25)
    q3 = np.percentile(data, 75)
    return (q1, q3)


def check_not_activated(na_page: str) -> dict[str, int | list[str]]:
    results: dict[str, int | list[str]] = {}
    if "has a private profile" in na_page:
        results["activated"] = 0
        results["not_activated"] = []
        results["unknown"] = 1
    else:
        response_html = bs4.BeautifulSoup(na_page, "html.parser")
        elements = cast(
            bs4.ResultSet[bs4.Tag],
            response_html.find_all(class_="notActivatedGame"),
        )
        results["not_activated"] = []
        for element in elements:
            results["not_activated"].append(element.get_text())
        results["activated"] = 0 if elements else 1
        results["unknown"] = 0
    return results


def check_multiple(mw_page: str) -> dict[str, int | list[str]]:
    results: dict[str, int | list[str]] = {}
    response_html = bs4.BeautifulSoup(mw_page, "html.parser")
    elements = cast(
        bs4.ResultSet[bs4.Tag], response_html.find_all(class_="multiplewins")
    )
    results["multiple"] = []
    for element in elements:
        results["multiple"].append(element.get_text())
    results["not_multiple"] = 0 if elements else 1
    return results


def check_not_activated_multiple_win(
    na_page: str, mw_page: str
) -> dict[str, int | list[str]]:
    return check_not_activated(na_page) | check_multiple(mw_page)


def export_list(
    session: requests.Session,
    user_list: list[str] | None = None,
    next_page: int = 1,
) -> list[str]:
    print(f"Retrieving list (page {next_page})...")
    url = "https://www.steamgifts.com/account/manage/whitelist/search"
    params = {"page": next_page}
    response: requests.Response = fetch_request(session, url, params)
    if response.status_code != 200:
        raise_not_logged_in()
    response_html = bs4.BeautifulSoup(response.text, "html.parser")
    elements = cast(
        bs4.ResultSet[bs4.Tag],
        response_html.find_all(class_="table__column__heading"),
    )
    if user_list is None:
        user_list = []
    for element in elements:
        user_list.append(element.get_text())
    pagination = cast(
        bs4.Tag, response_html.find(class_="pagination__navigation")
    )
    if pagination and "is-selected" not in cast(
        list[str],
        cast(bs4.Tag, pagination.contents[-1]).get(
            "class", cast(bs4.element.AttributeValueList, [])
        ),
    ):
        return export_list(session, user_list, next_page + 1)
    else:
        print("List exported with success!")
        return user_list


def fetch_request(
    session: requests.Session, url: str, params: dict[str, Any] | None = None
) -> requests.Response:
    time.sleep(1)
    response: requests.Response = session.get(
        url, params=params, timeout=10, allow_redirects=False
    )
    response.raise_for_status()
    return response


def filter_users(data: dict[str, Any]) -> list[str]:
    users: dict[str, Any] = data["users"]
    conditions: dict[str, float] = filter_users_conditions(data)
    usernames: list[str] = [
        k for k, v in users.items() if filter_users_func(v, conditions)
    ]
    print()
    print("Filter conditions:")
    for k, v in conditions.items():
        print(f"- {k}: {v}")
    return usernames


def filter_users_conditions(data: dict[str, Any]) -> dict[str, float]:
    my_profile: dict[str, Any] = data["my_profile"]
    my_profile_age = time.time() - my_profile["registration_date"]
    conditions: dict[str, float] = {}
    conditions["min_sent_real_cv"] = my_profile["sent_real_cv"]
    conditions["min_ratio_real_cv"] = my_profile["ratio_real_cv"]
    conditions["max_won_count"] = (
        my_profile["won_count"] / my_profile_age * 31536000
    )

    users: dict[str, Any] = data["users"]
    na_counts = [
        len(v["namwc"]["not_activated"])
        for v in users.values()
        if v["namwc"]["not_activated"]
    ]
    mw_counts = [
        len(v["namwc"]["multiple"])
        for v in users.values()
        if v["namwc"]["multiple"]
    ]
    na_q1, na_q3 = calculate_iqr(na_counts)
    na_iqr = na_q3 - na_q1
    conditions["na_lower_limit"] = (na_q1 - 1.5 * na_iqr).astype(float)
    conditions["na_upper_limit"] = (na_q3 + 1.5 * na_iqr).astype(float)
    mw_q1, mw_q3 = calculate_iqr(mw_counts)
    mw_iqr = mw_q3 - mw_q1
    conditions["mw_lower_limit"] = (mw_q1 - 1.5 * mw_iqr).astype(float)
    conditions["mw_upper_limit"] = (mw_q3 + 1.5 * mw_iqr).astype(float)
    return conditions


def filter_users_func(user: dict[str, Any], conds: dict[str, float]) -> bool:
    user_profile = user["profile"]
    user_namwc = user["namwc"]
    if user_profile["won_count"] and user_namwc["unknown"]:
        # The user has a private profile.
        return True
    if len(user_namwc["not_activated"]) > conds["na_upper_limit"]:
        # The user has too many not-activated wins.
        return True
    if len(user_namwc["multiple"]) > conds["mw_upper_limit"]:
        # The user has too many multiple wins.
        return True
    if user_profile["won_count"] <= conds["max_won_count"]:
        # Exception: The user has won less than my yearly average.
        return False
    if user_profile["won_real_cv"]:
        if user_profile["ratio_real_cv"] < conds["min_ratio_real_cv"]:
            # The user won something and has a lower real value ratio than me.
            return True
    else:
        if user_profile["sent_real_cv"] < conds["min_sent_real_cv"]:
            # The user won nothing and has a lower contributor value than me.
            return True
    return False


def load_my_profile() -> dict[str, float]:
    url = "https://www.steamgifts.com/account/settings/profile"
    response: requests.Response
    with requests.Session() as session:
        set_cookie(session)
        response = fetch_request(session, url)
    if response.status_code != 200:
        raise_not_logged_in()
    response_html = bs4.BeautifulSoup(response.text, "html.parser")
    element = cast(bs4.Tag, response_html.find(class_="nav__avatar-outer-wrap"))
    href = cast(str, element.get("href"))
    username = cast(re.Match[str], re.search("/user/(.+)", href)).group(1)
    url = "https://www.steamgifts.com/user/" + username
    with requests.Session() as session:
        response = fetch_request(session, url)
    my_profile: dict[str, float] = load_profile(response.text)
    add_sent_won_ratio(my_profile)
    print(f"Logged in as `{username}`.")
    return my_profile


def load_profile(user_page: str) -> dict[str, float]:
    profile: dict[str, float] = {}
    page_html = bs4.BeautifulSoup(user_page, "html.parser")
    elements = cast(
        bs4.ResultSet[bs4.Tag],
        page_html.find_all(
            class_="featured__table__row__left",
            string=re.compile(r"Registered|Gifts\s(Won|Sent)"),
        ),
    )
    re1: re.Pattern[str] = re.compile(",")
    re2: re.Pattern[str] = re.compile("[$,]")
    for element in elements:
        match element.get_text():
            case "Registered":
                profile["registration_date"] = int(
                    cast(
                        str,
                        cast(
                            bs4.Tag,
                            cast(
                                bs4.Tag, element.find_next_sibling("div")
                            ).find("span"),
                        ).get("data-timestamp"),
                    )
                )
            case "Gifts Won":
                tooltips = cast(
                    bs4.ResultSet[bs4.Tag],
                    cast(bs4.Tag, element.find_next_sibling("div")).find_all(
                        attrs={"data-ui-tooltip": True}
                    ),
                )
                rows = json.loads(
                    cast(str, tooltips[0].get("data-ui-tooltip"))
                )["rows"]
                profile["won_count"] = int(
                    re1.sub("", rows[0]["columns"][1]["name"])
                )
                profile["won_full"] = int(
                    re1.sub("", rows[1]["columns"][1]["name"])
                )
                profile["won_reduced"] = int(
                    re1.sub("", rows[2]["columns"][1]["name"])
                )
                profile["won_zero"] = int(
                    re1.sub("", rows[3]["columns"][1]["name"])
                )
                profile["won_not_received"] = int(
                    re1.sub("", rows[4]["columns"][1]["name"])
                )
                rows = json.loads(
                    cast(str, tooltips[1].get("data-ui-tooltip"))
                )["rows"]
                profile["won_cv"] = float(re2.sub("", tooltips[1].get_text()))
                profile["won_real_cv"] = float(
                    re2.sub("", rows[0]["columns"][1]["name"])
                )
            case "Gifts Sent":
                tooltips = cast(
                    bs4.ResultSet[bs4.Tag],
                    cast(bs4.Tag, element.find_next_sibling("div")).find_all(
                        attrs={"data-ui-tooltip": True}
                    ),
                )
                rows = json.loads(
                    cast(str, tooltips[0].get("data-ui-tooltip"))
                )["rows"]
                profile["sent_count"] = int(
                    re1.sub("", rows[0]["columns"][1]["name"])
                )
                profile["sent_full"] = int(
                    re1.sub("", rows[1]["columns"][1]["name"])
                )
                profile["sent_reduced"] = int(
                    re1.sub("", rows[2]["columns"][1]["name"])
                )
                profile["sent_zero"] = int(
                    re1.sub("", rows[3]["columns"][1]["name"])
                )
                profile["sent_awaiting"] = int(
                    re1.sub("", rows[4]["columns"][1]["name"])
                )
                profile["sent_not_received"] = int(
                    re1.sub("", rows[5]["columns"][1]["name"])
                )
                rows = json.loads(
                    cast(str, tooltips[1].get("data-ui-tooltip"))
                )["rows"]
                profile["sent_cv"] = float(re2.sub("", tooltips[1].get_text()))
                profile["sent_real_cv"] = float(
                    re2.sub("", rows[0]["columns"][1]["name"])
                )
            case _:
                pass
    return profile


def process_list(user_list: list[str]):
    users: dict[str, Any] = {}
    with requests.Session() as session:
        retries = urllib3.util.Retry(other=0, backoff_factor=0.3)
        session.mount(
            "https://", requests.adapters.HTTPAdapter(max_retries=retries)
        )
        urls = [
            "https://www.steamgifts.com/user/",
            "https://www.sgtools.info/nonactivated/",
            "https://www.sgtools.info/multiple/",
        ]
        url_count = len(urls)
        n = len(user_list)
        for i, user in enumerate(user_list, start=1):
            responses: list[requests.Response] = []
            for url in urls:
                response: requests.Response = fetch_request(session, url + user)
                if response.status_code != 200:
                    break
                responses.append(response)
            if len(responses) != url_count:
                print(f"There is no user with username {user}.")
                continue
            profile = load_profile(responses[0].text)
            add_sent_won_ratio(profile)
            users[user] = {"profile": profile}
            users[user]["namwc"] = check_not_activated_multiple_win(
                responses[1].text, responses[2].text
            )
            if i % 20 == 0:
                print(f"{i} of {n} user profiles retrieved...")
    print("All user profiles retrieved!")
    return users


def raise_not_logged_in():
    raise requests.HTTPError(
        "Login failed. "
        "Please check the value of cookie `PHPSESSID` in file `config.ini`."
    )


def read_cache() -> dict[str, Any] | None:
    data = None
    filename = "cache.zip"
    if pathlib.Path(filename).is_file():
        with zipfile.ZipFile(filename) as z:
            with z.open("cache.pkl") as f:
                data = cast(dict[str, Any], pickle.loads(f.read()))
        last_check = data["last_check"]
        print(f"Cache read! Last checked {time.ctime(last_check)}.")
        if time.time() - last_check > 604800:
            data = None
            print("Cache is more than 1 week old. Cache cleared!")
    return data


def read_config() -> configparser.ConfigParser:
    filename = "config.ini"
    if not pathlib.Path(filename).is_file():
        print(
            f"Config file `{filename}` not found.",
            "Please refer to the template file `config-tmpl.ini`.",
        )
    config_parser = configparser.ConfigParser()
    with open(filename, encoding="utf-8") as f:
        config_parser.read_file(f)
    return config_parser


def set_cookie(session: requests.Session):
    session.cookies.set(  # type: ignore
        "PHPSESSID",
        read_config()["steamgifts"]["cookie-phpsessid"],
        domain=".www.steamgifts.com",
    )


def write_cache(data: dict[str, Any]):
    with zipfile.ZipFile("cache.zip", "w", zipfile.ZIP_LZMA) as z:
        z.writestr("cache.pkl", pickle.dumps(data, pickle.HIGHEST_PROTOCOL))
    print("Cache written!")


def main():
    data: dict[str, Any] | None = read_cache()
    if not data:
        user_list: list[str]
        with requests.Session() as session:
            set_cookie(session)
            user_list = export_list(session)
        data = {
            "users": process_list(user_list),
            "my_profile": load_my_profile(),
            "last_check": time.time(),
        }
        write_cache(data)
    users_to_remove: list[str] = filter_users(data)
    n = len(users_to_remove)
    print()
    print(f"Results (total {n} user{"s" if n else ""}):")
    for user in users_to_remove:
        print("https://www.steamgifts.com/user/" + user)


if __name__ == "__main__":
    main()
