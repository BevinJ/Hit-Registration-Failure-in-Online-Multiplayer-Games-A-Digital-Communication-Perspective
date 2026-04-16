# ⚡ Hit Registration Simulator

Real-time FPS networking simulation — client-side prediction, lag compensation,
packet loss rollback, and server-authoritative hit validation.

## Files

```
server.py        ← Python async WebSocket server (Socket.IO + aiohttp)
index.html       ← Frontend (vanilla HTML/CSS/JS — no build step)
requirements.txt ← Python dependencies
```

---

## Quick Start

### 1 · Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2 · Run the server

```bash
python server.py
```

You should see:
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ⚡  HIT REGISTRATION SIMULATOR — SERVER
      http://localhost:5000
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### 3 · Open the frontend

Navigate to **http://localhost:5001** in your browser.

For **multiplayer** (two real players): open the same URL in a **second browser tab**
or on a second machine on the same network (replace `localhost` with the server's IP).

---

## Standalone Mode (no server)

If the server is not running, the frontend automatically falls back to
**standalone mode** — all network effects (latency, packet loss, lag compensation)
are simulated locally in the browser. The connection badge turns yellow.

---

## Concepts Demonstrated

| Concept | Where |
|---|---|
| **Client-side prediction** | Blood / muzzle flash appear before server reply |
| **Server authority** | Python `eval_hit()` is the final word on HIT/MISS |
| **Lag compensation** | Server rewinds to past player positions via `pos_history` |
| **Packet loss rollback** | Unconfirmed blood is removed when a packet is dropped |
| **Reconciliation** | Client corrects HP and blood when server disagrees with prediction |
| **Network presets** | Good / Normal / Bad / Chaos — adjustable live |
| **Prediction mismatch rate** | Sidebar shows % of shots where client & server disagreed |

---

## Architecture

```
Browser (index.html)                  Python (server.py)
─────────────────────                 ──────────────────
Click → shoot()                       
  • client prediction (evalHit)       
  • bullet animation                  
  • blood splatter (unconfirmed)      
  • socket.emit('shoot', data)  ────► receive 'shoot' event
                                        asyncio.sleep(latency)   ← simulated RTT
                                        random packet drop check
                                        rewind position history  ← lag compensation
                                        server evalHit()
                                        update game_state
                                        emit('shot_result', ev)  ──► all clients
handleResult(data)  ◄───────────────
  • confirm or rollback blood
  • apply server-authoritative HP
  • update event log
  • update mismatch stats
```

---

## Network Presets

| Mode   | Latency     | Packet Loss |
|--------|-------------|-------------|
| Good   | 15–60 ms    | 2 %         |
| Normal | 50–160 ms   | 10 %        |
| Bad    | 150–320 ms  | 27 %        |
| Chaos  | 300–750 ms  | 47 %        |

---

## Requirements

- Python 3.10+
- `python-socketio[asyncio_client]` ≥ 5.11
- `aiohttp` ≥ 3.9
- Modern browser (Chrome / Firefox / Edge)
