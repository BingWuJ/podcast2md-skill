# 更新日志 / Changelog

本仓库自 v2.0.0 起使用语义化版本（`MAJOR.MINOR.PATCH`）并打 annotated tag，同时在 GitHub Releases 发布对应说明。

- `MAJOR`：默认流水线或产物契约发生不兼容变化（例如这次把「总是下载 + 语音识别」改成「字幕优先」）。
- `MINOR`：新增向后兼容的能力、参数、文档章节。
- `PATCH`：缺陷修复、文案与校验口径修正，不改变默认行为。

v2.0.0 之前的提交没有版本号。文末「历史（重建）」按提交时间归并，只用于说明演进顺序，不代表当时打过 tag。

---

## v2.0.0 — 2026-10-25

字幕优先流水线 + 全文覆盖校验 + 探测状态不得被误写成「无字幕」。

### Why：为什么会做这次更新

这一版不是加功能，而是修四个会**静默产生错稿或白干活**的问题：

1. **「JSON 字幕字段为空」被当成「确认没有字幕」。** 播客/B 站视频里，`yt-dlp -J` 的 `subtitles`/`automatic_captions` 为空非常常见，但它只说明这一次 JSON 没带出轨道，不等于平台真的没有字幕。旧流程据此直接判定无字幕并转去跑语音识别，等于把「没探测到」写成「不存在」。
2. **旧校验只做「包含检查」，能放行残缺稿。** 旧逻辑要求 `chapters.md` 每一句能在 `.txt` 里找到，于是**删掉尾部整段、重复某句、打乱顺序、等长替换几个字**都能通过校验。这不是理论问题：只要切片或拼装少一段，稿子照样会被写盘并交付。
3. **有可用字幕也仍然下载音频、跑几十 MB 模型的语音识别。** B 站有 CC/AI 字幕时，这条路既慢又不必要，术语和专有名词还容易比平台字幕差。
4. **时间戳无效的字幕条目会丢文本或污染时间轴**，而论文式文字稿的拼装没有任何正文覆盖自检——少句也能写文件。

一句话：既然产物是「文字稿」，就需要一条能证明「文字没有丢、没有多、没有被换掉」的校验，以及一套不允许把「没探测到」说成「不存在」的状态语义。

### What：这一版改了什么

**Changed — 默认流水线反过来（不兼容）**

- 先独立执行 `yt-dlp --list-subs` 探测字幕，再决定路线；不再由 `-J` 的 JSON 字幕字段决定。
- `found`：保存字幕原件到 `original-subs/`，直接生成 `chapters.md`，**不下载音频、不跑 CapsWriter**，来源标注 `普通CC` 或 `平台AI`。
- `confirmed_none`：才下载音频并走 CapsWriter，来源标注 `本机ASR`。
- `ffmpeg`、`start_server.exe`、`start_client.exe` 的存在性检查从「启动即检查」移到「确认无可用字幕、真的要跑 ASR 时」才检查——字幕路径不再依赖它们。

**Added — 字幕探测状态机**

- 状态只有五种：`found`、`confirmed_none`、`login_required`、`request_failed`、`filter_no_match`。
- 三种失败状态一律停止：**不写成确认无字幕，也不静默改跑 ASR**。
- 弹幕（`danmaku`）、`live_chat` 不算字幕；只有弹幕时会判为 `confirmed_none` 并记录 `danmaku_ignored`。
- 每次探测写 `subtitle-probe.json`（含 `json_subtitle_field_empty`、`json_field_used_as_verdict`、`tracks`、`chosen`、`part` 等信息）。
- 新增参数 `--sub-lang <lang>`：只接受该语言轨道；有其他轨道却没有这一轨时状态为 `filter_no_match` 并停止。它不是 ASR 开关。

**Added — 全文覆盖校验（替代包含检查）**

- 新增 `coverage_report()`：按条目**原有顺序**做全文对齐，分别报告缺失、增加、重复、乱序、替换、标点改动，并给出 `coverage_ok` / `content_ok`。
- 包含检查降级为对照信息（`containment_would_pass`），**不能再单独放行**。
- 覆盖未通过时以退出码 7 退出，**不写 `chapters.md`**（写入改为 `chapters.md.tmp` 后原子替换）。
- 忠实模式（`--polish off`）下标点改动也算不通过；`--polish basic` 只报标点差异。

**Added — 无效时间戳不丢文本**

- 新增 `parse_srt_document()` 返回 `(cues, unlocated)`：`end < start` 等无效时间条目不再被塞进时间轴，也不会被丢弃，而是单列到 `chapters.md` 的「未定位文本」章，并在 `toc.json` 记 `timeline_ok: false`。
- `parse_srt()` 的返回签名保持不变，已有调用方不受影响。

**Added — 新脚本 `scripts/test_transcript_checks.py`**

