#!/usr/bin/env python3
"""Mózg Hermesa — live visualisation of Hermes agents.

Reads the agents' state.db files (read-only), the Hermes skills/memory and an
Obsidian vault, builds a "neuron" graph and streams agent activity over SSE.
Python standard library only.

    python3 server/server.py            # your own ~/.hermes + vault
    python3 server/server.py --demo     # fictional demo data from demo/
"""
import glob
import json
import os
import re
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
DEMO_DIR = os.path.join(ROOT, "demo")

# ---------- configuration ----------
# Priority: environment variables > config file > defaults.
# Config file: $MOZG_CONFIG or ~/.config/mozg-hermesa/config.json (see config.example.json)
DEFAULTS = {
    "hermes_home": "~/.hermes",
    "vault": "~/Obsidian/Vault",
    "host": "127.0.0.1",
    "port": 8110,
    # Optional external chat/tasks backend (host:port). Empty = chat and task lists disabled.
    "backend": "",
    # profile folder -> display name; "" = main Hermes profile. Empty dict = auto-detect.
    "agents": {},
    # vault top-level folders whose note titles are hidden (shown as "note")
    "private_folders": [],
    # external services: node id, label and regex matched against terminal/browser calls
    "services": [
        {"id": "x_github", "label": "GitHub", "match": r"github\.com|\bgh "},
        {"id": "x_youtube", "label": "YouTube", "match": r"yt-dlp|youtube"},
        {"id": "x_mail", "label": "E-mail", "match": r"\bsmtp|\bimap|sendmail|mail\.google"},
        {"id": "x_ha", "label": "Home Assistant", "match": r"homeassistant|home-assistant|:8123", "local": True},
    ],
    # remote machines reached over ssh/scp/rsync: regex on the command line
    "hosts": [
        {"id": "x_server", "label": "Remote server", "match": r"\bmy-server\b"},
    ],
}


def load_config(demo=False):
    cfg = dict(DEFAULTS)
    path = os.environ.get("MOZG_CONFIG") or os.path.expanduser("~/.config/mozg-hermesa/config.json")
    if demo:
        path = os.path.join(DEMO_DIR, "config.json")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            cfg.update(json.load(f))
    env = {"MOZG_HERMES_HOME": "hermes_home", "MOZG_VAULT": "vault", "MOZG_HOST": "host",
           "MOZG_PORT": "port", "MOZG_BACKEND": "backend"}
    for k, key in env.items():
        if os.environ.get(k) and not (demo and key in ("hermes_home", "vault")):
            cfg[key] = os.environ[k]
    if demo:
        cfg["hermes_home"] = os.path.join(DEMO_DIR, "hermes")
        cfg["vault"] = os.path.join(DEMO_DIR, "vault")
    cfg["hermes_home"] = os.path.expanduser(cfg["hermes_home"])
    cfg["vault"] = os.path.expanduser(cfg["vault"])
    cfg["port"] = int(cfg["port"])
    if not cfg["agents"]:
        ag = {"": "Hermes"}
        for p in sorted(glob.glob(os.path.join(cfg["hermes_home"], "profiles", "*"))):
            if os.path.isdir(p):
                n = os.path.basename(p)
                ag[n] = n.capitalize()
        cfg["agents"] = ag
    return cfg


DEMO = "--demo" in sys.argv or os.environ.get("MOZG_DEMO", "") not in ("", "0")
CFG = load_config(DEMO)
HOME = CFG["hermes_home"]
VAULT = CFG["vault"]
AGENTS = CFG["agents"]
MAIN = AGENTS.get("", next(iter(AGENTS.values())))
SOURCES = {"appka": "src_app", "telegram": "src_telegram", "discord": "src_discord", "cron": "src_cron",
           "api_server": "src_api", "desktop": "src_app", "cli": "src_app", "tui": "src_app", "webui": "src_app"}
USER_SOURCES = ("src_app", "src_telegram", "src_discord")
SERVICES = [dict(s, rx=re.compile(s["match"], re.I)) for s in CFG["services"]]
HOSTS = [dict(h, rx=re.compile(h["match"], re.I)) for h in CFG["hosts"]]


def agent_node(name):
    return "ag_" + re.sub(r"\W+", "_", (name or MAIN).lower())


NOTES = set()
MEMTXT = []


