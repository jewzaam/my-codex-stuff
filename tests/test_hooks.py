"""Tests for codex/hooks.json.

These hooks exist to emit OTEL telemetry. Retention elsewhere is opt-in: a hook
carrying a truthy `_keep` survives config stripping, and an unmarked one is
dropped. Nothing about that failure is loud -- the hook is simply absent and its
telemetry stops -- so the marker is asserted here rather than noticed later.

Codex itself never sees a stripped copy: openshell-sandbox's upload_config()
copies this file verbatim. The marker is kept in step anyway, so the two
harnesses declare retention the same way.
"""

import json
import pathlib
import unittest

HOOKS = pathlib.Path(__file__).resolve().parent.parent / "codex" / "hooks.json"


def hook_entries():
    """Every (event, hook) pair in hooks.json."""
    data = json.loads(HOOKS.read_text(encoding="utf-8"))
    return [
        (event, hook)
        for event, rules in data.get("hooks", {}).items()
        for rule in rules
        for hook in rule.get("hooks", [])
    ]


class HooksTests(unittest.TestCase):
    def test_file_has_hooks(self):
        self.assertTrue(HOOKS.is_file(), f"missing {HOOKS}")
        self.assertTrue(hook_entries(), "hooks.json declares no hooks")

    def test_every_hook_is_marked(self):
        unmarked = [event for event, hook in hook_entries() if not hook.get("_keep")]
        self.assertEqual(
            [],
            unmarked,
            "these hooks would be stripped out of a sandbox, silently ending "
            f"their telemetry: {unmarked}",
        )

    def test_marker_says_why(self):
        """A bare `true` survives stripping but tells the next reader nothing."""
        for event, hook in hook_entries():
            marker = hook.get("_keep")
            with self.subTest(event=event):
                self.assertIsInstance(marker, str)
                self.assertTrue(marker.strip(), "_keep should be a reason")

    def test_hooks_are_command_shaped(self):
        for event, hook in hook_entries():
            with self.subTest(event=event):
                self.assertEqual("command", hook.get("type"))
                self.assertTrue(hook.get("command"), "empty command")


if __name__ == "__main__":
    unittest.main()
