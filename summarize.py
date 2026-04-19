#!/usr/bin/env python3
"""
innie@feishu.skill — Step 4: Summarize
Builds the LLM analysis context from organized messages.
No external API key required — the executing agent (Claude) does the analysis.

Outputs:
  context.md  — structured context for the agent to analyze
  stats.json  — basic stats for render.py (message count, weeks, group count)

Usage:
    python3 summarize.py
    python3 summarize.py --input messages_organized.json \
                         --context context.md --stats stats.json
"""

import json, os, re, sys
from collections import Counter, defaultdict
from datetime import datetime

import jieba


# ── Text utilities ────────────────────────────────────────────────────────────

HTML_RE = re.compile(r"<[^>]+>")

STOPWORDS = {
    "的", "了", "是", "在", "我", "有", "和", "就", "不", "人", "都", "一",
    "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着",
    "没有", "看", "好", "自己", "这", "那", "他", "她", "它", "们",
    "啊", "哦", "嗯", "呢", "吧", "哈", "哈哈", "哈哈哈", "嗯嗯", "好的",
    "收到", "ok", "OK", "okk", "哦哦", "嗯呢", "哒", "啦", "哟", "呀",
    "这个", "那个", "什么", "怎么", "如何", "为什么", "因为", "所以",
    "但是", "然后", "还是", "就是", "这样", "那么", "可以", "应该",
    "已经", "还有", "只是", "一下", "一些", "之前", "之后", "时候",
    "感觉", "觉得", "知道", "可能", "现在", "然后", "这里", "那里",
    "一起", "大家", "我们", "你们", "他们", "东西", "地方", "时间",
    "工作", "问题", "情况", "需要", "进行", "发现", "通过", "关于",
    "对于", "使用", "目前", "其实", "而且", "或者", "以及", "同时",
    "具体", "相关", "方面", "希望", "可以", "主要", "部分", "直接",
    "如果", "虽然", "其他", "包括", "新的",
}

CHITCHAT_RE = [
    re.compile(r"^哈{2,}"),
    re.compile(r"^[😂🤣😄😁😊🙂]+$"),
    re.compile(
        r"^(好的|收到|ok|OK|嗯|好|行|是的|对|不错|加油|辛苦了|谢谢|感谢"
        r"|拜拜|晚安|早安|你好|在吗|在|来了|稍等|等一下|马上|好嘞|明白"
        r"|了解|懂了|知道了|没问题|可以|没事|没关系|随便|随时"
        r"|就这样|就这|好吧|那好|那行|那就这样)$"
    ),
    re.compile(r"^.{1,4}$"),
]


def clean(text: str) -> str:
    return HTML_RE.sub("", text).strip()


def is_chitchat(text: str) -> bool:
    t = clean(text)
    return any(p.match(t) for p in CHITCHAT_RE)


_MASK_RE = re.compile(r'^\[.+\]$')

def top_words(texts: list[str], n: int) -> list[tuple[str, int]]:
    counter: Counter = Counter()
    for text in texts:
        for w in jieba.lcut(clean(text)):
            w = w.strip()
            if len(w) >= 2 and w not in STOPWORDS and not re.match(r"^[\d\W]+$", w) and not _MASK_RE.match(w):
                counter[w] += 1
    return counter.most_common(n)


def parse_date(t: str) -> str:
    return t[:10]


def parse_week(t: str) -> str:
    try:
        dt = datetime.strptime(t[:16], "%Y-%m-%d %H:%M")
        return f"{dt.year}-W{dt.isocalendar()[1]:02d}"
    except Exception:
        return "unknown"


def parse_hour(t: str) -> int | None:
    try:
        return int(t[11:13])
    except Exception:
        return None


# ── Flatten messages ──────────────────────────────────────────────────────────

def flatten(organized: dict) -> list[dict]:
    msgs: list[dict] = []
    for gc in organized.get("group_chats", []):
        for m in gc["messages"]:
            msgs.append({
                "chat_name": gc["chat_name"],
                "chat_type": "group",
                "create_time": m["create_time"],
                "content": m["content"],
            })
    for pc in organized.get("p2p_chats", []):
        for m in pc["messages"]:
            msgs.append({
                "chat_name": pc["chat_label"],
                "chat_type": "p2p",
                "create_time": m["create_time"],
                "content": m["content"],
            })
    msgs.sort(key=lambda m: m["create_time"])
    return msgs


