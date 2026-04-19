#!/usr/bin/env python3
"""
innie@feishu.skill — Step 1: Fetch Messages
Retrieves messages from Feishu/Lark via lark-cli, querying week by week
to work around per-request API limits.

Usage:
    python3 fetch.py
    python3 fetch.py --weeks 6 --target 1000 --output messages_raw.json
"""

import subprocess, json, os, sys
from datetime import datetime, timedelta


def get_current_user_open_id() -> str:
    """Read open_id from lark-cli auth status."""
    result = subprocess.run(
        ["lark-cli", "auth", "status"], capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"lark-cli auth status failed: {result.stderr}")
    data = json.loads(result.stdout)
    open_id = data.get("userOpenId")
    if not open_id:
        raise RuntimeError("Could not find userOpenId in auth status output")
    return open_id


def query_week(sender_open_id: str, start: str, end: str) -> list:
    """Query one week window; returns list of message dicts."""
    # lark-cli expects ISO 8601 with timezone offset; append T00:00:00+08:00 if bare date
    def to_iso(date_str: str) -> str:
        if "T" not in date_str:
            return date_str + "T00:00:00+08:00"
        return date_str

    cmd = [
        "lark-cli", "im", "+messages-search",
        "--sender", sender_open_id,
        "--sender-type", "user",
        "--start", to_iso(start),
        "--end", to_iso(end),
        "--page-size", "50",
        "--page-all",
        "--format", "ndjson",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  [warn] query failed: {result.stderr[:200]}", file=sys.stderr)
        return []
    messages = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            # lark-cli returns page objects {"has_more":..., "messages":[...]}
            if isinstance(obj, dict) and "messages" in obj:
                messages.extend(obj["messages"])
            else:
                messages.append(obj)
        except json.JSONDecodeError:
            pass
    return messages


def fetch_messages(sender_open_id: str, weeks: int = 6, target: int = 1000) -> list:
    """
    Query lark-cli week-by-week (oldest → newest) to collect up to `target`
    non-deleted messages. Deduplicates by message_id.
    """
    seen: dict[str, dict] = {}
    today = datetime.now()

    for i in range(weeks - 1, -1, -1):          # oldest week first
        end = today - timedelta(days=i * 7)
        start = end - timedelta(days=7)
        start_str = start.strftime("%Y-%m-%d")
        end_str = end.strftime("%Y-%m-%d")
        week_num = weeks - i

        print(f"[week {week_num}/{weeks}] {start_str} → {end_str} ...", file=sys.stderr)
        msgs = query_week(sender_open_id, start_str, end_str)

        added = 0
        for m in msgs:
            mid = m.get("message_id")
            if mid and not m.get("deleted", False) and mid not in seen:
                seen[mid] = m
                added += 1

        print(f"  +{added} new  (total: {len(seen)})", file=sys.stderr)

        if len(seen) >= target:
            print(f"  Reached target {target}, stopping early.", file=sys.stderr)
            break

    messages = sorted(seen.values(), key=lambda m: m.get("create_time", ""))
    return messages


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Fetch Feishu messages via lark-cli")
    parser.add_argument("--sender", default=None,
                        help="Sender open_id (ou_…). Auto-detected if omitted.")
    parser.add_argument("--weeks", type=int, default=6,
                        help="Max weeks to query backward (default: 6)")
    parser.add_argument("--target", type=int, default=1000,
                        help="Stop once this many unique messages are collected (default: 1000)")
    parser.add_argument("--output", default="messages_raw.json",
                        help="Output file path (default: messages_raw.json)")
    parser.add_argument("--skip-if-exists", action="store_true",
                        help="Skip fetching if output file already exists")
    args = parser.parse_args()

    if args.skip_if_exists and os.path.exists(args.output):
        print(f"Output already exists, skipping fetch: {args.output}", file=sys.stderr)
        return

    sender = args.sender or get_current_user_open_id()
    print(f"Fetching messages for: {sender}", file=sys.stderr)

    messages = fetch_messages(sender, weeks=args.weeks, target=args.target)

    output = {
        "meta": {
            "sender_open_id": sender,
            "queried_at": datetime.now().isoformat(),
            "total": len(messages),
            "weeks_queried": args.weeks,
        },
        "messages": messages,
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nSaved {len(messages)} messages → {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
