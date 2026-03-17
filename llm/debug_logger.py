"""Debug logger — lưu toàn bộ prompt/response ra file JSON để dễ kiểm tra bug.

Cấu trúc thư mục output:
  logs/
    turn_1/
      TàoTháo_decision.json   ← system_prompt + user_prompt + raw response + orders đã parse
      LưuBị_decision.json
      ...
    turn_2/
      ...

Cách dùng: Sau khi chạy game, mở thư mục logs/ để xem LLM nhận gì và trả gì.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any


LOGS_DIR = "logs"


def _safe_name(name: str) -> str:
    """Chuẩn hóa tên file — loại bỏ ký tự đặc biệt."""
    return re.sub(r"[^\w\-]", "_", name)


def _get_turn_dir(turn: int) -> str:
    """Lấy đường dẫn thư mục log cho 1 lượt, tạo nếu chưa có."""
    path = os.path.join(LOGS_DIR, f"turn_{turn}")
    os.makedirs(path, exist_ok=True)
    return path


def save_agent_call(
    turn: int,
    agent_name: str,
    phase: str,
    system_prompt: str,
    user_prompt: str,
    raw_response: str,
    parsed_output: Any,
) -> None:
    """Lưu toàn bộ thông tin 1 lần gọi LLM của 1 agent.

    Args:
        turn:          Số lượt hiện tại
        agent_name:    Tên agent (VD: "Tào Tháo")
        phase:         Phase gọi LLM (hiện chỉ có "decision")
        system_prompt: Phần chỉ thị (luật chơi + persona)
        user_prompt:   Phần tình huống (world state + chronicle)
        raw_response:  Text thô LLM trả về (trước khi parse JSON)
        parsed_output: Kết quả đã parse (strategy + move_orders)
    """
    turn_dir = _get_turn_dir(turn)
    filename = f"{_safe_name(agent_name)}_{phase}.json"
    path = os.path.join(turn_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "turn": turn,
                "agent": agent_name,
                "phase": phase,
                "saved_at": datetime.now().isoformat(),
                "prompt": {
                    "system": system_prompt,
                    "user": user_prompt,
                    "combined_length": len(system_prompt) + len(user_prompt),
                },
                "raw_response": raw_response,
                "parsed_output": parsed_output,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
