#!/usr/bin/env python3
"""x-reply-triage: sort the replies under your X posts into humans, AI-like accounts and spam.

Read-only. It never replies, likes, blocks or mutes anything. Optional drafts are
written for humans only, and you decide what to send.

    python3 x_reply_triage.py demo
    python3 x_reply_triage.py collect --owner YOUR_HANDLE --out data/replies.json
    python3 x_reply_triage.py triage data/replies.json [--lang zh] [--llm-cmd "claude -p"]
"""
from __future__ import annotations

import argparse
import json
import random
import re
import shlex
import statistics
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

__version__ = "0.1.0"
INPUT_SCHEMA = "x_reply_triage.input.v1"
OUTPUT_SCHEMA = "x_reply_triage.output.v1"
HERE = Path(__file__).resolve().parent
DEMO_INPUT = HERE / "examples" / "demo_input.json"
PROMPT_FILE = HERE / "prompts" / "triage.md"
LABELS = ("human", "ai_like", "spam", "unverified")
INPUT_FIELDS = ("id", "url", "author", "author_id", "text", "created_at", "in_reply_to")
# Untrusted text goes into Markdown: neutralise images, links and inline HTML.
MD_ACTIVE = re.compile(r"([\\`\[\]()!])")
SAFE_URL = re.compile(r"https://x\.com/[\w/-]+")

# ---------------------------------------------------------------- signals ----

SPAM_TEXT = re.compile(
    r"(?i)(onlyfans|nsfw|porn|\bxxx\b|whats\s*app|telegram\s*[:@]|\btg\s*[:：@]|\bdm me\b"
    r"|link in (my )?bio|check (my|the) bio|free (usdt|crypto|airdrop)|airdrop (claim|is live)"
    r"|giveaway|guaranteed (profit|returns?)"
    r"|私[我信聊]|加我|加微|\bvx\b|v信|日入|月入|躺赚|带你(上车|赚)|拉群|进群|约[吗炮]|裸聊|空投领取|免费领)"
)
URL = re.compile(r"https?://\S+")
MENTION = re.compile(r"@\w+")
CJK_RUN = re.compile(r"[一-鿿]+")
EN_WORD = re.compile(r"[a-z][a-z0-9'-]{3,}")
EN_STOP = set(
    "this that with have from your what about just like they will more than them then when were been "
    "into only also some very much here there their would could should really think know people because "
    "https http make made does dont cant youre thats it's i'm don't can't you're that's".split()
)
CJK_STOP = set(
    "我们 你们 他们 这个 那个 就是 不是 一个 没有 可以 什么 自己 现在 还是 因为 所以 如果 但是 这种 时候 "
    "已经 真的 其实 这样 怎么 知道 觉得 大家 一下 东西 的人 是不 不会 也是 都是 不过 这些 那些 出来 起来 "
    "一样 而且 只是 还有 然后 就会 这是 时间 问题 的话 我的 你的 他的 的时 会有 了一".split()
)
CJK_FUNC = set("的了是在和也都就我你他她它这那吗呢吧啊么着过")

