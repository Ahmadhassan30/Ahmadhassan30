#!/usr/bin/env python3
"""Writes the activity block in README.md: contributions by month, drawn with unicode bars.

    GITHUB_TOKEN=$(gh auth token) python3 assets/build.py

The daily workflow (.github/workflows/activity.yml) runs this. No packages needed beyond Python.
The block lives between <!-- activity:start --> and <!-- activity:end -->.
The 3D shelf is a separate page: shelf/index.html.
"""

import datetime as dt
import json
import os
import re
import urllib.request
from pathlib import Path

README = Path(__file__).resolve().parent.parent / "README.md"
GITHUB_USER = "Ahmadhassan30"


def fetch_calendar(token):
    query = ("query($login:String!){user(login:$login){contributionsCollection{contributionCalendar{"
             "totalContributions weeks{contributionDays{date contributionCount}}}}}}")
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": {"login": GITHUB_USER}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)["data"]["user"]["contributionsCollection"]["contributionCalendar"]


def activity_block(cal):
    days = [(dt.date.fromisoformat(d["date"]), d["contributionCount"])
            for w in cal["weeks"] for d in w["contributionDays"]]
    by_month = {}
    for d, n in days:
        by_month[(d.year, d.month)] = by_month.get((d.year, d.month), 0) + n
    months = sorted(by_month)[-12:]
    peak = max(max(by_month[m] for m in months), 1)
    span = 36  # longest bar, in characters; partial blocks give eighth-character precision
    chart = []
    for y, m in months:
        v = by_month[(y, m)]
        units = round(v / peak * span * 8)
        bar = "█" * (units // 8) + " ▏▎▍▌▋▊▉"[units % 8].strip()
        bar = bar or ("▏" if v else "")
        chart.append(f"{dt.date(y, m, 1):%b %y}".lower() + f"   {bar:<{span + 1}}{v:>4}")

    recent = days[-365:]
    longest = run = 0
    for _, n in recent:
        run = run + 1 if n else 0
        longest = max(longest, run)
    active = sum(1 for _, n in recent if n)
    best_day, best_n = max(recent, key=lambda d: d[1])
    return "\n".join([
        "```text",
        "contributions by month",
        "",
        *chart,
        "",
        f"{cal['totalContributions']:,} in the last year · {active}/{len(recent)} days active · "
        f"longest streak {longest}d · best day {best_n} ({best_day:%d %b})".lower(),
        "```",
    ])


def main():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("no GITHUB_TOKEN set: activity block left as it is")
        return
    block = activity_block(fetch_calendar(token))
    text = README.read_text(encoding="utf-8")
    start, end = "<!-- activity:start -->", "<!-- activity:end -->"
    if start not in text or end not in text:
        raise SystemExit("activity markers not found in README.md")
    new = re.sub(f"{re.escape(start)}.*?{re.escape(end)}", lambda m: f"{start}\n{block}\n{end}", text, flags=re.S)
    README.write_text(new, encoding="utf-8")
    print("activity block updated")


if __name__ == "__main__":
    main()
