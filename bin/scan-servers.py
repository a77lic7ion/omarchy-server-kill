#!/usr/bin/env python3
"""Scan listening servers, group by process, derive app names, annotate stacks, output JSON."""
import json, subprocess, re, os

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STACKS_FILE = os.path.join(PLUGIN_DIR, "stacks.json")

# System daemons that are not user-launched servers.
SYSTEM_COMMS = {
    "systemd-resolve", "systemd-resolved", "systemd-networkd",
    "cupsd", "smbd", "nmbd", "avahi-daemon", "rpcbind",
    "dnsmasq", "dhcpcd", "wpa_supplicant", "chronyd", "bluetoothd",
}

# Internal worker/JVM noise that is not a "server" worth listing.
NOISE_PATTERNS = (
    "annotations-", "gradle-worker", "gradle-api", "gradle-test-kit",
    "agentmain", "jdk.internal", "sun.misc", "kotlin-daemon",
)

SKIP_BASENAMES = {
    "node", "python", "python3", "python3.11", "python3.12", "python3.13",
    "sh", "bash", "zsh", "env", "java", "exec", "uv", "uvicorn",
    "node-mainthread", "node-machthread", "mainthread",
}

GENERIC_SCRIPTS = {
    "server", "main", "app", "index", "run", "start", "manage", "dev", "serve",
    "server.js", "main.py", "app.py", "__main__",
}

GOOD_DIRS = ("bin", "src", "app", "dist", "build", "node_modules", "site-packages", ".venv", "venv")


def get_local_ips():
    try:
        out = subprocess.run(["hostname", "-I"], capture_output=True, text=True, timeout=2)
        ips = [i for i in out.stdout.strip().split() if i]
        if ips:
            return ips
    except Exception:
        pass
    try:
        out = subprocess.run(["ip", "-br", "-4", "addr"], capture_output=True, text=True, timeout=2)
        ips = []
        for line in out.stdout.splitlines():
            for p in line.split():
                if "/" in p and "." in p:
                    ip = p.split("/")[0]
                    if ip != "127.0.0.1":
                        ips.append(ip)
        return list(dict.fromkeys(ips))
    except Exception:
        return []


def get_tailscale_ip():
    try:
        out = subprocess.run(["tailscale", "status"], capture_output=True, text=True, timeout=3)
        m = re.search(r"(\d+\.\d+\.\d+\.\d+)", out.stdout)
        return m.group(1) if m else ""
    except Exception:
        return ""


def read_proc(pid):
    comm, cmdline, cwd = "", "", ""
    try:
        with open(f"/proc/{pid}/comm") as f:
            comm = f.read().strip()
    except Exception:
        pass
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            cmdline = f.read().replace(b"\x00", b" ").decode("utf-8", "replace").strip()
    except Exception:
        pass
    try:
        cwd = os.readlink(f"/proc/{pid}/cwd")
    except Exception:
        pass
    return comm, cmdline, cwd


def read_starttime(pid):
    """Process start time in clock ticks since boot (field 22 of /proc/<pid>/stat).

    Together with the PID it identifies one specific process instance; the
    kill helper verifies it before signalling, so a recycled PID is refused
    rather than killed.
    """
    try:
        with open(f"/proc/{pid}/stat", "rb") as f:
            data = f.read()
        return int(data.rsplit(b")", 1)[1].split()[19])
    except Exception:
        return -1


def read_unit(pid):
    """Innermost systemd service unit owning the pid ('' when none/session scope)."""
    try:
        with open(f"/proc/{pid}/cgroup") as f:
            text = f.read()
    except Exception:
        return ""
    best = ""
    for line in text.splitlines():
        path = line.split("::", 1)[-1]
        parts = [p for p in path.strip("/").split("/") if p]
        if parts and parts[-1].endswith(".service") and "user@" not in parts[-1]:
            best = parts[-1]
    return best


