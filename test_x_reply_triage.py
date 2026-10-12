import json
import shlex
import sys
import tempfile
import textwrap
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import x_reply_triage as xrt

DEMO = json.loads(xrt.DEMO_INPUT.read_text(encoding="utf-8"))
T0 = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)


def burst(n=20, gap_min=10, reply_share=0.6, likes=0, texts=("the harness decides everything",)):
    return [{"created_at": (T0 - timedelta(minutes=gap_min * i)).isoformat(), "text": f"{texts[i % len(texts)]} #{i}",
             "is_reply": i < n * reply_share, "likes": likes} for i in range(n)]


def labels(result):
    return {it["author"]: it["label"] for it in result["items"]}


class DemoLabels(unittest.TestCase):
    def test_demo_sample_sorts_as_designed(self):
        got = labels(xrt.triage(DEMO))
        for handle in ("demo_maya_builds", "demo_wang_pm", "demo_lin_trades", "demo_busy_newsdesk", "demo_tg_fan"):
            self.assertEqual(got[handle], "human", handle)
        for handle in ("demo_agent_harness_daily", "demo_token_is_power", "demo_growth_loop_ai"):
            self.assertEqual(got[handle], "ai_like", handle)
        for handle in ("demo_airdrop_claim", "demo_fuli_520"):
            self.assertEqual(got[handle], "spam", handle)
        self.assertEqual(got["demo_ghost_x"], "unverified")

    def test_counts_cover_every_reply(self):
        result = xrt.triage(DEMO)
        self.assertEqual(sum(result["counts"]["replies"].values()), len(DEMO["replies"]))


class Signals(unittest.TestCase):
    def test_pinned_post_does_not_hide_a_burst(self):
        posts = burst() + [{"created_at": (T0 - timedelta(days=90)).isoformat(), "text": "pinned", "is_reply": False, "likes": 50}]
        f = xrt.author_features(posts)
        self.assertGreaterEqual(f["posts_per_hour"], 5)
        self.assertEqual(xrt.classify("nice", f)[0], "ai_like")

    def test_busy_account_with_real_engagement_is_human(self):
        f = xrt.author_features(burst(reply_share=0.1, likes=40, texts=("news update",)))
        self.assertEqual(xrt.classify("can we quote this?", f)[0], "human")

    def test_slow_account_is_human_even_with_zero_likes(self):
        f = xrt.author_features(burst(gap_min=600, likes=0))
        self.assertEqual(xrt.classify("good point", f)[0], "human")

    def test_spam_word_alone_does_not_make_spam(self):
        f = xrt.author_features(burst(gap_min=480, reply_share=0.3, likes=5, texts=("今天整理了笔记",)))
        self.assertEqual(xrt.classify("TG: 群里也在讨论这个", f)[0], "human")

    def test_promo_reply_from_reply_only_account_is_spam(self):
        f = xrt.author_features(burst(gap_min=1, reply_share=1.0, texts=("想赚钱的私我",)))
        self.assertEqual(xrt.classify("想赚钱的私我，日入500U", f)[0], "spam")

    def test_too_few_posts_is_not_ai_like(self):
        f = xrt.author_features(burst(n=4, gap_min=5))
        self.assertEqual(xrt.classify("great", f)[0], "human")

    def test_theme_prefers_longest_chinese_term(self):
        f = xrt.author_features(burst(texts=("智能体要能续跑", "做智能体先做日志", "智能体不是聊天机器人", "好奇你们智能体怎么评测")))
        self.assertEqual(f["theme_term"], "智能体")

    def test_missing_author_data_is_unverified(self):
        self.assertEqual(xrt.classify("hi", None)[0], "unverified")
        self.assertEqual(xrt.classify("hi", {"n": 0})[0], "unverified")

    def test_sharing_different_links_is_not_copy_paste(self):
        posts = [{"created_at": (T0 - timedelta(hours=6 * i)).isoformat(), "is_reply": False, "likes": 4,
                  "text": f"new write-up: https://example.com/post/{i}"} for i in range(8)]
        f = xrt.author_features(posts)
        self.assertEqual(f["dup_share"], 0)
        self.assertEqual(xrt.classify("thanks, useful", f)[0], "human")

    def test_bad_timestamp_is_skipped_not_fatal(self):
        posts = burst(n=10) + [{"created_at": "not a date", "text": "x", "is_reply": True, "likes": 0}]
        self.assertEqual(xrt.author_features(posts)["n"], 10)

    def test_new_account_with_promo_word_needs_behaviour_to_be_spam(self):
        f = xrt.author_features(burst(n=2, gap_min=600, reply_share=0.0, likes=2, texts=("hello world",)))
        self.assertNotEqual(xrt.classify("TG: 一起聊", f)[0], "spam")


