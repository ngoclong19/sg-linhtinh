import time

import requests
import urllib3
import urllib3.exceptions

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

url = "https://www.2solve.me/api/quiz-attempt/anonymous/e031c847"
payload = {
    "anonymousClientKey": "6koke",
    "quizId": 188,
    "quizQuestionId": 701,
}

i = 0
while True:
    payload["answer"] = str(i)
    r = requests.post(url, json=payload, timeout=2, verify=False)
    if not i % 10:
        print(i)
    if r.json()["isCorrect"]:
        print(i)
        break
    i += 1
    time.sleep(5)
