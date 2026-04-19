#!/usr/bin/env python3
"""
innie@feishu.skill — Step 2: Mask Sensitive Information

Masking rules:
  发消息者 (被分析用户)          → [本人]
  其他人名 (中文 + 英文)         → [同事_A], [同事_B], ...
  手机号                        → [手机号]
  证件号                        → [证件号]
  邮箱                          → [邮箱]
  金额                          → [金额]
  UID / DID / 数字设备 ID        → [数据]
  open_id / chat_id             → [用户ID] / [会话ID]
  合同/订单号                    → [合同号]
  产品名 (mask_vocab.json)       → [品类标签]

Name detection:
  ① Name registry — pre-scanned from sender.name + mentions.name in raw data
                    covers both Chinese (周王鹏) and English (Chaofan Yu)
  ② LAC NER       — catches residual Chinese person names in content text
                    (optional; falls back gracefully if not installed)

Usage:
    python3 mask.py
    python3 mask.py --input messages_raw.json --output messages_masked.json
    python3 mask.py --no-lac
    python3 mask.py --vocab mask_vocab.json
"""

import json, re, sys
from pathlib import Path


# ── Regex patterns ────────────────────────────────────────────────────────────

PATTERNS: list[tuple[str, re.Pattern]] = [
    ("[手机号]",  re.compile(r'(?<!\d)1[3-9]\d{9}(?!\d)')),
    ("[证件号]",  re.compile(r'(?<!\d)\d{17}[\dXx](?!\d)')),
    ("[邮箱]",   re.compile(r'[\w.+\-]+@[\w\-]+(?:\.[a-zA-Z]{2,})+')),
    ("[用户ID]",  re.compile(r'\bou_[A-Za-z0-9]+')),
    ("[会话ID]",  re.compile(r'\boc_[A-Za-z0-9]+')),
    ("[数据]",   re.compile(r'(?:UID|DID|uid|did)\s*[:：]\s*\d+')),
    ("[金额]",   re.compile(r'[￥¥]\s*[\d,.]+\s*(?:[万亿千百]元?)?')),
    ("[合同号]",  re.compile(r'(?:合同|订单|单号|NO\.?|编号)\s*[:：]\s*[A-Za-z0-9\-_]{4,}')),
]


# ── Name registry ─────────────────────────────────────────────────────────────

