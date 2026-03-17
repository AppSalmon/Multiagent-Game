"""Template prompt cho LLM — xây dựng context và chỉ thị cho từng agent.

Prompt chính:
  - DECISION_SYSTEM_PROMPT: Hướng dẫn agent ra lệnh quân sự

Các hàm build_*_from_file() tạo phần "tình huống" (user prompt) từ world_state.json.
"""

from __future__ import annotations
from game.models import GameState, TurnChronicle


# ===========================================================================
# === CÁC HÀM BUILD PROMPT TỪ world_state.json (nguồn dữ liệu chính thức) ===
# ===========================================================================

def build_world_state_from_file(data: dict, viewer_agent_id: str) -> str:
    """Xây dựng mô tả thế giới từ world_state.json.

    Bao gồm:
    - Danh sách lãnh chúa (sống/chết, số thành, quân)
    - Bản đồ toàn bộ thành (chủ + quân + kết nối kèm ID)
    - Section "THÀNH CỦA BẠN": chỉ thành của agent + chi tiết từng đường nối
      giúp LLM biết chính xác có thể điều quân đi đâu
    """
    meta = data.get("meta", {})
    lines = [f"=== TÌNH HÌNH THẾ GIỚI - Vòng {meta.get('current_turn', '?')} ===\n"]

    # Danh sách lãnh chúa
    lines.append("--- Các Lãnh Chúa ---")
    for agent in data.get("agents", []):
        status = "SỐNG" if agent["alive"] else "ĐÃ BỊ LOẠI"
        lines.append(
            f"  {agent['name']} [{status}]: {agent['num_castles']} thành, {agent['total_troops']} quân"
        )

    # Bản đồ toàn bộ thành
    lines.append("\n--- Bản Đồ Tòa Thành ---")
    for castle in data.get("castles", []):
        owner_name = castle["owner_name"] or "Trống (Trung Lập)"
        troop_info = f", {castle['troops']} quân" if castle["owner_id"] else ""
        capital_mark = " [THỦ PHỦ]" if castle["castle_type"] == "capital" else ""
        conn_text = ", ".join(
            f"{c['name']} ({c['id']})" for c in castle.get("connections", [])
        )
        lines.append(
            f"  {castle['name']} (ID: {castle['id']}): Chủ={owner_name}{capital_mark}{troop_info}"
        )
        lines.append(f"    -> Nối với: {conn_text}")

    # Section riêng: thành của agent + chi tiết kết nối hợp lệ
    my_castles = [c for c in data.get("castles", []) if c["owner_id"] == viewer_agent_id]
    if my_castles:
        lines.append("\n--- THÀNH CỦA BẠN (chỉ có thể điều quân TỪ đây) ---")
        for castle in my_castles:
            capital_mark = " [THỦ PHỦ]" if castle["castle_type"] == "capital" else ""
            lines.append(f"  {castle['name']} ({castle['id']}){capital_mark}: {castle['troops']} quân")
            lines.append("    Có thể điều quân TỚI:")
            for conn in castle.get("connections", []):
                conn_owner = conn["owner_name"] or "Trung Lập"
                conn_troops = f", {conn['troops']} quân" if conn["owner_id"] else ""
                lines.append(f"    -> {conn['name']} ({conn['id']}): Chủ={conn_owner}{conn_troops}")

    return "\n".join(lines)


def build_chronicle_from_file(data: dict) -> str:
    """Xây dựng biên niên sử từ world_state.json (3 lượt gần nhất đã được lọc sẵn)."""
    chronicles = data.get("chronicles", [])
    if not chronicles:
        return "Chưa có lịch sử."

    lines = ["=== BIÊN NIÊN SỬ GẦN ĐÂY ==="]
    for ch in chronicles:
        lines.append(f"\n--- Vòng {ch['turn']} ---")
        for event in ch.get("events", []):
            lines.append(f"  * {event}")
    return "\n".join(lines)


# ===========================================================================
# === PROMPT QUYẾT ĐỊNH QUÂN SỰ ===
# Được format với: agent_name, core_directive, flaw_text
# ===========================================================================

DECISION_SYSTEM_PROMPT = """Bạn là Central AI điều khiển một Lãnh Chúa trong game chiến thuật "LLM Warlords".

LUẬT CHƠI:
- Mỗi vòng, quân đội tăng thêm 10 * (số thành sở hữu).
- Tấn công thành trống tốn 10 quân.
- Chiến đấu: Quân công > Quân thủ -> chiếm thành. Quân còn lại = Quân công - Quân thủ.
- Thua khi: Mất thủ phủ, mất hết thành, hoặc hết quân.
- Thắng: Là người sống sót cuối cùng hoặc chiếm >= 80% bản đồ.

BẠN ĐANG ĐÓNG VAI LÃNH CHÚA SAU:
Tên: {agent_name}
Chiến lược cốt lõi: {core_directive}
{flaw_text}

NHIỆM VỤ: Ra quyết định quân sự cho vòng này.
Bạn PHẢI phân bổ quân đội tại các thành của mình. Bạn có thể:
1. Giữ quân phòng thủ tại thành
2. Điều quân từ thành A sang tấn công thành B

*** LUẬT BẮT BUỘC VỀ ĐƯỜNG NỐI ***
- Bạn CHỈ ĐƯỢC điều quân tới thành có trong danh sách "Có thể điều quân TỚI" của thành nguồn.
- Nếu thành đích KHÔNG nằm trong danh sách kết nối → lệnh sẽ BỊ HỦY hoàn toàn.
- Hãy xem kỹ section "THÀNH CỦA BẠN" để biết chính xác bạn có thể điều quân đi đâu.

LƯU Ý KHÁC:
- Không được điều nhiều quân hơn số quân hiện có tại thành.
- Bảo vệ Thủ Phủ là ưu tiên sống còn (mất thủ phủ = thua).
- Dùng castle ID (VD: castle_0) chứ KHÔNG dùng tên thành.
- Đảm bảo mỗi lần chỉ được di chuyển 2 nước

Trả lời ĐÚNG định dạng JSON sau (KHÔNG có text nào khác):
```json
{{
  "strategy": "Nhận định chiến lược tổng thể của bạn trong vòng này (1-2 câu, đúng tính cách nhân vật)",
  "moves": [
    {{
      "from": "castle_id nguồn (thành CỦA BẠN)",
      "to": "castle_id đích (phải CÓ ĐƯỜNG NỐI từ thành nguồn)",
      "troops": số_quân,
      "reason": "Lý do cụ thể của lệnh này (1 câu ngắn)"
    }}
  ]
}}
```

Nếu không muốn di chuyển quân, trả về: {{"strategy": "...", "moves": []}}"""
