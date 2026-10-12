# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-10-12

### Added

- `demo`, `collect` and `triage` commands.
- Per-replier behaviour signals from their latest ~20 posts: posting rhythm (median gap), share of replies to others, median likes, one repeated theme word, copy-paste posts and promo/scam wording.
- Explainable rule labels — `human`, `ai_like`, `spam`, `unverified` — with reasons in English or Chinese.
- Optional model pass (`--llm-cmd`) that confirms labels and drafts replies for humans only.
- `xreach-cli` collector with a lookup cap, pacing and one retry on rate limits; it resolves handles from user ids and drops your own replies.
- Markdown report escapes untrusted text and keeps only x.com links.
- Synthetic offline demo sample, agent skill (`SKILL.md`) and unit tests.