def build_graph():
    nodes, links = [], []

    def N(id, label, kind, group=None, r=None):
        nodes.append({"id": id, "label": label, "kind": kind, "group": group or kind, "r": r})

    def L(a, b):
        links.append([a, b])

    main = agent_node(MAIN)
    # channels
    for i, l in [("src_app", "App / CLI"), ("src_telegram", "Telegram"), ("src_discord", "Discord"),
                 ("src_cron", "Cron"), ("src_api", "API")]:
        N(i, l, "source", r=9); L(i, "gateway")
    N("user", "YOU", "user", r=14)
    for s in USER_SOURCES:
        L("user", s)
    N("gateway", "Gateway", "core", r=12)
    # agents
    for key, name in AGENTS.items():
        N(agent_node(name), name, "agent", r=13 if not key else 9); L("gateway", agent_node(name))
    # models
    for i, l in [("m_haiku", "Haiku"), ("m_sonnet", "Sonnet"), ("m_opus", "Opus"), ("m_deepseek", "DeepSeek"), ("m_other", "other model")]:
        N(i, l, "model", r=9); L(main, i)
    # tools
    tools = [("t_terminal", "Terminal"), ("t_files", "Files"), ("t_web", "Web search"), ("t_browser", "Browser"),
             ("t_delegate", "Subagents"), ("t_memory", "Memory (write)"), ("t_skills", "Skills"), ("t_code", "Code"), ("t_misc", "Other tools")]
    for i, l in tools:
        N(i, l, "tool", r=9); L(main, i)
    # outside world
    N("x_internet", "INTERNET", "ext", r=10); N("x_anthropic", "Anthropic API", "ext", r=8)
    for s in SERVICES:
        N(s["id"], s["label"], "ext", r=8)
        L("t_terminal", s["id"]) if s.get("local") else L("x_internet", s["id"])
    for h in HOSTS:
        N(h["id"], h["label"], "ext", r=8); L("t_terminal", h["id"])
    L("t_web", "x_internet"); L("t_browser", "x_internet"); L("t_terminal", "x_internet")
    for m in ("m_haiku", "m_sonnet", "m_opus"):
        L(m, "x_anthropic")
    L("x_anthropic", "x_internet"); L("m_deepseek", "x_internet")
    # memory
    N("mem_hub", "Memory", "memhub", r=11); L(main, "mem_hub"); L("t_memory", "mem_hub")
    try:
        txt = open(f"{HOME}/memories/MEMORY.md", encoding="utf-8").read()
        MEMTXT.clear(); MEMTXT.extend([x.strip() for x in txt.split("§") if x.strip()])
        for k, e in enumerate(MEMTXT):
            N(f"mem_{k}", re.sub(r"\s+", " ", e)[:34], "memory", r=3); L("mem_hub", f"mem_{k}")
    except OSError:
        pass
    # skills
    N("sk_hub", "Skills", "skhub", r=11); L(main, "sk_hub"); L("t_skills", "sk_hub")
    seen = set()
    for p in sorted(glob.glob(f"{HOME}/skills/*/*/SKILL.md")):
        parts = p.split(os.sep); cat, name = parts[-3], parts[-2]
        seen.add(name); N("sk_" + name, name, "skill", group=cat, r=2.4); L("sk_hub", "sk_" + name)
    for p in sorted(glob.glob(f"{HOME}/skills/*/SKILL.md")):
        name = p.split(os.sep)[-2]
        if name not in seen:
            N("sk_" + name, name, "skill", group="other", r=2.4); L("sk_hub", "sk_" + name)
    # vault
    N("vault_hub", "Obsidian", "vaulthub", r=12); L("t_files", "vault_hub"); L(main, "vault_hub")
    NOTES.clear()
    if os.path.isdir(VAULT):
        for d in sorted(os.listdir(VAULT)):
            if os.path.isdir(f"{VAULT}/{d}") and not d.startswith("."):
                N("v_" + d, d, "vault", r=5); L("vault_hub", "v_" + d)
        for root, dirs, files in os.walk(VAULT):
            dirs[:] = [x for x in dirs if not x.startswith(".")]
            for f in files:
                if not f.endswith(".md"):
                    continue
                rel = os.path.relpath(os.path.join(root, f), VAULT); top = rel.split(os.sep)[0]
                if os.sep not in rel or not os.path.isdir(f"{VAULT}/{top}"):
                    continue
                nid = "n_" + rel; NOTES.add(nid)
                lab = "note" if top in CFG["private_folders"] else f[:-3][:30]
                N(nid, lab, "note", group=top, r=1.3); L("v_" + top, nid)
    return {"nodes": nodes, "links": links}


