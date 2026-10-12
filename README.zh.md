# x-reply-triage

![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)
![License MIT](https://img.shields.io/badge/license-MIT-green)

English: [README.md](./README.md)

评论区里的 AI 号越来越多：几分钟发一条，每条都先夸你一句、再抛个问题，点赞基本为零。x-reply-triage 把评论分成真人、AI 号和垃圾号，让你的回复只花在真人身上。

## 你能得到什么

- **一份分好类的待回清单**：🧑 真人（值得回）、🤖 AI 号（不回）、🚫 垃圾号（想拉黑就手动拉）、❔ 未核实。
- **每个判断都写明依据**，比如「最近 20 条发帖，中位间隔 9 分钟；其中 80% 是在回复别人；点赞中位数 0」。你不同意，可以直接推翻。
- **看行为，不看文风**：判断依据是对方最近 20 条发帖的节奏和互动，不是这一条评论读起来像不像 AI。
- **只给真人起草回复（可选）**：接任何从标准输入读提示词的模型命令，比如 `claude -p`、`codex exec`。
- **只读**：不回复、不点赞、不拉黑、不静音。
- **自带离线演示**：演示数据里的账号和帖子全是虚构的，不登录也能先跑一遍。

## 怎么判断

```text
别人回复你的评论（最近 N 天）
  ↓ 采集：搜一次评论，再对每个评论者：
  ↓       查一次帖子拿到账号名 + 搜一次他最近约 20 条发帖
每个账号的信号
  · 发帖节奏（相邻两条的中位间隔）
  · 回复别人的占比
  · 点赞中位数
  · 有没有一个词反复出现
  · 复制粘贴、推广 / 诈骗话术
  ↓ 分拣：可解释的规则（可选再过一遍模型：复核标签、给真人起草回复）
output/triage.md + output/triage.json
```

v0.1 的规则：

- **垃圾号**：评论本身带推广/诈骗话术，且对方几乎只发回复、复制粘贴或在发推广；或者对方最近发帖大多是推广、复制粘贴的回复。
- **AI 号**：最近发帖至少 8 条，每小时大约 2 条以上，几乎没人互动（点赞中位数 ≤ 3），并且节奏、主题重复、回复占比、点赞这几项加起来至少 4 分。
- **真人**：读得到账号、又不属于上面两类的。
- **未核实**：读不到对方账号。

## 安装

```bash
git clone https://github.com/runesleo/x-reply-triage.git
cd x-reply-triage
python3 x_reply_triage.py demo --lang zh    # 只用 Python 标准库
```

要分拣自己的评论，先装好采集器并登录 X：

```bash
npm install -g xreach-cli                   # https://github.com/Panniantong/xfetch
```

用 Claude Code 或 Codex 的话，`SKILL.md` 可以直接当 skill 用。

## 环境要求

- Python 3.9+，只用标准库。
- 可选：[`xreach-cli`](https://github.com/Panniantong/xfetch)，`collect` 要用。
- 可选：一个能从标准输入读提示词的模型命令行，`--llm-cmd` 要用。

**隐私说明**：`collect` 通过 `xreach-cli` 读取 X，用的是你自己已登录的浏览器会话；本工具不接触、也不保存你的 Cookie。`data/` 和 `output/` 里是别人的公开发帖，已经写进 `.gitignore`，请不要公开。加 `--llm-cmd` 时，账号名、评论正文和对方最近几条发帖会发给这个命令背后的模型服务；这个命令以你的环境运行，请选一个不能读写文件、不能调用工具的。用登录态读取 X 可能与 X 关于自动化访问的规则冲突：保持低频（默认最多查 40 个账号，每个间隔 10 秒），只用来处理自己的评论。

## 快速开始

```bash
python3 x_reply_triage.py demo --lang zh
python3 x_reply_triage.py collect --owner 你的账号 --since 2026-10-05 --out data/replies.json
python3 x_reply_triage.py triage data/replies.json --lang zh
# 可选：给真人起草回复
python3 x_reply_triage.py triage data/replies.json --lang zh --llm-cmd "claude -p"
```

## 已验证

| 场景 | 环境 | 结果 |
|---|---|---|
| 离线演示，12 条虚构评论 | macOS，Python 3.9 和 3.14 | 真人 5 · AI 号 4 · 垃圾号 2 · 未核实 1，与设计一致 |
| 单元测试 | `python3 -m unittest -q test_x_reply_triage`（Python 3.9 和 3.14） | 22 个全部通过 |
| 作者自己评论区，7 天（2026-10-05 → 10-12） | xreach-cli 0.3.3 | X 搜索取到 40 条评论、30 个账号：AI 号 14 个（47%），真人 16 个，垃圾号 0 个。AI 号每 0.4–7.7 分钟发一条，真人大多隔几小时到几天。再让模型（`claude -p`，能看到规则依据）复核一遍，一条没改判。 |

## 已知限制（v0.1）

- 这是经验规则，不是检测器。特别活跃、又少有人点赞的真人可能被判成 AI 号；发得慢的 AI 号也可能被当成真人。依据都写在结果里，方便你推翻。
- `xreach-cli` 0.3.x 的搜索结果只带用户 id，所以每个评论者要多查一次才能拿到账号名；0.3.3 的 `tweets --replies` 会报错，所以对方最近的发帖改用 `from:` 搜索获取，可能有延迟或漏掉几条。
- 主题词按词频判断：英文按单词，中文按 2–4 个字的词。
- X 搜索只能取到你收到的一部分评论，统计数字只代表取到的那部分。
- 模型复核时能看到规则依据，所以它同意只算一次校验，不算独立判断。
- 目前只支持 X。

## 路线图

- 账号信号跨次缓存，少查几次。
- 白名单 / 黑名单：认识的账号不用再判。
- 把「真人待回」导出给其他回复工具。
- 更多采集方式：官方 API、浏览器导出。

## 关于作者

*Leo（[@runes_leo](https://x.com/runes_leo)）— AI × Crypto 独立构建者。在 [Polymarket](https://polymarket.com/?via=runes-leo&r=runesleo&utm_source=github&utm_content=x-reply-triage) 做量化，用 Claude Code 和 Codex 搭数据与内容管线。*

*[leolabs.me](https://leolabs.me) — 写作 · 社群 · 开源工具 · 独立项目*

*[X 订阅](https://x.com/runes_leo/creator-subscriptions/subscribe) — 付费内容周刊*

*Learn in public, Build in public.*

## License

MIT — 见 [LICENSE](LICENSE)。
