#!/usr/bin/env python3
"""
innie@feishu.skill — Step 2: Organize & Filter Messages
- Filters obvious noise (stickers, images, pure emoji, short acks)
- Groups messages by chat (group chats keep their name; p2p are anonymized)
- Sorts each conversation chronologically
- Produces a token-efficient JSON for analysis

Usage:
    python3 organize.py
    python3 organize.py --input messages_raw.json --output messages_organized.json
"""

import json, re, sys
from collections import defaultdict


# ─── Noise filters ────────────────────────────────────────────────────────────

NOISE_MSG_TYPES = {"sticker", "image", "file", "audio", "video", "system",
                   "hongbao", "post", "share", "location", "card"}

# Patterns that indicate content carries no information
NOISE_CONTENT_PATTERNS = [
    re.compile(r"^\[.*\]$"),                   # [Sticker], [Image], [File]
    re.compile(r"^[\U0001F300-\U0001FFFF\s]+$"),  # emoji-only
    re.compile(r"^[👍🙏✅❤️😂🤔💪🎉👌🙌🤝😄😊✨🔥💯🎊]+$"),
]

# Very short casual acknowledgment phrases (Chinese & English)
CASUAL_ACKS = {
    "ok", "好", "嗯", "哦", "啊", "呢", "的", "了",
    "收到", "好的", "嗯嗯", "好哒", "okk", "OK", "好滴",
    "哈哈", "哈哈哈", "😄", "👍", "🙏", "✅",
}


def get_msg_type(msg: dict) -> str:
    """Return message type, accepting both msg_type and message_type field names."""
    return msg.get("msg_type") or msg.get("message_type") or "text"


def get_content(msg: dict) -> str:
    """Return message content, accepting both direct 'content' and nested 'body.content'."""
    content = msg.get("content")
    if content is None and isinstance(msg.get("body"), dict):
        content = msg["body"].get("content", "")
    return (content or "").strip()


def is_noise(msg: dict) -> bool:
    """Return True if this message should be filtered out."""
    if get_msg_type(msg) in NOISE_MSG_TYPES:
        return True
    content = get_content(msg)
    if not content:
        return True
    # Pure bracket tags
    for pattern in NOISE_CONTENT_PATTERNS:
        if pattern.match(content):
            return True
    # Casual short acks (≤4 chars)
    if len(content) <= 4 and content in CASUAL_ACKS:
        return True
    return False


# ─── Organizer ────────────────────────────────────────────────────────────────

def organize(input_path: str, output_path: str):
    with open(input_path, encoding="utf-8") as f:
        raw = json.load(f)

    messages = raw.get("messages", [])
    total_before = len(messages)

    # Bucket into group and p2p by chat_id
    group_buckets: dict[str, dict] = {}   # chat_id → {"name": ..., "msgs": [...]}
    p2p_buckets:   dict[str, list] = defaultdict(list)

    for msg in messages:
        if is_noise(msg):
            continue

        chat_id   = msg.get("chat_id", "unknown")
        chat_type = msg.get("chat_type", "p2p")

        slim = {
            "create_time": msg.get("create_time", ""),
            "content":     get_content(msg),
        }

        if chat_type == "group":
            if chat_id not in group_buckets:
                group_buckets[chat_id] = {
                    "chat_name": msg.get("chat_name", chat_id),
                    "msgs": [],
                }
            if msg.get("mentions"):
                slim["mentions"] = [m["name"] for m in msg["mentions"]]
            group_buckets[chat_id]["msgs"].append(slim)
        else:
            p2p_buckets[chat_id].append(slim)

    # Sort each conversation chronologically
    for v in group_buckets.values():
        v["msgs"].sort(key=lambda m: m["create_time"])
    for msgs in p2p_buckets.values():
        msgs.sort(key=lambda m: m["create_time"])

    # Build final structures (group chats sorted by message count desc)
    group_chats = [
        {
            "chat_name": v["chat_name"],
            "message_count": len(v["msgs"]),
            "messages": v["msgs"],
        }
        for v in sorted(group_buckets.values(), key=lambda x: -len(x["msgs"]))
    ]

    # P2P chats: anonymised (p2p_1, p2p_2 …) sorted by count desc
    p2p_chats = [
        {
            "chat_label": f"p2p_{i+1}",
            "message_count": len(msgs),
            "messages": [
                {"create_time": m["create_time"], "content": m["content"]}
                for m in msgs
            ],
        }
        for i, (_, msgs) in enumerate(
            sorted(p2p_buckets.items(), key=lambda x: -len(x[1]))
        )
    ]

    total_after = sum(c["message_count"] for c in group_chats) + \
                  sum(c["message_count"] for c in p2p_chats)

    output = {
        "meta": raw.get("meta", {}),
        "stats": {
            "total_before_filter": total_before,
            "total_after_filter":  total_after,
            "filtered_out":        total_before - total_after,
            "group_chats":         len(group_chats),
            "p2p_chats":           len(p2p_chats),
        },
        "group_chats": group_chats,
        "p2p_chats":   p2p_chats,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Filter: {total_before} → {total_after} messages "
          f"({total_before - total_after} removed)", file=sys.stderr)
    print(f"Groups: {len(group_chats)}  P2P chats: {len(p2p_chats)}", file=sys.stderr)
    print(f"Saved → {output_path}", file=sys.stderr)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Organize and filter Feishu messages")
    parser.add_argument("--input",  default="messages_raw.json")
    parser.add_argument("--output", default="messages_organized.json")
    args = parser.parse_args()
    organize(args.input, args.output)


if __name__ == "__main__":
    main()
