import requests, os, sys, time, threading, json
from flask import Flask, jsonify
import logging

TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    print("Set BOT_TOKEN env var"); sys.exit(1)

TG = f"https://api.telegram.org/bot{TOKEN}"
API = "http://api.arafatcodex.xyz:5004/like"
KEY = os.environ.get("API_KEY", "FREE7DAYS")
CFG = "/tmp/auto_config.json"
offset = 0

logging.basicConfig(level=logging.INFO)

def load():
    try:
        with open(CFG) as f: return json.load(f)
    except: return {}

def save(c):
    with open(CFG, "w") as f: json.dump(c, f, indent=2)

def tg(method, data):
    for _ in range(3):
        try:
            r = requests.post(f"{TG}/{method}", json=data, timeout=15)
            return r.json()
        except: time.sleep(2)
    return None

def send_likes(uid, srv):
    try:
        r = requests.get(API, params={"uid": uid, "server_name": srv, "key": KEY}, timeout=25)
        d = r.json()
        if d.get("status") == 1:
            nick = d.get("PlayerNickname", "Unknown")
            before = d.get("LikesbeforeCommand", 0)
            after = d.get("LikesafterCommand", 0)
            added = d.get("LikesGivenByAPI", 0)
            txt = (f"\u2705 Autolikes Sent Successfully \u2728\n"
                   f"\U0001f464 Name : {nick}\n"
                   f"\U0001f194 UID : {uid}\n"
                   f"\U0001f30d Region : {srv.upper()}\n"
                   f"\u2b05\ufe0f Previous Likes : {before} Likes\n"
                   f"\u2795 Added Likes : {added} Likes\n"
                   f"\U0001f916 Final Likes : {after} Likes")
            return (True, txt)
        elif d.get("status") == 2:
            return (False, f"\u23f3 Cooldown. Current likes: {d.get('LikesafterCommand','?')}")
        return (False, f"\u274c Error: {d}")
    except Exception as e:
        return (False, f"\u274c API error: {e}")

def auto_loop():
    while True:
        try:
            cfg = load()
            for cid, entries in list(cfg.items()):
                changed = False
                for e in entries:
                    if time.time() - e["last_run"] >= e["interval"] * 60:
                        ok, res = send_likes(e["uid"], e["server"])
                        tg("sendMessage", {"chat_id": int(cid), "text": res})
                        short = res.split("\n")[0][:40] if ok else res[:40]
                        hist = e.get("history", [])
                        hist.append({"time": time.time(), "result": short, "ok": ok})
                        e["history"] = hist[-50:]
                        e["last_run"] = time.time()
                        changed = True
                if changed:
                    save(cfg)
        except Exception as ex:
            logging.error(f"Auto loop: {ex}")
        time.sleep(30)

app = Flask(__name__)

@app.route("/")
def home():
    return jsonify({"status": "running", "uptime": time.time() - start_time})

@app.route("/health")
def health():
    return "OK", 200

def bot_poll():
    global offset
    while True:
        try:
            r = requests.get(f"{TG}/getUpdates", params={"offset": offset, "timeout": 30}, timeout=35)
            for u in r.json().get("result", []):
                offset = u["update_id"] + 1
                msg = u.get("message")
                if not msg: continue
                cid = str(msg["chat"]["id"])
                txt = msg.get("text", "").strip()
                low = txt.lower()

                if low == "/start":
                    tg("sendMessage", {"chat_id": cid, "text":
                        "Commands:\n/like UID server\n/autolike UID server interval label\n/stopauto label\n/stopall\n/list\n/status"})
                elif low.startswith("/like"):
                    parts = txt.split()
                    if len(parts) < 2: continue
                    uid, srv = parts[1], parts[2] if len(parts) >= 3 else "sg"
                    tg("sendMessage", {"chat_id": cid, "text": f"Processing {uid} ({srv})..."})
                    _, res = send_likes(uid, srv)
                    tg("sendMessage", {"chat_id": cid, "text": res})
                elif low.startswith("/autolike"):
                    parts = txt.split()
                    if len(parts) < 3: continue
                    uid, srv = parts[1], parts[2]
                    interval = int(parts[3]) if len(parts) >= 4 else 1440
                    label = parts[4] if len(parts) >= 5 else uid
                    cfg = load()
                    entries = cfg.get(cid, [])
                    for e in entries:
                        if e["label"] == label:
                            e.update({"uid": uid, "server": srv, "interval": interval, "last_run": 0})
                            break
                    else:
                        entries.append({"label": label, "uid": uid, "server": srv, "interval": interval, "last_run": 0, "history": []})
                    cfg[cid] = entries
                    save(cfg)
                    tg("sendMessage", {"chat_id": cid, "text": f"Auto-like added: {label} -> {uid} every {interval}min"})
                elif low.startswith("/stopauto"):
                    parts = txt.split()
                    if len(parts) < 2: continue
                    label = parts[1]
                    cfg = load()
                    entries = cfg.get(cid, [])
                    cfg[cid] = [e for e in entries if e["label"] != label]
                    save(cfg)
                    tg("sendMessage", {"chat_id": cid, "text": f"Stopped: {label}"})
                elif low == "/stopall":
                    cfg = load()
                    cfg.pop(cid, None)
                    save(cfg)
                    tg("sendMessage", {"chat_id": cid, "text": "All stopped."})
                elif low == "/list":
                    cfg = load()
                    entries = cfg.get(cid, [])
                    if not entries:
                        tg("sendMessage", {"chat_id": cid, "text": "No auto-like entries."})
                    else:
                        lines = [f"Your entries ({len(entries)}):"]
                        for e in entries:
                            last = time.strftime("%m-%d %H:%M", time.localtime(e["last_run"])) if e["last_run"] else "never"
                            lines.append(f"  [{e['label']}] {e['uid']} @ {e['server']} every {e['interval']}m (last: {last})")
                        tg("sendMessage", {"chat_id": cid, "text": "\n".join(lines)})
                elif low == "/status":
                    cfg = load()
                    if not cfg:
                        tg("sendMessage", {"chat_id": cid, "text": "No configs."})
                    else:
                        lines = ["=== All Auto-Like ==="]
                        for c, entries in cfg.items():
                            lines.append(f"\nUser {c[-6:]} ({len(entries)}):")
                            for e in entries:
                                last = time.strftime("%m-%d %H:%M", time.localtime(e["last_run"])) if e["last_run"] else "never"
                                hist = e.get("history", [])
                                ok = sum(1 for h in hist if h.get("ok"))
                                lines.append(f"  [{e['label']}] {e['uid']} | {e['interval']}m | last: {last} | runs:{len(hist)} ok:{ok}")
                                for h in hist[-3:]:
                                    t = time.strftime("%m-%d %H:%M", time.localtime(h["time"]))
                                    lines.append(f"    {t} {'OK' if h['ok'] else '--'} {h['result'][:60]}")
                        for chunk in ["\n".join(lines)[i:i+4000] for i in range(0, len("\n".join(lines)), 4000)]:
                            tg("sendMessage", {"chat_id": cid, "text": chunk})
        except Exception as ex:
            logging.error(f"Poll: {ex}")
            time.sleep(5)

start_time = time.time()
threading.Thread(target=auto_loop, daemon=True).start()
threading.Thread(target=bot_poll, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
