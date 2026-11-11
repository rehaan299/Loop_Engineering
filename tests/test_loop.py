"""Tests for the loop CLI. Run: python3 -m unittest discover -s tests -v"""
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "loop-engineering" / "scripts"))
import loop  # noqa: E402


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True).stdout.strip()


class LoopTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
        os.environ["NO_COLOR"] = "1"
        git(self.root, "init", "-q")
        git(self.root, "config", "user.email", "t@example.com")
        git(self.root, "config", "user.name", "Test")
        (self.root / "src").mkdir()
        (self.root / "src" / "app.py").write_text("print('hi')\n")
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "initial")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *argv: str, stdin: str = None) -> tuple:
        buf = io.StringIO()
        old_stdin = sys.stdin
        if stdin is not None:
            sys.stdin = io.StringIO(stdin)
        try:
            with redirect_stdout(buf):
                code = loop.main(["--root", str(self.root), *argv])
        finally:
            sys.stdin = old_stdin
        return code, buf.getvalue()

    @property
    def d(self) -> Path:
        return self.root / "docs" / "loop"

    def fill_minimal(self):
        """Replace scaffolds with small, valid content."""
        self.run_cli("init")
        for p in self.d.glob("*.md"):
            if p.name != "PROTOCOL.md":
                p.write_text(p.read_text().replace(loop.UNFILLED + "\n", ""))
        (self.d / "decisions.md").write_text("# decisions.md\n\n### D-001: Use SQLite\n\nStatus: ACTIVE\n")
        (self.d / "traps.md").write_text("# traps.md\n\n### TRAP-001: Tests need TZ=UTC\n\nStatus: ACTIVE\n")
        (self.d / "next-steps.md").write_text(
            "# next-steps.md\n\n## START HERE\n\nT-001: Add login. See D-001, watch TRAP-001.\n\n## Queue\n\n### T-001: Add login\n")
        (self.d / "codebase-map.md").write_text("# codebase-map.md\n\n## Tree\n\n- `src/app.py`: entry\n\n### F-01: Startup\n")


class TestInit(LoopTestCase):
    def test_init_scaffolds_everything(self):
        code, out = self.run_cli("init", "--local", "--claude")
        self.assertEqual(code, 0)
        for fname, _ in loop.FILES:
            self.assertTrue((self.d / fname).exists(), fname)
        self.assertTrue((self.d / "loop.json").exists())
        self.assertTrue((self.d / "PROTOCOL.md").exists())
        self.assertIn("loop-engineering:start", (self.root / "AGENTS.md").read_text())
        self.assertIn("@AGENTS.md", (self.root / "CLAUDE.md").read_text())
        self.assertIn("docs/loop/", (self.root / ".gitignore").read_text())

    def test_init_is_idempotent_and_never_overwrites(self):
        self.run_cli("init")
        (self.d / "BOOT.md").write_text("custom boot\n")
        (self.root / "AGENTS.md").write_text((self.root / "AGENTS.md").read_text() + "\nTeam rule.\n")
        self.run_cli("init", "--local")
        self.run_cli("init", "--local")
        self.assertEqual((self.d / "BOOT.md").read_text(), "custom boot\n")
        agents = (self.root / "AGENTS.md").read_text()
        self.assertEqual(agents.count("loop-engineering:start"), 1)
        self.assertIn("Team rule.", agents)
        self.assertEqual((self.root / ".gitignore").read_text().count("docs/loop/"), 1)

    def test_existing_claude_md_gets_import(self):
        (self.root / "CLAUDE.md").write_text("# House rules\n")
        self.run_cli("init")
        text = (self.root / "CLAUDE.md").read_text()
        self.assertTrue(text.startswith("@AGENTS.md"))
        self.assertIn("# House rules", text)


class TestCheck(LoopTestCase):
    def test_scaffold_has_warnings_but_no_errors(self):
        self.run_cli("init")
        errors, warnings, _ = loop.run_checks(self.root)
        self.assertEqual(errors, [])
        self.assertTrue(any("scaffold" in w for w in warnings))

    def test_valid_install_passes(self):
        self.fill_minimal()
        code, out = self.run_cli("check")
        self.assertEqual(code, 0, out)

    def test_dangling_and_duplicate_ids(self):
        self.fill_minimal()
        with open(self.d / "BOOT.md", "a") as f:
            f.write("\n- D-099: does not exist\n")
        with open(self.d / "decisions.md", "a") as f:
            f.write("\n### D-001: Duplicate\n")
        errors, _, _ = loop.run_checks(self.root)
        self.assertTrue(any("D-099" in e and "never defined" in e for e in errors), errors)
        self.assertTrue(any("D-001 defined 2 times" in e for e in errors), errors)

    def test_boot_budget(self):
        self.fill_minimal()
        (self.d / "BOOT.md").write_text("x" * (loop.BOOT_BUDGET + 1))
        code, out = self.run_cli("check")
        self.assertEqual(code, 1)
        self.assertIn("over the", out)

    def test_secret_detection(self):
        self.fill_minimal()
        fake = "ghp_" + "a1B2" * 9
        with open(self.d / "progress.md", "a") as f:
            f.write(f"\nGITHUB_TOKEN={fake}\n")
        errors, _, _ = loop.run_checks(self.root)
        self.assertTrue(any("GitHub token" in e for e in errors), errors)

    def test_stale_map_path_warning(self):
        self.fill_minimal()
        with open(self.d / "codebase-map.md", "a") as f:
            f.write("\n- `src/removed.py`: gone\n- `src/app.py:main`: still here\n")
        _, warnings, _ = loop.run_checks(self.root)
        joined = " ".join(warnings)
        self.assertIn("src/removed.py", joined)
        self.assertNotIn("src/app.py", joined)

    def test_strict_fails_on_warnings(self):
        self.run_cli("init")
        code, _ = self.run_cli("check", "--strict")
        self.assertEqual(code, 1)


