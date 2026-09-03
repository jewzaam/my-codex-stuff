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
