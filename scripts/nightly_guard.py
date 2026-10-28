"""Decide whether this nightly run should go ahead, and wait for the New York close if needed.

The nightly ranking is started three ways: when the evening UK job finishes (the usual path,
so the two never overlap), by a 21:15 UTC schedule as a fallback (GitHub often starts scheduled
jobs hours late, and sometimes not at all), and by hand. Only one of these should do the four-hour
US price sync each night, so a run is skipped when another nightly run is under way or finished
successfully in the last 12 hours. A run triggered before the US close waits for it, if that is
under an hour away; otherwise it stops and leaves the night to the fallback schedule.

Writes run=true|false to $GITHUB_OUTPUT. Needs GH_TOKEN with actions:read.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
import urllib.request
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
MAX_WAIT = 60 * 60          # seconds
RECENT = dt.timedelta(hours=12)


def wait_for_close(now: dt.datetime) -> float:
    """Seconds until 16:10 New York time today, or 0 if past it (or a weekend)."""
    ny = now.astimezone(NY)
    if ny.weekday() >= 5:
        return 0.0
    close = ny.replace(hour=16, minute=10, second=0, microsecond=0)
    return max(0.0, (close - ny).total_seconds())


def other_runs(repo: str, token: str, run_id: str) -> list[dict]:
    url = f"https://api.github.com/repos/{repo}/actions/workflows/nightly.yml/runs?per_page=15"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        runs = json.load(r).get("workflow_runs", [])
    return [r for r in runs if str(r.get("id")) != str(run_id)]


def duplicate(runs: list[dict], now: dt.datetime) -> str:
    for r in runs:
        started = dt.datetime.fromisoformat(r["run_started_at"].replace("Z", "+00:00")) if r.get("run_started_at") else None
        if r.get("status") in ("in_progress", "queued", "waiting", "pending", "requested"):
            return f"run {r['id']} is already {r['status']}"
        # only automatic runs count (a hand-started quick re-rank must not cancel the night's run), and a
        # run that skipped itself doesn't either: a real run syncs prices for hours, a skipped one takes seconds
        if r.get("event") in ("schedule", "workflow_run") and r.get("conclusion") == "success" and started and now - started < RECENT:
            ended = dt.datetime.fromisoformat(r["updated_at"].replace("Z", "+00:00"))
            if ended - started > dt.timedelta(minutes=20):
                return f"run {r['id']} finished successfully at {r['updated_at']}"
    return ""


def main() -> int:
    event = os.environ.get("EVENT", "")
    out = os.environ.get("GITHUB_OUTPUT")
    run = True
    now = dt.datetime.now(dt.timezone.utc)
    if event != "workflow_dispatch":
        try:
            why = duplicate(other_runs(os.environ["GITHUB_REPOSITORY"], os.environ["GH_TOKEN"], os.environ.get("GITHUB_RUN_ID", "")), now)
        except Exception as e:  # if GitHub can't be asked, running twice is better than not at all
            print(f"::warning::Could not check other nightly runs ({e}); going ahead")
            why = ""
        if why:
            print(f"::notice::Skipping: {why}.")
            run = False
        else:
            wait = wait_for_close(now)
            if wait > MAX_WAIT:
                print(f"::notice::Skipping: the New York close is {wait / 3600:.1f} hours away; the 21:15 UTC schedule will run tonight.")
                run = False
            elif wait > 0:
                print(f"Waiting {wait / 60:.0f} minutes for the New York close")
                time.sleep(wait)
    if out:
        with open(out, "a") as f:
            f.write(f"run={'true' if run else 'false'}\n")
    print(f"run={run}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
