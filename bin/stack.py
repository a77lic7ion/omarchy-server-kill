#!/usr/bin/env python3
"""Stop/start a registered server stack (see stacks.json)."""
import json
import os
import shlex
import subprocess
import sys

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STACKS_FILE = os.path.join(PLUGIN_DIR, "stacks.json")


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ("stop", "start"):
        print("usage: stack.py <stop|start> <stack-id>", file=sys.stderr)
        return 2
    action, sid = sys.argv[1], sys.argv[2]
    try:
        with open(STACKS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"cannot read stacks.json: {e}", file=sys.stderr)
        return 1
    stack = next((s for s in data.get("stacks", []) if s.get("id") == sid), None)
    if not stack:
        print(f"unknown stack: {sid}", file=sys.stderr)
        return 1
    cwd = stack.get("cwd") or os.path.expanduser("~")
    cmds = stack.get(action, [])
    if not cmds:
        print(f"no {action} commands for {sid}", file=sys.stderr)
        return 1
    timeout = 420 if action == "start" else 180
    for cmd in cmds:
        print(f"$ {cmd}")
        full = f"cd {shlex.quote(cwd)} && {cmd}"
        try:
            r = subprocess.run(["bash", "-lc", full], capture_output=True,
                               text=True, timeout=timeout, stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            print(f"timed out: {cmd}", file=sys.stderr)
            return 1
        if r.stdout.strip():
            print(r.stdout.strip())
        if r.returncode != 0:
            msg = (r.stderr or r.stdout or "").strip() or f"exit {r.returncode}"
            print(f"failed: {cmd}\n{msg}", file=sys.stderr)
            return r.returncode if 0 < r.returncode < 125 else 1
    print(f"{action} {sid}: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