MSG = {
    "en": {
        "no_data": "couldn't read this account's recent posts — check it yourself",
        "rate": "{n} recent posts, median gap {gap} min (~{rate}/h)",
        "replies": "{pct}% of them are replies to others",
        "likes": "median likes {likes}",
        "theme": "\"{term}\" shows up in {pct}% of them",
        "dup": "{pct}% of recent posts are copy-paste",
        "spam_reply": "promo/scam wording in this reply",
        "spam_share": "{pct}% of recent posts read like promo/scam",
        "profile": "normal rhythm: {n} recent posts · median gap {gap} min · {rep}% replies · median likes {likes}",
        "title": "Reply triage",
        "summary": "{replies} replies from {accounts} accounts",
        "readonly": "Read-only: nothing was replied to, liked, blocked or muted.",
        "draft": "draft",
        "note": "note",
        "sep": "; ",
        "sections": {
            "human": "🧑 Humans — worth a reply",
            "ai_like": "🤖 AI-like accounts — skip",
            "spam": "🚫 Spam — block by hand if you like",
            "unverified": "❔ Unverified — couldn't read the account",
        },
    },
    "zh": {
        "no_data": "没读到这个号最近的发帖，请自己点进去看",
        "rate": "最近 {n} 条发帖，中位间隔 {gap} 分钟（约每小时 {rate} 条）",
        "replies": "其中 {pct}% 是在回复别人",
        "likes": "点赞中位数 {likes}",
        "theme": "「{term}」出现在 {pct}% 的帖子里",
        "dup": "{pct}% 的最近发帖是复制粘贴",
        "spam_reply": "这条回复本身带推广/诈骗话术",
        "spam_share": "最近发帖里 {pct}% 像推广/诈骗",
        "profile": "节奏正常：最近 {n} 条 · 中位间隔 {gap} 分钟 · {rep}% 是回复 · 点赞中位数 {likes}",
        "title": "评论分拣",
        "summary": "{replies} 条回复，来自 {accounts} 个账号",
        "readonly": "只读：没有回复、点赞、拉黑或静音任何人。",
        "draft": "草稿",
        "note": "备注",
        "sep": "；",
        "sections": {
            "human": "🧑 真人（值得回）",
            "ai_like": "🤖 AI 号（不回）",
            "spam": "🚫 垃圾号（想拉黑就手动拉）",
            "unverified": "❔ 未核实（没读到对方账号）",
        },
    },
}


def parse_time(value: str) -> datetime:
    """Accept ISO 8601 or X's `Sun Oct 11 17:10:38 +0000 2026`."""
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        dt = datetime.strptime(value, "%a %b %d %H:%M:%S %z %Y")
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def to_iso(value: str) -> str:
    try:
        return parse_time(value).astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError, AttributeError):
        return ""


def terms(text: str) -> set[str]:
    """English words + Chinese 2–4 character n-grams, minus function words."""
    clean = MENTION.sub(" ", URL.sub(" ", (text or "").lower()))
    out = {w for w in EN_WORD.findall(clean) if w not in EN_STOP}
    for run in CJK_RUN.findall(clean):
        for size in (2, 3, 4):
            out.update(g for g in (run[i:i + size] for i in range(len(run) - size + 1))
                       if not (set(g) & CJK_FUNC) and not any(s in g for s in CJK_STOP))
    return out


def fingerprint(text: str) -> str:
    """Copy-paste check on the whole post. Links stay in, so sharing different links isn't a duplicate."""
    return re.sub(r"\s+", "", MENTION.sub("", (text or "").lower()))


def author_features(recent: list[dict]) -> dict[str, Any]:
    """Behavioural signals from an account's latest posts (newest ~20)."""
    posts, times = [], []
    for p in recent:
        try:
            times.append(parse_time(p.get("created_at") or ""))
        except (ValueError, TypeError, AttributeError):
            continue  # one bad timestamp must not sink the batch
        posts.append(p)
    n = len(posts)
    if n == 0:
        return {"n": 0}
    times.sort()
    gaps = [(b - a).total_seconds() / 3600 for a, b in zip(times, times[1:])]
    # Median gap, not span: one pinned or old post must not hide a burst.
    gap_h = statistics.median(gaps) if gaps else None
    rate = 1 / max(gap_h, 1 / 60) if gap_h is not None else 0.0
    likes = statistics.median(int(p.get("likes") or 0) for p in posts)
    df: Counter[str] = Counter()
    for p in posts:
        df.update(terms(p.get("text", "")))
    theme_count = max(df.values(), default=0)
    # Among equally common terms prefer the longest: 智能体 over 智能 / 能体.
    theme_term = max((t for t, c in df.items() if c == theme_count), key=lambda t: (len(t), t), default="")
    prints = [fingerprint(p.get("text", "")) for p in posts]
    return {
        "n": n,
        "median_gap_min": round(gap_h * 60, 1) if gap_h is not None else None,
        "posts_per_hour": round(rate, 2),
        "reply_share": round(sum(1 for p in posts if p.get("is_reply")) / n, 2),
        "median_likes": int(likes) if float(likes).is_integer() else round(likes, 1),
        "theme_term": theme_term,
        "theme_share": round(theme_count / n, 2),
        "dup_share": round(1 - len(set(prints)) / n, 2),
        "spam_share": round(sum(1 for p in posts if SPAM_TEXT.search(p.get("text", ""))) / n, 2),
        "samples": [clip(p.get("text", ""), 80) for p in posts[:3]],
    }


