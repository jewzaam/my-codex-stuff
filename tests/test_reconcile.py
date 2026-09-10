import json
import tempfile
import tomllib
import unittest
from pathlib import Path

from scripts import reconcile
from scripts.reconcile import reconcile_file


class ReconcileTests(unittest.TestCase):
    def test_merge_preserves_local_tables(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.toml"
            destination = root / "destination.toml"
            source.write_text('[features]\nfoo = true\n')
            destination.write_text(
                '[projects."/machine-only"]\ntrust_level = "trusted"\n'
                '\n[features]\nfoo = false\nbar = "local"\n'
            )

            reconcile_file(source, destination)

            result = destination.read_text()
            self.assertIn('[projects."/machine-only"]', result)
            self.assertIn('foo = true', result)
            self.assertIn('bar = "local"', result)

    def test_merge_repairs_multiline_inline_tables(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.toml"
            destination = root / "destination.toml"
            source.write_text('[features]\nfoo = true\n')
            destination.write_text(
                '[otel]\nexporter = { otlp-grpc = {\n'
                '  endpoint = "http://localhost:4317"\n} }\n'
            )

            reconcile_file(source, destination)

            self.assertEqual(
                "http://localhost:4317",
                tomllib.loads(destination.read_text())["otel"]["exporter"][
                    "otlp-grpc"
                ]["endpoint"],
            )


if __name__ == "__main__":
    unittest.main()


class SkillHookTests(unittest.TestCase):
    """Skills ship their own Codex hook registration; reconcile collects it.

    Copying it into codex/hooks.json would make this repo a second source of
    truth that drifts the moment the skill changes its events or its path.
    """

    def _skill(self, claude_dir, name, fragment):
        hooks = claude_dir / "skills" / name / "hooks"
        hooks.mkdir(parents=True)
        (hooks / "register.codex.json").write_text(json.dumps(fragment))

    def test_no_skills_leaves_hooks_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "hooks.json"
            source.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [{"a": 1}]}]}}))
            (root / "claude").mkdir()
            self.assertEqual(
                {"hooks": {"Stop": [{"hooks": [{"a": 1}]}]}},
                reconcile.desired_hooks(source, root / "claude"),
            )

    def test_skill_hook_joins_the_same_event(self):
        """The repo's observe-hook must survive a skill claiming that event."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "hooks.json"
            source.write_text(
                json.dumps(
                    {
                        "hooks": {
                            "PostToolUse": [
                                {"hooks": [{"type": "command", "command": "observe"}]}
                            ]
                        }
                    }
                )
            )
            claude = root / "claude"
            claude.mkdir()
            self._skill(
                claude,
                "commit",
                {
                    "hooks": {
                        "PostToolUse": [
                            {"hooks": [{"type": "command", "command": "attribute"}]}
                        ]
                    }
                },
            )
            result = reconcile.desired_hooks(source, claude)
            commands = [
                hook["command"]
                for rule in result["hooks"]["PostToolUse"]
                for hook in rule["hooks"]
            ]
            self.assertEqual(["observe", "attribute"], commands)

    def test_merge_is_idempotent(self):
        """Reconcile runs repeatedly; the same rule must not stack up."""
        base = {"hooks": {"Stop": [{"hooks": [{"command": "x"}]}]}}
        fragment = {"hooks": {"Stop": [{"hooks": [{"command": "y"}]}]}}
        once = reconcile.merge_hooks(base, fragment)
        twice = reconcile.merge_hooks(once, fragment)
        self.assertEqual(once, twice)
        self.assertEqual(2, len(twice["hooks"]["Stop"]))

    def test_new_event_is_added(self):
        base = {"hooks": {"Stop": [{"hooks": [{"command": "x"}]}]}}
        fragment = {"hooks": {"PreToolUse": [{"hooks": [{"command": "y"}]}]}}
        result = reconcile.merge_hooks(base, fragment)
        self.assertEqual({"Stop", "PreToolUse"}, set(result["hooks"]))
