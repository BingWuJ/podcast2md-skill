# podcast2md feature map

给 AI 助手用的一张地图：这个 skill 有哪些入口、产物长什么样、状态怎么读、坑在哪。
维护规则：**每次踩到新坑，就往「坑」里追加一行**，不要只留在会话里。改完跑一次 `podcast2md.py verify-all`。

## 1. 入口：用户从哪儿进来

| 用户给的东西 | 走哪条路 | 命令 |
|---|---|---|
| 播客 / B 站单集链接 | 本 CLI，内部自动探测字幕 | `python podcast2md.py "<URL>"` |
| 本地音频文件（无链接） | 不走本 CLI URL 流水；默认 CapsWriter | 见 SKILL.md「本地音频」；复用 `work\\_local_transcribe.py` |
| 用户单独给的 srt / vtt | 不走本 CLI，走 srt-translator | 见 SKILL.md「相邻场景分工」 |
| 只要核对已完成的单集 | 本 CLI 的取证入口 | `python podcast2md.py verify <单集目录>` |
| 查转过哪些 / 打开最终稿 | 本 CLI 的 history | `python podcast2md.py history` / `history search` / `history open` |
| 本地音频出稿后入账 | 本 CLI 的 history register（脚本本身不登记） | `python podcast2md.py history register --source <音频> --final <文字稿>` |

## 2. 产物：`work/<slug>/` 里有什么

| 文件 | 何时存在 | 用途 |
|---|---|---|
| `chapters.md` | 一定有 | 交付物。章节文字稿 |
| `toc.json` | 一定有 | 章节、文字来源、`source_fingerprint`、`verify` 覆盖统计 |
| `subtitle-probe.json` | 一定有 | 字幕探测状态与轨道，**不是**「确认无字幕」的替代结论 |
| `original-subs/*.srt` | 走字幕路径时 | 平台字幕原件（普通CC / 平台AI） |
| `<slug>.srt/.txt/.json` | 走 ASR 路径时 | CapsWriter 产物 |
| `<slug>.m4a` | 走 ASR 路径时 | 下载的音频 |
| `logs/` | 一定有 | `list-subs.log`、`ytdlp.log`、`client.log` |
| `<CAPSWRITER_HOME>\\history\\转录历史.md` | 有过登记后 | 跨 URL/本地音频的中文历史清单；默认在部署目录 `history`；不是校对证明 |

## 3. 状态：字幕探测五态怎么读

| 状态 | 含义 | 能否继续 |
|---|---|---|
| `found` | 有可用轨道，用平台字幕出稿，不下载音频 | ✅ |
| `confirmed_none` | 明确没有可用轨道（弹幕不算） | ✅ 走 ASR |
| `login_required` | 需要登录才能看字幕 | ❌ 停止，不得写成「无字幕」 |
| `request_failed` | 探测请求失败 | ❌ 停止 |
| `filter_no_match` | 传了 `--sub-lang` 但没这个语言 | ❌ 停止 |

## 4. 取证入口（核对时只跑这些，不要重跑流水线）

```powershell
python podcast2md.py probe "<URL>" --json          # 只探测，不下载不转写
python podcast2md.py verify "<单集目录>" --json     # 只重算覆盖与结构
python podcast2md.py verify-all --json             # 批量体检 work 下所有单集
```

`verify --json` 的固定字段：`ok` / `text_source` / `cues` / `body_lines` / `unlocated` /
`chapters_md` / `chapters_toc` / `coverage{missing,added,duplicate,reordered,replaced,punctuation}` /
`timeline_ok` / `toc_signature_ok` / `polish_inferred` / `reasons` / `warnings`。

判读口诀：`ok: true` 是**本地校验通过的必要条件**，不代替网页/内容验收；`reasons` 非空是硬失败；`warnings` 是能交付但要说明的情况
（`timeline_has_unlocated_text`、`toc_signature_mismatch`、`toc_signature_absent`、`chapter_count_mismatch`）。

### `verify` 的边界（很容易误读）

