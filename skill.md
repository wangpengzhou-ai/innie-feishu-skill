# innie@feishu.skill

Analyze your Feishu/Lark work messages to surface 3 hidden behavioral truths about yourself.
Produces a shareable insight card (HTML + PNG).

---

## Prerequisites

- Python 3.10+
- Node.js 18+ (for lark-cli)
- `pip install jieba` — required for `summarize.py`
- The skill scripts in a local directory (`$SKILL_DIR` points to this repo)
- **No external API key required** — the executing agent does the analysis

---

## Steps

### 0 · Install & configure lark-cli

**Check if lark-cli is installed:**
```bash
lark-cli --version
```

If the command fails or lacks `im +messages-search` support, install it:
```bash
npm install -g @larksuite/cli
```

**Check if lark-cli is configured:**
```bash
lark-cli config show
```

If there is no `appId` field, configure it (replace values):
```bash
echo "APP_SECRET_HERE" | lark-cli config init \
  --app-id APP_ID_HERE \
  --app-secret-stdin \
  --brand feishu
```

> **Enterprise IP restriction**: If running in a cloud environment, your server IP may be blocked by Feishu's enterprise policy. Fix: add the server's public IP to your Feishu admin console → Security → IP allowlist; or run locally.

---

### 1 · Detect user identity

```bash
lark-cli auth status
```

If no user is logged in, authenticate first:
```bash
lark-cli auth login --domain im
```

Extract `userOpenId` (the `ou_…` string) from the output. Set `SENDER_ID` to that value.

---

### 2 · Fetch messages

```bash
python3 $SKILL_DIR/fetch.py \
  --sender "$SENDER_ID" \
  --weeks 6 \
  --target 1000 \
  --output messages_raw.json
```

Target: ≥ 500 messages. Increase `--weeks` if needed (up to 8).
On repeat runs, add `--skip-if-exists` to reuse the cached file and skip the API calls.

---

### 3 · Mask sensitive information

```bash
python3 $SKILL_DIR/mask.py \
  --input  messages_raw.json \
  --output messages_masked.json \
  --no-lac
```

Replaces real names with `[同事_A]`, `[同事_B]` … and masks phones, emails, open_ids, etc.
Use `--vocab mask_vocab.json` (default) to also replace product names with category labels.
Add `pip install lac` and drop `--no-lac` for better Chinese NER coverage.

---

### 4 · Organize & filter

```bash
python3 $SKILL_DIR/organize.py \
  --input  messages_masked.json \
  --output messages_organized.json
```

Groups messages by chat, filters noise (stickers, images, short acks), sorts by time.
P2P chat partners are further anonymized to `p2p_1`, `p2p_2` … labels.

---

### 5 · Build analysis context (no API key needed)

```bash
python3 $SKILL_DIR/summarize.py \
  --input   messages_organized.json \
  --context context.md \
  --stats   stats.json
```

Outputs:
- `context.md` — word frequency + all messages grouped by day and by top chat
- `stats.json` — basic stats for render.py

No API key required. The agent reads `context.md` directly in the next step.

---

### 6 · Write daily & chat summaries (agent LLM step)

Read `context.md`. It contains three sections:
- `## Word Frequency` — word frequency table
- `## Daily Message Records` — raw messages grouped by date
- `## Top 10 Conversations` — raw messages for the 10 most active chats

For each date section and each Top-10 chat section, write a 2–4 sentence summary
inserted right after the section heading (before the raw messages). Cover: what was
being worked on, key decisions or blockers, and emotional tone. Keep it tight.

Write the enriched `context.md` back to disk.

---

### 7 · Generate 3 hidden truths (agent LLM step)

Read `$SKILL_DIR/prompts/analysis.md` and follow the prompt instructions exactly.
Use the enriched `context.md` (with your summaries from Step 6) as the analysis material.

Ensure evidence is drawn from ALL weeks, not just the most recent one.
Output exactly 3 truths in the JSON format from `analysis.md`. Save to `truths.json`.

> **JSON safety**: Use Unicode curly quotes `\u201c` / `\u201d` (or 「」) inside string
> values instead of ASCII `"` to avoid invalid JSON.

---

### 7 · Render share card

```bash
python3 $SKILL_DIR/render.py \
  --stats   stats.json \
  --truths  truths.json \
  --card    share-card.html \
  --author-name     "Your Name" \
  --author-subtitle "Company · Role"
```

---

### 8 · Export to PNG

Start a local HTTP server (required so Google Fonts load — `file://` blocks them):

```bash
# From the directory containing share-card.html
python3 -m http.server 7788 &
SERVER_PID=$!
```

Install and run Puppeteer:

```bash
cd /tmp && mkdir -p ss_proj && cd ss_proj && npm init -y && npm install puppeteer

node --input-type=module <<'EOF'
import puppeteer from '/tmp/ss_proj/node_modules/puppeteer/lib/esm/puppeteer/puppeteer.js';
const b = await puppeteer.launch({
  executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  args: ['--no-sandbox']
});
const p = await b.newPage();
await p.setViewport({width: 760, height: 900, deviceScaleFactor: 2});
await p.goto('http://localhost:7788/share-card.html', {waitUntil: 'domcontentloaded'});
await new Promise(r => setTimeout(r, 2000));
await p.screenshot({path: 'share-card.png', fullPage: true});
await b.close();
console.log('Done: share-card.png');
EOF

kill $SERVER_PID
```

> Use `domcontentloaded` (not `networkidle2`) — Google Fonts may time out in restricted environments.
> If the share card is in a subdirectory, use `http://localhost:7788/subdir/share-card.html`.

---

## Output files

| File | Description |
|------|-------------|
| `messages_raw.json` | Full message cache — reusable across runs |
| `messages_organized.json` | Filtered & grouped messages |
| `context.md` | Agent analysis input (word freq + daily + top-chat messages) |
| `stats.json` | Basic stats for render.py |
| `truths.json` | 3 hidden truths (machine-readable JSON) |
| `share-card.html` | Insight share card with 3 truths |
| `share-card.png` | Exportable PNG (2x resolution) |
