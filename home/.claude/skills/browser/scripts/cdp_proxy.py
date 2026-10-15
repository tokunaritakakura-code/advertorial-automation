#!/usr/bin/env python3
"""cdp_proxy — 127.0.0.1:<from> を 127.0.0.1:<to> に中継する（裏用の 9333 を本人の Dia の 9222 に繋ぐ）。
本人の画面を動かす HTTP の呼び出しだけは中継しない（本人 2026-10-07「勝手に切り替わる」）:
  /json/activate/<id> … 何もせず「済んだ」と返す
  /json/new?<url>     … 本人の窓で前に出さず、裏のタブ（background）で開いて同じ形の JSON を返す
"""
import asyncio, json, socket, sys, threading, urllib.request
FROM, TO = int(sys.argv[1]), int(sys.argv[2])

def pipe(a, b):
    try:
        while (d := a.recv(65536)):
            b.sendall(d)
    except OSError:
        pass
    finally:
        for s in (a, b):
            try: s.shutdown(socket.SHUT_RDWR)
            except OSError: pass

def reply(c, status, body):
    b = body.encode()
    c.sendall(f"HTTP/1.1 {status}\r\nContent-Type: application/json; charset=UTF-8\r\nContent-Length: {len(b)}\r\nConnection: close\r\n\r\n".encode() + b)
    c.close()

def new_background(url):
    import websockets
    ws_url = json.load(urllib.request.urlopen(f"http://127.0.0.1:{TO}/json/version", timeout=5))["webSocketDebuggerUrl"]
    async def go():
        async with websockets.connect(ws_url, max_size=2**24) as ws:
            await ws.send(json.dumps({"id": 1, "method": "Target.createTarget", "params": {"url": url or "about:blank", "background": True}}))
            while True:
                m = json.loads(await ws.recv())
                if m.get("id") == 1: return m["result"]["targetId"]
    tid = asyncio.run(go())
    for t in json.load(urllib.request.urlopen(f"http://127.0.0.1:{TO}/json/list", timeout=5)):
        if t["id"] == tid: return t
    return {"id": tid}

def handle(c):
    try:
        c.settimeout(5); first = c.recv(65536); c.settimeout(None)
    except OSError:
        c.close(); return
    line = first.split(b"\r\n", 1)[0].decode("latin-1")
    parts = line.split(" ")
    path = parts[1] if len(parts) > 1 else ""
    if path.startswith("/json/activate/"):
        return reply(c, "200 OK", '"Target activated"')
    if path.startswith("/json/new"):
        try:
            url = path.split("?", 1)[1] if "?" in path else ""
            return reply(c, "200 OK", json.dumps(new_background(url)))
        except Exception as e:
            return reply(c, "500 Internal Server Error", json.dumps({"error": str(e)[:200]}))
    try:
        u = socket.create_connection(("127.0.0.1", TO), timeout=5); u.settimeout(None)
    except OSError:
        c.close(); return
    u.sendall(first)
    threading.Thread(target=pipe, args=(c, u), daemon=True).start()
    pipe(u, c)

srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("127.0.0.1", FROM)); srv.listen(64)
while True:
    c, _ = srv.accept()
    threading.Thread(target=handle, args=(c,), daemon=True).start()