def sanitize(name):
    name = re.sub(r"[\"'`()\[\]{}]+", "", name)
    name = name.strip(" .,-_")
    return name


GENERIC_BINARIES = {
    "node", "python", "python3", "python3.11", "python3.12", "python3.13",
    "java", "sh", "bash", "zsh", "env", "uv", "deno", "bun",
}

GENERIC_DIRS = {
    "shaun", "home", "root", "tmp", "temp", "workspace", "workspaces",
    "bin", "src", "app", "dist", "build", "node_modules", "site-packages",
    ".venv", "venv", "current", "default", "instances",
}

CUSTOM_MODES = {"dev", "development", "prod", "production", "staging", "test", "testing"}


def fmt_project(name):
    """Turn a folder name like 'Elderwatch-New' into 'Elderwatch'."""
    low = name.lower()
    for suf in ("-new", "_new", "-main", "_main", "-dev", "_dev", "-app", "_app", "-local", "_local"):
        if low.endswith(suf):
            name = name[: -len(suf)]
            low = name.lower()
    name = re.sub(r"[-_]+", " ", name)
    words = [w for w in name.split() if w]
    return " ".join(w[:1].upper() + w[1:] for w in words) if words else name


def find_mode(parts):
    for i, p in enumerate(parts):
        if p in ("--mode", "--variant") and i + 1 < len(parts):
            return parts[i + 1]
        if p.startswith("--mode=") or p.startswith("--variant="):
            return p.split("=", 1)[1]
    return ""


def guess_name(comm, cmdline, cwd):
    parts = [p for p in cmdline.split() if p]
    if not parts:
        return sanitize(comm) or "unknown"

    # python -m module
    for i, p in enumerate(parts):
        if p in ("-m", "--module") and i + 1 < len(parts):
            return sanitize(parts[i + 1].split(":")[0])

    binary = os.path.basename(parts[0]).replace(".exe", "")
    project = fmt_project(os.path.basename(cwd.rstrip("/"))) if cwd else ""
    joined = cmdline.lower()

    # A real app binary (postgres, adb, sunshine, opencode) names itself.
    if binary and binary.lower() not in GENERIC_BINARIES:
        return sanitize(binary)

    # Strong signatures that beat a generic project folder.
    if "gradledaemon" in joined or "gradle-daemon-main" in joined:
        return "gradle"
    if "hermes-agent" in joined or "hermes_cli" in joined or "hermes_bootstrap" in joined:
        return "hermes"
    if "paperclipai" in joined or "paperclip" in joined:
        return "paperclip"
    if "comfyui" in joined or "comfy" in joined:
        return "ComfyUI"
    if "opencode" in joined:
        return "opencode"

    # A meaningful process comm (hermes, postgres, nemo-speech) beats the cwd.
    if comm and comm.lower() not in SKIP_BASENAMES and comm.lower() not in GENERIC_BINARIES:
        return sanitize(comm)

    # For interpreters (node/python/java...), the project folder is the real name.
    if project and project.lower() not in GENERIC_DIRS:
        mode = find_mode(parts)
        if mode and mode.lower() not in CUSTOM_MODES:
            project = project + " " + mode[:1].upper() + mode[1:]
        return sanitize(project)

    # Fall back to the script basename.
    for p in parts[1:]:
        cp = p.split("=", 1)[1] if p.startswith("--") and "=" in p else p
        if "/" in cp or cp.endswith((".js", ".ts", ".mjs", ".cjs", ".tsx", ".jsx",
                                     ".py", ".rb", ".go", ".php")):
            base = os.path.basename(cp.rstrip("/"))
            stem = os.path.splitext(base)[0]
            if stem and stem.lower() not in SKIP_BASENAMES and stem.lower() not in GENERIC_SCRIPTS:
                return sanitize(stem)

    # Generic signatures last (vite, uvicorn, etc.).
    for key, label in (
        ("vite", "vite"), ("uvicorn", "uvicorn"), ("gunicorn", "gunicorn"),
        ("postgres", "postgres"), ("redis", "redis"), ("mongo", "mongodb"),
        ("sunshine", "sunshine"), ("parakeet", "parakeet"), ("adb", "adb"),
    ):
        if key in joined:
            return label

    return sanitize(project) or sanitize(comm) or "unknown"