# ── Section builders ──────────────────────────────────────────────────────────

def build_word_freq(msgs: list[dict]) -> str:
    lines = ["## Word Frequency\n", "| Word | Count |", "|------|-------|"]
    for w, c in top_words([m["content"] for m in msgs], 30):
        lines.append(f"| {w} | {c} |")
    lines.append("")
    return "\n".join(lines)


def build_daily_summaries(msgs: list[dict]) -> str:
    """Output raw messages grouped by day — no LLM call needed."""
    lines = ["## Daily Message Records\n"]

    by_date: dict[str, list[dict]] = defaultdict(list)
    for m in msgs:
        by_date[parse_date(m["create_time"])].append(m)

    dates = sorted(by_date)
    for date in dates:
        work = [m for m in by_date[date] if not is_chitchat(m["content"])]
        lines.append(f"### {date} ({len(work)} messages)\n")
        if not work:
            lines.append("_No substantive work messages on this day_\n")
            continue
        for m in work:
            lines.append(
                f"- `{m['create_time']}` [{m['chat_type']}] {m['chat_name']}"
            )
            lines.append(f"  {clean(m['content'])}")
        lines.append("")

    return "\n".join(lines)


def build_top10_summaries(msgs: list[dict]) -> str:
    """Output raw messages for top 10 most active chats — no LLM call needed."""
    lines = ["## Top 10 Conversations (excluding chitchat)\n"]

    by_chat: dict[str, list[dict]] = defaultdict(list)
    for m in msgs:
        if not is_chitchat(m["content"]):
            by_chat[m["chat_name"]].append(m)

    top10 = sorted(by_chat.items(), key=lambda x: -len(x[1]))[:10]

    for rank, (name, chat_msgs) in enumerate(top10, 1):
        type_label = "group" if chat_msgs[0]["chat_type"] == "group" else "p2p"
        dates = sorted(set(parse_date(m["create_time"]) for m in chat_msgs))
        lines.append(
            f"### Top {rank}: [{type_label}] {name}"
            f" ({len(chat_msgs)} messages, {dates[0]} ~ {dates[-1]})\n"
        )
        for m in chat_msgs:
            lines.append(f"- `{m['create_time']}` {clean(m['content'])}")
        lines.append("")

    return "\n".join(lines)


# ── Stats for render.py ───────────────────────────────────────────────────────

def build_stats(msgs: list[dict], organized: dict) -> dict:
    n = len(msgs)
    weeks_count = len(set(parse_week(m["create_time"]) for m in msgs))
    return {
        "meta":              organized.get("meta", {}),
        "total_messages":    n,
        "group_chats_count": len(organized.get("group_chats", [])),
        "weeks_count":       weeks_count,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def summarize(input_path: str, context_path: str, stats_path: str):
    with open(input_path, encoding="utf-8") as f:
        organized = json.load(f)

    msgs = flatten(organized)
    print(f"Loaded {len(msgs)} messages from {input_path}", file=sys.stderr)

    print("Building word frequency...", file=sys.stderr)
    freq_section = build_word_freq(msgs)

    print("Building daily message records...", file=sys.stderr)
    daily_section = build_daily_summaries(msgs)

    print("Building top-10 chat records...", file=sys.stderr)
    top10_section = build_top10_summaries(msgs)

    context = "\n\n".join([freq_section, daily_section, top10_section])
    with open(context_path, "w", encoding="utf-8") as f:
        f.write(context)
    print(f"Context → {context_path} ({len(context)} chars)", file=sys.stderr)

    stats = build_stats(msgs, organized)
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"Stats   → {stats_path}", file=sys.stderr)


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Build agent analysis context from organized messages (no API key required)"
    )
    parser.add_argument("--input",   default="messages_organized.json")
    parser.add_argument("--context", default="context.md")
    parser.add_argument("--stats",   default="stats.json")
    args = parser.parse_args()
    summarize(args.input, args.context, args.stats)


if __name__ == "__main__":
    main()
