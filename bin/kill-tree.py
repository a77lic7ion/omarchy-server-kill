#!/usr/bin/env python3
"""Kill a process and all of its descendants (SIGTERM, then SIGKILL)."""
import os
import signal
import sys
import time


def read_ppid(pid):
    try:
        with open(f"/proc/{pid}/stat", "rb") as f:
            data = f.read()
        return int(data.rsplit(b")", 1)[1].split()[1])
    except Exception:
        return -1


def descendants(root):
    ppids = {}
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        pid = int(entry)
        ppids[pid] = read_ppid(pid)
    children = {}
    for pid, ppid in ppids.items():
        children.setdefault(ppid, []).append(pid)
    out, seen, stack = [], {root}, [root]
    while stack:
        p = stack.pop()
        for c in children.get(p, []):
            if c not in seen:
                seen.add(c)
                out.append(c)
                stack.append(c)
    return out


def alive(pid):
    return os.path.exists(f"/proc/{pid}")


def main():
    if len(sys.argv) != 2:
        print("usage: kill-tree.py <pid>", file=sys.stderr)
        return 2
    root = int(sys.argv[1])
    if root <= 1 or root == os.getpid():
        print("refusing to kill pid " + str(root), file=sys.stderr)
        return 2

    tree = descendants(root) + [root]
    for pid in tree:
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass

    deadline = time.time() + 3.0
    while time.time() < deadline and any(alive(p) for p in tree):
        time.sleep(0.25)

    survivors = [p for p in tree if alive(p)]
    for pid in survivors:
        try:
            os.kill(pid, signal.SIGKILL)
        except Exception:
            pass
    time.sleep(0.3)

    still = [p for p in tree if alive(p)]
    if still:
        print(f"some processes survived: {still}", file=sys.stderr)
        return 1
    print(f"killed {len(tree)} process(es)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