def normalize_addr(addr):
    a = addr.strip().split("%")[0]
    if a.startswith("[::ffff:") and a.endswith("]"):
        a = a[8:-1]
    if a in ("::", "[::]"):
        return "0.0.0.0"
    if a.startswith("[") and a.endswith("]"):
        a = a[1:-1]
    return a


def is_wildcard(addr):
    return addr == "0.0.0.0"


def is_noise(comm, cmdline):
    low = (comm + " " + cmdline).lower()
    return any(p in low for p in NOISE_PATTERNS)


def primary_local_ip(local_ips):
    for ip in local_ips:
        if ip.startswith(("192.168.", "10.")) and not ip.startswith("10.74."):
            return ip
    for ip in local_ips:
        if not ip.startswith(("127.", "172.17.", "172.18.", "100.")):
            return ip
    return local_ips[0] if local_ips else "127.0.0.1"


def scan(local_ips, ts_ip):
    primary = primary_local_ip(local_ips)
    listening = set()
    procs = {}
    try:
        out = subprocess.run(["ss", "-tlnp"], capture_output=True, text=True, timeout=4)
    except Exception:
        return [], listening
    for line in out.stdout.splitlines():
        if "LISTEN" not in line:
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        local = parts[3]
        m = re.search(r'users:\(\("([^"]+)",pid=(\d+)', line)
        if not m:
            continue
        pid = int(m.group(2))
        if pid <= 0:
            continue
        comm = m.group(1)
        if comm in SYSTEM_COMMS:
            continue
        try:
            addr, port_str = local.rsplit(":", 1)
            port = int(port_str)
        except Exception:
            continue
        addr = normalize_addr(addr)
        e = procs.setdefault(pid, {"ports": [], "addrs": set(), "comm_raw": comm})
        if port not in e["ports"]:
            e["ports"].append(port)
        listening.add(port)
        e["addrs"].add(addr)

    servers = []
    for pid, e in procs.items():
        comm, cmdline, cwd = read_proc(pid)
        comm = comm or e["comm_raw"]
        if is_noise(comm, cmdline):
            continue
        wildcard = any(is_wildcard(a) for a in e["addrs"])
        local_only = bool(e["addrs"]) and all(a == "127.0.0.1" for a in e["addrs"])

        entries = []
        for port in sorted(e["ports"]):
            if local_only:
                entries.append({"port": port, "local_url": f"http://127.0.0.1:{port}", "tail_url": ""})
            elif wildcard:
                tail = f"http://{ts_ip}:{port}" if ts_ip else ""
                entries.append({"port": port, "local_url": f"http://{primary}:{port}", "tail_url": tail})
            else:
                # bound to a specific interface
                addr = sorted(a for a in e["addrs"] if a != "0.0.0.0")[0] if e["addrs"] else primary
                if addr == "127.0.0.1":
                    entries.append({"port": port, "local_url": f"http://127.0.0.1:{port}", "tail_url": ""})
                else:
                    tail = f"http://{ts_ip}:{port}" if ts_ip else ""
                    entries.append({"port": port, "local_url": f"http://{addr}:{port}", "tail_url": tail})

        servers.append({
            "name": guess_name(comm, cmdline, cwd),
            "pid": pid,
            "starttime": read_starttime(pid),
            "unit": read_unit(pid),
            "ports": sorted(e["ports"]),
            "wildcard": wildcard,
            "local_only": local_only,
            "entries": entries,
        })

    servers.sort(key=lambda s: (s["local_only"], s["name"].lower(), s["pid"]))
    return servers, listening


