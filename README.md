# innie@feishu.skill

innie@feishu is inspired by Severance.
In the show, your work self and your outside self are severed — the innie knows nothing but work, and that's exactly what makes them see it clearly.
This skill does something similar. It takes weeks of your work messages and looks for the person you've become inside them — not your job title, not what you think you're doing, but the actual patterns: what you keep pushing, what you keep avoiding, where your real anxiety lives, and what role you've quietly agreed to play.
Your innie has been at the office the whole time. This is just the first time someone's asking what they've noticed.

---

> Analyze your Feishu/Lark work messages to surface **3 hidden behavioral truths** about yourself — things you can't see because you're inside them.

Produces:
- A **shareable insight card** with 3 behavioral truths (HTML + PNG)

Works as an agent skill — give `skill.md` to any LLM agent with shell access (Claude Code, Cursor, Windsurf, a custom API agent, …).

---

## What it does

```
Feishu messages
     │
     ▼ fetch.py          week-by-week queries (up to 1000 msgs, 6 weeks)
     │
     ▼ mask.py           replace PII with [colleague_1] / [phone_1] / [org_1] …
     │
     ▼ organize.py       group by chat · filter noise · anonymize p2p
     │
     ▼ summarize.py      word freq + daily messages + top-10 chat messages
     │                   → context.md (analysis input) + stats.json (render input)
     │
     ▼ LLM               3 hidden truths via structured prompt (prompts/analysis.md)
     │
     ▼ render.py         share-card.html + share-card.png
```

### The summarize approach

Instead of feeding raw stats to the LLM, `summarize.py` first builds a structured context:

- **Word frequency** (overall + per week) — reveals what topics truly dominated each period
- **Daily message records** — all messages grouped by workday, with chitchat filtered out
- **Top-10 chat summaries** — compressed view of the most active conversations, with full message history

This gives the final LLM a narrative spine to reason from, while preserving access to the raw signal for nuanced interpretation.

---

## Setup

### 1. Install lark-cli and authenticate

```bash
npm install -g @larksuite/cli

# Feishu (mainland China)
echo "YOUR_APP_SECRET" | lark-cli config init \
  --app-id YOUR_APP_ID \
  --app-secret-stdin \
  --brand feishu

lark-cli auth login --domain im
```

### 2. Clone this repo

```bash
git clone https://github.com/wangpengzhou-ai/innie-feishu-skill.git
export SKILL_DIR="$PWD/innie-feishu-skill"
```

### 3. Install Python dependencies

```bash
pip install jieba openai
pip install lac  # optional: enables NER for better PII masking
```

### 4. Set your OpenRouter API key

```bash
export OPENROUTER_API_KEY="sk-or-v1-..."
```

---

## How to run

`skill.md` is the entry point — a prompt document that instructs any LLM agent to run the full pipeline.

### Any agent

```bash
export SKILL_DIR="$PWD/innie-feishu-skill"
```

Give the agent `skill.md` as its prompt. It needs shell access (bash + python3).

**Cursor / Windsurf** — open the project folder and tell your agent: *"Follow the instructions in `skill.md`."*

### Claude Code — slash command

```bash
mkdir -p .claude/commands
cp "$SKILL_DIR/skill.md" .claude/commands/feishu-innie.md
```

Then in Claude Code:
```
/feishu-innie
```

---

## Customizing `mask_vocab.json`

`mask_vocab.json` maps product or organization names to generic category labels, so they are replaced before any LLM step. Edit this file to add names relevant to your company:

```json
{
  "Your Product Name": "[short-video platform]",
  "Your Org Name":     "[department]"
}
```

---

## Troubleshooting

### "Host not in allowlist"

Your server's outbound IP is blocked by Feishu's enterprise network policy. Fix: run locally, or add your server IP to Feishu admin console → Security → IP allowlist.

### lark-cli not found after npm install

Add npm's global bin directory to your `PATH`: run `npm bin -g` to find the path.

---

## Privacy

- **PII is masked before any LLM step** — `mask.py` replaces names, phone numbers, emails, open_ids, and more with consistent numbered placeholders. The LLM never sees real personal data.
- **P2P chats are fully anonymized** — private chat partners appear as `p2p_1`, `p2p_2`, etc.
- The skill runs entirely locally; no data is sent to any server without your credentials.
- Add `messages_raw.json` and `messages_masked.json` to `.gitignore`.

---

## Output files

| File | Description |
|------|-------------|
| `messages_raw.json` | Full cache — reuse to skip re-fetching |
| `messages_masked.json` | PII-masked — recommended for all downstream steps |
| `messages_organized.json` | Filtered, grouped, anonymized |
| `context.md` | Structured LLM analysis context |
| `stats.json` | Basic stats for render.py |
| `truths.json` | 3 truths in machine-readable form |
| `share-card.html` | Shareable insight card |
| `share-card.png` | Exportable PNG (2x resolution) |

---

## Requirements

- Python 3.10+
- Node.js 18+ with [`@larksuite/cli`](https://github.com/larksuite/cli) authenticated with `im` scopes
- `pip install jieba openai`
- `pip install lac` — optional, for better NER in `mask.py`
- OpenRouter API key for `summarize.py`

---

## License

MIT