# ---------- events ----------
def tool_path(name, args):
    """returns (list of node ids on the way from the agent, label)"""
    name = name.replace("mcp__", "")
    s = json.dumps(args, ensure_ascii=False) if not isinstance(args, str) else args
    low = s.lower()
    if name == "skill_view":
        n = ((args.get("name") or "") if isinstance(args, dict) else "").split(":")[-1]
        return ["t_skills", "sk_hub", "sk_" + n], f"skill: {n}"
    if name in ("skills_list", "skill_manage"):
        return ["t_skills", "sk_hub"], name
    if name in ("session_search", "chat_history_lookup"):
        return ["t_memory", "mem_hub"], "long memory: " + name
    if name in ("memory", "context_notes"):
        return ["t_memory", "mem_hub"], "memory write"
    if name == "delegate_task":
        return ["t_delegate"], "subagents"
    if name in ("web_search", "web_extract"):
        return ["t_web", "x_internet"], name.replace("_", " ")
    if name.startswith("browser"):
        r = ["t_browser", "x_internet"]
        for sv in SERVICES:
            if not sv.get("local") and sv["rx"].search(low):
                r.append(sv["id"]); break
        return r, "browser"
    if name in ("read_file", "write_file", "patch", "search_files"):
        p = (args.get("path") or "") if isinstance(args, dict) else ""
        vp = VAULT.rstrip("/") + "/"
        if p.startswith(vp) or "obsidian" in p.lower():
            rel = p[len(vp):] if p.startswith(vp) else ""
            top = rel.split("/")[0] if rel else ""
            fn = os.path.basename(p)
            r = ["t_files", "vault_hub"]
            if top and os.path.isdir(f"{VAULT}/{top}"):
                r.append("v_" + top)
            if "n_" + rel in NOTES:
                r.append("n_" + rel)
            return r, ("note: " + fn[:40]) if fn.endswith(".md") else "vault: " + (top or "/")
        m = re.search(r'/skills/(?:[^/]+/)*([^/]+)/(?:SKILL\.md|references|scripts|templates)', p)
        if m:
            return ["t_skills", "sk_hub", "sk_" + m.group(1)], "skill (file): " + m.group(1)
        return ["t_files"], name
    if name in ("terminal", "process_manage"):
        c = (args.get("command") if isinstance(args, dict) else "") or ""
        cl = c.lower().split("<<")[0]
        r = ["t_terminal"]
        m = re.search(r'/skills/(?:[^/ ]+/)*([^/ ]+)/(?:scripts|references|templates|skill\.md)', cl)
        if m:
            return ["t_terminal", "t_skills", "sk_hub", "sk_" + m.group(1)], "skill (script): " + m.group(1)
        remote = bool(re.search(r"\b(ssh|scp|rsync|sftp|sshfs)\b", cl))
        for h in HOSTS:
            if remote and h["rx"].search(cl):
                return r + [h["id"]], "terminal (ssh)"
        for sv in SERVICES:
            if sv["rx"].search(cl):
                return r + ([sv["id"]] if sv.get("local") else ["x_internet", sv["id"]]), "terminal"
        if re.search(r"curl |wget |http", cl):
            r.append("x_internet")
        elif VAULT.lower() in cl or "obsidian" in cl:
            r.append("vault_hub")
        return r, "terminal"
    if name == "execute_code":
        return ["t_code"], "code"
    return ["t_misc"], name


def model_node(m):
    m = (m or "").lower()
    for k in ("haiku", "sonnet", "opus", "deepseek"):
        if k in m:
            return "m_" + k
    return "m_other"


