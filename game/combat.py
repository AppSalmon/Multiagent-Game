"""Hệ thống giải quyết chiến đấu — logic thuần game engine, không liên quan đến LLM.

Luồng xử lý mỗi lượt:
  1. validate_orders()  — Kiểm tra tính hợp lệ của tất cả lệnh di quân
  2. resolve_combat()   — Trừ quân nguồn, gom quân theo thành đích, xử lý từng trận đánh
  3. check_eliminations() — Loại agent mất thủ phủ / hết thành / hết quân
  4. check_victory()    — Kiểm tra điều kiện thắng (1 người sống hoặc >= 80% bản đồ)
"""

from __future__ import annotations

import logging

from game.models import (
    AgentDecision, BattleResult, Castle, CastleType, GameState, MoveOrder,
)
from config import NEUTRAL_CAPTURE_COST

logger = logging.getLogger(__name__)


def validate_orders(state: GameState, decisions: list[AgentDecision]) -> list[AgentDecision]:
    """Kiểm tra và lọc tất cả lệnh quân sự, chỉ giữ lại lệnh hợp lệ.

    Các điều kiện hợp lệ:
    - Agent còn sống
    - Thành nguồn thuộc về agent
    - Thành đích tồn tại trên bản đồ
    - Thành đích phải có đường kết nối với thành nguồn
    - Không điều nhiều quân hơn số quân hiện có (trừ đi quân đã cam kết cho lệnh trước)
    """
    validated: list[AgentDecision] = []

    for decision in decisions:
        agent = state.agents.get(decision.agent_id)
        if not agent or not agent.alive:
            continue

        agent_name = agent.name
        agent_castles = {c.id: c for c in state.get_agent_castles(decision.agent_id)}
        troops_committed: dict[str, int] = {}

        valid_moves = []
        for order in decision.move_orders:
            if order.from_castle not in agent_castles:
                logger.warning(
                    f"[LỆNH BỊ HỦY] {agent_name}: {order.from_castle} không thuộc về agent"
                )
                continue
            if order.to_castle not in state.castles:
                logger.warning(
                    f"[LỆNH BỊ HỦY] {agent_name}: {order.to_castle} không tồn tại trên bản đồ"
                )
                continue
            castle = agent_castles[order.from_castle]
            if order.to_castle not in castle.connections:
                src_name = castle.name
                dst_name = state.castles[order.to_castle].name
                logger.warning(
                    f"[LỆNH BỊ HỦY] {agent_name}: {src_name} ({order.from_castle}) "
                    f"KHÔNG có đường nối tới {dst_name} ({order.to_castle})"
                )
                continue

            committed = troops_committed.get(order.from_castle, 0)
            available = castle.troops - committed
            actual_troops = min(max(0, order.troops), available)
            if actual_troops <= 0:
                logger.warning(
                    f"[LỆNH BỊ HỦY] {agent_name}: không đủ quân tại {castle.name} "
                    f"({order.from_castle}), yêu cầu {order.troops}, khả dụng {available}"
                )
                continue

            troops_committed[order.from_castle] = committed + actual_troops
            valid_moves.append(MoveOrder(
                agent_id=decision.agent_id,
                from_castle=order.from_castle,
                to_castle=order.to_castle,
                troops=actual_troops,
            ))

        rejected_count = len(decision.move_orders) - len(valid_moves)
        if rejected_count > 0:
            logger.warning(
                f"[VALIDATION] {agent_name}: {rejected_count}/{len(decision.move_orders)} lệnh bị hủy"
            )

        decision.move_orders = valid_moves
        validated.append(decision)

    return validated


def resolve_combat(state: GameState, decisions: list[AgentDecision]) -> list[BattleResult]:
    """Giải quyết toàn bộ di quân và chiến đấu trong 1 lượt.

    Luồng:
    1. Validate tất cả lệnh
    2. Trừ quân khỏi thành nguồn (tất cả cùng lúc, trước khi đánh)
    3. Gom các lệnh theo thành đích
    4. Xử lý từng thành đích:
       - Thành trung lập → tốn NEUTRAL_CAPTURE_COST quân để chiếm
       - Thành có chủ, quân mình → cộng dồn quân (viện binh)
       - Thành có chủ, quân địch → so quân, bên nhiều hơn thắng
    """
    decisions = validate_orders(state, decisions)
    results: list[BattleResult] = []

    # Bước 1: Trừ quân nguồn trước — tất cả quân rời thành cùng lúc
    for decision in decisions:
        for order in decision.move_orders:
            source = state.castles[order.from_castle]
            source.troops -= order.troops

    # Bước 2: Gom lệnh theo thành đích để xử lý chung
    attacks_by_target: dict[str, list[MoveOrder]] = {}
    for decision in decisions:
        for order in decision.move_orders:
            attacks_by_target.setdefault(order.to_castle, []).append(order)

    # Bước 3: Xử lý chiến đấu tại từng thành đích
    for target_id, incoming in attacks_by_target.items():
        target = state.castles[target_id]

        # Gom tổng quân theo từng agent (1 agent có thể gửi quân từ nhiều thành)
        grouped: dict[str, int] = {}
        for order in incoming:
            grouped[order.agent_id] = grouped.get(order.agent_id, 0) + order.troops

        if target.is_neutral:
            # Đánh thành trung lập — mỗi agent đánh riêng lẻ
            for attacker_id, troops in grouped.items():
                result = _resolve_neutral_attack(target, attacker_id, troops)
                results.append(result)
        elif len(grouped) == 1:
            attacker_id = list(grouped.keys())[0]
            attacker_troops = grouped[attacker_id]

            if attacker_id == target.owner_id:
                # Viện binh — cùng chủ thì cộng dồn quân
                target.troops += attacker_troops
            else:
                result = _resolve_attack(target, attacker_id, attacker_troops)
                results.append(result)
        else:
            # Nhiều agent cùng tấn công 1 thành — xử lý lần lượt
            for attacker_id, troops in grouped.items():
                if attacker_id == target.owner_id:
                    target.troops += troops
                else:
                    result = _resolve_attack(target, attacker_id, troops)
                    results.append(result)

    return results