def classify(reply_text: str, f: dict[str, Any] | None, lang: str = "en") -> tuple[str, int, list[str]]:
    """Rule label + score + human-readable reasons. Explainable on purpose."""
    m = MSG[lang]
    if not f or not f.get("n"):
        return "unverified", 0, [m["no_data"]]

    def pct(x: float) -> int:
        return round(x * 100)

    spam_reply = bool(SPAM_TEXT.search(reply_text or ""))
    spammy_account = f["reply_share"] >= 0.7 or f["dup_share"] >= 0.3 or f["spam_share"] >= 0.3
    if (spam_reply and spammy_account) or f["spam_share"] >= 0.5 or (f["dup_share"] >= 0.5 and f["reply_share"] >= 0.7):
        reasons = [m["spam_reply"]] if spam_reply else []
        if f["dup_share"] >= 0.3:
            reasons.append(m["dup"].format(pct=pct(f["dup_share"])))
        if f["spam_share"] >= 0.3:
            reasons.append(m["spam_share"].format(pct=pct(f["spam_share"])))
        if f["reply_share"] >= 0.7:
            reasons.append(m["replies"].format(pct=pct(f["reply_share"])))
        return "spam", 0, reasons

    score, reasons = 0, []
    rate = f["posts_per_hour"]
    if f["n"] >= 8 and rate >= 2:
        score += 2 if rate >= 4 else 1
        reasons.append(m["rate"].format(n=f["n"], gap=f["median_gap_min"], rate=rate))
    if f["n"] >= 8 and f["theme_share"] >= 0.5:
        score += 2 if f["theme_share"] >= 0.75 else 1
        reasons.append(m["theme"].format(term=f["theme_term"], pct=pct(f["theme_share"])))
    if f["reply_share"] >= 0.5:
        score += 1
        reasons.append(m["replies"].format(pct=pct(f["reply_share"])))
    if f["median_likes"] <= 1:
        score += 1
        reasons.append(m["likes"].format(likes=f["median_likes"]))
    # Real audiences show up as likes; the reply-bot pattern is busy *and* ignored.
    if score >= 4 and rate >= 2 and f["n"] >= 8 and f["median_likes"] <= 3:
        return "ai_like", score, reasons
    gap = f["median_gap_min"] if f["median_gap_min"] is not None else "—"
    return "human", score, [m["profile"].format(n=f["n"], gap=gap, rep=pct(f["reply_share"]), likes=f["median_likes"])]


# -------------------------------------------------------------- collector ----

def xreach_json(xreach: str, args: list[str], timeout: int = 180) -> Any:
    proc = subprocess.run(shlex.split(xreach) + args + ["--json"], capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout).strip()[:300] or f"xreach exit {proc.returncode}")
    return json.loads(proc.stdout or "null")


def rows_of(data: Any) -> list[dict]:
    if isinstance(data, dict):
        data = data.get("items") or data.get("tweets") or data.get("data") or []
    return [d for d in data or [] if isinstance(d, dict)]


def with_retry(fn: Callable[[], Any], wait: float = 90.0) -> Any:
    """One retry after a pause when X rate-limits; anything else propagates."""
    try:
        return fn()
    except Exception as exc:
        if "429" not in str(exc) and "rate" not in str(exc).lower():
            raise
        time.sleep(wait)
        return fn()