- 15 条确定性单元测试，不下载、不写 `work/`，可直接 `python -m unittest test_transcript_checks`：
  - 覆盖对齐 6 条：完全一致、删尾但包含检查仍通过、重复、乱序、等长替换、标点改动只报不误判替换。
  - 探测分类 9 条：JSON 字幕字段为空不作结论、AI 轨道标注、CC 标注、需登录、请求失败、仅有弹幕、空输出、`--sub-lang` 不匹配、无效时间戳保留文本 + `parse_srt` 签名未变。
- `scripts/.gitignore` 的发布白名单补上该脚本（此前只有 `selftest_contract.py` 在名单内）。

**Changed — `toc.json` 契约**

- 新增 `text_source`（`kind` / `lang` / `probe_status`）与 `transcript`（字幕路径绝对值改为相对路径，`.txt` / `.json` 仅 ASR 路径存在）。
- `verify` 字段从 `body_lines / literal_miss / normalized_miss` 改为 `coverage_ok / missing_count / added_count / duplicate_count / reordered / replaced_count / punctuation_count / timeline_ok / containment_is_not_acceptance`。
- 指纹不一致时**行为变更**：以前只打印警告且不改写文件，现在会写入 `stale: true` 标记（仍不自动重跑）。

**Changed — 目录保护语义**

- 以前「目录非空即拒绝」，现在只含 `subtitle-probe.json` / `logs/` 的目录允许直接重试，不必 `--force`；音频、字幕原件、章节稿仍受保护。

**Changed — `chapters.md` 头部**

- 新增 `文字来源`（普通CC / 平台AI / 本机ASR）、`字幕探测` 状态行，以及边界声明：正文与原件一致只说明转换没丢改，**不能证明字幕覆盖整段音频，也不能证明识别准确**。

**Changed — 论文式文字稿**

- `build_paper_transcript.py` 拼装后复用 `coverage_report()` 自检正文覆盖，未覆盖章节原稿时以非零码退出且**不写 `论文式文字稿.md`**。
- `verify_note()` 改读新的覆盖字段；遇到旧 `toc.json`（无 `coverage_ok`）会明确提示「只有旧校验，不能当全文覆盖通过」。

**Changed — 文档**

- `SKILL.md`：description 扩展为播客 + B 站并写入探测状态语义；新增「B 站字幕与文字来源」章（三种来源标注、失败状态不得写成无字幕、不收 Cookie / 不加 `--cookies-from-browser` / 不装下载器 / 不做 OCR、已有通过稿不重复转写）。
- `scripts/PODCAST2MD.md`：流水线改为 6 步（探测 → 有轨道 → 确认无 → 目录 → 切分 → 校验）；输出目录补充 `original-subs/`、`subtitle-probe.json`；新增 `--sub-lang` 行；校验段落改为顺序全文覆盖口径。
- `scripts/README.md`：中文与英文的流水线图、前置依赖同步为「字幕优先」。

### 兼容性与迁移

- **不兼容**：默认行为从「总是下载 + ASR」变为「字幕优先」。依赖旧行为（例如期望每次都拿到 CapsWriter 的 `.txt`/`.json`）的自动化需要显式确认探测结果为 `confirmed_none`，或直接对音频直链调用。
- **旧产物可继续读**：旧 `toc.json` 没有 `coverage_ok` 时，论文稿工具会提示「旧校验不能当全文覆盖通过」，不会假装通过；`mark_stale_toc` 只在指纹不一致时写入 `stale: true`。
- 退出码不变：3 下载失败 / 4 server 失败 / 5 转录失败 / 6 成品已存在或占用 / 7 切分或校验失败。

### 验证

- `python -m unittest test_transcript_checks -v` → **15 tests, OK**（2026-10-25，Python 3.14.6，Windows）。
- 变更规模：`scripts/podcast2md.py` +400 / −86 行；`scripts/build_paper_transcript.py` +28 / −7；`SKILL.md`、`scripts/PODCAST2MD.md`、`scripts/README.md` 文档同步。
- **未验证**：本轮没有跑真实单集下载、平台字幕下载和 CapsWriter 转录（无网络下载夹具），因此「平台字幕实际覆盖率」「AI 字幕质量对比」都没有实测结论，只有状态机与校验逻辑的确定性单测。

---

## v2.1.0 — 2026-10-28

把「核对」从临场动作变成可复用的取证入口，并修掉一个会把「需要登录」误报成「有字幕」的解析缺陷。

### Why：为什么会做这次更新

