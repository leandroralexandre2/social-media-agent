#!/usr/bin/env python3
"""Minimal JSON-RPC client for the Plow/Latch MCP relay."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

TIMEOUT_S = 60
WAIT_MS = 20_000
POLL_S = 1


class RelayError(RuntimeError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "refusing redirect", headers, fp)


OPENER = urllib.request.build_opener(NoRedirect)


def call(tool: str, arguments: dict) -> dict:
    url = os.environ.get("PLOW_MCP_URL")
    token = os.environ.get("PLOW_AGENT_TOKEN")
    if not url or not token:
        raise RelayError("PLOW_MCP_URL and PLOW_AGENT_TOKEN must be set")
    body = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": tool, "arguments": arguments},
    }).encode()
    request = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    })
    try:
        with OPENER.open(request, timeout=TIMEOUT_S) as response:
            raw = response.read().decode()
    except (OSError, urllib.error.URLError) as exc:
        raise RelayError(f"relay request failed: {exc}") from exc
    if raw.lstrip().startswith(("event:", "data:")):
        raw = "\n".join(line[5:].strip() for line in raw.splitlines() if line.startswith("data:"))
    try:
        message = json.loads(raw)
        if "error" in message:
            raise RelayError(f"{tool}: {message['error'].get('message', 'unknown MCP error')}")
        result = message["result"]
        text = next(block["text"] for block in result.get("content", []) if block.get("type") == "text")
        payload = json.loads(text)
    except (KeyError, StopIteration, json.JSONDecodeError) as exc:
        raise RelayError(f"{tool}: malformed MCP response") from exc
    if result.get("isError"):
        diagnosis = payload.get("diagnosis") or {}
        raise RelayError(f"{tool}: {payload.get('error')} ({diagnosis.get('cause', 'no diagnosis')})")
    return payload


def run(argv: list[str], *, write_paths: tuple[str, ...] = (), network: bool = False,
        timeout: float = 120, goal: str = "social-media-agent host command") -> tuple[int, str]:
    deadline = time.monotonic() + timeout
    result = call("plow_run_command", {
        "argv": argv,
        "write_paths": list(write_paths),
        "network": network,
        "wait_ms": WAIT_MS,
        "goal": goal,
    })
    handle = None
    while result.get("status") in ("pending", "running"):
        if time.monotonic() > deadline:
            raise RelayError("host command exceeded its deadline")
        time.sleep(POLL_S)
        handle = result.get("handle", handle)
        if not handle:
            raise RelayError("host command is running without a result handle")
        poll_tool = "plow_get_result" if result["status"] == "pending" else "plow_get_output"
        result = call(poll_tool, {"handle": handle})
        if result.get("status") == "ready":
            result = result["result"]
    if result.get("status") != "completed":
        raise RelayError(f"host command ended with status {result.get('status')!r}")
    return int(result["exit_code"]), str(result.get("output", ""))