def _resolve_neutral_attack(castle: Castle, attacker_id: str, troops: int) -> BattleResult:
    """Xử lý tấn công thành trung lập.

    Cần tối thiểu NEUTRAL_CAPTURE_COST quân để chiếm.
    Quân dư = troops - cost, trở thành quân trú đóng.
    """
    cost = NEUTRAL_CAPTURE_COST
    if troops >= cost:
        remaining = troops - cost
        castle.owner_id = attacker_id
        castle.troops = remaining
        castle.castle_type = CastleType.CONQUERED
        return BattleResult(
            location_castle=castle.id, attacker_id=attacker_id,
            defender_id=None, attacker_troops=troops, defender_troops=0,
            winner_id=attacker_id, troops_remaining=remaining, castle_captured=True,
        )
    return BattleResult(
        location_castle=castle.id, attacker_id=attacker_id,
        defender_id=None, attacker_troops=troops, defender_troops=cost,
        winner_id=None, troops_remaining=0, castle_captured=False,
    )


def _resolve_attack(castle: Castle, attacker_id: str, attacker_troops: int) -> BattleResult:
    """Xử lý tấn công thành có chủ.

    Luật đơn giản: quân công > quân thủ → chiếm thành, quân còn = hiệu số.
    Ngược lại → phòng thủ thành công, quân thủ còn = hiệu số.
    """
    defender_id = castle.owner_id
    defender_troops = castle.troops

    if attacker_troops > defender_troops:
        remaining = attacker_troops - defender_troops
        castle.owner_id = attacker_id
        castle.troops = remaining
        castle.castle_type = CastleType.CONQUERED
        return BattleResult(
            location_castle=castle.id, attacker_id=attacker_id,
            defender_id=defender_id, attacker_troops=attacker_troops,
            defender_troops=defender_troops, winner_id=attacker_id,
            troops_remaining=remaining, castle_captured=True,
        )
    else:
        remaining = defender_troops - attacker_troops
        castle.troops = remaining
        return BattleResult(
            location_castle=castle.id, attacker_id=attacker_id,
            defender_id=defender_id, attacker_troops=attacker_troops,
            defender_troops=defender_troops, winner_id=defender_id,
            troops_remaining=remaining, castle_captured=False,
        )


def check_eliminations(state: GameState) -> list[str]:
    """Kiểm tra và loại các agent đã thua. Trả về danh sách agent_id bị loại.

    Điều kiện bị loại (bất kỳ 1 trong 3):
    - Mất hết thành
    - Hết quân (tổng quân = 0)
    - Mất thủ phủ (thủ phủ đổi chủ)
    """
    eliminated: list[str] = []

    for agent in state.get_alive_agents():
        owned = state.get_agent_castles(agent.id)
        total_troops = sum(c.troops for c in owned)
        lost_capital = agent.capital_id and state.castles[agent.capital_id].owner_id != agent.id

        if len(owned) == 0 or total_troops == 0 or lost_capital:
            agent.alive = False
            eliminated.append(agent.id)

    return eliminated


def check_victory(state: GameState) -> str | None:
    """Kiểm tra điều kiện chiến thắng. Trả về agent_id người thắng hoặc None.

    Thắng khi:
    - Là người sống sót duy nhất, HOẶC
    - Chiếm >= WIN_TERRITORY_PERCENT% tổng số thành trên bản đồ
    """
    alive = state.get_alive_agents()

    if len(alive) == 1:
        return alive[0].id

    total_castles = len(state.castles)
    from config import WIN_TERRITORY_PERCENT
    threshold = total_castles * WIN_TERRITORY_PERCENT / 100

    for agent in alive:
        if len(state.get_agent_castles(agent.id)) >= threshold:
            return agent.id

    return None