1. **判据不稳定。** 同一个问题「这集转换对不对」，每次都由 agent 临场换一套写法（这次数条数、下次比 hash、再下次漏掉），结论不可比，也没法回溯。
2. **论文稿脚本跑不到。** `build_paper_transcript.py` 只存在于 skill 仓库，部署目录里没有，要出论文式文字稿得先 cd 到别处。
3. **探测会误报。** B 站未登录时 `yt-dlp --list-subs` 只给 `danmaku`（弹幕）加一行 `WARNING: Subtitles are only available when logged in`；旧解析器把 `WARNING:` 当成语言名，状态被判成 `found`，接着会去下载一个不存在的语言轨道。

### Added

- `probe <url> [--json]`：只探测字幕状态，不下载、不转写、不建单集目录。
- `verify <单集目录> [--json]`：重算全文覆盖与结构（章节数、时间轴、toc 指纹），不改写任何文件。
- `verify-all [--json]`：批量体检输出根目录下所有含 `toc.json` 的单集。
- `--json` 输出固定字段：`ok` / `text_source` / `cues` / `body_lines` / `unlocated` / `chapters_md` / `chapters_toc` / `coverage{...}` / `timeline_ok` / `toc_signature_ok` / `polish_inferred` / `reasons` / `warnings`。
- `--help` 现在列出四个入口；无子命令仍走原有完整流水线。
- `references/feature-map.md`：入口、产物、探测五态、取证命令、已知坑，带「每次踩坑追加一行」的维护规则。

### Fixed

- `parse_list_subs()` 不再把 `WARNING:` / `ERROR:` / `[...]` 日志行当成语言名，并要求行尾是真实字幕格式（`srt`/`vtt`/`ass`/`json3`/`xml` 等）。B 站未登录的输出现已正确判为 `login_required`，而不是 `found`。
- 旧 `toc.json` 缺少 `source_fingerprint` 时告警 `toc_signature_absent`，不再静默当作校验通过。

### Changed

- `build_paper_transcript.py` 与 `podcast2md.py` 一样部署到 CapsWriter 根目录，出论文式文字稿不再需要切换目录。
- `SKILL.md` 新增「核对已有单集」一节，明确「只跑取证入口，不要重跑流水线」。
- `scripts/PODCAST2MD.md` 补中英文子命令说明与字段含义。

### 兼容性

- 主流水线 CLI 未变，参数和退出码保持。
- 新增退出码无变化：`0` 通过 / `2` 用法 / `3` 下载或探测 / `4` 服务端 / `5` 转录 / `6` 成品已存在 / `7` 校验失败。子命令复用同一套退出码。
- 旧单集（无 `text_source` / `source_fingerprint`）仍可通过 `verify`，只是多一条 `toc_signature_absent` 告警。

### 验证

- `python -m unittest test_transcript_checks` → **23 tests OK**（v2.0.0 的 15 条全部保留 + 新增 5 条 verify 子命令 + 3 条真实 B 站 `--list-subs` 回归）。

### 已知局限（2026-10-28 验收暴露）

`verify` 不联网，`scope=local_only`、`web_check=not_verified`。`ok: true` 只意味着**本地硬失败判据未触发**（`reasons` 为空）；
正文按 `coverage` 与 `polish_inferred` 口径判读，章数 / 指纹另外看对应字段与 `warnings`（它们不会翻转 `ok`）。
**它不证明章节与当前网页目录一致**。实例：44 号小宇宙单集。运行时刻（2026-10-26 20:33）从页面 HTML 抽到 15 章；
2026-10-28 网页复核当前页 11 章（本地多出 1680/3151/3508/3719），且 53s 标题 `婉婷`→`Wanting`、909s `千万级`→`亿万级`。
用同一份 `extract_toc_from_html` 解析当前 HTML，能准确得到这 11 章，说明**当前页解析没有问题**；15→11 的原因仍未定
（可能是网页后来更新了目录，也可能是历史处理差异），未找到历史网页快照或日志可判定，因此不归因于抽取器。
尚未做：运行时不归档原始 HTML（两个时刻的 DOM 无法直接出示）；`verify` 不做网页对照（需显式批准后才能加，默认不联网）。
尚未做：运行时不归档原始 HTML（两时刻的 DOM 无法直接出示）；`verify` 不做网页对照（需你批准后才能加，默认不联网）。
- `verify-all` → work 下 6 集全部通过，`ok: true`，退出码 0。
- `verify` 对「非本 CLI 产物」的目录（无 `toc.json`）→ `toc_missing_or_invalid`，退出码 7，不崩溃。
- `probe` 小宇宙（`44 丨对大厂祛魅后`）→ `confirmed_none`，退出码 0，`slug` 与主流水线一致。
- `probe` B 站 `BV1mRn66JERc`（未登录）→ `login_required`，`tracks: 0`，退出码 3。
- **未验证**：未在「真的能拿到平台字幕」的已登录环境跑 `found` 路径；`polish_inferred` 未在真实的 `--polish basic` 单集上验证（目前只用单元测试覆盖）。

---

