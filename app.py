#!/usr/bin/env python3
"""Jogo Reverso — adivinhe a música que está tocando ao contrário.

Servidor local: admin (PC com caixa de som) + jogadores (celular, só o botão).
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import random
import re
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

import uvicorn
from fastapi import (Body, FastAPI, Header, HTTPException, Request, WebSocket,
                     WebSocketDisconnect)
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE = Path(__file__).resolve().parent
STATIC = BASE / "static"
DATA = BASE / "data"
MEDIA = BASE / "media"
RAW = MEDIA / "raw"
for _d in (DATA, MEDIA, RAW):
    _d.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA / "db.json"
ADMIN_KEY = os.environ.get("JOGO_KEY", "troque-esta-chave")
PUBLIC_HOST = os.environ.get("JOGO_HOST", "192.168.0.81")
PORT = int(os.environ.get("JOGO_PORT", "8099"))

# yt-dlp precisa de um JS runtime pra resolver os formatos do YouTube.
_YTDLP_VENV = BASE / ".venv" / "bin" / "yt-dlp"
YTDLP = os.environ.get("JOGO_YTDLP") or (str(_YTDLP_VENV) if _YTDLP_VENV.exists() else "yt-dlp")
NODE = os.environ.get("JOGO_NODE") or "/home/miguel/.hermes/node/bin/node"
YT_ARGS = ["--js-runtimes", f"node:{NODE}", "--remote-components", "ejs:github",
           "--no-warnings", "--no-update"]

DEFAULT_DB: dict[str, Any] = {
    "settings": {"value": 1, "offset": 45},
    "tracks": [],
    "players": {},
    "cursor": -1,
    "phase": "idle",        # idle | armed | buzzed | reveal
    "buzzer": None,
    "revealed": False,
    "judge": {"seq": 0, "pid": None, "ok": None},
    "started": False,
}

LOCK = asyncio.Lock()


# --------------------------------------------------------------------------
# persistência
# --------------------------------------------------------------------------
def load_db() -> dict[str, Any]:
    if DB_PATH.exists():
        try:
            db = json.loads(DB_PATH.read_text("utf-8"))
            if "started" not in db:
                # jogo já em andamento quando o campo passou a existir
                db["started"] = bool(db.get("cursor", -1) >= 0 or db.get("phase", "idle") != "idle")
            for k, v in DEFAULT_DB.items():
                db.setdefault(k, json.loads(json.dumps(v)))
            for k, v in DEFAULT_DB["settings"].items():
                db["settings"].setdefault(k, v)
            return db
        except Exception:
            pass
    return json.loads(json.dumps(DEFAULT_DB))


DB = load_db()


def save() -> None:
    tmp = DB_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(DB, ensure_ascii=False, indent=1), "utf-8")
    tmp.replace(DB_PATH)


# --------------------------------------------------------------------------
# hub de websockets
# --------------------------------------------------------------------------
class Hub:
    def __init__(self) -> None:
        self.conns: dict[WebSocket, dict[str, Any]] = {}

    async def add(self, ws: WebSocket, role: str, pid: Optional[str] = None) -> None:
        self.conns[ws] = {"role": role, "pid": pid}

    def drop(self, ws: WebSocket) -> None:
        self.conns.pop(ws, None)

    def online(self) -> set[str]:
        return {m["pid"] for m in self.conns.values() if m.get("pid")}

    async def push(self) -> None:
        payloads = {}
        for ws, meta in list(self.conns.items()):
            role = meta["role"]
            if role not in payloads:
                payloads[role] = ({
                    "type": "state",
                    "state": admin_state(),
                } if role == "admin" else {
                    "type": "state",
                    "state": public_state(),
                })
            try:
                await ws.send_json(payloads[role])
            except Exception:
                self.drop(ws)

    async def cmd(self, role: str, msg: dict[str, Any]) -> None:
        for ws, meta in list(self.conns.items()):
            if meta["role"] != role:
                continue
            try:
                await ws.send_json(msg)
            except Exception:
                self.drop(ws)


HUB = Hub()


# --------------------------------------------------------------------------
# estado
# --------------------------------------------------------------------------
def current_track() -> Optional[dict[str, Any]]:
    i = DB["cursor"]
    if 0 <= i < len(DB["tracks"]):
        return DB["tracks"][i]
    return None


def cur_id() -> Optional[str]:
    i = DB["cursor"]
    if 0 <= i < len(DB["tracks"]):
        return DB["tracks"][i]["id"]
    return None


def fix_cursor(cid: Optional[str]) -> None:
    """Recoloca o cursor na mesma faixa depois de mexer na ordem."""
    if cid is not None:
        for i, t in enumerate(DB["tracks"]):
            if t["id"] == cid:
                DB["cursor"] = i
                return
    DB["cursor"] = min(DB["cursor"], len(DB["tracks"]) - 1)
    if not DB["tracks"]:
        DB["cursor"] = -1


def player_list() -> list[dict[str, Any]]:
    online = HUB.online()
    out = [
        {"id": pid, "name": p["name"], "score": p["score"], "online": pid in online}
        for pid, p in DB["players"].items()
    ]
    out.sort(key=lambda x: (-x["score"], x["name"].lower()))
    return out


def buzzer_obj() -> Optional[dict[str, Any]]:
    pid = DB["buzzer"]
    if pid and pid in DB["players"]:
        return {"id": pid, "name": DB["players"][pid]["name"]}
    return None


def public_state() -> dict[str, Any]:
    t = current_track()
    reveal = bool(DB["revealed"])
    return {
        "phase": DB["phase"],
        "cursor": DB["cursor"],
        "total": sum(1 for x in DB["tracks"]),
        "buzzer": buzzer_obj(),
        "players": player_list(),
        "revealed": reveal,
        "started": bool(DB.get("started")),
        "judge": DB.get("judge") or {"seq": 0, "pid": None, "ok": None},
        "value": DB["settings"]["value"],
        "track": ({"title": t.get("title") if reveal else None,
                   "url": t.get("source_url") if reveal else None}
                  if t else None),
    }


def admin_state() -> dict[str, Any]:
    s = public_state()
    t = current_track()
    s["join_url"] = f"http://{PUBLIC_HOST}:{PORT}/"
    s["current"] = ({"id": t["id"], "title": t.get("title"),
                     "status": t["status"], "offset": t.get("offset"),
                     "duration": t.get("duration"),
                     "source_url": t.get("source_url"),
                     "error": t.get("error")} if t else None)
    s["queue"] = [{"id": x["id"], "title": x.get("title") or x.get("ytid"),
                   "status": x["status"], "duration": x.get("duration"),
                   "offset": x.get("offset"), "error": x.get("error")}
                  for x in DB["tracks"]]
    s["settings"] = dict(DB["settings"])
    return s


def check_key(x_key: Optional[str] = Header(default=None), k: Optional[str] = None) -> None:
    if x_key != ADMIN_KEY and k != ADMIN_KEY:
        raise HTTPException(401, "chave inválida")


# --------------------------------------------------------------------------
# processamento de mídia
# --------------------------------------------------------------------------
def ytid_of(url: str) -> Optional[str]:
    m = re.search(r"(?:v=|youtu\.be/|/shorts/|/embed/)([A-Za-z0-9_-]{11})", url)
    return m.group(1) if m else None


async def run(*cmd: str, timeout: int = 900) -> tuple[int, str, str]:
    p = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(p.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        p.kill()
        return 124, "", "timeout"
    return p.returncode, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")


async def probe_duration(path: Path) -> float:
    rc, out, _ = await run("ffprobe", "-v", "error", "-show_entries",
                           "format=duration", "-of",
                           "default=nw=1:nk=1", str(path))
    try:
        return float(out.strip())
    except Exception:
        return 0.0


async def process_track(tid: str) -> None:
    t = next((x for x in DB["tracks"] if x["id"] == tid), None)
    if not t:
        return
    try:
        t["status"] = "baixando"
        t.pop("error", None)
        save()
        await HUB.push()

        raw = RAW / f"{t['ytid']}.mp3"
        if not raw.exists() or raw.stat().st_size < 20000:
            old = list(RAW.glob(f"{t['ytid']}.*"))
            for f in old:
                if f != raw:
                    f.unlink(missing_ok=True)
            rc, out, err = await run(
                YTDLP, *YT_ARGS, "-f", "bestaudio/best", "-x", "--audio-format", "mp3",
                "--audio-quality", "4", "--no-playlist", "--quiet",
                "-o", str(RAW / f"{t['ytid']}.%(ext)s"),
                f"https://www.youtube.com/watch?v={t['ytid']}")
            if rc != 0 or not raw.exists():
                t["status"] = "erro"
                t["error"] = (err or out or "falha no download").strip()[-240:]
                save()
                await HUB.push()
                return

        dur = await probe_duration(raw)
        if dur <= 0:
            t["status"] = "erro"
            t["error"] = "não consegui ler o áudio"
            save()
            await HUB.push()
            return
        t["duration"] = round(dur)

        clip = 60.0
        max_start = max(0.0, dur - clip - 1)
        off = float(t.get("offset") or DB["settings"]["offset"] or 45)
        off = min(off, max_start)
        t["offset"] = round(off)

        out_path = MEDIA / f"{tid}.mp3"
        tmp_path = MEDIA / f"{tid}.tmp.mp3"
        plain_path = MEDIA / f"{tid}_n.mp3"
        tmp_plain = MEDIA / f"{tid}_n.tmp.mp3"

        # trecho normal (para ouvir depois do acerto/erro)
        rc, out, err = await run(
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-ss", f"{off:.2f}", "-t", f"{clip:.2f}", "-i", str(raw),
            "-ac", "2", "-ar", "44100",
            "-c:a", "libmp3lame", "-b:a", "160k", str(tmp_plain))
        if rc != 0 or not tmp_plain.exists():
            t["status"] = "erro"
            t["error"] = (err or "falha no ffmpeg (normal)").strip()[-240:]
            save()
            await HUB.push()
            return
        tmp_plain.replace(plain_path)

        # trecho invertido (o jogo em si)
        rc, out, err = await run(
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-ss", f"{off:.2f}", "-t", f"{clip:.2f}", "-i", str(raw),
            "-af", "areverse", "-ac", "2", "-ar", "44100",
            "-c:a", "libmp3lame", "-b:a", "160k", str(tmp_path))
        if rc != 0 or not tmp_path.exists():
            t["status"] = "erro"
            t["error"] = (err or "falha no ffmpeg").strip()[-240:]
            save()
            await HUB.push()
            return
        tmp_path.replace(out_path)
        t["status"] = "pronto"
        save()
    except Exception as e:  # noqa: BLE001
        t["status"] = "erro"
        t["error"] = str(e)[:240]
        save()
    finally:
        await HUB.push()


JOB_Q: asyncio.Queue[str] = asyncio.Queue()


async def worker() -> None:
    while True:
        tid = await JOB_Q.get()
        try:
            await process_track(tid)
        except Exception:
            pass
        finally:
            JOB_Q.task_done()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # jobs interrompidos voltam para a fila
    for t in DB["tracks"]:
        if t["status"] in ("baixando", "fila"):
            t["status"] = "fila"
            JOB_Q.put_nowait(t["id"])
    save()
    task = asyncio.create_task(worker())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(title="Jogo Reverso", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


# --------------------------------------------------------------------------
# modelos
# --------------------------------------------------------------------------
class AuthIn(BaseModel):
    key: str


class JoinIn(BaseModel):
    name: str


class JudgeIn(BaseModel):
    ok: bool


class ScoreIn(BaseModel):
    pid: str
    delta: int


class QueueIn(BaseModel):
    url: str


class OffsetIn(BaseModel):
    offset: int


class SettingsIn(BaseModel):
    value: Optional[int] = None
    offset: Optional[int] = None


# --------------------------------------------------------------------------
# páginas
# --------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def play_page():
    return HTMLResponse((STATIC / "play.html").read_text("utf-8"))


@app.get("/admin", response_class=HTMLResponse)
async def admin_page():
    return HTMLResponse((STATIC / "admin.html").read_text("utf-8"))


@app.get("/tv", response_class=HTMLResponse)
async def tv_page():
    return HTMLResponse((STATIC / "tv.html").read_text("utf-8"))


@app.get("/health")
async def health():
    return {"ok": True, "tracks": len(DB["tracks"]),
            "phase": DB["phase"], "players": len(DB["players"])}


@app.get("/media/normal/{tid}.mp3")
async def media_normal(tid: str):
    p = MEDIA / f"{tid}_n.mp3"
    if not p.exists():
        raise HTTPException(404, "trecho normal não gerado")
    return FileResponse(p, media_type="audio/mpeg",
                        headers={"Cache-Control": "no-store"})


@app.get("/media/{tid}.mp3")
async def media(tid: str):
    p = MEDIA / f"{tid}.mp3"
    if not p.exists():
        raise HTTPException(404, "faixa não pronta")
    return FileResponse(p, media_type="audio/mpeg",
                        headers={"Cache-Control": "no-store"})


@app.get("/api/qr")
async def qr():
    try:
        import qrcode
        img = qrcode.make(f"http://{PUBLIC_HOST}:{PORT}/")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return Response(buf.getvalue(), media_type="image/png")
    except Exception:
        raise HTTPException(500, "qr indisponível")


@app.get("/api/state")
async def state_public():
    return public_state()


@app.get("/api/admin/state")
async def state_admin(_=Header(default=None, alias="X-Key")):
    check_key(_)
    return admin_state()


class BuzzIn(BaseModel):
    token: str


@app.post("/api/buzz")
async def buzz_http(body: BuzzIn):
    """Fallback HTTP do buzz, caso o websocket do celular caia."""
    pid = next((p for p, d in DB["players"].items()
                if secrets.compare_digest(d["token"], body.token)), None)
    if not pid:
        raise HTTPException(401, "sessão inválida")
    if DB["phase"] != "armed":
        return {"ok": False, "reason": DB["phase"]}
    DB["phase"] = "buzzed"
    DB["buzzer"] = pid
    DB["revealed"] = False
    save()
    await HUB.push()
    await HUB.cmd("admin", {"type": "cmd", "cmd": "pause"})
    return {"ok": True}


# --------------------------------------------------------------------------
# auth / entrada
# --------------------------------------------------------------------------
@app.post("/api/auth")
async def auth(body: AuthIn):
    if not secrets.compare_digest(body.key, ADMIN_KEY):
        raise HTTPException(401, "chave inválida")
    return {"ok": True}


@app.post("/api/join")
async def join(body: JoinIn):
    name = body.name.strip()[:24]
    if len(name) < 2:
        raise HTTPException(400, "nome muito curto")
    low = name.lower()
    for pid, p in DB["players"].items():
        if p["name"].lower() == low:
            return {"pid": pid, "token": p["token"], "name": p["name"]}
    pid = secrets.token_hex(4)
    token = secrets.token_urlsafe(16)
    DB["players"][pid] = {"name": name, "score": 0, "token": token}
    save()
    await HUB.push()
    return {"pid": pid, "token": token, "name": name}


# --------------------------------------------------------------------------
# websocket
# --------------------------------------------------------------------------
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    q = ws.query_params
    role = q.get("role", "player")

    if role == "admin":
        if not secrets.compare_digest(q.get("k", ""), ADMIN_KEY):
            await ws.send_json({"type": "error", "msg": "chave inválida"})
            await ws.close()
            return
        await HUB.add(ws, "admin")
        await HUB.push()
        try:
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            HUB.drop(ws)
            await HUB.push()
        return

    if role == "tv":
        await HUB.add(ws, "tv")
        await HUB.push()
        try:
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            HUB.drop(ws)
        return

    # jogador
    token = q.get("token", "")
    pid = next((p for p, d in DB["players"].items()
                if secrets.compare_digest(d["token"], token)), None)
    if not pid:
        await ws.send_json({"type": "error", "msg": "sessão inválida"})
        await ws.close()
        return

    await HUB.add(ws, "player", pid)
    await HUB.push()
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            if msg.get("type") != "buzz":
                continue
            # seção crítica sem await: primeiro que chega leva
            if DB["phase"] != "armed":
                await ws.send_json({"type": "buzz_rejected",
                                    "reason": DB["phase"]})
                continue
            if pid not in DB["players"]:
                continue
            DB["phase"] = "buzzed"
            DB["buzzer"] = pid
            DB["revealed"] = False
            save()
            await HUB.push()
            await HUB.cmd("admin", {"type": "cmd", "cmd": "pause"})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        HUB.drop(ws)
        await HUB.push()


# --------------------------------------------------------------------------
# controle do jogo (admin)
# --------------------------------------------------------------------------
def first_ready() -> Optional[int]:
    for i, t in enumerate(DB["tracks"]):
        if t["status"] == "pronto":
            return i
    return None


async def arm_index(i: Optional[int]) -> bool:
    if i is None or not (0 <= i < len(DB["tracks"])):
        DB["phase"] = "idle"
        DB["buzzer"] = None
        save()
        await HUB.push()
        return False
    t = DB["tracks"][i]
    if t["status"] != "pronto":
        DB["phase"] = "idle"
        DB["buzzer"] = None
        save()
        await HUB.push()
        return False
    DB["cursor"] = i
    t["played"] = True
    DB["phase"] = "armed"
    DB["buzzer"] = None
    DB["revealed"] = False
    save()
    await HUB.push()
    await HUB.cmd("admin", {"type": "cmd", "cmd": "play",
                            "src": f"/media/{t['id']}.mp3"})
    return True


@app.post("/api/start")
async def start(_=Header(default=None, alias="X-Key")):
    check_key(_)
    if DB.get("started"):
        raise HTTPException(409, "O jogo já começou — use Reiniciar jogo.")
    i = first_ready()
    if i is None:
        raise HTTPException(400, "nenhuma música pronta — adicione uma playlist primeiro")
    for p in DB["players"].values():
        p["score"] = 0
    for t in DB["tracks"]:
        t["played"] = False
    DB["started"] = True
    await arm_index(i)
    return {"ok": True}


@app.post("/api/restart")
async def restart(_=Header(default=None, alias="X-Key")):
    check_key(_)
    i = first_ready()
    if i is None:
        raise HTTPException(400, "nenhuma música pronta na fila")
    for p in DB["players"].values():
        p["score"] = 0
    for t in DB["tracks"]:
        t["played"] = False
    DB["started"] = True
    await arm_index(i)
    return {"ok": True}


@app.post("/api/next")
async def next_track(_=Header(default=None, alias="X-Key")):
    check_key(_)
    start_i = DB["cursor"] + 1
    i = next((k for k in range(start_i, len(DB["tracks"]))
              if DB["tracks"][k]["status"] == "pronto"), None)
    if i is None:
        DB["phase"] = "idle"
        DB["buzzer"] = None
        save()
        await HUB.push()
        return {"ok": True, "finished": True}
    await arm_index(i)
    return {"ok": True}


@app.post("/api/prev")
async def prev_track(_=Header(default=None, alias="X-Key")):
    check_key(_)
    i = next((k for k in range(DB["cursor"] - 1, -1, -1)
              if DB["tracks"][k]["status"] == "pronto"), None)
    if i is None:
        raise HTTPException(400, "já é a primeira música")
    await arm_index(i)
    return {"ok": True}


@app.post("/api/random")
async def random_track(_=Header(default=None, alias="X-Key")):
    check_key(_)
    if not any(t["status"] == "pronto" for t in DB["tracks"]):
        raise HTTPException(400, "nenhuma música pronta")
    # embaralha a lista inteira e mantém o cursor na faixa que estava tocando
    cid = cur_id()
    random.shuffle(DB["tracks"])
    fix_cursor(cid)

    def cands():
        return [i for i, t in enumerate(DB["tracks"])
                if t["status"] == "pronto" and not t.get("played")
                and i != DB["cursor"]]
    pool = cands()
    if not pool:
        # rodada completa: limpa o historico e sorteia de novo
        for t in DB["tracks"]:
            t["played"] = False
        pool = cands()
    if not pool:
        pool = [i for i, t in enumerate(DB["tracks"]) if t["status"] == "pronto"]
    i = random.choice(pool)
    await arm_index(i)
    return {"ok": True, "index": i, "title": DB["tracks"][i].get("title"),
            "shuffled": len(DB["tracks"])}


@app.post("/api/shuffle")
async def shuffle_queue(_=Header(default=None, alias="X-Key")):
    check_key(_)
    cid = cur_id()
    random.shuffle(DB["tracks"])
    fix_cursor(cid)
    save()
    await HUB.push()
    return {"ok": True, "total": len(DB["tracks"])}


class ReorderIn(BaseModel):
    ids: list[str]


@app.post("/api/queue/reorder")
async def reorder_queue(body: ReorderIn, _=Header(default=None, alias="X-Key")):
    check_key(_)
    by_id = {t["id"]: t for t in DB["tracks"]}
    if len(body.ids) != len(by_id) or set(body.ids) != set(by_id):
        raise HTTPException(400, "A lista mudou — recarregue a página.")
    cid = cur_id()
    DB["tracks"] = [by_id[i] for i in body.ids]
    fix_cursor(cid)
    save()
    await HUB.push()
    return {"ok": True}


@app.post("/api/queue/{tid}/set-next")
async def set_next(tid: str, _=Header(default=None, alias="X-Key")):
    """Move a faixa para logo depois da atual (a próxima do ⏭ Próxima)."""
    check_key(_)
    idx = next((i for i, t in enumerate(DB["tracks"]) if t["id"] == tid), None)
    if idx is None:
        raise HTTPException(404, "faixa não existe")
    if idx == DB["cursor"]:
        raise HTTPException(400, "essa já é a música atual")
    cid = cur_id()
    track = DB["tracks"].pop(idx)
    fix_cursor(cid)
    pos = DB["cursor"] + 1 if DB["cursor"] >= 0 else 0
    DB["tracks"].insert(pos, track)
    if pos <= DB["cursor"]:
        DB["cursor"] += 1
    save()
    await HUB.push()
    return {"ok": True}


@app.post("/api/play/{tid}")
async def play_track(tid: str, _=Header(default=None, alias="X-Key")):
    """Toca essa faixa agora (fecha a rodada atual)."""
    check_key(_)
    idx = next((i for i, t in enumerate(DB["tracks"]) if t["id"] == tid), None)
    if idx is None:
        raise HTTPException(404, "faixa não existe")
    if DB["tracks"][idx]["status"] != "pronto":
        raise HTTPException(400, "essa faixa ainda não está pronta")
    await arm_index(idx)
    return {"ok": True}


@app.post("/api/replay")
async def replay(_=Header(default=None, alias="X-Key")):
    """Re-arma a mesma faixa do zero."""
    check_key(_)
    await HUB.cmd("admin", {"type": "cmd", "cmd": "restart"})
    await arm_index(DB["cursor"])
    return {"ok": True}


@app.post("/api/reveal")
async def reveal(_=Header(default=None, alias="X-Key")):
    check_key(_)
    DB["revealed"] = True
    if DB["phase"] != "idle":
        DB["phase"] = "reveal"
    save()
    await HUB.push()
    await HUB.cmd("admin", {"type": "cmd", "cmd": "pause"})
    return {"ok": True}


@app.post("/api/pause")
async def pause(_=Header(default=None, alias="X-Key")):
    check_key(_)
    if DB["phase"] == "armed":
        DB["phase"] = "idle"
        DB["buzzer"] = None
        save()
        await HUB.push()
    await HUB.cmd("admin", {"type": "cmd", "cmd": "pause"})
    return {"ok": True}


@app.post("/api/resume")
async def resume(_=Header(default=None, alias="X-Key")):
    check_key(_)
    if DB["phase"] in ("idle", "armed"):
        DB["phase"] = "armed"
        DB["buzzer"] = None
        save()
        await HUB.push()
    await HUB.cmd("admin", {"type": "cmd", "cmd": "resume"})
    return {"ok": True}


@app.post("/api/judge")
async def judge(body: JudgeIn, _=Header(default=None, alias="X-Key")):
    check_key(_)
    pid = DB["buzzer"]
    if not pid or pid not in DB["players"]:
        raise HTTPException(400, "ninguém apertou ainda")
    if DB["phase"] != "buzzed":
        raise HTTPException(409, "Rodada já encerrada — vá para a próxima música.")
    DB["judge"] = {"seq": int((DB.get("judge") or {}).get("seq", 0)) + 1,
                   "pid": pid, "ok": bool(body.ok)}
    if body.ok:
        DB["players"][pid]["score"] += int(DB["settings"]["value"])
        DB["revealed"] = True
        DB["phase"] = "reveal"
        save()
        await HUB.push()
        return {"ok": True, "scored": DB["settings"]["value"]}
    # errou: libera o botão de novo, áudio fica pausado (admin decide)
    DB["buzzer"] = None
    DB["phase"] = "armed" if not DB["revealed"] else "reveal"
    save()
    await HUB.push()
    return {"ok": True, "scored": 0}


@app.post("/api/score")
async def score(body: ScoreIn, _=Header(default=None, alias="X-Key")):
    check_key(_)
    if body.pid not in DB["players"]:
        raise HTTPException(404, "jogador não existe")
    p = DB["players"][body.pid]
    p["score"] = max(0, p["score"] + int(body.delta))
    save()
    await HUB.push()
    return {"ok": True, "score": p["score"]}


@app.post("/api/player/{pid}/kick")
async def kick(pid: str, _=Header(default=None, alias="X-Key")):
    check_key(_)
    DB["players"].pop(pid, None)
    if DB["buzzer"] == pid:
        DB["buzzer"] = None
    save()
    await HUB.push()
    return {"ok": True}


# --------------------------------------------------------------------------
# fila de músicas
# --------------------------------------------------------------------------
@app.post("/api/queue")
async def add_queue(body: QueueIn, _=Header(default=None, alias="X-Key")):
    check_key(_)
    url = body.url.strip()
    if not url:
        raise HTTPException(400, "url vazia")

    yid = ytid_of(url)
    entries: list[tuple[str, str, int]] = []
    if yid and "list=" not in url:
        rc, out, err = await run(
            YTDLP, *YT_ARGS, "--no-playlist", "--print", "%(id)s\t%(title)s\t%(duration)s",
            url, timeout=120)
        if rc == 0 and out.strip():
            parts = out.strip().split("\n")[0].split("\t")
            entries.append((parts[0], parts[1] if len(parts) > 1 else parts[0],
                            int(float(parts[2])) if len(parts) > 2 and parts[2] not in ("NA", "") else 0))
        else:
            raise HTTPException(400, f"não consegui ler o vídeo: {(err or out)[-160:]}")
    else:
        rc, out, err = await run(
            YTDLP, *YT_ARGS, "--flat-playlist", "--print",
            "%(id)s\t%(title)s\t%(duration)s", url, timeout=240)
        if rc != 0 or not out.strip():
            raise HTTPException(400, f"não consegui ler a playlist: {(err or out)[-160:]}")
        for line in out.strip().split("\n"):
            parts = line.split("\t")
            if len(parts) < 2 or not parts[0]:
                continue
            dur = 0
            if len(parts) > 2 and parts[2] not in ("NA", ""):
                try:
                    dur = int(float(parts[2]))
                except Exception:
                    dur = 0
            entries.append((parts[0], parts[1], dur))

    existing = {t["ytid"] for t in DB["tracks"]}
    added = []
    for yid_, title, dur in entries[:150]:
        if yid_ in existing:
            continue
        tid = secrets.token_hex(4)
        DB["tracks"].append({
            "id": tid, "ytid": yid_, "title": title,
            "duration": dur or None, "offset": None,
            "status": "fila", "source_url": f"https://www.youtube.com/watch?v={yid_}",
            "added": int(time.time()),
        })
        JOB_Q.put_nowait(tid)
        existing.add(yid_)
        added.append(tid)
    save()
    await HUB.push()
    return {"ok": True, "added": len(added), "skipped": len(entries) - len(added)}


@app.post("/api/queue/clear")
async def clear_queue(_=Header(default=None, alias="X-Key")):
    check_key(_)
    n = len(DB["tracks"])
    for t in DB["tracks"]:
        (MEDIA / f"{t['id']}.mp3").unlink(missing_ok=True)
        (MEDIA / f"{t['id']}_n.mp3").unlink(missing_ok=True)
    for f in list(RAW.glob("*")):
        f.unlink(missing_ok=True)
    DB["tracks"] = []
    DB["cursor"] = -1
    DB["phase"] = "idle"
    DB["buzzer"] = None
    DB["revealed"] = False
    DB["started"] = False
    save()
    await HUB.push()
    await HUB.cmd("admin", {"type": "cmd", "cmd": "pause"})
    return {"ok": True, "removed": n}


@app.post("/api/queue/{tid}/delete")
async def del_track(tid: str, _=Header(default=None, alias="X-Key")):
    check_key(_)
    idx = next((i for i, t in enumerate(DB["tracks"]) if t["id"] == tid), None)
    if idx is None:
        raise HTTPException(404, "faixa não existe")
    DB["tracks"].pop(idx)
    if DB["cursor"] >= idx:
        DB["cursor"] = max(-1, DB["cursor"] - 1)
    (MEDIA / f"{tid}.mp3").unlink(missing_ok=True)
    save()
    await HUB.push()
    return {"ok": True}


@app.post("/api/queue/{tid}/offset")
async def set_offset(tid: str, body: OffsetIn,
                     _=Header(default=None, alias="X-Key")):
    check_key(_)
    t = next((x for x in DB["tracks"] if x["id"] == tid), None)
    if not t:
        raise HTTPException(404, "faixa não existe")
    t["offset"] = max(0, int(body.offset))
    t["status"] = "fila"
    save()
    JOB_Q.put_nowait(tid)
    await HUB.push()
    return {"ok": True}


@app.post("/api/settings")
async def settings(body: SettingsIn, _=Header(default=None, alias="X-Key")):
    check_key(_)
    if body.value is not None:
        DB["settings"]["value"] = max(1, min(100, int(body.value)))
    if body.offset is not None:
        DB["settings"]["offset"] = max(0, int(body.offset))
    save()
    await HUB.push()
    return {"ok": True, "settings": DB["settings"]}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
