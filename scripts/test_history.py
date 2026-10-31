# -*- coding: utf-8 -*-
"""历史账本的确定性检查。只用临时目录，不写真实 history，不碰 work 原稿。"""
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import podcast2md as p


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="podcast2md-history-")
        self.root = Path(self.tmp.name)
        self.hist = self.root / "history"
        self.old = os.environ.get("PODCAST2MD_HISTORY")
        os.environ["PODCAST2MD_HISTORY"] = str(self.hist)

    def tearDown(self):
        if self.old is None:
            os.environ.pop("PODCAST2MD_HISTORY", None)
        else:
            os.environ["PODCAST2MD_HISTORY"] = self.old
        self.tmp.cleanup()

    def test_sanitize_strips_secret_query(self):
        raw = "https://user:pw@example.invalid/e?id=1&token=abc&signature=zzz#frag"
        out = p.sanitize_source(raw)
        self.assertEqual(out, "https://example.invalid/e?id=1")
        self.assertNotIn("token", out)
        self.assertNotIn("user", out)

    def test_local_success_then_fail_keeps_one_row_and_old_final(self):
        wav = self.root / "audio.wav"
        wav.write_bytes(b"x")
        final = self.root / "final.md"
        final.write_text("稿\n", encoding="utf-8")
        p.history_remember(source=str(wav), final_path=final, latest_status="completed",
                           title="同一输入", processed_at="2026-01-01 00:00:00")
        p.history_remember(source=str(wav), latest_status="failed", last_error="boom",
                           processed_at="2026-02-01 00:00:00")
        rows = p.load_history_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["latest_status"], "failed")
        self.assertEqual(Path(rows[0]["final_path"]).resolve(), final.resolve())
        self.assertEqual(p.display_history_status(rows[0]), "有旧稿，最近一次失败")

    def test_two_local_sources_not_merged(self):
        shang_src = self.root / "shang.wav"
        xia_src = self.root / "xia.wav"
        shang = self.root / "shang.md"
        xia = self.root / "xia.md"
        for path in (shang_src, xia_src, shang, xia):
            path.write_text("x", encoding="utf-8")
        p.history_remember(source=str(shang_src), final_path=shang, latest_status="completed", title="上")
        p.history_remember(source=str(xia_src), final_path=xia, latest_status="completed", title="下")
        rows = p.load_history_rows()
        self.assertEqual(len(rows), 2)

    def test_missing_final_is_not_completed(self):
        row = {
            "final_path": str(self.root / "gone.md"),
            "latest_status": "completed",
            "verification": "unverified",
        }
        self.assertEqual(p.display_history_status(row), "最终稿缺失")

    def test_manual_register_without_time_is_unknown(self):
        final = self.root / "old.md"
        final.write_text("旧稿\n", encoding="utf-8")
        src = str(self.root / "old.wav")
        code = p.cmd_history(["register", "--title", "旧稿", "--source", src, "--final", str(final)])
        self.assertEqual(code, 0)
        row = p.load_history_rows()[0]
        self.assertEqual(row["processed_at"], "")
        self.assertIn("未知", p.display_history_time(row))

    def test_unknown_time_sorts_last(self):
        p.write_history_catalog([
            {"title": "KNOWN", "processed_at": "2026-01-01 00:00:00", "source": "", "final_path": ""},
            {"title": "UNKNOWN", "processed_at": "", "source": "", "final_path": ""},
        ])
        text = (p.history_dir() / p.HISTORY_CATALOG).read_text(encoding="utf-8")
        self.assertLess(text.find("KNOWN"), text.find("UNKNOWN"))

    def test_explicit_register_write_failure_nonzero_no_ok_text(self):
        final = self.root / "ok.md"
        final.write_text("x", encoding="utf-8")
        original = p.save_history_rows

        def denied(_rows):
            raise PermissionError("synthetic deny")

        p.save_history_rows = denied
        buf = io.StringIO()
        err = io.StringIO()
        try:
            with redirect_stdout(buf), redirect_stderr(err):
                with self.assertRaises(p.PodError) as ctx:
                    p.cmd_history(["register", "--source", str(self.root / "a.wav"),
                                   "--final", str(final)])
            self.assertEqual(ctx.exception.code, p.EX_SPLIT)
            self.assertNotIn("已登记", buf.getvalue())
        finally:
            p.save_history_rows = original

    def test_auto_remember_failure_does_not_raise(self):
        original = p.save_history_rows

        def denied(_rows):
            raise PermissionError("synthetic deny")

        p.save_history_rows = denied
        try:
            row = p.history_remember(source="https://example.invalid/e", latest_status="completed",
                                     strict=False)
            self.assertIsNone(row)
        finally:
            p.save_history_rows = original

    def test_backfill_does_not_overwrite_failed_status(self):
        episode = self.root / "episode"
        episode.mkdir()
        chapters = episode / "chapters.md"
        chapters.write_text("# t\n\n> 来源：https://example.invalid/e\n\n正文\n", encoding="utf-8")
        (episode / "toc.json").write_text(
            '{"url":"https://example.invalid/e","title":"E","slug":"episode","source":"none","chapters":[]}',
            encoding="utf-8")
        p.history_remember(
            source="https://example.invalid/e", source_kind="url", final_path=chapters,
            latest_status="completed", processed_at="2026-01-01 00:00:00", title="E")
        p.history_remember(
            source="https://example.invalid/e", source_kind="url", latest_status="failed",
            processed_at="2026-02-01 00:00:00", last_error="asr")
        result = p._backfill_episode(episode)
        self.assertIn(result, {"kept", "filled"})
        row = p.load_history_rows()[0]
        self.assertEqual(row["latest_status"], "failed")
        self.assertEqual(row["processed_at"], "2026-02-01 00:00:00")
        self.assertEqual(p.display_history_status(row), "有旧稿，最近一次失败")

    def test_backfill_write_failure_nonzero(self):
        episode = self.root / "episode2"
        episode.mkdir()
        (episode / "chapters.md").write_text("# t\n\n正文\n", encoding="utf-8")
        blocked = self.root / "blocked-history"
        blocked.write_text("not-a-dir", encoding="utf-8")
        os.environ["PODCAST2MD_HISTORY"] = str(blocked)
        with self.assertRaises(p.PodError) as ctx:
            p.cmd_history(["backfill", "--root", str(self.root)])
        self.assertNotEqual(ctx.exception.code, 0)
        self.assertNotEqual(ctx.exception.code, p.EX_OK)

    def test_short_input_canonical_retry_failure_one_row(self):
        final = self.root / "zoo.md"
        final.write_text("稿\n", encoding="utf-8")
        p.history_remember(
            source="https://www.youtube.com/watch?v=jNQXAC9IVRw",
            source_input="https://youtu.be/jNQXAC9IVRw",
            source_kind="url",
            final_path=final,
            latest_status="completed",
            processed_at="2026-01-01 00:00:00",
            title="zoo",
        )
        p.history_remember(
            source="https://youtu.be/jNQXAC9IVRw",
            source_kind="url",
            latest_status="failed",
            processed_at="2026-02-01 00:00:00",
            last_error="失败 https://cdn.example.invalid/a?token=secret&signature=zzz",
            title="https://cdn.example.invalid/a?token=secret",
        )
        rows = p.load_history_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["latest_status"], "failed")
        self.assertTrue(Path(rows[0]["final_path"]).exists())
        self.assertEqual(p.display_history_status(rows[0]), "有旧稿，最近一次失败")
        blob = json.dumps(rows[0], ensure_ascii=False)
        self.assertNotIn("token=secret", blob)
        self.assertNotIn("signature=zzz", blob)
        episode = self.root / "zoo-ep"
        episode.mkdir()
        chapters = episode / "chapters.md"
        chapters.write_text("# zoo\n", encoding="utf-8")
        (episode / "toc.json").write_text(
            '{"url":"https://www.youtube.com/watch?v=jNQXAC9IVRw","title":"zoo","source":"none","chapters":[]}',
            encoding="utf-8")
        p._backfill_episode(episode)
        rows = p.load_history_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["latest_status"], "failed")

    def test_cli_relative_final_survives_cwd_change(self):
        episode = self.root / "rel-ep"
        episode.mkdir()
        (episode / "a.m4a").write_bytes(b"x")
        (episode / "t.md").write_text("稿\n", encoding="utf-8")
        script = Path(p.__file__).resolve()
        env = os.environ.copy()
        env["PODCAST2MD_HISTORY"] = str(self.hist)
        proc = subprocess.run(
            [sys.executable, "-B", str(script), "history", "register",
             "--title", "rel", "--source", "a.m4a", "--final", "t.md", "--inferred"],
            cwd=str(episode), env=env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        other = self.root / "other"
        other.mkdir()
        here = os.getcwd()
        try:
            os.chdir(other)
            rows = p.load_history_rows()
            self.assertEqual(len(rows), 1)
            self.assertTrue(Path(rows[0]["final_path"]).is_absolute())
            self.assertTrue(Path(rows[0]["final_path"]).exists())
            self.assertTrue(Path(rows[0]["source"]).is_absolute())
            self.assertTrue(Path(rows[0]["source"]).exists())
        finally:
            os.chdir(here)


if __name__ == "__main__":
    unittest.main()
