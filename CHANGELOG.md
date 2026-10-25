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