class TestIdsAndStamp(LoopTestCase):
    def test_next_id(self):
        self.fill_minimal()
        self.assertEqual(loop.next_id(self.root, "D"), "D-002")
        self.assertEqual(loop.next_id(self.root, "trap"), "TRAP-002")
        self.assertEqual(loop.next_id(self.root, "F"), "F-02")
        self.assertEqual(loop.next_id(self.root, "Q"), "Q-001")

    def test_stamp_and_drift(self):
        self.fill_minimal()
        code, out = self.run_cli("stamp", "--agent", "test-model")
        self.assertEqual(code, 0)
        state = json.loads((self.d / "loop.json").read_text())
        self.assertEqual(state["session"], 1)
        self.assertEqual(state["agent"], "test-model")
        self.assertEqual(state["git_anchor"], git(self.root, "rev-parse", "--short", "HEAD"))

        (self.root / "src" / "new.py").write_text("x = 1\n")
        git(self.root, "add", "src/new.py")
        git(self.root, "commit", "-qm", "teammate change")
        dr = loop.drift(self.root, state["git_anchor"])
        self.assertEqual(len(dr["commits"]), 1)
        self.assertIn("teammate change", loop.drift_text(dr))


class TestStartHere(LoopTestCase):
    def test_start_here_extracts_task_and_handles_empty(self):
        self.fill_minimal()
        self.assertIn("T-001: Add login", loop.start_here(self.root))
        (self.d / "next-steps.md").write_text("# n\n\n## START HERE\n\n## Queue\n")
        self.assertEqual(loop.start_here(self.root), "(empty)")


class TestBootAndHook(LoopTestCase):
    def test_boot_prints_drift(self):
        self.fill_minimal()
        self.run_cli("stamp")
        code, out = self.run_cli("boot")
        self.assertEqual(code, 0)
        self.assertIn("# BOOT:", out)
        self.assertIn("Drift: none", out)

    def test_hook_emits_valid_json_within_cap(self):
        self.fill_minimal()
        (self.d / "BOOT.md").write_text("# BOOT\n" + "y" * 20000)
        code, out = self.run_cli("hook", "session-start", stdin=json.dumps({"source": "compact"}))
        self.assertEqual(code, 0)
        data = json.loads(out)
        ctx = data["hookSpecificOutput"]["additionalContext"]
        self.assertEqual(data["hookSpecificOutput"]["hookEventName"], "SessionStart")
        self.assertLessEqual(len(ctx), 10000)
        self.assertIn("session start: compact", ctx)
        self.assertIn("truncated", ctx)

    def test_hook_silent_when_not_installed(self):
        code, out = self.run_cli("hook", "session-start", stdin="{}")
        self.assertEqual(code, 0)
        self.assertEqual(out, "")


class TestMigrate(LoopTestCase):
    def test_v3_migration(self):
        self.d.mkdir(parents=True)
        for name in ("prompt.md", "progress.md", "codebase-map.md", "decisions.md",
                     "next-steps.md", "how-it-works.md"):
            (self.d / name).write_text(f"# {name}\n")
        (self.d / "system-design.md").write_text("| # | Date |\n| 1 | x |\n| 4 | y |\n")
        code, out = self.run_cli("migrate")
        self.assertEqual(code, 0)
        self.assertTrue((self.d / "BOOT.md").exists())
        self.assertTrue((self.d / "traps.md").exists())
        state = json.loads((self.d / "loop.json").read_text())
        self.assertEqual(state["session"], 4)
        self.assertTrue((self.d / "prompt.md").exists(), "migration must not delete prompt.md")


class TestProtocolSync(unittest.TestCase):
    def test_root_copy_matches_skill_protocol(self):
        root_copy = (ROOT / "LOOP_ENGINEERING.md").read_text(encoding="utf-8")
        skill_copy = (ROOT / "skills" / "loop-engineering" / "PROTOCOL.md").read_text(encoding="utf-8")
        self.assertEqual(root_copy, skill_copy, "LOOP_ENGINEERING.md must be an exact copy of skills/loop-engineering/PROTOCOL.md")

    def test_no_em_dashes_in_protocol(self):
        text = (ROOT / "skills" / "loop-engineering" / "PROTOCOL.md").read_text(encoding="utf-8")
        self.assertNotIn("\u2014", text)


if __name__ == "__main__":
    unittest.main()
