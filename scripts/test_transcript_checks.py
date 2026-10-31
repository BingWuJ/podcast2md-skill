# -*- coding: utf-8 -*-
"""字幕状态与全文覆盖的确定性检查。不下载、不写 work。"""
import unittest

import podcast2md as p


def listed(lang, automatic=False):
    title = "automatic captions" if automatic else "subtitles"
    return f"[info] Available {title} for BV1:\nLanguage Name Formats\n{lang} unknown srt\n"


class CoverageTests(unittest.TestCase):
    def test_exact_match(self):
        report = p.coverage_report(["甲", "乙", "丙", "丁"], ["甲", "乙", "丙", "丁"])
        self.assertTrue(report["ok"])
        self.assertTrue(report["content_ok"])

    def test_deleted_tail_fails_even_if_containment_passes(self):
        report = p.coverage_report(["甲", "乙", "丙", "丁"], ["甲", "乙"])
        self.assertFalse(report["ok"])
        self.assertEqual(report["missing_count"], 2)
        self.assertTrue(report["containment_would_pass"])

    def test_duplicate_fails(self):
        report = p.coverage_report(["甲", "乙"], ["甲", "乙", "乙"])
        self.assertFalse(report["ok"])
        self.assertGreater(report["duplicate_count"], 0)

    def test_reorder_fails(self):
        report = p.coverage_report(["甲", "乙", "丙"], ["甲", "丙", "乙"])
        self.assertFalse(report["ok"])
        self.assertTrue(report["reordered"])

    def test_equal_length_replace_fails(self):
        report = p.coverage_report(["甲乙丙丁"], ["甲乙戊己"])
        self.assertFalse(report["ok"])
        self.assertGreater(report["replaced_count"], 0)

    def test_punctuation_is_recorded_and_blocks_faithful_mode(self):
        report = p.coverage_report(["甲乙。"], ["甲乙"])
        self.assertFalse(report["ok"])
        self.assertTrue(report["content_ok"])
        self.assertGreater(report["punctuation_count"], 0)
        self.assertEqual(report["replaced_count"], 0)


class ProbeTests(unittest.TestCase):
    def test_empty_json_does_not_decide(self):
        probe = p.classify_subtitle_probe(listed("zh-Hans"), "", 0, [])
        self.assertEqual(probe["status"], "found")
        self.assertTrue(probe["json_subtitle_field_empty"])
        self.assertFalse(probe["json_field_used_as_verdict"])
        self.assertEqual(probe["chosen"]["lang"], "zh-Hans")

    def test_automatic_track_is_ai(self):
        probe = p.classify_subtitle_probe(listed("zh", automatic=True), "", 0, [])
        self.assertTrue(probe["chosen"]["automatic"])
        self.assertEqual(p.source_label("平台AI", probe["chosen"]["lang"]), "平台AI（zh）")

    def test_manual_track_is_cc(self):
        self.assertEqual(p.source_label("普通CC", "zh-Hans"), "普通CC（zh-Hans）")

    def test_login_is_not_confirmed_none(self):
        text = "WARNING: Subtitles are only available when logged in.\nBV1 has no subtitles\n"
        probe = p.classify_subtitle_probe("", text, 0, [])
        self.assertEqual(probe["status"], "login_required")

    def test_request_failure_is_not_confirmed_none(self):
        probe = p.classify_subtitle_probe("", "ERROR: HTTP Error 412", 1, [])
        self.assertEqual(probe["status"], "request_failed")

    def test_only_danmaku_is_confirmed_none(self):
        probe = p.classify_subtitle_probe(listed("danmaku"), "BV1 has no automatic captions\n", 0, ["danmaku"])
        self.assertEqual(probe["status"], "confirmed_none")
        self.assertTrue(probe["danmaku_ignored"])

    def test_empty_output_is_not_confirmed_none(self):
        probe = p.classify_subtitle_probe("", "", 0, [])
        self.assertEqual(probe["status"], "request_failed")

    def test_filter_no_match_is_not_confirmed_none(self):
        probe = p.classify_subtitle_probe(listed("en"), "", 0, [], requested_lang="zh-Hans")
        self.assertEqual(probe["status"], "filter_no_match")

    def test_parse_srt_signature_unchanged_and_invalid_time_kept(self):
        self.assertIn("list", str(p.parse_srt.__annotations__["return"]))
        cues, unlocated = p.parse_srt_document(
            "1\n00:00:02,000 --> 00:00:01,000\n丢失会错\n\n2\n00:00:03,000 --> 00:00:04,000\n保留\n")
        self.assertEqual([cue["text"] for cue in cues], ["保留"])
        self.assertEqual(unlocated, ["丢失会错"])


