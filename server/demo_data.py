"""Demo mode: builds throw-away Hermes-like state.db files from demo/sessions.json
and keeps "replaying" fictional agent turns so the brain is alive without a real Hermes.

All data in demo/ is invented.
"""
import datetime as dt
import json
import os
import random
import re
import sqlite3
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO_DIR = os.path.join(ROOT, "demo")

SCHEMA = """
create table if not exists sessions(id text primary key, source text, model text,
    parent_session_id text, end_reason text, started_at real);
create table if not exists messages(id integer primary key autoincrement, session_id text,
    role text, content text, tool_calls text, timestamp real);
"""


def _load_script():
    with open(os.path.join(DEMO_DIR, "sessions.json"), encoding="utf-8") as f:
        return json.load(f)


def _subst(obj, vault):
    if isinstance(obj, str):
        return obj.replace("{vault}", vault).replace("{hermes}", os.path.join(DEMO_DIR, "hermes"))
    if isinstance(obj, list):
        return [_subst(x, vault) for x in obj]
    if isinstance(obj, dict):
        return {k: _subst(v, vault) for k, v in obj.items()}
    return obj


def _db_path(home, key):
    return os.path.join(home, "state.db") if not key else os.path.join(home, "profiles", key, "state.db")


def _insert_turn(c, turn, ts, sid, vault):
    c.execute("insert or ignore into sessions(id,source,model,started_at) values(?,?,?,?)",
              (sid, turn.get("source", "cli"), turn.get("model", "claude-sonnet"), ts))
    c.execute("insert into messages(session_id,role,content,tool_calls,timestamp) values(?,?,?,?,?)",
              (sid, "user", turn.get("user", ""), None, ts))
    calls = []
    for i, (name, args) in enumerate(turn.get("tools", [])):
        calls.append({"id": f"call_{i}", "type": "function",
                      "function": {"name": name, "arguments": json.dumps(_subst(args, vault), ensure_ascii=False)}})
    c.execute("insert into messages(session_id,role,content,tool_calls,timestamp) values(?,?,?,?,?)",
              (sid, "assistant", turn.get("answer", ""), json.dumps(calls) if calls else None, ts + 2))


def prepare(home, agents):
    """create fresh state.db files with ~30 days of fictional history"""
    script = _load_script()
    vault = os.path.join(DEMO_DIR, "vault")
    rnd = random.Random(42)
    now = time.time()
    paths = {}
    for key in agents:
        p = _db_path(home, key)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        if os.path.exists(p):
            os.remove(p)
        c = sqlite3.connect(p)
        c.executescript(SCHEMA)
        turns = [t for t in script["turns"] if t.get("agent", "") == key] or script["turns"][:2]
        for d in range(30, 0, -1):
            for k in range(rnd.randint(1, 4) if not key else rnd.randint(0, 2)):
                t = rnd.choice(turns)
                _insert_turn(c, t, now - d * 86400 + k * 1800, f"demo-{key or 'main'}-{d}", vault)
        c.commit(); c.close()
        paths[key] = p
    return {"paths": paths, "script": script, "vault": vault}


def start_replay(state, every=4.0):
    """append one scripted turn every few seconds (looping) — the UI animates it live"""
    def run():
        turns = state["script"]["turns"]; i = 0
        while True:
            t = turns[i % len(turns)]; key = t.get("agent", "")
            p = state["paths"].get(key)
            if p:
                try:
                    c = sqlite3.connect(p, timeout=3)
                    _insert_turn(c, t, time.time(), f"demo-{key or 'main'}-live-{i // len(turns)}", state["vault"])
                    c.commit(); c.close()
                except sqlite3.Error as e:
                    print("demo replay:", e)
            i += 1
            time.sleep(every)
    threading.Thread(target=run, daemon=True).start()


def api_json(name):
    """demo answers for the side panel; "{d+N}" = today + N days, "{t-N}" = now - N minutes"""
    p = os.path.join(DEMO_DIR, "api", name + ".json")
    if not os.path.isfile(p):
        return b"{}"
    txt = open(p, encoding="utf-8").read()
    today = dt.date.today()
    txt = re.sub(r"\{d([+-]\d+)\}", lambda m: (today + dt.timedelta(days=int(m.group(1)))).isoformat(), txt)
    txt = re.sub(r'"\{t-(\d+)\}"', lambda m: str(int(time.time() - 60 * int(m.group(1)))), txt)
    return txt.encode()
