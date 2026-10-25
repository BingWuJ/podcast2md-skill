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


if __name__ == "__main__":
    unittest.main()
