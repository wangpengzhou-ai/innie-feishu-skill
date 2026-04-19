#!/usr/bin/env python3
"""
innie@feishu.skill — Step 5.5: Enrich context with summaries

Adds 2-4 sentence summaries above each daily section and each top-chat section
in context.md so the final analysis prompt has higher-level narrative guidance.

Usage:
    python3 enrich_context.py
    python3 enrich_context.py --input messages_organized.json \
                              --context context.md
"""

import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from typing import Iterable

import jieba


HTML_RE = re.compile(r"<[^>]+>")
MASK_RE = re.compile(r"\[[^\]]+\]")
URL_RE = re.compile(r"https?://\S+")
ASCII_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9._/-]*")

STOPWORDS = {
    "的", "了", "是", "在", "我", "有", "和", "就", "不", "人", "都", "一",
    "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着",
    "没有", "看", "好", "自己", "这", "那", "他", "她", "它", "们",
    "啊", "哦", "嗯", "呢", "吧", "哈", "哈哈", "哈哈哈", "嗯嗯", "好的",
    "收到", "ok", "OK", "okk", "哦哦", "嗯呢", "哒", "啦", "哟", "呀",
    "这个", "那个", "什么", "怎么", "如何", "为什么", "因为", "所以",
    "但是", "然后", "还是", "就是", "这样", "那么", "可以", "应该",
    "已经", "还有", "只是", "一下", "一些", "之前", "之后", "时候",
    "感觉", "觉得", "知道", "可能", "现在", "这里", "那里", "一起",
    "大家", "我们", "你们", "他们", "东西", "地方", "时间", "工作",
    "问题", "情况", "需要", "进行", "发现", "通过", "关于", "对于",
    "使用", "目前", "其实", "而且", "或者", "以及", "同时", "具体",
    "相关", "方面", "希望", "主要", "部分", "直接", "如果", "虽然",
    "其他", "包括", "新的", "一下子", "一下哈", "一下哦", "一下呀",
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

TOPIC_RULES = [
    ("合规与风险", {"法务", "合规", "风险", "举报", "下架", "审查", "灰度", "sign", "off"}),
    ("需求与方案", {"需求", "方案", "PRD", "文档", "评审", "范围", "设计", "入口", "开关"}),
    ("发布与推进", {"提测", "上线", "排期", "发布", "灰度", "实验", "mvp", "推进", "节点"}),
    ("模型与效果", {"模型", "评测", "效果", "workflow", "离线", "训练", "seed", "cot"}),
    ("跨团队协同", {"研发", "产品", "法务", "PR", "PNS", "DS", "团队", "对齐", "沟通"}),
]

DECISION_HINTS = (
    "定了", "确定", "结论", "改成", "保留", "同步", "对齐", "同意", "sign off",
    "提测", "上线", "开灰度", "可以", "没问题",
)
BLOCKER_HINTS = (
    "风险", "blocker", "卡住", "来不及", "问题", "限制", "没有权限", "合规",
    "法务", "不行", "不让", "担心", "焦躁", "纠结",
)
ACTION_HINTS = (
    "推进", "确认", "跟进", "整理", "评估", "讨论", "同步", "补", "约",
    "取数", "建个", "review", "看下", "研究",
)
TONE_HINTS = {
    "高压但推进中": ("风险", "焦躁", "催", "尽快", "赶", "推进", "blocker"),
    "审慎校准": ("确认", "理解一致", "评估", "口径", "边界", "同步"),
    "方案发散": ("玩法", "体验", "文案", "入口", "banner", "toggle"),
    "坦诚松弛": ("哈哈", "笑哭", "捂脸", "hh", "hhh", "辛苦"),
}


def clean(text: str) -> str:
    text = HTML_RE.sub(" ", text or "")
    text = URL_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def is_chitchat(text: str) -> bool:
    t = clean(text)
    return any(p.match(t) for p in CHITCHAT_RE)


def parse_date(t: str) -> str:
    return t[:10]


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


def extract_keywords(texts: Iterable[str], n: int = 5) -> list[str]:
    counter: Counter[str] = Counter()
    for text in texts:
        cleaned = clean(text)
        for token in jieba.lcut(cleaned):
            token = token.strip()
            if not token or token in STOPWORDS:
                continue
            if len(token) < 2 and not ASCII_WORD_RE.fullmatch(token):
                continue
            if MASK_RE.fullmatch(token):
                continue
            if re.fullmatch(r"[\d\W_]+", token):
                continue
            counter[token] += 1
        for token in ASCII_WORD_RE.findall(cleaned):
            if token.lower() not in {"http", "https", "com"}:
                counter[token] += 1
    return [word for word, _ in counter.most_common(n)]


def detect_topics(texts: Iterable[str]) -> list[str]:
    joined = " ".join(clean(t) for t in texts)
    hits: list[tuple[int, str]] = []
    for label, keywords in TOPIC_RULES:
        score = sum(joined.count(keyword) for keyword in keywords)
        if score:
            hits.append((score, label))
    hits.sort(reverse=True)
    topics = [label for _, label in hits[:2]]
    return topics or ["项目推进"]


def count_hint_hits(texts: Iterable[str], hints: tuple[str, ...]) -> int:
    joined = " ".join(clean(t) for t in texts)
    return sum(joined.count(h) for h in hints)


def pick_tone(texts: Iterable[str]) -> str:
    joined = " ".join(clean(t) for t in texts)
    scored: list[tuple[int, str]] = []
    for label, hints in TONE_HINTS.items():
        score = sum(joined.count(h) for h in hints)
        if score:
            scored.append((score, label))
    if not scored:
        return "务实克制"
    scored.sort(reverse=True)
    return scored[0][1]


def find_time_window(msgs: list[dict]) -> str:
    hours = []
    for m in msgs:
        try:
            hours.append(datetime.strptime(m["create_time"], "%Y-%m-%d %H:%M").hour)
        except ValueError:
            continue
    if not hours:
        return ""
    early = sum(1 for h in hours if h < 11)
    late = sum(1 for h in hours if h >= 18)
    if late > early and late >= max(3, len(hours) // 4):
        return "，而且不少信息延续到了晚上"
    if early >= max(3, len(hours) // 4):
        return "，节奏从白天较早时段就启动了"
    return ""


def build_daily_summary(date: str, msgs: list[dict]) -> str:
    texts = [m["content"] for m in msgs]
    topics = detect_topics(texts)
    keywords = extract_keywords(texts, n=4)
    tone = pick_tone(texts)
    decisions = count_hint_hits(texts, DECISION_HINTS)
    blockers = count_hint_hits(texts, BLOCKER_HINTS)
    actions = count_hint_hits(texts, ACTION_HINTS)
    time_note = find_time_window(msgs)

    lead = f"这一天的讨论主轴落在{topics[0]}"
    if len(topics) > 1:
        lead += f"与{topics[1]}"
    lead += f"，关键词集中在{('、'.join(keywords[:3]) or '推进、对齐、确认')}{time_note}。"

    if blockers > 0 and decisions > 0:
        middle = "一边在压缩风险和边界不清带来的不确定性，一边也在持续形成结论、推进节点往前走。"
    elif blockers > 0:
        middle = "主要精力放在识别阻塞点、确认限制条件和避免后续返工上。"
    elif decisions > 0 or actions > 0:
        middle = "整体不是发散式聊天，而是在围绕具体动作、责任分配和下一步安排快速收口。"
    else:
        middle = "讨论虽然分散在不同会话里，但都指向同一个项目面的澄清与协同。"

    tail = f"语气上呈现出明显的{tone}感，说明这天更像是在现实约束中校准方案，而不是单纯交换想法。"
    return f"{lead} {middle} {tail}"


def build_chat_summary(chat_name: str, msgs: list[dict]) -> str:
    texts = [m["content"] for m in msgs]
    topics = detect_topics(texts)
    keywords = extract_keywords(texts, n=5)
    tone = pick_tone(texts)
    blockers = count_hint_hits(texts, BLOCKER_HINTS)
    decisions = count_hint_hits(texts, DECISION_HINTS)
    actions = count_hint_hits(texts, ACTION_HINTS)
    first_day = parse_date(msgs[0]["create_time"])
    last_day = parse_date(msgs[-1]["create_time"])

    lead = (
        f"这段对话贯穿 {first_day} 到 {last_day}，长期围绕{topics[0]}"
        + (f"和{topics[1]}" if len(topics) > 1 else "")
        + "展开。"
    )
    middle = (
        f"高频词更偏向{('、'.join(keywords[:4]) or '推进、方案、确认')}，"
        "说明这不是一次性的问答，而是反复回到同一组问题上做拆解和收口。"
    )
    if blockers > 0 and decisions > 0:
        behavior = "你在这类关系里既会暴露现实阻力，也会立刻把话题拉回可执行动作，像是在边消化压力边维持推进。"
    elif actions >= decisions:
        behavior = "你在这类关系里更像一个持续推进的人，会不断补信息、追节点、确认边界，保持项目不掉线。"
    else:
        behavior = "这段关系承担了较多关键判断与口径校准，很多信息都在这里被压缩成可落地的结论。"
    tail = f"整体语气偏{tone}，能看到你在这个会话里最常展现的是现实判断，而不是抽象表达。"
    return f"{lead} {middle} {behavior} {tail}"


def inject_summaries(context: str, daily_map: dict[str, str], chat_map: dict[str, str]) -> str:
    lines = context.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        if line.startswith("### ") and "messages" in line:
            match = re.match(r"### (\d{4}-\d{2}-\d{2}) \(", line)
            if match:
                summary = daily_map.get(match.group(1))
                if summary:
                    i += 1
                    while i < len(lines) and (lines[i] == "" or lines[i].startswith("> Summary:")):
                        i += 1
                    out.append("")
                    out.append(f"> Summary: {summary}")
                    out.append("")
                    continue
            match = re.match(r"### Top \d+: \[(?:group|p2p)\] (.+)", line)
            if match:
                summary = chat_map.get(line[4:])
                if summary:
                    i += 1
                    while i < len(lines) and (lines[i] == "" or lines[i].startswith("> Summary:")):
                        i += 1
                    out.append("")
                    out.append(f"> Summary: {summary}")
                    out.append("")
                    continue
        i += 1
    return "\n".join(out) + "\n"


def enrich(input_path: str, context_path: str):
    with open(input_path, encoding="utf-8") as f:
        organized = json.load(f)
    with open(context_path, encoding="utf-8") as f:
        context = f.read()

    msgs = flatten(organized)
    by_date: dict[str, list[dict]] = defaultdict(list)
    by_chat: dict[str, list[dict]] = defaultdict(list)
    for m in msgs:
        if is_chitchat(m["content"]):
            continue
        by_date[parse_date(m["create_time"])].append(m)
        by_chat[m["chat_name"]].append(m)

    daily_map = {
        date: build_daily_summary(date, date_msgs)
        for date, date_msgs in sorted(by_date.items())
    }

    top10 = sorted(by_chat.items(), key=lambda item: -len(item[1]))[:10]
    chat_map: dict[str, str] = {}
    for rank, (name, chat_msgs) in enumerate(top10, 1):
        type_label = "group" if chat_msgs[0]["chat_type"] == "group" else "p2p"
        dates = sorted({parse_date(m["create_time"]) for m in chat_msgs})
        header = f"Top {rank}: [{type_label}] {name} ({len(chat_msgs)} messages, {dates[0]} ~ {dates[-1]})"
        chat_map[header] = build_chat_summary(name, chat_msgs)

    enriched = inject_summaries(context, daily_map, chat_map)
    with open(context_path, "w", encoding="utf-8") as f:
        f.write(enriched)

    print(f"Enriched {len(daily_map)} daily sections and {len(chat_map)} top-chat sections → {context_path}", file=sys.stderr)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Add heuristic summaries into context.md")
    parser.add_argument("--input", default="messages_organized.json")
    parser.add_argument("--context", default="context.md")
    args = parser.parse_args()
    enrich(args.input, args.context)


if __name__ == "__main__":
    main()
