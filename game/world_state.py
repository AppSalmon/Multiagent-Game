"""Quản lý file world_state.json — nguồn dữ liệu duy nhất về trạng thái thế giới game.

File world_state.json được cập nhật sau mỗi pha quan trọng:
  setup    → bản đồ ban đầu
  income   → quân số các thành sau khi tăng
  combat   → chủ sở hữu và quân số sau trận đánh

Cấu trúc world_state.json:
{
  "meta": { current_turn, phase, updated_at, game_over, winner_id },
  "agents": [ { id, name, alive, capital_id, persona, core_directive, flaw,
                num_castles, total_troops } ],
  "castles": [ { id, name, owner_id, owner_name, troops, castle_type,
                 connections: [ {id, name, owner_id, owner_name, troops} ] } ],
  "chronicles": [ { turn, events: [...] } ]
}
"""

from __future__ import annotations

import json
from datetime import datetime

from game.models import GameState

WORLD_STATE_FILE = "world_state.json"


def _serialize(state: GameState, phase: str) -> dict:
    """Chuyển GameState thành dict có thể ghi ra JSON."""
    # --- Agents ---
    agents = []
    for a in state.agents.values():
        owned = state.get_agent_castles(a.id)
        agents.append({
            "id": a.id,
            "name": a.name,
            "alive": a.alive,
            "capital_id": a.capital_id,
            "persona": a.config.persona,
            "core_directive": a.config.core_directive,
            "flaw": a.config.flaw,
            "num_castles": len(owned),
            "total_troops": sum(c.troops for c in owned),
        })

    # --- Castles (bao gồm chi tiết từng kết nối để LLM không phải tra thêm) ---
    castles = []
    for c in state.castles.values():
        owner_name = None
        if c.owner_id and c.owner_id in state.agents:
            owner_name = state.agents[c.owner_id].name

        connections = []
        for conn_id in c.connections:
            if conn_id not in state.castles:
                continue
            conn = state.castles[conn_id]
            conn_owner_name = None
            if conn.owner_id and conn.owner_id in state.agents:
                conn_owner_name = state.agents[conn.owner_id].name
            connections.append({
                "id": conn_id,
                "name": conn.name,
                "owner_id": conn.owner_id,
                "owner_name": conn_owner_name,
                "troops": conn.troops,
            })

        castles.append({
            "id": c.id,
            "name": c.name,
            "owner_id": c.owner_id,
            "owner_name": owner_name,
            "troops": c.troops,
            "castle_type": c.castle_type.value,
            "connections": connections,
        })

    # --- Chronicles (3 lượt gần nhất) ---
    chronicles = []
    for ch in state.chronicles[-3:]:
        chronicles.append({
            "turn": ch.turn,
            "events": ch.events,
        })

    return {
        "meta": {
            "current_turn": state.current_turn,
            "phase": phase,
            "updated_at": datetime.now().isoformat(),
            "game_over": state.game_over,
            "winner_id": state.winner_id,
        },
        "agents": agents,
        "castles": castles,
        "chronicles": chronicles,
    }


def update(state: GameState, phase: str) -> None:
    """Ghi/cập nhật world_state.json với trạng thái hiện tại.

    Được gọi từ engine sau mỗi thay đổi quan trọng:
    - setup: sau khi tạo bản đồ
    - income: sau khi quân tăng
    - combat_complete: sau khi giải quyết chiến đấu
    """
    data = _serialize(state, phase)
    with open(WORLD_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load() -> dict:
    """Load world_state.json và trả về dict.

    Được gọi ngay trước khi build prompt cho LLM để lấy trạng thái mới nhất.
    Raise FileNotFoundError nếu chưa có file (game chưa được setup).
    """
    with open(WORLD_STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)