def collect(owner: str, since: str, xreach: str = "xreach", max_pages: int = 5, max_replies: int = 200,
            max_authors: int = 40, pause: float = 10.0, seed: int = 42,
            log: Callable[[str], None] = lambda s: print(s, file=sys.stderr)) -> dict[str, Any]:
    """Read-only: replies to `owner` since `since`, plus each replier's latest ~20 posts.

    xreach search results identify users by id only, so each sampled replier costs
    two reads: one tweet lookup for the handle, one `from:` search for recent posts.
    """
    owner = owner.lstrip("@")
    try:  # search results carry only user ids, so learn the owner's id to drop their own replies
        me = xreach_json(xreach, ["user", owner]) or {}
        owner_id = str((me.get("user") or me).get("restId") or "")
    except Exception:
        owner_id = ""
    rows = rows_of(with_retry(lambda: xreach_json(
        xreach, ["search", f"to:{owner} since:{since}", "--type", "latest", "-n", "20",
                 "--all", "--max-pages", str(max_pages), "--delay", "2000"])))
    replies, seen = [], set()
    for t in rows:
        user = t.get("user") or {}
        handle = user.get("screenName") or ""
        uid = str(user.get("restId") or user.get("id") or "")
        tid = str(t.get("id") or "")
        mine_own = handle.lower() == owner.lower() or (owner_id and uid == owner_id)
        if not re.fullmatch(r"\d+", tid) or tid in seen or not (handle or uid) or mine_own:
            continue
        seen.add(tid)
        replies.append({"id": tid, "url": f"https://x.com/i/status/{tid}", "author": handle, "author_id": uid,
                        "text": t.get("text", ""), "created_at": to_iso(t.get("createdAt", "")),
                        "in_reply_to": t.get("inReplyToTweetId") or t.get("inReplyToStatusId")})
    replies = replies[:max_replies]
    keys = list(dict.fromkeys(r["author_id"] or r["author"] for r in replies))
    checked = keys if len(keys) <= max_authors else random.Random(seed).sample(keys, max_authors)
    log(f"{len(replies)} replies from {len(keys)} accounts; checking {len(checked)}")
    authors: dict[str, Any] = {}
    for i, key in enumerate(checked):
        if i:
            time.sleep(pause)
        mine = [r for r in replies if (r["author_id"] or r["author"]) == key]
        handle = mine[0]["author"]
        try:
            if not handle:
                lookup = with_retry(lambda: xreach_json(xreach, ["tweet", mine[0]["id"]]))
                handle = ((lookup or {}).get("user") or {}).get("screenName") or ""
                if not handle:
                    raise RuntimeError("tweet lookup returned no handle")
            for r in mine:
                r["author"] = handle
            if handle.lower() == owner.lower():
                continue  # the owner's own replies, found only after the lookup
            posts = rows_of(with_retry(lambda: xreach_json(
                xreach, ["search", f"from:{handle}", "--type", "latest", "-n", "20"])))
            authors[handle] = {"recent": [{"created_at": to_iso(t.get("createdAt", "")), "text": t.get("text", ""),
                                           "is_reply": bool(t.get("isReply")), "likes": t.get("likeCount") or 0}
                                          for t in posts]}
            log(f"[{i + 1}/{len(checked)}] @{handle}: {len(posts)} posts")
        except Exception as exc:  # one bad account must not sink the run
            authors[handle or f"id:{key}"] = {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}
            log(f"[{i + 1}/{len(checked)}] {handle or key}: {type(exc).__name__}")
    authors.pop(owner, None)
    replies = [r for r in replies if r["author"].lower() != owner.lower()]
    for r in replies:
        r["author"] = r["author"] or f"id:{r['author_id']}"
    return {"schema": INPUT_SCHEMA, "owner": owner, "since": since, "collector": "xreach-cli",
            "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "coverage": {"replies": len(replies), "accounts": len({r["author_id"] or r["author"] for r in replies}),
                         "accounts_checked": len(authors),
                         "accounts_failed": sum(1 for a in authors.values() if "error" in a)},
            "replies": replies, "authors": authors}


