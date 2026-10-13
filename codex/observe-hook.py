#!/usr/bin/env python3
"""Export Codex hook input to the local OTLP collector."""

import hashlib
import json
import os
import socket
import sys
import time
import urllib.request
from pathlib import Path

def parse_resource_attributes(raw):
    """Parse OTEL_RESOURCE_ATTRIBUTES (W3C Baggage-ish: comma-separated k=v)."""
    attributes = {}
    for item in raw.split(","):
        key, _, value = item.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and value:
            attributes[key] = value
    return attributes


payload = json.load(sys.stdin)
received_at = time.time()
event = payload.get("hook_event_name", "")

# Identity comes from OTEL_RESOURCE_ATTRIBUTES when the environment supplies it.
# In an OpenShell sandbox that is host knowledge written to /sandbox/.env and
# exported by the shell: host.name (the creating machine, never the container),
# sandbox.source, sandbox.openshell_name, sandbox.profile. Without them the
# recording rules cannot join a Codex session to a sandbox row, and
# claude-dashboard shows the sandbox at Unknown forever.
#
# Parsing the variable rather than reading a list of SANDBOX_* names keeps this
# in step with whatever the host decides to put in it.
resource = parse_resource_attributes(os.environ.get("OTEL_RESOURCE_ATTRIBUTES", ""))
resource["service.name"] = "codex-hook-observer"
# Bare host sessions may invoke Codex without a wrapper that sources the
# machine environment. Preserve an injected sandbox host name; otherwise use
# the local machine name so recording rules can identify the session.
resource.setdefault("host.name", os.environ.get("HOSTNAME") or socket.gethostname())

# Pin host project at SessionStart so an app-level project root cannot win.
# OTEL_RESOURCE_ATTRIBUTES, and in a sandbox .env carries the host-side sandbox
# On the host, cwd supplies the launch path and the cache keeps it stable across /cd.
conversation_id = payload.get("conversation_id") or payload.get("session_id", "")
cwd = payload.get("cwd") or ""
is_sandbox = cwd.startswith("/sandbox/") or any(
    resource.get(key)
    for key in ("sandbox.source", "sandbox.profile", "sandbox.openshell_name")
)
project_dir = Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex")) / "session-projects"
project_path = (
    project_dir / (hashlib.sha256(conversation_id.encode()).hexdigest() + ".txt")
    if conversation_id else None
)

project = ""
if project_path is not None and event != "SessionStart":
    try:
        project = project_path.read_text(encoding="utf-8").strip()
    except OSError:
        pass

if not project:
    if is_sandbox:
        project = resource.get("project") or os.environ.get("CODEX_PROJECT") or cwd
    else:
        project = cwd or os.environ.get("CODEX_PROJECT") or resource.get("project") or ""
    if project_path is not None and project:
        try:
            project_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.chmod(project_dir, 0o700)
            temp_path = project_path.with_name(f".{project_path.name}.{os.getpid()}.tmp")
            temp_path.write_text(project, encoding="utf-8")
            temp_path.replace(project_path)
            os.chmod(project_path, 0o600)
        except OSError as exc:
            print(f"codex hook project pin failed: {exc}", file=sys.stderr)
resource["project"] = project

attributes = {
    "event_name": f"codex.hook.{event or 'unknown'}",
    # Native Codex telemetry calls this identity conversation_id. Keep the
    # recording-rule/session-state name for compatibility, but prefer the
    # native name when the hook payload provides both fields.
    "session_id": conversation_id,
    "conversation_id": conversation_id,
    "cwd": payload.get("cwd", ""),
    "project": project,
    "model": payload.get("model", ""),
    "hook_event_name": event,
    # Event ordering belongs in Loki recording rules, not in the hook
    # exporter. Keep the timestamp as raw telemetry so rules can determine
    # which event is current after a session goes through /cd or resumes.
    "observed_timestamp": int(received_at * 1_000_000_000),
}

def otel_value(value):
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, (int, float)):
        return {"doubleValue": value}
    return {"stringValue": str(value)}


body = json.dumps(payload, separators=(",", ":"))
record = {
    "timeUnixNano": str(int(received_at * 1_000_000_000)),
    "severityText": "INFO",
    "body": {"stringValue": body},
    "attributes": [
        {"key": key, "value": otel_value(value)}
        for key, value in attributes.items()
        if value != ""
    ],
}

endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4318").rstrip("/")
if not endpoint.endswith("/v1/logs"):
    endpoint += "/v1/logs"

request = urllib.request.Request(
    endpoint,
    data=json.dumps(
        {
            "resourceLogs": [
                {
                    "resource": {
                        "attributes": [
                            {"key": key, "value": otel_value(value)}
                            for key, value in resource.items()
                        ]
                    },
                    "scopeLogs": [
                        {
                            "scope": {"name": "codex-hook-observer"},
                            "logRecords": [record],
                        }
                    ],
                }
            ]
        }
    ).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)

try:
    with urllib.request.urlopen(request, timeout=3):
        pass
    if event == "SessionEnd" and project_path:
        project_path.unlink(missing_ok=True)
except Exception as exc:
    print(f"codex hook OTLP export failed: {exc}", file=sys.stderr)