## v2.2.0 — 2026-11-01

补上「转录历史账本」，并纠正 SKILL.md 里写错的本地音频默认引擎。

### Why：为什么会做这次更新

1. **本地音频走错了引擎。** SKILL.md 的「本地音频」段把 transformers 版 Fun-ASR-Nano 写成默认路径，参考位置写成 `<FunASR目录>\work\full_transcribe.py`——而本机并不存在 `D:\iStall\FunASR\work`：真实脚本与 venv 都在 `FunASR-Nano`，框架仓库 `FunASR` 里两样都没有。照着这段执行会多花 3–4 倍时间，产物质量还更差：同一批 8 分半音频，transformers 版约 5.5 分钟，CapsWriter 冷启动 90 秒、服务端已热 64 秒，且「得到」「橙色」这类热词 transformers 版认不出。
2. **同一段音频做两遍，结果无从对比。** 换引擎、改切片、补热词之后，没有账本说明「哪一集用什么引擎出的、当时校验过没有」，只能翻 `work` 目录逐个数，也没法回答「这版比上版好在哪」。
3. **历史记录容易顺手把敏感参数写进库。** 播客与视频链接常带 `?sig=`、`token=`、`SESSDATA=` 之类查询参数，原样记账等于把凭据落到磁盘上。

### Added

- `history` 子命令：`history`（列出中文历史）、`history list [--query 词]`、`history search <词>`、`history register`、`history backfill [--root 目录]`、`history open`。
- 出稿后自动登记到 `history/ledger.jsonl`，并生成中文清单 `history/转录历史.md`（按时间倒序、可按关键词过滤）。**登记失败不影响出稿**，只打一行告警——账本是旁路，不该成为产物的单点故障。
- URL 查询串中的敏感参数（`sig`/`signature`/`token`/`access_token`/`SESSDATA`/`cookie`/`auth`/`password`/`secret`/`hmac`/`credential`/`x-amz-*` 等）在记账前脱敏。
- `scripts/test_history.py`：历史账本的确定性检查，只用临时目录，不写真实 `history`、不碰 `work` 原稿。

### Fixed

- `SKILL.md`「本地音频」段：默认引擎改为 **CapsWriter**（`start_server.exe` + `start_client.exe`，复用 `podcast2md.ensure_server` / `run_client`），并写明两者实测耗时；transformers 版降为 CapsWriter 不可用时的后备，同时纠正 `FunASR` 与 `FunASR-Nano` 的路径混淆。
- `references/feature-map.md`「坑（追加区）」追加四条：默认引擎选择、`FunASR` 与 `FunASR-Nano` 目录混淆、CapsWriter 会整句重复与跨句拼接漏句、本地音频复用入口 `work\_local_transcribe.py`。

### 同步

本次一并推送此前只存在于本地的 v2.1.0 内容：`probe` / `verify` / `verify-all` 三个只读取证入口、全文覆盖校验、`references/feature-map.md`，以及 `evals/evals.json`。

### 验证

- `python -m unittest test_transcript_checks test_history` → **35 tests OK**（v2.1.0 的 23 条 + 历史账本 12 条）。
- 引擎对照实测（2026-10-31，两段 8 分半音频）：CapsWriter 冷启动 90 秒出稿、服务端已热 64 秒；同内容 transformers 版约 5.5 分钟。

### 已知局限

- 账本只记「谁出的稿、当时状态」，不记录音频指纹，无法证明某一集后来有没有被重新转录过。
- `history register` 允许手工补登，因此账本可被人工改写；它是工作记录，不是审计日志。

## 历史（重建）

以下版本号是按提交时间归并的说明性编号，仓库当时没有 tag。

### v1.2.0 — 2026-10-24

- 失败前置：`ffmpeg` 缺失在下载和拉起服务端之前就以退出码 2 停止；无效转录不落盘。
- `--transcribe-timeout` 默认改为按音频时长计算（`max(600, 时长×4+120)`，取不到时长用 7200），显式传入不被覆盖。
- 拒绝截断转录与乱序 token；`toc.json` 指纹不一致的检查改为只读，不自动重跑。

### v1.1.0 — 2026-10-24

- 安装流程可执行化：新增可复制的 `winget` 命令与 Agent 单段安装脚本，占位符不得原样执行。
- CapsWriter 路径显式化（`CAPSWRITER_HOME`），未设置时给出可运行的命令而不是 `/podcast2md.py`。
- 交付与安全另存规则：默认集中存放，明确要求时才复制最终论文或摘要，不静默覆盖同名文件。

### v1.0.0 — 2026-10-20

- 首次发布：podcast2md skill（`SKILL.md` + `references/`）与 CLI 源码 `scripts/podcast2md.py`、双语说明 `scripts/README.md` / `scripts/PODCAST2MD.md`。