class Poller(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.lock = threading.Lock(); self.events = []; self.seq = 0
        self.lastts = {}; self.heat = {}; self.cur = {}; self.counting = False; self.collect = False
        self.last = {}; self.sess = {}; self.convs = {}
        self.dbs = {}
        self.find_dbs()

    def find_dbs(self):
        for key in AGENTS:
            p = f"{HOME}/state.db" if not key else f"{HOME}/profiles/{key}/state.db"
            if os.path.exists(p):
                self.dbs[key] = p

    def conn(self, p):
        return sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=3)

    def sinfo(self, c, sid):
        if sid not in self.sess:
            r = c.execute("select source,model from sessions where id=?", (sid,)).fetchone()
            self.sess[sid] = r or ("", "")
        return self.sess[sid]

    def conv(self, c, sid):
        """conversation id: sessions continued after compression belong to the same conversation"""
        if sid in self.convs:
            return self.convs[sid]
        cur, seen = sid, 0
        while cur and seen < 60:
            r = c.execute("select parent_session_id from sessions where id=?", (cur,)).fetchone()
            par = r[0] if r else None
            if not par:
                break
            pr = c.execute("select end_reason from sessions where id=?", (par,)).fetchone()
            if not pr or pr[0] != "compression":
                break
            cur, seen = par, seen + 1
        self.convs[sid] = cur
        return cur

    def add_heat(self, path):
        ids = [p for p in path if p]
        for a, b in zip(ids, ids[1:]):
            k = a + "|" + b if a < b else b + "|" + a
            self.heat[k] = self.heat.get(k, 0) + 1

    def emit(self, ev):
        with self.lock:
            self.seq += 1; ev["id"] = self.seq
            if self.counting:
                self.add_heat(ev["path"])
            # trail of the CURRENT conversation (agent+channel); a new conversation clears it
            key = ev.get("agent", "?") + "|" + (ev.get("src") or "?")
            st = self.cur.get(key)
            if not st or st["conv"] != ev.get("conv"):
                st = self.cur[key] = {"conv": ev.get("conv"), "edges": {}, "t": ev.get("t", 0)}
            st["t"] = ev.get("t", 0)
            ids = [x for x in ev["path"] if x]
            for a, b in zip(ids, ids[1:]):
                k = a + "|" + b if a < b else b + "|" + a
                st["edges"][k] = st["edges"].get(k, 0) + 1
            if self.collect:
                return
            self.events.append(ev); self.events = self.events[-400:]

    def process(self, key, c, rows):
        name = AGENTS[key]; ag = agent_node(name)
        for mid, sid, role, tcs, ts in rows:
            if ts > self.lastts.get(name, 0):
                self.lastts[name] = ts
            src, model = self.sinfo(c, sid)
            base = {"t": ts, "agent": name, "sid": sid, "conv": self.conv(c, sid), "src": src or ""}

            def emit(kind, path, label):
                self.emit(dict(base, kind=kind, path=path, label=label))

            if role == "user":
                s = SOURCES.get(src, "src_api")
                emit("in", (["user"] if s in USER_SOURCES else []) + [s, "gateway", ag], "request · " + (src or "?"))
                cont = ""
                try:
                    cont = (c.execute("select content from messages where id=?", (mid,)).fetchone() or [""])[0] or ""
                    for sk in list(set(re.findall(r'The "([a-z0-9_-]+)" skill is auto-loaded', cont)))[:4]:
                        emit("tool", [ag, "sk_hub", "sk_" + sk], "skill (auto): " + sk)
                except sqlite3.Error:
                    pass
                # memory is injected on every turn — gentle flash
                emit("mem", [ag, "mem_hub"], "memory loaded")
                qw = set(re.findall(r"\w{6,}", cont[:600].lower()))
                hit = [k for k, e in enumerate(MEMTXT) if qw & set(re.findall(r"\w{6,}", e.lower()))]
                for k in hit[:3]:
                    emit("mem", [ag, "mem_hub", f"mem_{k}"], "memory: " + MEMTXT[k][:40])
            elif role == "assistant":
                mn = model_node(model)
                emit("think", [ag, mn] + (["x_anthropic", "x_internet"] if mn in ("m_haiku", "m_sonnet", "m_opus") else []),
                     "thinking · " + (model or "?")[:24])
                if tcs:
                    try:
                        calls = json.loads(tcs)
                    except ValueError:
                        calls = []
                    for cl in calls:
                        fn = cl.get("function", {}); nm = fn.get("name", "?")
                        try:
                            args = json.loads(fn.get("arguments") or "{}")
                        except ValueError:
                            args = {}
                        pth, lab = tool_path(nm, args)
                        emit("tool", [ag] + pth, lab)

    Q = "select id,session_id,role,tool_calls,timestamp from messages where id>? and role in ('user','assistant')"

    def seed(self):
        """worn paths: routes from the last 30 days (counted, not streamed)"""
        since = time.time() - 30 * 86400; self.collect = True; self.counting = True
        for key, p in self.dbs.items():
            try:
                c = self.conn(p); lastid = 0
                while True:
                    rows = c.execute(self.Q + " and timestamp>? order by id limit 4000", (lastid, since)).fetchall()
                    if not rows:
                        break
                    lastid = rows[-1][0]; self.process(key, c, rows)
                c.close()
            except sqlite3.Error as e:
                print("seed", key, e)
        self.collect = False; self.counting = False
        print("seed ready, edges:", len(self.heat), flush=True)

    def run(self):
        # start: replay the last ~60 messages of the main agent so the network is alive right away
        for key, p in self.dbs.items():
            try:
                c = self.conn(p)
                mx = c.execute("select max(id) from messages").fetchone()[0] or 0
                self.last[key] = mx
                if not key:
                    rows = c.execute(self.Q + " order by id", (mx - 160,)).fetchall()
                    self.process(key, c, rows[-60:])
                c.close()
            except sqlite3.Error as e:
                print("init", key, e)
        self.seed()
        self.counting = True
        while True:
            for key, p in self.dbs.items():
                try:
                    c = self.conn(p)
                    rows = c.execute(self.Q + " order by id limit 300", (self.last.get(key, 0),)).fetchall()
                    if rows:
                        self.last[key] = rows[-1][0]; self.process(key, c, rows)
                    c.close()
                except sqlite3.Error:
                    pass
            time.sleep(1.2)


