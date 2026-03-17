"""LLM Client — giao tiếp với Google GenAI để tạo quyết định quân sự.

Luồng dữ liệu:
  1. Engine cập nhật world_state.json trước khi gọi generate_decision()
  2. Client load world_state.json để xây user prompt (context cho LLM)
  3. LLM trả JSON → parse → trả về AgentDecision cho engine

Mọi lần gọi LLM đều được ghi ra logs/ để dễ debug.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from google import genai
from google.genai import types

from config import GOOGLE_API_KEY, LLM_MODEL
from game.models import Agent, AgentDecision, GameState, MoveOrder
from game.world_state import load as load_world_state
from llm.prompts import (
    DECISION_SYSTEM_PROMPT,
    build_world_state_from_file,
    build_chronicle_from_file,
)
from llm.debug_logger import save_agent_call

logger = logging.getLogger(__name__)

# Singleton client — tạo 1 lần, dùng lại xuyên suốt game
_client: genai.Client | None = None


def get_client() -> genai.Client:
    """Lấy hoặc tạo GenAI client (singleton pattern)."""
    global _client
    if _client is None:
        _client = genai.Client(api_key=GOOGLE_API_KEY)
    return _client


def _extract_json(text: str) -> dict[str, Any]:
    """Trích xuất JSON từ response LLM.

    LLM thường trả JSON bọc trong markdown code block (```json ... ```),
    nên cần parse linh hoạt: thử code block trước, rồi fallback tìm { }.
    """
    code_block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if code_block:
        return json.loads(code_block.group(1))

    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        return json.loads(brace_match.group(0))

    raise ValueError(f"No valid JSON found in LLM response: {text[:200]}")


async def _call_llm(system_prompt: str, user_prompt: str, temperature: float = 0.7, max_tokens: int = 800) -> str:
    """Gọi Google GenAI API và trả về text response.

    Gộp system_prompt và user_prompt thành 1 message duy nhất
    (do một số model không hỗ trợ system message riêng).
    """
    client = get_client()
    combined = f"[CHỈ THỊ]\n{system_prompt}\n\n[TÌNH HUỐNG]\n{user_prompt}"
    response = await client.aio.models.generate_content(
        model=LLM_MODEL,
        contents=combined,
        config=types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        ),
    )
    return response.text or ""


async def generate_decision(state: GameState, agent: Agent) -> AgentDecision:
    """Tạo lệnh quân sự cho 1 agent bằng LLM.

    Context được load từ world_state.json (engine đã cập nhật trước lời gọi này).
    LLM trả JSON: { strategy, moves: [{from, to, troops, reason}] }.
    Validation (đường nối, số quân) do combat.py xử lý sau.
    """
    flaw_text = f"Điểm yếu: {agent.config.flaw}" if agent.config.flaw else ""
    system_prompt = DECISION_SYSTEM_PROMPT.format(
        agent_name=agent.name,
        core_directive=agent.config.core_directive,
        flaw_text=flaw_text,
    )

    # Load world_state.json — engine đã cập nhật ngay trước lời gọi này
    world_data = load_world_state()
    world_state_text = build_world_state_from_file(world_data, agent.id)
    chronicle_text = build_chronicle_from_file(world_data)

user_prompt = f"{world_state_text}\n\n{chronicle_text}\n\nHãy ra quyết định quân sự."

    try:
        content = await _call_llm(system_prompt, user_prompt, temperature=0.7, max_tokens=600)
        logger.info(f"Decision response for {agent.name}: {content[:150]}")
        data = _extract_json(content)

        strategy = data.get("strategy", "")

        move_orders = []
        for move in data.get("moves", []):
            from_castle = move.get("from", "")
            to_castle = move.get("to", "")
            troops = int(move.get("troops", 0))
            reason = move.get("reason", "")
            if from_castle and to_castle and troops > 0:
                move_orders.append(MoveOrder(
                    agent_id=agent.id,
                    from_castle=from_castle,
                    to_castle=to_castle,
                    troops=troops,
                    reason=reason,
                ))

        # Lưu log: prompt đầy đủ + raw response + orders đã parse
        save_agent_call(
            turn=state.current_turn,
            agent_name=agent.name,
            phase="decision",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            raw_response=content,
            parsed_output={
                "strategy": strategy,
                "moves": [
                    {"from": o.from_castle, "to": o.to_castle, "troops": o.troops, "reason": o.reason}
                    for o in move_orders
                ],
            },
        )

        return AgentDecision(agent_id=agent.id, move_orders=move_orders, strategy=strategy)

    except Exception as e:
        logger.error(f"Decision generation failed for {agent.name}: {e}")
        save_agent_call(
            turn=state.current_turn,
            agent_name=agent.name,
            phase="decision",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            raw_response=f"ERROR: {e}",
            parsed_output=None,
        )
        return AgentDecision(agent_id=agent.id)
