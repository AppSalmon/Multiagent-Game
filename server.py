"""FastAPI server — cung cấp REST API và WebSocket real-time cho frontend.

Kiến trúc:
  - REST API: /api/setup (tạo game), /api/run (chạy tự động), /api/step (chạy từng lượt)
  - WebSocket: /ws — broadcast trạng thái game real-time tới tất cả client
  - Static files: /static — serve frontend (HTML/JS/CSS)

Luồng hoạt động:
  1. Client gọi POST /api/setup với danh sách agent config → engine tạo bản đồ
  2. Client gọi POST /api/run hoặc /api/step → engine chạy game
  3. Mỗi lượt xong, engine gọi callback → server broadcast qua WebSocket → UI cập nhật
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from game.engine import GameEngine
from game.models import AgentConfig, GameState, TurnChronicle

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="LLM Warlords: Lãnh Chúa Prompt")


@app.on_event("startup")
async def startup_check():
    """Kiểm tra cấu hình LLM khi server khởi động."""
    from config import GOOGLE_API_KEY, LLM_MODEL
    logger.info(f"LLM Config: model={LLM_MODEL}")
    if not GOOGLE_API_KEY:
        logger.error("GOOGLE_API_KEY is EMPTY! LLM calls will fail. Check your .env file.")
    else:
        logger.info(f"Google API Key loaded (length={len(GOOGLE_API_KEY)})")

app.mount("/static", StaticFiles(directory="web/static"), name="static")

# Game engine singleton — 1 server chạy 1 game tại 1 thời điểm
engine = GameEngine()
# Danh sách WebSocket client đang kết nối — để broadcast state
connected_clients: list[WebSocket] = []


# === Pydantic models cho request validation ===
class AgentInput(BaseModel):
    """Thông tin 1 agent do frontend gửi lên."""
    name: str
    persona: str
    core_directive: str
    flaw: str = ""


class SetupRequest(BaseModel):
    """Request tạo game mới."""
    agents: list[AgentInput]
    num_neutral: int = 8


def serialize_state(state: GameState) -> dict:
    """Chuyển GameState thành dict JSON-serializable để gửi cho frontend.

    Bao gồm: danh sách thành (tọa độ, chủ, quân, kết nối),
    danh sách agent (tên, sống/chết, số thành, tổng quân),
    biên niên sử 5 lượt gần nhất, và thông tin người thắng.
    """
    castles = []
    for c in state.castles.values():
        owner_name = None
        if c.owner_id and c.owner_id in state.agents:
            owner_name = state.agents[c.owner_id].name
        castles.append({
            "id": c.id, "name": c.name, "x": c.x, "y": c.y,
            "owner_id": c.owner_id, "owner_name": owner_name,
            "troops": c.troops, "castle_type": c.castle_type.value,
            "connections": c.connections,
        })

    agents = []
    for a in state.agents.values():
        castles_owned = state.get_agent_castles(a.id)
        agents.append({
            "id": a.id, "name": a.name, "alive": a.alive,
            "capital_id": a.capital_id,
            "persona": a.config.persona,
            "core_directive": a.config.core_directive,
            "flaw": a.config.flaw,
            "num_castles": len(castles_owned),
            "total_troops": sum(c.troops for c in castles_owned),
        })

    # Chỉ gửi 5 lượt gần nhất để giữ payload nhẹ
    chronicles = []
    for ch in state.chronicles[-5:]:
        battles = []
        for b in ch.battles:
            attacker_name = state.agents[b.attacker_id].name if b.attacker_id in state.agents else "?"
            defender_name = state.agents[b.defender_id].name if b.defender_id and b.defender_id in state.agents else "Trung Lập"
            castle_name = state.castles[b.location_castle].name if b.location_castle in state.castles else "?"
            battles.append({
                "castle_name": castle_name,
                "attacker_name": attacker_name,
                "defender_name": defender_name,
                "attacker_troops": b.attacker_troops,
                "defender_troops": b.defender_troops,
                "winner_id": b.winner_id,
                "castle_captured": b.castle_captured,
                "troops_remaining": b.troops_remaining,
            })
        chronicles.append({
            "turn": ch.turn, "events": ch.events, "battles": battles,
        })

    winner_name = None
    if state.winner_id and state.winner_id in state.agents:
        winner_name = state.agents[state.winner_id].name

    return {
        "current_turn": state.current_turn,
        "game_over": state.game_over,
        "winner_id": state.winner_id,
        "winner_name": winner_name,
        "castles": castles,
        "agents": agents,
        "chronicles": chronicles,
    }


async def broadcast(message: dict):
    """Gửi message tới tất cả WebSocket client đang kết nối.

    Tự động dọn dẹp client đã ngắt kết nối.
    """
    data = json.dumps(message, ensure_ascii=False)
    disconnected = []
    for ws in connected_clients:
        try:
            await ws.send_text(data)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        connected_clients.remove(ws)


async def on_turn_complete(state: GameState, chronicle: TurnChronicle):
    """Callback được engine gọi sau mỗi lượt — broadcast state mới cho frontend."""
    await broadcast({
        "type": "turn_complete",
        "state": serialize_state(state),
    })


async def on_phase_update(phase: str, turn: int):
    """Callback khi đổi pha (income → diplomacy → decision → combat)."""
    await broadcast({
        "type": "phase_update",
        "phase": phase,
        "turn": turn,
    })


# === REST API Endpoints ===

@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve trang chủ (HTML)."""
    with open("web/templates/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.post("/api/setup")
async def setup_game(request: SetupRequest):
    """Tạo game mới: nhận config các agent, sinh bản đồ, trả state ban đầu."""
    configs = [
        AgentConfig(
            name=a.name,
            persona=a.persona,
            core_directive=a.core_directive,
            flaw=a.flaw,
        )
        for a in request.agents
    ]
    state = engine.setup(configs, num_neutral=request.num_neutral)
    engine.on_turn_complete = on_turn_complete
    engine.on_phase_update = on_phase_update
    return serialize_state(state)


@app.post("/api/run")
async def run_game():
    """Chạy game tự động liên tục (background task) cho đến khi kết thúc."""
    if not engine.state:
        return {"error": "Game not set up"}
    asyncio.create_task(engine.run_game())
    return {"status": "Game started"}


@app.post("/api/step")
async def step_game():
    """Chạy 1 lượt duy nhất (chế độ step-by-step để xem từng bước)."""
    if not engine.state:
        return {"error": "Game not set up"}
    chronicle = await engine.run_single_turn()
    if chronicle is None:
        return {"error": "Game is over or not set up"}
    return serialize_state(engine.state)


@app.post("/api/stop")
async def stop_game():
    """Dừng game đang chạy tự động."""
    engine.stop()
    return {"status": "Game stopped"}


@app.get("/api/state")
async def get_state():
    """Lấy trạng thái hiện tại của game (polling thay vì WebSocket)."""
    if not engine.state:
        return {"error": "Game not set up"}
    return serialize_state(engine.state)


@app.get("/api/test-llm")
async def test_llm():
    """Endpoint kiểm tra kết nối LLM — gọi thử 1 câu đơn giản."""
    from config import GOOGLE_API_KEY, LLM_MODEL
    from llm.client import _call_llm

    if not GOOGLE_API_KEY:
        return {"ok": False, "error": "GOOGLE_API_KEY is empty. Check .env file."}

    try:
        reply = await _call_llm("You are a helpful assistant.", "Say 'OK' in one word.", max_tokens=10)
        return {"ok": True, "model": LLM_MODEL, "reply": reply}
    except Exception as e:
        return {"ok": False, "model": LLM_MODEL, "error": str(e)}


# === WebSocket Endpoint ===

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """WebSocket endpoint — client kết nối để nhận state update real-time.

    Hỗ trợ ping/pong để giữ kết nối sống.
    Khi client ngắt, tự động xóa khỏi danh sách broadcast.
    """
    await ws.accept()
    connected_clients.append(ws)
    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)

            if msg.get("type") == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))

    except WebSocketDisconnect:
        if ws in connected_clients:
            connected_clients.remove(ws)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