CODE_TOOLS = {"write_file", "patch", "terminal", "execute_code", "skill_manage"}


def live_code(limit=40):
    """recent code written by agents: write_file/patch/terminal/execute_code calls (last 2 h)"""
    out = []; since = time.time() - 2 * 3600
    for key, p in POLL.dbs.items():
        try:
            c = POLL.conn(p)
            rows = c.execute("select id,timestamp,tool_calls from messages where role='assistant' and tool_calls is not null and timestamp>? order by id desc limit 120", (since,)).fetchall()
            c.close()
        except sqlite3.Error:
            continue
        for mid, ts, tcs in rows:
            try:
                calls = json.loads(tcs)
            except ValueError:
                continue
            for i, cl in enumerate(calls):
                fn = cl.get("function", {}); nm = fn.get("name", "").replace("mcp__", "")
                if nm not in CODE_TOOLS:
                    continue
                try:
                    a = json.loads(fn.get("arguments") or "{}")
                except ValueError:
                    a = {"raw": fn.get("arguments", "")}
                if nm == "write_file":
                    plik, kod, typ = a.get("path", ""), a.get("content", ""), "nowy plik"
                elif nm == "patch":
                    plik, kod, typ = a.get("path", ""), "--- było\n" + (a.get("old_string") or "") + "\n+++ jest\n" + (a.get("new_string") or ""), "zmiana"
                elif nm == "terminal":
                    plik, kod, typ = (a.get("workdir") or "terminal"), a.get("command", ""), "terminal"
                elif nm == "execute_code":
                    plik, kod, typ = "python", a.get("code", ""), "python"
                else:
                    plik, kod, typ = a.get("name", "skill"), json.dumps(a, ensure_ascii=False, indent=1), "skill"
                out.append({"id": f"{key}:{mid}:{i}", "agent": AGENTS[key], "t": ts, "narzedzie": nm,
                            "plik": plik, "rodzaj": typ, "kod": (kod or "")[:30000]})
    out.sort(key=lambda x: (x["t"], x["id"]), reverse=True)
    return out[:limit]


if DEMO:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import demo_data  # noqa: E402  (builds throw-away state.db files from demo/sessions.json)
    DEMO_STATE = demo_data.prepare(HOME, AGENTS)

POLL = Poller()
GRAPH = {"t": 0, "g": None}
BACKEND = CFG["backend"].strip().rstrip("/")
if BACKEND and not BACKEND.startswith("http"):
    BACKEND = "http://" + BACKEND


def demo_json(name):
    return demo_data.api_json(name) if DEMO else b"{}"


