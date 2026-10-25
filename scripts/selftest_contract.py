"""契约校验的合成反例。不读取、不写回 work 目录。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import podcast2md as cli


def expect_pass(name, fn):
    fn()
    print(f"PASS {name}")


def expect_transcribe_error(name, fn, needle):
    try:
        fn()
    except cli.PodError as exc:
        if exc.code != cli.EX_TRANSCRIBE or needle not in str(exc):
            raise SystemExit(f"FAIL {name}: {exc.code} {exc}")
        print(f"PASS {name}")
        return
    raise SystemExit(f"FAIL {name}: no error")


def test_normal():
    text = "你好，世界。今天测试。"
    cues = [{"text": "你好，世界。"}, {"text": "今天测试。"}]
    result = cli.require_srt_txt_contract(cues, text)
    if not result["ok"] or result["ratio"] != 1:
        raise SystemExit(f"normal ratio {result}")


def test_truncated_srt():
    text = "你好世界今天这是一段足够长的完整测试文本用于发现截断"
    cues = [{"text": "你好世界"}]

    def run():
        cli.require_srt_txt_contract(cues, text)

    expect_transcribe_error("srt-truncated", run, "比值")


def test_tokens_count_mismatch(tmp):
    path = tmp / "bad-count.json"
    path.write_text('{"tokens":["你","好"],"timestamps":[1]}', encoding="utf-8")

    def run():
        cli.require_json_tokens(path, "你好")

    expect_transcribe_error("tokens-count", run, "timestamps")


def test_tokens_reordered(tmp):
    path = tmp / "reordered.json"
    path.write_text('{"tokens":["界","世","好","你"],"timestamps":[1,2,3,4]}', encoding="utf-8")

    def run():
        cli.require_json_tokens(path, "你好世界")

    expect_transcribe_error("tokens-reordered", run, "首个缺失位置")


def test_tokens_short(tmp):
    path = tmp / "short-tokens.json"
    path.write_text('{"tokens":["你"],"timestamps":[1]}', encoding="utf-8")

    def run():
        cli.require_json_tokens(path, "你好世界这是一段完整文本")

    expect_transcribe_error("tokens-short", run, "比值")


def test_tokens_field_absent(tmp):
    path = tmp / "no-tokens.json"
    path.write_text('{"timestamps":[1,2]}', encoding="utf-8")
    if cli.check_json_tokens(path, "你好") is not None:
        raise SystemExit("missing tokens field should be skipped")
    print("PASS tokens-field-absent")


def test_timeout_respects_explicit():
    if cli.compute_transcribe_timeout(100, 15) != 15:
        raise SystemExit("explicit timeout was overridden")
    if cli.compute_transcribe_timeout(None, None) != 7200:
        raise SystemExit("missing duration did not fall back to 7200")
    if cli.compute_transcribe_timeout(0, None) != 7200:
        raise SystemExit("zero duration did not fall back to 7200")
    if cli.compute_transcribe_timeout(30, None) != 600:
        raise SystemExit("short audio budget should be at least 600")
    if cli.compute_transcribe_timeout(300, None) != 1320:
        raise SystemExit("300s audio budget should be 1320")
    print("PASS timeout-budget")


def check_real_work_samples():
    """只读核对现有成品。目录不存在就跳过，不锁定样本数量。"""
    root = Path(r"D:\iStall\CapsWriter-Offline\work")
    if not root.exists():
        print(f"SKIP real samples: {root} 不存在")
        return
    rows = []
    for srt in sorted(root.rglob("*.srt")):
        txt = srt.with_suffix(".txt")
        js = srt.with_suffix(".json")
        if not txt.exists() or not js.exists():
            continue
        data = json.loads(js.read_text(encoding="utf-8"))
        if "tokens" not in data:
            continue
        cues = cli.parse_srt(srt)
        text = txt.read_text(encoding="utf-8")
        srt_result = cli.require_srt_txt_contract(cues, text)
        cli.require_json_tokens(js, text)
        rows.append((srt.parent.name, srt_result["ratio"]))
    if not rows:
        print("SKIP real samples: 没有同时具备 srt、txt 和 tokens 的样本")
        return
    for name, ratio in rows:
        print(f"PASS real {name} ratio={ratio}")


def main():
    import tempfile
    expect_pass("srt-normal", test_normal)
    test_truncated_srt()
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        test_tokens_count_mismatch(tmp)
        test_tokens_short(tmp)
        test_tokens_reordered(tmp)
        test_tokens_field_absent(tmp)
    test_timeout_respects_explicit()
    check_real_work_samples()
    print("SELFTEST_OK")


if __name__ == "__main__":
    main()
