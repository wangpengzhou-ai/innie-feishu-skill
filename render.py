#!/usr/bin/env python3
"""
innie@feishu.skill — Step 5: Render share-card.html
Generates share-card.html from stats.json and truths.json.

Usage:
    python3 render.py --stats stats.json --truths truths.json
    python3 render.py --stats stats.json --truths truths.json \
                      --card share-card.html \
                      --author-name "Your Name" --author-subtitle "Company · Role"
"""

import json, sys
from pathlib import Path

TEMPLATES_DIR = Path(__file__).parent / "templates"


def load_template(name: str) -> str:
    return (TEMPLATES_DIR / name).read_text(encoding="utf-8")


def inject(template: str, var_name: str, data: dict) -> str:
    placeholder = f"/* __INJECT_{var_name}__ */"
    replacement = f"const {var_name} = {json.dumps(data, ensure_ascii=False, indent=2)};"
    return template.replace(placeholder, replacement, 1)


def build_share_card(stats: dict, truths: list, output_path: str,
                     author_name: str = "", author_subtitle: str = ""):
    card_data = {
        "truths": truths,
        "stats": {
            "messages": stats["total_messages"],
            "days":     stats["weeks_count"] * 7,
            "groups":   stats["group_chats_count"],
            "truths":   len(truths),
        },
        "author_initial":  (author_name[0].upper() if author_name else "A"),
        "author_name":     author_name or "Anonymous",
        "author_subtitle": author_subtitle or "",
        "generated_by":    "innie@feishu.skill",
    }
    html = inject(load_template("share-card.html"), "CARD_DATA", card_data)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(html, encoding="utf-8")
    print(f"Share card → {output_path}", file=sys.stderr)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Render share card HTML")
    parser.add_argument("--stats",   default="stats.json")
    parser.add_argument("--truths",  default="truths.json")
    parser.add_argument("--card",    default="share-card.html")
    parser.add_argument("--author-name",     default="")
    parser.add_argument("--author-subtitle", default="")
    args = parser.parse_args()

    with open(args.stats, encoding="utf-8") as f:
        stats = json.load(f)

    with open(args.truths, encoding="utf-8") as f:
        truths = json.load(f)

    build_share_card(stats, truths, args.card,
                     author_name=args.author_name,
                     author_subtitle=args.author_subtitle)


if __name__ == "__main__":
    main()
