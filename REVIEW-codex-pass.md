# REVIEW — independent Codex pass (v0.1.0)

Reviewer: Codex, independent pass (asked to evaluate from scratch, read-only), 2026-10-12.
Scope: `x_reply_triage.py`, tests, `SKILL.md`, `prompts/triage.md`, READMEs, `CHANGELOG.md`, `.gitignore`, demo sample.

## Findings (verbatim)

## 🔴 Blockers

- `x_reply_triage.py:137`：指纹删除全部 URL 并截断到 40 字符，实测 8 条不同链接被算成 88% 重复、直接判为 `spam`，会把正常分享资料的账号误列入垃圾号。
- `x_reply_triage.py:372`：评论未经 Markdown／HTML 转义便写入报告，攻击者提供的图片语法会原样保留，在允许加载远程图片的预览器中产生跟踪请求。

## 🟡 Warnings

- `x_reply_triage.py:146`：单条无效时间戳会抛出异常并终止整批分拣，而 `to_iso()` 又会保留解析失败的原值。
- `x_reply_triage.py:257`：自身账号过滤发生在补全用户名之前，实测只有用户 ID 的自身回复在补全后仍进入待回清单。
- `x_reply_triage.py:249`、`CHANGELOG.md:13`：首次评论搜索没有接入重试，实测遇到 429 直接失败，与“限流重试一次”的描述不完全一致。
- `x_reply_triage.py:413`：数量和间隔参数缺少范围校验，负数会导致切片错误或运行时异常，且本机 xreach 0.3.3 将 `--max-pages 0` 解释为不限页数。
- `x_reply_triage.py:183`、`README.md:37`、`README.zh.md:37`：代码把“历史帖子不足 3 条”也作为垃圾账号条件，实测普通账号仅因回复包含 `TG:` 被判为垃圾号，文档未说明此分支。
- `x_reply_triage.py:373`、`README.md:13`、`README.zh.md:13`：Markdown 隐藏所有 `human` 的规则依据，与“每个判断都展示依据”的承诺不符。
- `x_reply_triage.py:323`、`x_reply_triage.py:375`：输入中已有的 `draft` 会被直接继承，实测垃圾号也能保留并展示草稿，绕过“仅真人有草稿”的限制。
- `x_reply_triage.py:306`、`prompts/triage.md:14`：模型命令继承调用环境和自身工具权限，防提示注入仅靠文字约束，无法保证任意 `--llm-cmd` 都遵守只读承诺。
- `README.md:64`、`README.zh.md:64`：隐私说明没有披露模型步骤会传入账号名、评论正文和近期帖子样本，数据可能发送至所选模型服务。
- `.gitignore:2`、`.gitignore:7`：仓库规则未忽略 `.env.local`、`.env.production` 或自定义输出目录，默认目录之外的数据仍可能被误提交。
- `README.md:81`、`README.zh.md:81`：公布的测试命令需要 pytest，却没有安装说明；标准库环境应使用已验证可运行的 `python3 test_x_reply_triage.py`。
- `README.md:82`、`README.zh.md:82`：仍残留 `STUDY_ROW_EN`／`STUDY_ROW_ZH` 模板占位符。

## 🟢 OK

- `test_x_reply_triage.py:25`：当前版本 pytest 实测 16 项全部通过，已禁用字节码和 pytest 缓存写入。
- `x_reply_triage.py:434`：Python 3.14.6 下禁用 site-packages 的离线 demo 成功，结果为真人 5、AI-like 4、垃圾号 2、未核实 1。
- `x_reply_triage.py:217`、`x_reply_triage.py:306`：子进程使用参数列表且未启用 shell，未发现评论文本经 shell 拼接执行的命令注入路径。
- `examples/demo_input.json:7`、`.gitignore:7`：示例使用虚构标识，所查文件未发现密钥或本机绝对路径，默认采集和输出目录已忽略。

## Resolution

| Finding | Status | Where |
|---|---|---|
| 🔴 Fingerprint stripped links and cut to 40 chars, so link-sharing accounts looked like spam | Fixed: whole post, links kept | `fingerprint()`, `test_sharing_different_links_is_not_copy_paste` |
| 🔴 Untrusted reply text rendered as Markdown/HTML (remote images) | Fixed: `<>&` entity-encoded, Markdown link/image syntax escaped, only `https://x.com/...` URLs rendered | `md()`, `SAFE_URL`, `test_untrusted_text_cannot_inject_markdown` |
| 🟡 One bad timestamp aborted the batch | Fixed: bad timestamps are skipped; `to_iso` returns empty on failure | `author_features()`, `test_bad_timestamp_is_skipped_not_fatal` |
| 🟡 The owner's own id-only replies reached the queue | Fixed: owner id looked up first; replies that resolve to the owner are left out | `collect()`, collector test |
| 🟡 First search had no rate-limit retry | Fixed | `collect()` |
| 🟡 No range checks on numeric flags | Fixed: `--max-pages` / `--max-replies` ≥ 1, `--max-authors` / `--pause` ≥ 0 | `at_least()`, `test_cli_rejects_bad_numbers` |
| 🟡 "Fewer than 3 posts" counted as spam behaviour | Fixed: removed; spam needs reply-only, copy-paste or promo behaviour | `classify()`, `test_new_account_with_promo_word_needs_behaviour_to_be_spam` |
| 🟡 Humans showed no reasons | Fixed: humans show their signal summary | `classify()`, rendering test |
| 🟡 A `draft` in the input could survive on spam | Fixed: input fields are whitelisted | `INPUT_FIELDS`, `test_input_cannot_smuggle_a_draft` |
| 🟡 `--llm-cmd` runs with the caller's environment | Documented: use a command without file or tool access; the prompt treats reply text as untrusted | README Privacy, `SKILL.md` |
| 🟡 Privacy note didn't cover the model step | Fixed | README Privacy (EN/ZH), `SKILL.md` |
| 🟡 `.gitignore` missed `.env.*`; custom output dirs | Fixed for `.env.*`; custom dirs documented ("keep them out of git") | `.gitignore`, README |
| 🟡 Test command needed pytest | Fixed: `python3 -m unittest -q test_x_reply_triage` | README |
| 🟡 Template placeholders left in READMEs | Fixed | README Verified |

Smoke after fixes: 22 tests pass on Python 3.9 and 3.14; the offline demo is unchanged (5 human · 4 AI-like · 2 spam · 1 unverified); the 7-day real sample re-triaged with identical labels.
