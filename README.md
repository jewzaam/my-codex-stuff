# my-codex-stuff

Codex configuration and hooks managed from this repository.

- `codex/config.toml` -> `~/.codex/config.toml`
- `codex/hooks.json` -> `~/.codex/hooks.json`
- `codex/observe-hook.py` -> `~/.codex/observe-hook.py`

Deploy with:

```bash
make reconcile
```

`config.toml` is merged into the existing live file. Machine-specific
`[projects]` trust entries and Codex-generated `[hooks.state]` are preserved
locally and are intentionally not tracked.

## harness_guards

`hooks.json` registers two PreToolUse guards that block restricted commands and
paths:

```
python3 -m harness_guards.block_commands
python3 -m harness_guards.block_paths
```

`harness_guards` is a **dependency**, not a copy. It is the installable package
of [my-claude-stuff](https://github.com/jewzaam/my-claude-stuff), so both
harnesses run the same definition and there is nothing here to drift. Invoking
it as a module means no hook has to know where pip put it — in particular, a
machine running only Codex needs no `~/.claude` on disk.

`make reconcile` installs it. To install or update it on its own:

```bash
make install-guards                                   # from ../my-claude-stuff
make install-guards GUARDS_SOURCE=git+https://github.com/jewzaam/my-claude-stuff
make install-guards PIP_FLAGS=--break-system-packages # externally-managed python3
```

The guards must be importable by whatever `python3` resolves to when Codex runs
the hook. If they are not, `python3 -m` exits 1 — which Codex reports as a hook
error, not a block, so the guards are simply off.

The guards are registered **without** a `# KEEP:` marker, which is what makes
openshell-sandbox strip them when it builds a sandbox. A sandbox runs Codex with
approvals bypassed on purpose — the network policy is the boundary there, not
these hooks.