`scope: local_only`、`web_check: not_verified` 是固定字段：`verify` **不联网**。
所以 `ok: true` 的含义是：**本地硬失败判据未触发**（`reasons` 为空）。正文是否与原件一致要按 `coverage` 与 `polish_inferred` 的口径判读；章数与指纹**不在 `ok` 里**，另看 `chapters_md` / `chapters_toc` / `toc_signature_ok` 以及 `warnings`（`chapter_count_mismatch`、`toc_signature_mismatch`、`toc_signature_absent` 只进 `warnings`，**不会**让 `ok` 变 false）。它**不**证明与当前网页目录一致。
它**不**证明章节与**当前**网页目录一致。已知的实例（44 号小宇宙单集）里，本地与当前网页就不一致；
**原因未定**：可能是网页后来更新了目录，也可能是历史处理差异（旧章节目录怎么来的，目前没找到历史网页快照或日志可判定）：

- 2026-10-26 20:33 运行时刻：15 章（含 1680 / 3151 / 3508 / 3719）
- 2026-10-28 网页复核：当前页 11 章，且 53s 标题 `婉婷`→`Wanting`、909s `千万级`→`亿万级`

验收报告必须分开写两句话：「本地全文覆盖通过」与「与当前网页目录一致（需人工或单独的联网核对）」。
判断章节是否过期：看 `chapter_origin`。它为 `html`/`description` 时，网页一改就过期；为 `yt-dlp` 时跟随平台 metadata。

退出码：`0` 通过 / `2` 用法错误 / `3` 下载或探测失败 / `4` 服务端失败 / `5` 转录失败 /
`6` 成品已存在 / `7` 校验失败。

## 5. 坑（追加区）

- `CAPSWRITER_HOME` 为空时不要写 `python "$env:CAPSWRITER_HOME\podcast2md.py"`，那会变成 `python "\podcast2md.py"`；先 `cd` 到部署目录用相对路径。
- 6016 端口被别的程序占用时，本脚本会误判「服务端已就绪」，最终表现为退出码 5。先确认该端口属于 `start_server.exe`。
- `--force` 会删掉单集目录，包括手动改过的文件。
- B 站未登录时 `--list-subs` 只给 `danmaku`（弹幕）+ 一行 `WARNING: Subtitles are only available when logged in`。这是 `login_required`，不是 `found`，也不是「无字幕」。2026-10-27 修过一次把 `WARNING:` 当语言名的解析缺陷。
- 小宇宙没有专用提取器，generic 能解析到 `media.xyzcdn.net` 的 m4a；把**页面 URL** 交给脚本，别改成音频直链，否则丢掉页面时间戳目录。
- 只含 `subtitle-probe.json` 和 `logs/` 的目录允许直接重试（不必 `--force`）；一旦有音频、字幕原件或 `chapters.md` 就受保护。
- 论文式文字稿的拼装脚本现在与 `podcast2md.py` 同目录（`build_paper_transcript.py`），它自己会再跑一遍正文覆盖自检，不通过不写文件。
- `history` 不是全事件记录：Ctrl+C、exit 6（成品已存在）、probe/verify、直接运行 `_local_transcribe.py`、未 register 的本地稿/srt 稿都不会自动出现。backfill 只补空缺，不把「最近一次失败」改成已生成。显式 `history register`/`backfill` 写入失败必须非零退出。
- 本地音频的**默认引擎是 CapsWriter**（`start_server.exe`/`start_client.exe`，同一套 fun_asr_nano），不是 transformers 版 Fun-ASR-Nano。2026-10-31 实测同一批 8 分半音频：CapsWriter 冷启动 90 秒 / 已热 64 秒，transformers 版约 5.5 分钟。选错引擎要重跑一遍，白等。
- `FunASR-Nano` 与 `FunASR` 是两个目录，不要混：`D:\iStall\FunASR` 是框架仓库、**没有** `work` 目录；转录脚本和 venv 都在 `D:\iStall\FunASR-Nano`。2026-10-31 因为 SKILL.md 早期写成 `<FunASR目录>\work\full_transcribe.py`，多花两次全盘搜索才定位。
- CapsWriter 偶尔会出现**整句重复**和**跨句拼接/漏句**：2026-10-31 下篇有一处「应用场景」整段重复，另有一处把前文「交付什么」的短语拼进「成功标准」那一条。交付前必须拿相邻段比对一遍，不能把 `.txt` 直接当定稿。
- 本地音频转录的复用入口：`work\_local_transcribe.py`（2026-10-31 新增），只 import `podcast2md` 调 `ensure_server` + `run_client`，不重写引擎。用法 `python work\_local_transcribe.py --audio "<m4a>" --slug <slug>`。