# ----------------------------------------------------------------- triage ----

def llm_pass(items: list[dict], llm_cmd: str, lang: str, timeout: int = 900) -> dict[str, dict]:
    """Optional: let a model confirm labels and draft replies for humans only."""
    view = [{"id": it["id"], "author": it["author"], "text": it["text"], "rule_label": it["label"],
             "signals": it["reasons"], "author_samples": it["features"].get("samples", [])} for it in items]
    prompt = PROMPT_FILE.read_text(encoding="utf-8").replace("{LANG}", lang)
    proc = subprocess.run(shlex.split(llm_cmd), input=prompt + "\n\n" + json.dumps(view, ensure_ascii=False, indent=1),
                          capture_output=True, text=True, timeout=timeout)
    out = proc.stdout.strip()
    start, end = out.find("["), out.rfind("]")
    if proc.returncode != 0 or not 0 <= start < end:
        raise RuntimeError(f"llm-cmd returned no JSON array (exit {proc.returncode})")
    rows = json.loads(out[start:end + 1])
    return {str(r["id"]): r for r in rows if isinstance(r, dict) and r.get("id")}


def triage(data: dict[str, Any], lang: str = "en", llm_cmd: str | None = None) -> dict[str, Any]:
    authors = data.get("authors") or {}
    feats = {h: author_features(a.get("recent") or []) for h, a in authors.items() if not a.get("error")}
    items = []
    for r in data.get("replies") or []:
        f = feats.get(r.get("author", ""))
        label, score, reasons = classify(r.get("text", ""), f, lang)
        base = {k: r[k] for k in INPUT_FIELDS if k in r}
        items.append({**base, "label": label, "rule_label": label, "score": score, "reasons": reasons, "features": f or {}})
    llm_status = None
    if llm_cmd and items:
        try:
            verdicts = llm_pass(items, llm_cmd, lang)
            for it in items:
                v = verdicts.get(str(it["id"])) or {}
                if v.get("label") in LABELS:
                    it["label"] = v["label"]
                if v.get("why"):
                    it["llm_note"] = v["why"]
                if it["label"] == "human" and v.get("draft"):
                    it["draft"] = v["draft"]
            llm_status = f"ok ({len(verdicts)}/{len(items)})"
        except Exception as exc:  # the rule labels still stand on their own
            llm_status = f"failed: {exc}"
    counts = Counter(it["label"] for it in items)
    accounts: dict[str, set[str]] = {k: set() for k in LABELS}
    for it in items:
        accounts[it["label"]].add(it.get("author", ""))
    return {"schema": OUTPUT_SCHEMA, "version": __version__, "owner": data.get("owner"), "since": data.get("since"),
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "lang": lang,
            "coverage": data.get("coverage"), "llm": llm_status,
            "counts": {"replies": {k: counts.get(k, 0) for k in LABELS},
                       "accounts": {k: len(v) for k, v in accounts.items()}},
            "items": items}


