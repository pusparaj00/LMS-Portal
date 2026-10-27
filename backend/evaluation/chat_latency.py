"""F-50, TR-P-03: how long does a chat reply take, by kind of message, for one student and for a crowd?

Run inside the api container of a throwaway stack (it registers students):
    python -m evaluation.chat_latency [MESSAGES_PER_ROW] [CONCURRENT_STUDENTS]

A message with a clear phrase is routed without a model call; one without it costs a routing call first. The `general`
row is answered by the model. Nothing here is hard-coded output: every number is a timing made in this run.
"""
import statistics
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import httpx
from sqlalchemy import text

from app.db import get_engine
from evaluation.consent import agree
from evaluation.join import join_course

API = "http://localhost:8000/api/v1"
MESSAGES = {
    "hint, clear phrase": "give me a hint",
    "hint, no clear phrase": "Point me in the right direction please",
    "progress, clear phrase": "how am i doing",
    "progress, no clear phrase": "where do I stand in this course",
    "explain, clear phrase": "why did my submission fail",
    "explain, no clear phrase": "I do not understand the error my code gives",
    "recommend, no clear phrase": "which topic would help me most now",
    "general (model answers)": "what is a tuple in python",
}
WRONG = "n = int(input())\ntotal = 0\nfor i in range(n):\n    total += i\nprint(total)\n"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 3
CONCURRENT = int(sys.argv[2]) if len(sys.argv) > 2 else 12


def student():
    client = httpx.Client(timeout=180)
    token = client.post(f"{API}/auth/register", json={"email": f"chat-{uuid.uuid4().hex[:8]}@eval.local", "password": "eval-password-1"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    agree(client, API, headers)
    with get_engine().connect() as conn:
        course = conn.execute(text("SELECT id FROM courses WHERE title = 'Python Fundamentals' ORDER BY id LIMIT 1")).scalar_one()
    join_course(client, API, course, headers)
    problems = client.get(f"{API}/problems", params={"course_id": course}, headers=headers).json()["problems"]
    pid = next(p["id"] for p in problems if p["title"] == "Sum from 1 to n")
    sub = client.post(f"{API}/submissions", headers=headers, json={"problem_id": pid, "code": WRONG}).json()
    assert sub["status"] == "failed", sub
    return client, headers, pid


def say(client, headers, pid, message):
    started = time.perf_counter()
    reply = client.post(f"{API}/chat", headers=headers, json={"message": message, "problem_id": pid})
    reply.raise_for_status()
    body = reply.json()
    return time.perf_counter() - started, body["route"], body["router"]["how"]


def pct(values, q):
    values = sorted(values)
    return values[min(len(values) - 1, int(q * len(values)))]


print(f"## One student at a time, {N} messages per row\n")
print("| Message | Route | How routed | Median s | Max s |\n| --- | --- | --- | --- | --- |")
client, headers, pid = student()
for label, message in MESSAGES.items():
    times, routes, hows = [], set(), set()
    for _ in range(N):
        seconds, route, how = say(client, headers, pid, message)
        times.append(seconds)
        routes.add(route)
        hows.add(how)
        time.sleep(2)
    print(f"| {label} | {'/'.join(sorted(routes))} | {'/'.join(sorted(hows))} | {statistics.median(times):.2f} | {max(times):.2f} |")

print(f"\n## {CONCURRENT} students at once, one message each of the same kind\n")
print("| Message | Median s | 95th pct s | Max s |\n| --- | --- | --- | --- |")
crowd = [student() for _ in range(CONCURRENT)]
for label, message in MESSAGES.items():
    with ThreadPoolExecutor(CONCURRENT) as pool:
        times = list(pool.map(lambda s, text=message: say(*s, text)[0], crowd))
    print(f"| {label} | {statistics.median(times):.2f} | {pct(times, 0.95):.2f} | {max(times):.2f} |")
    time.sleep(3)