class Rendering(unittest.TestCase):
    def test_markdown_in_both_languages(self):
        en = xrt.render_md(xrt.triage(DEMO, "en"))
        zh = xrt.render_md(xrt.triage(DEMO, "zh"))
        self.assertIn("Humans — worth a reply", en)
        self.assertIn("Read-only", en)
        self.assertIn("真人（值得回）", zh)
        self.assertIn("「智能体」", zh)
        self.assertNotIn("draft:", en)
        self.assertIn("normal rhythm", en)  # humans show their signals too

    def test_untrusted_text_cannot_inject_markdown(self):
        data = json.loads(json.dumps(DEMO))
        data["replies"][0]["text"] = "![x](https://evil.example/t.png) <img src=x> [a](b)"
        data["replies"][0]["url"] = "javascript:alert(1)"
        out = xrt.render_md(xrt.triage(data))
        self.assertNotIn("![x](", out)
        self.assertNotIn("<img", out)
        self.assertIn("&lt;img", out)
        self.assertNotIn("javascript:", out)

    def test_input_cannot_smuggle_a_draft(self):
        data = json.loads(json.dumps(DEMO))
        for r in data["replies"]:
            r["draft"] = "smuggled"
        result = xrt.triage(data)
        self.assertFalse(any("draft" in it for it in result["items"]))

    def test_cli_rejects_bad_numbers(self):
        with self.assertRaises(SystemExit) as caught:
            xrt.main(["collect", "--owner", "me", "--max-pages", "0"])
        self.assertEqual(caught.exception.code, 2)

    def test_cli_demo_writes_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(xrt.main(["demo", "--out-dir", tmp]), 0)
            out = json.loads(Path(tmp, "triage.json").read_text(encoding="utf-8"))
            self.assertEqual(out["schema"], xrt.OUTPUT_SCHEMA)
            self.assertTrue(Path(tmp, "triage.md").exists())

    def test_cli_rejects_other_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp, "bad.json")
            bad.write_text('{"schema": "other"}', encoding="utf-8")
            self.assertEqual(xrt.main(["triage", str(bad), "--out-dir", tmp]), 2)


def script(tmp: str, name: str, body: str) -> str:
    path = Path(tmp, name)
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return f"{shlex.quote(sys.executable)} {shlex.quote(str(path))}"


FAKE_XREACH = """
    import json, sys
    args = sys.argv[1:]
    t0 = "Sat Oct 10 12:00:00 +0000 2026"
    if args[0] == "user":
        print(json.dumps({"restId": "u0", "screenName": "me"}))
    elif args[0] == "search" and args[1].startswith("to:"):
        print(json.dumps({"items": [
            {"id": "5", "text": "@me my reply in my own thread", "createdAt": t0, "user": {"restId": "u0"}},
            {"id": "1", "text": "@me nice", "createdAt": t0, "user": {"restId": "u1"}},
            {"id": "2", "text": "@me same", "createdAt": t0, "user": {"restId": "u1"}},
            {"id": "3", "text": "@me hi", "createdAt": t0, "user": {"restId": "u2", "screenName": "bob"}},
            {"id": "4", "text": "my own reply", "createdAt": t0, "user": {"restId": "u0", "screenName": "me"}},
        ]}))
    elif args[0] == "tweet":
        print(json.dumps({"id": args[1], "user": {"screenName": "alice"}}))
    elif args[0] == "search" and args[1].startswith("from:"):
        if args[1] == "from:bob":
            sys.exit("boom")
        print(json.dumps({"items": [{"id": str(i), "text": "post", "createdAt": t0,
                                      "isReply": True, "likeCount": 0} for i in range(3)]}))
"""


class Collector(unittest.TestCase):
    def test_collect_resolves_handles_and_survives_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = xrt.collect("me", "2026-10-01", xreach=script(tmp, "xreach.py", FAKE_XREACH),
                               pause=0, log=lambda _: None)
        self.assertEqual([r["author"] for r in data["replies"]], ["alice", "alice", "bob"])
        self.assertEqual(len(data["authors"]["alice"]["recent"]), 3)
        self.assertIn("error", data["authors"]["bob"])
        self.assertEqual(data["coverage"], {"replies": 3, "accounts": 2, "accounts_checked": 2, "accounts_failed": 1})
        self.assertEqual(xrt.triage(data)["counts"]["replies"]["unverified"], 1)


FAKE_LLM = """
    import json, sys
    sys.stdin.read()
    print("Sure:")
    print(json.dumps([
        {"id": "demo-0001", "label": "human", "draft": "Claude for this one.", "why": "real question"},
        {"id": "demo-0010", "label": "spam", "draft": "should be dropped", "why": "bait"},
        {"id": "demo-0009", "label": "human", "draft": "Mostly scripts.", "why": "reads like a person"},
    ]))
"""


class ModelPass(unittest.TestCase):
    def test_drafts_only_for_humans_and_overrides_are_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = xrt.triage(DEMO, llm_cmd=script(tmp, "llm.py", FAKE_LLM))
        items = {it["id"]: it for it in result["items"]}
        self.assertEqual(items["demo-0001"]["draft"], "Claude for this one.")
        self.assertNotIn("draft", items["demo-0010"])
        self.assertEqual(items["demo-0009"]["label"], "human")
        self.assertEqual(items["demo-0009"]["rule_label"], "ai_like")
        self.assertTrue(result["llm"].startswith("ok"))

    def test_failed_model_keeps_rule_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = xrt.triage(DEMO, llm_cmd=script(tmp, "llm.py", "import sys; sys.exit(3)"))
        self.assertTrue(result["llm"].startswith("failed"))
        self.assertEqual(labels(result)["demo_agent_harness_daily"], "ai_like")


if __name__ == "__main__":
    unittest.main()