def md(text: Any) -> str:
    plain = str(text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return MD_ACTIVE.sub(r"\\\1", plain)


def clip(text: str, n: int = 200) -> str:
    one_line = " ".join((text or "").split())
    return one_line if len(one_line) <= n else one_line[: n - 1] + "…"


def render_md(result: dict[str, Any]) -> str:
    m = MSG[result.get("lang") or "en"]
    items = result["items"]
    c = result["counts"]["replies"]
    accounts = len({it.get("author") for it in items})
    tally = " · ".join(f"{m['sections'][k].split(' ')[0]} {c[k]}" for k in LABELS)
    lines = [f"# {m['title']} · @{result.get('owner') or '?'} · {result['generated_at'][:10]}", "",
             f"{m['summary'].format(replies=len(items), accounts=accounts)} · {tally}", "",
             f"> {m['readonly']}", ""]
    for label in LABELS:
        group = [it for it in items if it["label"] == label]
        if not group:
            continue
        lines += [f"## {m['sections'][label]} ({len(group)})", ""]
        for it in group:
            url = it.get("url", "") if SAFE_URL.fullmatch(str(it.get("url", ""))) else ""
            lines.append(f"{'- [ ] ' if label == 'human' else '- '}@{md(it.get('author'))} · {url}".rstrip(" ·"))
            lines.append(f"  - “{md(clip(it.get('text', '')))}”")
            lines.append(f"  - {md(m['sep'].join(it['reasons']))}")
            if it.get("draft"):
                lines.append(f"  - {m['draft']}: {md(it['draft'])}")
            if it.get("llm_note"):
                lines.append(f"  - {m['note']}: {md(it['llm_note'])}")
        lines.append("")
    return "\n".join(lines)


def write_outputs(result: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    jp, mp = out_dir / "triage.json", out_dir / "triage.md"
    jp.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    mp.write_text(render_md(result), encoding="utf-8")
    return jp, mp


def summary_line(result: dict[str, Any]) -> str:
    r, a = result["counts"]["replies"], result["counts"]["accounts"]
    return (f"replies: human {r['human']} · ai_like {r['ai_like']} · spam {r['spam']} · unverified {r['unverified']}"
            f" | accounts: human {a['human']} · ai_like {a['ai_like']} · spam {a['spam']} · unverified {a['unverified']}")


# -------------------------------------------------------------------- cli ----

def at_least(lo: float, cast: Callable[[str], Any] = int) -> Callable[[str], Any]:
    def parse(value: str) -> Any:
        number = cast(value)
        if number < lo:
            raise argparse.ArgumentTypeError(f"must be >= {lo}")
        return number
    return parse


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="x-reply-triage", description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--version", action="version", version=f"x-reply-triage {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("demo", help="run on the bundled synthetic sample (offline, no login)")
    d.add_argument("--lang", choices=sorted(MSG), default="en")
    d.add_argument("--out-dir", default="output")

    c = sub.add_parser("collect", help="read replies + repliers' recent posts via xreach-cli (read-only)")
    c.add_argument("--owner", required=True, help="your X handle")
    c.add_argument("--since", default=(datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d"))
    c.add_argument("--out", default="data/replies.json")
    c.add_argument("--xreach", default="xreach", help='xreach command, e.g. "xreach --chrome-profile Default"')
    c.add_argument("--max-pages", type=at_least(1), default=5, help="search pages of 20 replies")
    c.add_argument("--max-replies", type=at_least(1), default=200)
    c.add_argument("--max-authors", type=at_least(0), default=40, help="accounts to look up (random sample above this)")
    c.add_argument("--pause", type=at_least(0, float), default=10.0, help="seconds between account lookups")
    c.add_argument("--seed", type=int, default=42)

    t = sub.add_parser("triage", help="label replies and write triage.md + triage.json")
    t.add_argument("input")
    t.add_argument("--out-dir", default="output")
    t.add_argument("--lang", choices=sorted(MSG), default="en")
    t.add_argument("--llm-cmd", help='optional model command that reads stdin, e.g. "claude -p"')

    args = ap.parse_args(argv)
    if args.cmd == "collect":
        data = collect(args.owner, args.since, args.xreach, args.max_pages, args.max_replies,
                       args.max_authors, args.pause, args.seed)
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"wrote {out} · coverage {json.dumps(data['coverage'])}")
        return 0
    source = DEMO_INPUT if args.cmd == "demo" else Path(args.input)
    data = json.loads(source.read_text(encoding="utf-8"))
    if data.get("schema") != INPUT_SCHEMA:
        print(f"error: {source} is not {INPUT_SCHEMA}", file=sys.stderr)
        return 2
    result = triage(data, args.lang, getattr(args, "llm_cmd", None))
    jp, mp = write_outputs(result, Path(args.out_dir))
    print(summary_line(result))
    if result.get("llm"):
        print(f"llm: {result['llm']}")
    print(f"wrote {mp} and {jp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
