"""
Hit Registration Simulator — Python/Socket.IO Backend
Run: python server.py
Open: http://localhost:5000
"""
import asyncio
import random
import math
import time
from pathlib import Path
from aiohttp import web
import socketio

# SERVER SETUP
sio = socketio.AsyncServer(
    cors_allowed_origins="*",
    async_mode="aiohttp",
    logger=False,
    engineio_logger=False,
)
app = web.Application()
sio.attach(app)

# HITBOX CONSTANTS  (must match index.html)
HEAD_R  = 20
HEAD_OY = -44        
BODY_W  = 38
BODY_H  = 70

SPAWN = {
    "player1": {"x": 120, "y": 180},
    "player2": {"x": 580, "y": 180},
}

# NETWORK SIMULATION PRESETS
NET_MODES = {
    "good":   {"min_ms": 15,  "max_ms": 60,  "loss": 0.02},
    "normal": {"min_ms": 50,  "max_ms": 160, "loss": 0.10},
    "bad":    {"min_ms": 150, "max_ms": 320, "loss": 0.27},
    "chaos":  {"min_ms": 300, "max_ms": 750, "loss": 0.47},
}

# SHARED GAME STATE
players: dict[str, str] = {}   

game_state = {
    "player1": {"health": 100, **SPAWN["player1"]},
    "player2": {"health": 100, **SPAWN["player2"]},
}

# Lag-compensation history  [{ts, player1: {x,y}, player2: {x,y}},]
pos_history: list[dict] = []

event_log: list[dict] = []


# HELPERS
def record_positions() -> None:
    pos_history.append({
        "ts":      time.time(),
        "player1": dict(game_state["player1"]),
        "player2": dict(game_state["player2"]),
    })
    # Keep only last 5 seconds
    cut = time.time() - 5.0
    while pos_history and pos_history[0]["ts"] < cut:
        pos_history.pop(0)


def rewind_to(shot_ts: float) -> tuple[dict, dict]:
    """Return player positions at the time of the shot (lag compensation)."""
    if not pos_history:
        return game_state["player1"], game_state["player2"]
    best = min(pos_history, key=lambda h: abs(h["ts"] - shot_ts))
    return best["player1"], best["player2"]


def eval_hit(ax: float, ay: float, target: str,
             off_x: float = 0.0, off_y: float = 0.0) -> str:
    """Server-authoritative hit detection with optional lag-compensation offset."""
    p  = game_state[target]
    px = p["x"] + off_x
    py = p["y"] + off_y

    # Head check
    if math.hypot(ax - px, ay - (py + HEAD_OY)) <= HEAD_R:
        return "HEADSHOT"

    # Body check
    if px - BODY_W / 2 <= ax <= px + BODY_W / 2:
        if py - BODY_H / 2 <= ay <= py + BODY_H / 2:
            return "HIT"

    return "MISS"


def role_for_new_client() -> str:
    taken = {r for r in players.values() if r in ("player1", "player2")}
    for r in ("player1", "player2"):
        if r not in taken:
            return r
    return "spectator"


def player_count() -> int:
    return sum(1 for r in players.values() if r in ("player1", "player2"))


# SOCKET.IO EVENTS
@sio.event
async def connect(sid: str, environ: dict) -> None:
    role = role_for_new_client()
    players[sid] = role
    record_positions()

    await sio.emit("role_assigned", {
        "role":         role,
        "player_count": player_count(),
        "state":        game_state,
    }, to=sid)

    await sio.emit("player_joined", {
        "role":         role,
        "player_count": player_count(),
    })
    print(f"[+] {sid[:8]}  →  {role}  ({player_count()}/2 players)")


@sio.event
async def disconnect(sid: str) -> None:
    role = players.pop(sid, "unknown")
    cnt  = player_count()
    await sio.emit("player_left", {"role": role, "player_count": cnt})
    print(f"[-] {sid[:8]}  disconnected ({role})  ({cnt}/2 players)")