class NameRegistry:
    """
    Pre-scanned from raw message data. Assigns consistent labels:
      main sender → [本人]
      others      → [同事_A], [同事_B], ... [同事_Z], [同事_AA], ...
    """

    def __init__(self):
        self._name_to_label: dict[str, str] = {}
        self._counter = 0

    def _next_label(self) -> str:
        n = self._counter
        self._counter += 1
        if n < 26:
            return f"[同事_{chr(65 + n)}]"
        hi = chr(65 + (n // 26) - 1)
        lo = chr(65 + (n % 26))
        return f"[同事_{hi}{lo}]"

    def register(self, name: str, is_self: bool = False) -> str:
        if not name or name in self._name_to_label:
            return self._name_to_label.get(name, "")
        label = "[本人]" if is_self else self._next_label()
        self._name_to_label[name] = label
        return label

    def get(self, name: str) -> str | None:
        return self._name_to_label.get(name)

    def apply(self, text: str) -> str:
        """Replace all registered names in text (longest match first)."""
        for name in sorted(self._name_to_label, key=len, reverse=True):
            # Skip single-character names and very short English words — too risky
            if len(name) < 2:
                continue
            is_ascii = bool(re.search(r'[A-Za-z]', name))
            if is_ascii and len(name) < 4 and " " not in name:
                continue  # e.g. "Ma", "Yu", "Wu" — too ambiguous standalone
            label = self._name_to_label[name]
            if is_ascii:
                text = re.sub(r'\b' + re.escape(name) + r'\b', label, text)
            else:
                text = text.replace(name, label)
        return text

    @property
    def summary(self) -> dict:
        return {
            "total_persons": len(self._name_to_label),
            "labels": dict(sorted(self._name_to_label.items(), key=lambda x: x[1])),
        }


def build_registry(raw: dict) -> tuple[NameRegistry, str]:
    """
    Two-pass scan:
      Pass 1 — identify main sender and register as [本人] first
      Pass 2 — register all other senders and mentioned people
    Returns (registry, main_sender_name).
    """
    registry = NameRegistry()
    sender_open_id = raw.get("meta", {}).get("sender_open_id", "")

    # Pass 1: register main user first so they always get [本人]
    main_name = ""
    for msg in raw.get("messages", []):
        if msg.get("sender", {}).get("id") == sender_open_id:
            main_name = msg["sender"].get("name", "")
            if main_name:
                registry.register(main_name, is_self=True)
                break

    # Pass 2: register everyone else
    # Sources: sender.name, mentions[].name, and @-patterns in content text
    AT_RE = re.compile(r'@([\u4e00-\u9fa5]{2,6}|[A-Z][a-zA-Z]{2,}(?:\s[A-Z][a-zA-Z]+)*)')

    for msg in raw.get("messages", []):
        name = msg.get("sender", {}).get("name", "")
        if name and name != main_name:
            registry.register(name, is_self=False)

        for mention in msg.get("mentions", []):
            m_name = mention.get("name", "")
            if m_name and m_name != main_name:
                registry.register(m_name, is_self=False)

        # Fallback: scan content text for @Name patterns not in mentions field
        for at_name in AT_RE.findall(msg.get("content", "")):
            at_name = at_name.strip()
            if at_name and at_name != main_name:
                registry.register(at_name, is_self=False)

    return registry, main_name


# ── Product vocabulary ────────────────────────────────────────────────────────

def load_vocab(vocab_path: str) -> dict[str, str]:
    """Load product name → label mapping. Sorted longest-first for safe substitution."""
    if not Path(vocab_path).exists():
        return {}
    with open(vocab_path, encoding="utf-8") as f:
        vocab = json.load(f)
    return dict(sorted(vocab.items(), key=lambda x: -len(x[0])))


def apply_vocab(text: str, vocab: dict[str, str]) -> str:
    for term, label in vocab.items():
        is_ascii = bool(re.search(r'[A-Za-z]', term))
        if is_ascii:
            text = re.sub(r'\b' + re.escape(term) + r'\b', label, text)
        else:
            text = text.replace(term, label)
    return text


# ── Core masking ──────────────────────────────────────────────────────────────

class Masker:
    def __init__(self, registry: NameRegistry, vocab: dict[str, str], use_lac: bool = True):
        self._registry = registry
        self._vocab = vocab
        self._lac = None
        if use_lac:
            try:
                from LAC import LAC as _LAC
                self._lac = _LAC(mode="lac")
                print("[mask] LAC NER enabled.", file=sys.stderr)
            except ImportError:
                print(
                    "[mask] LAC not installed — NER disabled (registry + regex only).\n"
                    "       Install: pip install lac",
                    file=sys.stderr,
                )

    def mask(self, text: str) -> str:
        if not text or not text.strip():
            return text

        # ① Product vocabulary (longest match first, before names)
        text = apply_vocab(text, self._vocab)

        # ② Name registry (pre-scanned from structured data)
        text = self._registry.apply(text)

        # ③ Regex patterns for structured PII
        for placeholder, pattern in PATTERNS:
            text = pattern.sub(placeholder, text)

        # ④ LAC NER for residual Chinese person names in content
        if self._lac:
            try:
                tokens, tags = self._lac.run(text)
                parts = []
                for token, tag in zip(tokens, tags):
                    if tag == "PER":
                        label = self._registry.get(token)
                        if label is None:
                            label = self._registry.register(token, is_self=False)
                        parts.append(label)
                    else:
                        parts.append(token)
                text = "".join(parts)
            except Exception:
                pass

        return text


# ── Field-level masking ───────────────────────────────────────────────────────

def mask_message(msg: dict, masker: Masker, registry: NameRegistry) -> dict:
    m = dict(msg)

    # Sender identity
    if m.get("sender"):
        s = dict(m["sender"])
        s["name"] = registry.get(s.get("name", "")) or s.get("name", "")
        s["id"] = "[用户ID]"
        s.pop("tenant_key", None)
        m["sender"] = s

    # Message content
    if m.get("content"):
        m["content"] = masker.mask(m["content"])

    # Chat name (groups)
    if m.get("chat_name"):
        m["chat_name"] = masker.mask(m["chat_name"])

    # Mentions
    if m.get("mentions"):
        m["mentions"] = [
            {
                **mn,
                "name": registry.get(mn.get("name", "")) or mn.get("name", ""),
                "id": "[用户ID]",
                "open_id": "[用户ID]",
            }
            for mn in m["mentions"]
        ]

    # chat_partner open_id
    if m.get("chat_partner"):
        m["chat_partner"] = {**m["chat_partner"], "open_id": "[用户ID]"}

    # chat_id is an opaque internal identifier used by organize.py for grouping;
    # keep it intact so downstream steps can distinguish between chats.
    # oc_* patterns in message *content* are still masked by the regex pass above.

    return m


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Mask PII in raw Feishu messages")
    parser.add_argument("--input",  default="messages_raw.json")
    parser.add_argument("--output", default="messages_masked.json")
    parser.add_argument("--vocab",  default="mask_vocab.json")
    parser.add_argument("--no-lac", action="store_true")
    args = parser.parse_args()

    with open(args.input, encoding="utf-8") as f:
        raw = json.load(f)

    vocab = load_vocab(args.vocab)
    if vocab:
        print(f"[mask] Loaded {len(vocab)} product terms from {args.vocab}", file=sys.stderr)

    registry, main_name = build_registry(raw)
    print(f"[mask] Main sender: {main_name!r} → [本人]", file=sys.stderr)
    print(f"[mask] Registered {registry.summary['total_persons']} persons total", file=sys.stderr)

    masker = Masker(registry, vocab, use_lac=not args.no_lac)

    meta = dict(raw.get("meta", {}))
    meta["sender_open_id"] = "[本人]"

    masked = [mask_message(msg, masker, registry) for msg in raw.get("messages", [])]

    result = {
        "meta":       meta,
        "messages":   masked,
        "mask_stats": registry.summary,
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    s = registry.summary
    print(f"[mask] {s['total_persons']} persons masked → {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
