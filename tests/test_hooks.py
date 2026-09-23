"""Tests for codex/hooks.json and the guards it registers.

Two kinds of hook live in this file, and they want opposite treatment when a
sandbox is built.

The OTEL hooks exist to emit telemetry and must reach a sandbox, so their
command carries a `# KEEP:` shell comment -- the marker openshell-sandbox's
strip-settings.py looks for. Nothing about losing one is loud: the hook is
simply absent and its telemetry stops.

The harness_guards hooks block restricted commands and paths on the host. They
must NOT reach a sandbox -- there the network policy is the boundary, and
Codex runs with --dangerously-bypass-approvals-and-sandbox on purpose -- so
they are deliberately unmarked. A `# KEEP:` added to one would ship host
restrictions into a sandbox that does not want them.

What the guards *do* is not tested here. They are the `harness_guards` package
from my-claude-stuff, installed by `make install-guards` rather than copied in,
and that repo's suite covers the patterns. One definition, one place it is
tested. What is this repo's business is the registration: the right modules,
invoked as modules, unmarked.
"""

import json
import pathlib
import re
import unittest

# A shell comment rather than a JSON key: Claude Code drops unrecognised keys
# nested inside hook objects when it rewrites settings.json, and a dummy
# argument would land in observe-hook.py's argv. The command string survives,
# and the shell eats the comment before the program sees it.
KEEP_RE = re.compile(r"#\s*KEEP:\s*(\S.*)")

ROOT = pathlib.Path(__file__).resolve().parent.parent
HOOKS = ROOT / "codex" / "hooks.json"

# `python3 -m <module>`, so neither harness needs to know where pip put the
# package. A wrong module name is quiet -- `python3 -m` exits 1 on ImportError
# and both harnesses treat only exit 2 as a block -- so the shape is pinned.
GUARD_RE = re.compile(r"^python3 -m (harness_guards\.\w+)$")
GUARD_MODULES = {"harness_guards.block_commands", "harness_guards.block_paths"}


def hook_entries():
    """Every (event, hook) pair in hooks.json."""
    data = json.loads(HOOKS.read_text(encoding="utf-8"))
    return [
        (event, hook)
        for event, rules in data.get("hooks", {}).items()
        for rule in rules
        for hook in rule.get("hooks", [])
    ]


def is_guard(hook):
    return "harness_guards" in hook.get("command", "")


def telemetry_entries():
    return [(e, h) for e, h in hook_entries() if not is_guard(h)]


def guard_entries():
    return [(e, h) for e, h in hook_entries() if is_guard(h)]


class HooksTests(unittest.TestCase):
    def test_file_has_hooks(self):
        self.assertTrue(HOOKS.is_file(), f"missing {HOOKS}")
        self.assertTrue(hook_entries(), "hooks.json declares no hooks")

    def test_every_telemetry_hook_is_marked(self):
        unmarked = [
            event
            for event, hook in telemetry_entries()
            if not KEEP_RE.search(hook.get("command", ""))
        ]
        self.assertEqual(
            [],
            unmarked,
            "these hooks would be stripped out of a sandbox, silently ending "
            f"their telemetry: {unmarked}",
        )

    def test_marker_says_why(self):
        """A bare `# KEEP` is retained but tells the next reader nothing."""
        for event, hook in telemetry_entries():
            match = KEEP_RE.search(hook.get("command", ""))
            with self.subTest(event=event):
                self.assertIsNotNone(match, "no `# KEEP: <reason>` in command")
                self.assertTrue(match.group(1).strip(), "KEEP should give a reason")

    def test_marker_is_a_comment_not_an_argument(self):
        """The marker must be shell-commented out, or it reaches argv."""
        for event, hook in telemetry_entries():
            command = hook.get("command", "")
            with self.subTest(event=event):
                self.assertIn("#", command.split("KEEP")[0][-4:])

    def test_hooks_are_command_shaped(self):
        for event, hook in hook_entries():
            with self.subTest(event=event):
                self.assertEqual("command", hook.get("type"))
                self.assertTrue(hook.get("command"), "empty command")


class GuardHooksTests(unittest.TestCase):
    def test_both_guards_are_registered(self):
        registered = {
            GUARD_RE.match(hook["command"]).group(1)
            for event, hook in guard_entries()
            if event == "PreToolUse" and GUARD_RE.match(hook["command"])
        }
        self.assertEqual(GUARD_MODULES, registered)

    def test_guards_are_module_invocations(self):
        """Not a path. There is no copy of these files in this repo."""
        for event, hook in guard_entries():
            with self.subTest(event=event, command=hook["command"]):
                self.assertRegex(hook["command"], GUARD_RE)

    def test_guards_are_only_on_pre_tool_use(self):
        """They return a block decision; no other event reads one."""
        for event, hook in guard_entries():
            with self.subTest(event=event):
                self.assertEqual("PreToolUse", event)

    def test_guards_are_not_marked_keep(self):
        marked = [
            hook["command"]
            for _, hook in guard_entries()
            if KEEP_RE.search(hook["command"])
        ]
        self.assertEqual(
            [],
            marked,
            "a marked guard would ship host restrictions into a sandbox, "
            f"which runs Codex with approvals bypassed on purpose: {marked}",
        )

    def test_no_vendored_copy(self):
        """One definition. A copy here would be free to drift from it."""
        self.assertFalse(
            (ROOT / "codex" / "harness_guards").exists(),
            "harness_guards is a dependency (make install-guards), not a copy",
        )


if __name__ == "__main__":
    unittest.main()