@sio.event
async def shoot(sid: str, data: dict) -> None:
    shooter    = data["shooter"]
    target     = data["target"]
    aim_x      = float(data["aim_x"])
    aim_y      = float(data["aim_y"])
    shot_ts    = float(data.get("timestamp", time.time()))
    prediction = data.get("prediction", "UNKNOWN")
    net_mode   = data.get("net_mode", "normal")

    cfg       = NET_MODES.get(net_mode, NET_MODES["normal"])
    lat_s     = random.uniform(cfg["min_ms"], cfg["max_ms"]) / 1000.0

    # Simulate round-trip latency
    await asyncio.sleep(lat_s)
    lat_ms = int(lat_s * 1000)

    # ── Packet loss ──────────────────────────────────────────
    if random.random() < cfg["loss"]:
        await sio.emit("shot_result", {
            "result":     "LOST",
            "shooter":    shooter,
            "target":     target,
            "latency":    lat_ms,
            "prediction": prediction,
            "aim_x":      aim_x,
            "aim_y":      aim_y,
        })
        print(f"  ✗ PKT LOST  {shooter}→{target}  {lat_ms}ms")
        return

    # ── Lag compensation ─────────────────────────────────────
    p1_past, p2_past = rewind_to(shot_ts)
    past = {"player1": p1_past, "player2": p2_past}

    off_x = past[target]["x"] - game_state[target]["x"] + random.uniform(-3, 3)
    off_y = past[target]["y"] - game_state[target]["y"] + random.uniform(-3, 3)

    # ── Server-authoritative hit detection ───────────────────
    result = eval_hit(aim_x, aim_y, target, off_x, off_y)
    damage = {"HIT": 22, "HEADSHOT": 40}.get(result, 0)

    if damage:
        game_state[target]["health"] = max(0, game_state[target]["health"] - damage)

    record_positions()

    ev = {
        "result":       result,
        "shooter":      shooter,
        "target":       target,
        "aim_x":        aim_x,
        "aim_y":        aim_y,
        "damage":       damage,
        "latency":      lat_ms,
        "prediction":   prediction,
        "health":       game_state[target]["health"],
        "lag_offset_x": round(off_x, 2),
        "lag_offset_y": round(off_y, 2),
    }
    event_log.append({**ev, "ts": time.time()})
    if len(event_log) > 500:
        event_log.pop(0)

    # Broadcast to ALL connected clients so both screens update
    await sio.emit("shot_result", ev)

    icon = {"HIT": "●", "HEADSHOT": "◆", "MISS": "○"}.get(result, "?")
    mismatch = " ⚠ MISMATCH" if result != prediction else ""
    print(f"  {icon} {result:8s}  {shooter}→{target}  {lat_ms}ms{mismatch}")


@sio.event
async def reset_game(sid: str, data: dict = None) -> None:
    game_state["player1"]["health"] = 100
    game_state["player2"]["health"] = 100
    event_log.clear()
    pos_history.clear()
    await sio.emit("game_reset", {"state": game_state})
    print("  ↺ Game reset")


# STATIC FILE — serve index.html at root
async def serve_index(request: web.Request) -> web.FileResponse:
    path = Path(__file__).parent / "index.html"
    if not path.exists():
        return web.Response(text="index.html not found — place it next to server.py", status=404)
    return web.FileResponse(path)


app.router.add_get("/", serve_index)


# ENTRY POINT
if __name__ == "__main__":
    HOST, PORT = "0.0.0.0", 5001
    print("━" * 46)
    print("  ⚡  HIT REGISTRATION SIMULATOR — SERVER")
    print(f"      http://localhost:{PORT}")
    print("━" * 46)
    print("  Open two browser tabs for multiplayer.")
    print("  Press  Ctrl-C  to stop.\n")
    web.run_app(app, host=HOST, port=PORT, print=lambda *_: None)