STOP_UNIT_DENY = ("wayland-wm@", "user@")


def stoppable_unit(unit):
    return bool(unit) and not unit.startswith(STOP_UNIT_DENY)


def load_stacks():
    try:
        with open(STACKS_FILE, encoding="utf-8") as f:
            return json.load(f).get("stacks", [])
    except Exception:
        return []


def apply_stacks(servers, stacks):
    for s in servers:
        for st in stacks:
            unit_hit = s.get("unit") and s["unit"] in st.get("units", [])
            port_hit = any(p in st.get("ports", []) for p in s.get("ports", []))
            if unit_hit or port_hit:
                s["_stack"] = st
                break
    merged, seen = [], {}
    for s in servers:
        st = s.pop("_stack", None)
        if st is None:
            s["stoppable"] = stoppable_unit(s.get("unit", ""))
            merged.append(s)
            continue
        sid = st["id"]
        if sid in seen:
            m = seen[sid]
            m["pids"].append(s["pid"])
            for p in s["ports"]:
                if p not in m["ports"]:
                    m["ports"].append(p)
            for ent in s["entries"]:
                if not any(x["port"] == ent["port"] for x in m["entries"]):
                    m["entries"].append(ent)
        else:
            m = {
                "name": st["name"],
                "stack": sid,
                "unit": "",
                "pid": s["pid"],
                "pids": [s["pid"]],
                "ports": list(s["ports"]),
                "entries": list(s["entries"]),
                "wildcard": s.get("wildcard", False),
                "local_only": s.get("local_only", False),
            }
            seen[sid] = m
            merged.append(m)
    return merged, seen


def stack_states(stacks, listening, ts_ip):
    all_units = []
    for st in stacks:
        all_units.extend(st.get("units", []))
    active = {}
    if all_units:
        try:
            r = subprocess.run(["systemctl", "--user", "is-active"] + all_units,
                               capture_output=True, text=True, timeout=6)
            for u, line in zip(all_units, r.stdout.strip().splitlines()):
                active[u] = line.strip() in ("active", "activating", "reloading")
        except Exception:
            pass
    out = []
    for st in stacks:
        units = st.get("units", [])
        ports = st.get("ports", [])
        any_active = any(active.get(u) for u in units)
        port_hit = any(p in listening for p in ports)
        state = "running" if (any_active or port_hit) else "stopped"
        entries = []
        for p in [x for x in ports if x in listening]:
            tail = f"http://{ts_ip}:{p}" if ts_ip else ""
            entries.append({"port": p, "local_url": f"http://127.0.0.1:{p}", "tail_url": tail})
        out.append({
            "id": st["id"],
            "name": st["name"],
            "description": st.get("description", ""),
            "state": state,
            "units": [{"name": u, "active": bool(active.get(u))} for u in units],
            "ports": ports,
            "entries": entries,
        })
    return out


def main():
    local_ips = get_local_ips()
    ts_ip = get_tailscale_ip()
    servers, listening = scan(local_ips, ts_ip)
    stacks = load_stacks()
    servers, seen = apply_stacks(servers, stacks)
    states = stack_states(stacks, listening, ts_ip)
    for st in states:
        if st["state"] == "running" and st["id"] not in seen:
            servers.append({
                "name": st["name"],
                "stack": st["id"],
                "unit": "",
                "pid": 0,
                "pids": [],
                "ports": [e["port"] for e in st["entries"]],
                "entries": st["entries"],
                "wildcard": False,
                "local_only": False,
            })
    servers.sort(key=lambda s: (s.get("local_only", False), s["name"].lower(), s.get("pid", 0)))
    print(json.dumps({
        "local_ips": local_ips,
        "primary_local_ip": primary_local_ip(local_ips),
        "tailscale_ip": ts_ip,
        "servers": servers,
        "stacks": states,
        "count": len(servers),
    }))


if __name__ == "__main__":
    main()
