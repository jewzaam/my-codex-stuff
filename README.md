# my-codex-stuff

Codex configuration and hooks managed from this repository.

- `codex/config.toml` -> `~/.codex/config.toml`
- `codex/hooks.json` -> `~/.codex/hooks.json`
- `codex/rules/*.rules` -> `~/.codex/rules/*.rules`
- `codex/observe-hook.py` -> `~/.codex/observe-hook.py`

Deploy with:

```bash
make reconcile
```

`config.toml` is merged into the existing live file. Machine-specific
`[projects]` trust entries and Codex-generated `[hooks.state]` are preserved
locally and are intentionally not tracked.

Global command permissions live in standalone `codex/rules/*.rules` files,
named by context. Reconcile copies these files as-is and manages only the
`my-codex-stuff-*.rules` names. Other global rule files are left alone. It
removes the old `default.rules` only when its rules still exactly match these
files. `make test-rules` parses the files with Codex's policy checker and is
part of `make check`.

## Refresh a provider model catalog

Run `scripts/codex-refresh-models.sh` from this checkout to refresh a profile's
model catalog. It requires Bash, `curl`, `jq`, and Python 3.11 or newer (for
`tomllib`).

The profile file must already exist at `$CODEX_HOME/<PROFILE>.config.toml`;
`CODEX_HOME` defaults to `~/.codex`. The script reads `model_provider` and
`model_providers` from that file, falling back to `$CODEX_HOME/config.toml`.
Provider definitions in the profile replace global definitions with the same
name.

The endpoint comes from the provider's `model_catalog_url`, or its `base_url`
with `/models` appended. Set the environment variable named by the provider's
`env_key` to supply the bearer token. For example, with a `work` profile whose
provider uses `env_key = "WORK_API_KEY"`:

```bash
export WORK_API_KEY='your-provider-token'
./scripts/codex-refresh-models.sh work
```

This replaces `$CODEX_HOME/work.models.json`. Override the endpoint, token, or
output path when needed:

```bash
./scripts/codex-refresh-models.sh work \
  --url https://provider.example/v1/models \
  --token "$WORK_API_KEY" \
  --output /tmp/work.models.json
./scripts/codex-refresh-models.sh --help
```

Responses with a top-level `models` field are copied as a catalog; responses
with a top-level `data` field are converted from model IDs. The conversion uses
fixed capability defaults, including a 1,048,576-token context window and
`low`, `high`, and `max` reasoning levels; check these against your provider
before using the generated catalog. The script only writes the catalog; it
does not update profile configuration or run during reconciliation.

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