class H(BaseHTTPRequestHandler):
    LISTS = ("/api/zadania", "/api/zakupy", "/api/spotkania", "/api/harmonogram", "/api/pamiec")

    def log_message(self, *a):
        pass

    def _send(self, code, body, ct):
        self.send_response(code); self.send_header("Content-Type", ct); self.send_header("Cache-Control", "no-store")
        self.end_headers(); self.wfile.write(body)

    def _proxy(self, body=None, ctype="application/json", timeout=10):
        """forward /api/... to the optional backend; in demo mode answer from demo/api/*.json"""
        if not BACKEND:
            if DEMO and body is None:
                name = self.path.split("?")[0].strip("/").replace("api/", "").replace("/", "_")
                return self._send(200, demo_json(name), "application/json")
            if DEMO:
                return self._send(200, b'{"demo":true}', "application/json")
            return self._send(503, b'{"detail":"no backend configured (MOZG_BACKEND)"}', "application/json")
        try:
            rq = urllib.request.Request(BACKEND + self.path, data=body, method="POST" if body is not None else "GET",
                                        headers={"Content-Type": ctype})
            with urllib.request.urlopen(rq, timeout=timeout) as r:
                return self._send(200, r.read(), "application/json")
        except urllib.error.HTTPError as e:
            return self._send(e.code, e.read(), "application/json")
        except Exception as e:  # noqa: BLE001
            return self._send(502, json.dumps({"detail": str(e)}).encode(), "application/json")

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 200 << 20:
            return self._send(413, b'{"detail":"too large"}', "application/json")
        if self.path.startswith(self.LISTS) or self.path.startswith("/api/tryb/"):
            return self._proxy(self.rfile.read(n) if n else b"{}")
        if self.path.startswith("/api/plik"):
            return self._proxy(self.rfile.read(n), self.headers.get("Content-Type", ""), timeout=120)
        self._send(404, b"not found", "text/plain")

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            return self._send(200, open(os.path.join(WEB, "index.html"), "rb").read(), "text/html; charset=utf-8")
        if path == "/config.js":
            js = "window.MOZG=" + json.dumps({"backend": BACKEND.split("://", 1)[-1], "demo": DEMO, "main": MAIN}) + ";"
            return self._send(200, js.encode(), "application/javascript")
        if path.startswith(self.LISTS) or path.startswith("/api/tryb/") or path.startswith("/api/komendy/"):
            return self._proxy()
        if path.startswith("/api/boty"):
            if BACKEND:
                return self._proxy(timeout=4)
            return self._send(200, json.dumps([{"id": k or "main", "nazwa": v} for k, v in AGENTS.items()]).encode(), "application/json")
        if path.startswith("/api/czat-demo"):
            return self._send(200, demo_json("czat") if DEMO else b"[]", "application/json")
        if path.startswith("/api/graph"):
            if time.time() - GRAPH["t"] > 60:
                GRAPH["g"] = json.dumps(build_graph(), ensure_ascii=False).encode(); GRAPH["t"] = time.time()
            return self._send(200, GRAPH["g"], "application/json")
        if path.startswith("/api/kod"):
            return self._send(200, json.dumps(live_code(), ensure_ascii=False).encode(), "application/json")
        if path.startswith("/api/radar"):
            with POLL.lock:
                d = {"now": time.time(), "agents": dict(POLL.lastts)}
            return self._send(200, json.dumps(d).encode(), "application/json")
        if path.startswith("/api/heat"):
            with POLL.lock:
                cut = time.time() - 6 * 3600  # conversation trails idle for 6 h fade out
                h = {"all": dict(POLL.heat), "cur": {k: v for k, v in POLL.cur.items() if v["t"] > cut}}
            return self._send(200, json.dumps(h).encode(), "application/json")
        if path.startswith("/events"):
            self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.send_header("Cache-Control", "no-store")
            self.end_headers()
            m = re.search(r"since=(\d+)", self.path); last = int(m.group(1)) if m else 0
            if last == 0:
                with POLL.lock:
                    last = max(0, POLL.seq - 45)
            try:
                while True:
                    with POLL.lock:
                        evs = [e for e in POLL.events if e["id"] > last]
                    for e in evs:
                        self.wfile.write(f"data: {json.dumps(e, ensure_ascii=False)}\n\n".encode()); last = e["id"]
                    if not evs:
                        self.wfile.write(b": ping\n\n")
                    self.wfile.flush(); time.sleep(1)
            except OSError:
                return
        self._send(404, b"not found", "text/plain")


if __name__ == "__main__":
    POLL.start()
    if DEMO:
        demo_data.start_replay(DEMO_STATE)
    print(f"Mózg Hermesa: http://{CFG['host']}:{CFG['port']}/" + ("  (demo)" if DEMO else ""), flush=True)
    ThreadingHTTPServer((CFG["host"], CFG["port"]), H).serve_forever()
