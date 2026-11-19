#!/usr/bin/env python3
"""Kill a process and all of its descendants (SIGTERM, then SIGKILL).

Identity-safe: the caller must pass the identity token captured when the PID
was first observed - the starttime field (22) of /proc/<pid>/stat, i.e. clock
ticks since boot, which uniquely identifies a process instance. The token is
verified on entry and re-verified immediately before every signal, including
the SIGKILL after the grace period, so a recycled PID can never cause an
unrelated process to be killed. Only processes owned by the invoking user
are ever signalled.
"""
import os
import signal
import sys
import time


def proc_info(pid):
    """Return (state, ppid, starttime) for pid, or ("", -1, -1) when unreadable."""
    try:
        with open(f"/proc/{pid}/stat", "rb") as f:
            data = f.read()
        rest = data.rsplit(b")", 1)[1].split()
        return rest[0].decode("ascii", "replace"), int(rest[1]), int(rest[19])
    except Exception:
        return "", -1, -1


def read_ppid(pid):
    return proc_info(pid)[1]


def starttime(pid):
    return proc_info(pid)[2]


def owner_uid(pid):
    try:
        return os.stat(f"/proc/{pid}").st_uid
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
    """True only for a process that is still running (zombies are dead)."""
    return proc_info(pid)[0] not in ("", "Z", "X")


def main():
    usage = "usage: kill-tree.py <pid> <starttime>  (starttime = field 22 of /proc/<pid>/stat)"
    if len(sys.argv) != 3:
        print(usage, file=sys.stderr)
        return 2
    try:
        root = int(sys.argv[1])
        token = int(sys.argv[2])
    except ValueError:
        print(usage, file=sys.stderr)
        return 2

    me = os.geteuid()
    if root <= 1 or root == os.getpid():
        print("refusing to kill pid " + str(root), file=sys.stderr)
        return 2
    if token < 0:
        print(f"refusing: no identity token for pid {root} (rescan and try again)", file=sys.stderr)
        return 2

    # Entry gate: the PID must still be the exact process instance the caller
    # scanned - this catches reuse between the scan and the kill.
    entry_st = starttime(root)
    if entry_st != token:
        why = "no longer exists" if entry_st < 0 else "was recycled (identity mismatch)"
        print(f"refusing: pid {root} {why}; not killing anything", file=sys.stderr)
        return 2
    if owner_uid(root) != me:
        print(f"refusing: pid {root} is not owned by this user", file=sys.stderr)
        return 2

    # Walk the process family, snapshotting each member's identity as we go.
    tree = descendants(root) + [root]
    ident = {}
    for pid in tree:
        st = starttime(pid)
        if st >= 0 and owner_uid(pid) == me:
            ident[pid] = st

    # If the root changed hands mid-walk, the tree cannot be trusted.
    if starttime(root) != token:
        print(f"refusing: pid {root} changed during the tree walk; not killing anything", file=sys.stderr)
        return 2

    def same(pid):
        st = ident.get(pid)
        return st is not None and starttime(pid) == st and owner_uid(pid) == me

    def send(pid, sig):
        if not same(pid):  # re-verify the identity immediately before signalling
            return
        try:
            os.kill(pid, sig)
        except (ProcessLookupError, PermissionError):
            pass

    for pid in ident:
        send(pid, signal.SIGTERM)

    deadline = time.time() + 3.0
    while time.time() < deadline and any(alive(p) for p in ident):
        time.sleep(0.25)

    for pid in [p for p in ident if alive(p)]:
        send(pid, signal.SIGKILL)  # identity re-checked again - a PID reused during the grace period is skipped

    time.sleep(0.3)
    still = [p for p in ident if alive(p) and same(p)]
    if still:
        print(f"some processes survived: {still}", file=sys.stderr)
        return 1
    print(f"killed {len(ident)} process(es)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