class VerifySubcommandTests(unittest.TestCase):
    """verify 子命令自己也要有测试，否则它就是下一个“包含检查”。"""

    def make_episode(self, tmp, drop_tail=False, with_toc=True, name="ep"):
        import json, pathlib
        ep = pathlib.Path(tmp) / name
        ep.mkdir(parents=True, exist_ok=True)
        srt = (
            "1\n00:00:01,000 --> 00:00:02,000\n甲\n\n"
            "2\n00:00:03,000 --> 00:00:04,000\n乙\n"
        )
        srt_path = ep / "ep.srt"
        srt_path.write_text(srt, encoding="utf-8")
        body = "甲\n" if drop_tail else "甲\n乙\n"
        (ep / "chapters.md").write_text(
            f"# 测试\n\n## 0:00:00 全文\n\n{body}", encoding="utf-8")
        if with_toc:
            fingerprint, size = p.srt_fingerprint(srt_path)
            (ep / "toc.json").write_text(json.dumps({
                "slug": "ep",
                "chapters": [{"start": 0, "title": "全文"}],
                "text_source": {"kind": "本机ASR", "lang": None, "probe_status": "confirmed_none"},
                "source_fingerprint": fingerprint,
                "srt_bytes": size,
            }, ensure_ascii=False), encoding="utf-8")
        return ep

    def test_complete_episode_passes(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            ep = self.make_episode(tmp)
            r = p.verify_episode(ep)
            self.assertTrue(r["ok"], r)
            self.assertEqual(r["coverage"]["missing"], 0)
            self.assertEqual(r["cues"], 2)
            self.assertEqual(r["body_lines"], 2)
            self.assertTrue(r["toc_signature_ok"])

    def test_dropped_tail_fails(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            ep = self.make_episode(tmp, drop_tail=True)
            r = p.verify_episode(ep)
            self.assertFalse(r["ok"])
            self.assertIn("coverage_failed", r["reasons"])
            # 旧口径（包含检查）会放行，正是要拦的东西
            self.assertTrue(r["coverage"]["containment_would_pass"])

    def test_missing_toc_is_reported_not_crashed(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            ep = self.make_episode(tmp, with_toc=False)
            r = p.verify_episode(ep)
            self.assertFalse(r["ok"])
            self.assertIn("toc_missing_or_invalid", r["reasons"])

    def test_missing_dir_is_reported(self):
        import pathlib, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            r = p.verify_episode(pathlib.Path(tmp) / "does-not-exist")
            self.assertFalse(r["ok"])
            self.assertIn("episode_dir_missing", r["reasons"])

    def test_verify_cli_exit_codes_and_json(self):
        import contextlib, io, json, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            ok_dir = self.make_episode(tmp)
            bad_dir = self.make_episode(tmp, drop_tail=True, name="ep-bad")

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code_ok = p.cli(["verify", str(ok_dir), "--json"])
            payload = json.loads(buf.getvalue())
            self.assertEqual(code_ok, p.EX_OK)
            self.assertTrue(payload["ok"])
            self.assertIsInstance(payload["episode"], str)

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code_bad = p.cli(["verify", str(bad_dir), "--json"])
            payload = json.loads(buf.getvalue())
            self.assertEqual(code_bad, p.EX_SPLIT)
            self.assertFalse(payload["ok"])


class ListSubsParserTests(unittest.TestCase):
    """真实 B 站输出回归：没登录时只有弹幕轨 + 一行 WARNING，不能被当成 found。"""

    BILI_LOGIN_REQUIRED = (
        "[BiliBili] Extracting URL: https://www.bilibili.com/video/BV1mRn66JERc/\n"
        "[info] Available subtitles for BV1mRn66JERc:\n"
        "Language Formats\n"
        "danmaku  xml\n"
        "\n"
        "WARNING: [BiliBili] Subtitles are only available when logged in. "
        "Use --cookies-from-browser or --cookies for the authentication.\n"
    )

    def test_warning_line_is_not_a_track(self):
        tracks = p.parse_list_subs(self.BILI_LOGIN_REQUIRED)
        self.assertEqual([t["lang"] for t in tracks], ["danmaku"])

    def test_login_required_wins_over_danmaku(self):
        probe = p.classify_subtitle_probe(self.BILI_LOGIN_REQUIRED, "", 0, [])
        self.assertEqual(probe["status"], "login_required")
        self.assertNotIn("chosen", probe)

    def test_normal_track_still_parsed(self):
        text = ("[info] Available subtitles for X:\nLanguage Formats\nzh-Hans  srt\nen  vtt\n")
        tracks = p.parse_list_subs(text)
        self.assertEqual([t["lang"] for t in tracks], ["zh-Hans", "en"])
        self.assertFalse(tracks[0]["automatic"])


if __name__ == "__main__":
    unittest.main()
