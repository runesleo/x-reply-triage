# x-reply-triage

![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)
![License MIT](https://img.shields.io/badge/license-MIT-green)

Sort the replies under your X posts into humans, AI-like accounts and spam — and spend your replies on humans.

[中文](README.zh.md)

## What you get

- A reply queue in four groups: 🧑 humans, 🤖 AI-like accounts, 🚫 spam, ❔ unverified.
- Every label shows its reasons — "20 recent posts, median gap 9 min · 80% replies to others · median likes 0" — so you can overrule it.
- Judged on behaviour: each replier's latest ~20 posts, not on whether one reply "sounds like AI".
- Optional drafts for humans only, through any model command that reads stdin (`claude -p`, `codex exec`, …).
- Read-only. It never replies, likes, blocks or mutes.
- An offline demo on a synthetic sample, so you can try it without logging in.

## How it works

```text
replies to you (last N days)
  ↓ collect — 1 search for the replies, then per replier:
  ↓           1 tweet lookup (handle) + 1 search of their latest ~20 posts
signals per account
  · posting rhythm (median gap between posts)
  · share of posts that are replies to others
  · median likes
  · one theme word repeated across posts
  · copy-paste posts, promo / scam wording
  ↓ triage — explainable rules (+ optional model pass: confirm labels, draft replies for humans)
output/triage.md + output/triage.json
```

Rules in v0.1:

- **spam** — promo/scam wording in the reply from a reply-only, copy-paste or promo account; or an account whose recent posts are mostly promo or copy-paste replies.
- **AI-like** — at least 8 recent posts, about 2+ an hour, low engagement (median likes ≤ 3), and a score ≥ 4 across rhythm, theme repetition, reply share and likes.
- **human** — everything else the tool could read.
- **unverified** — the account couldn't be read.

## Setup

```bash
git clone https://github.com/runesleo/x-reply-triage.git
cd x-reply-triage
python3 x_reply_triage.py demo     # standard library only
```

For your own replies, install the collector and log it in to X:

```bash
npm install -g xreach-cli          # https://github.com/Panniantong/xfetch
```

Using Claude Code or Codex? `SKILL.md` is a drop-in skill.

## Requirements

- Python 3.9+, standard library only.
- Optional: [`xreach-cli`](https://github.com/Panniantong/xfetch) for `collect`.
- Optional: a model CLI that reads a prompt from stdin, for `--llm-cmd`.

**Privacy.** `collect` reads X through `xreach-cli`, which uses your own logged-in browser session; this tool never sees or stores your cookies. `data/` and `output/` hold other people's public posts — they are git-ignored, keep them that way. With `--llm-cmd`, handles, reply text and a few of each replier's recent posts are sent to whatever model that command uses; the command runs with your environment, so pick one without file or tool access. Reading X through a logged-in session can conflict with X's rules on automated access: keep volumes low (defaults: 40 accounts, 10 s apart) and use it on your own replies.

## Quick start

```bash
python3 x_reply_triage.py demo --lang en
python3 x_reply_triage.py collect --owner YOUR_HANDLE --since 2026-10-05 --out data/replies.json
python3 x_reply_triage.py triage data/replies.json --lang en
# optional: drafts for humans
python3 x_reply_triage.py triage data/replies.json --llm-cmd "claude -p"
```

## Verified

| Scenario | Environment | Result |
|---|---|---|
| Offline demo, 12 synthetic replies | macOS, Python 3.9 and 3.14 | 5 human · 4 AI-like · 2 spam · 1 unverified, as designed |
| Unit tests | `python3 -m unittest -q test_x_reply_triage` (Python 3.9 and 3.14) | 22 passed |
| The author's own replies, 7 days (2026-10-05 → 10-12) | xreach-cli 0.3.3 | X search returned 40 replies from 30 accounts: 14 AI-like (47%), 16 human, 0 spam. AI-like accounts posted every 0.4–7.7 min; humans mostly hours or days apart. A model second pass (`claude -p`, which sees the rule signals) changed none. |

## Known limitations (v0.1)

- Heuristics, not detection. A very busy, rarely-liked human can look AI-like; a slow AI account can pass as human. The reasons are there so you can overrule.
- `xreach-cli` 0.3.x search results carry only user ids, so each replier costs two reads. Its `tweets --replies` fails in 0.3.3, so recent posts come from a `from:` search, which can lag or skip posts.
- Theme detection is word-based: English words and Chinese 2–4 character terms.
- X search returns only part of the replies you get, so counts describe what it returned.
- The model pass sees the rule signals, so its agreement is a sanity check, not an independent verdict.
- X only.

## Roadmap

- Cache account signals between runs.
- Allow / deny lists for accounts you already know.
- Export the human queue to other reply tools.
- More collectors: official API, browser export.

## About the author

*Leo ([@runes_leo](https://x.com/runes_leo)) — AI × Crypto independent builder. Trading on [Polymarket](https://polymarket.com/?via=runes-leo&r=runesleo&utm_source=github&utm_content=x-reply-triage), building data and content pipelines with Claude Code and Codex.*

*[leolabs.me](https://leolabs.me) — writing · community · open-source tools · indie projects · all platforms.*

*[X Subscription](https://x.com/runes_leo/creator-subscriptions/subscribe) — paid content weekly, or just buy me a coffee 😁*

*Learn in public, Build in public.*

## License

MIT — see [LICENSE](LICENSE).
