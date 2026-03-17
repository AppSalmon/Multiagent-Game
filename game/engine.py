"""Game Engine chính — điều phối vòng lặp 3 pha mỗi lượt.

Mỗi lượt chơi gồm 3 pha tuần tự:
  Phase 0 - Income:   Mỗi thành tạo thêm quân
  Phase 1 - Decision: Các agent ra lệnh quân sự (qua LLM)
  Phase 2 - Combat:   Giải quyết di quân và chiến đấu
  + Kiểm tra loại / thắng sau mỗi lượt
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Awaitable, Optional

from config import TROOPS_PER_CASTLE_PER_TURN, MAX_TURNS
from game.models import Agent, AgentConfig, AgentDecision, BattleResult, GameState, TurnChronicle
from game.map_generator import generate_map
from game.combat import resolve_combat, check_eliminations, check_victory
from llm.client import generate_decision
import game.world_state as world_state_mgr

logger = logging.getLogger(__name__)

# Callback type: được gọi sau mỗi lượt để broadcast state qua WebSocket
TurnCallback = Callable[[GameState, TurnChronicle], Awaitable[None]]


class GameEngine:
    """Bộ máy điều phối game — quản lý setup, vòng lặp lượt, và trạng thái."""

    def __init__(self):
        self.state: Optional[GameState] = None
        self.on_turn_complete: Optional[TurnCallback] = None   # Callback sau mỗi lượt
        self.on_phase_update: Optional[Callable] = None         # Callback khi đổi pha
        self._running = False

    def setup(self, agent_configs: list[AgentConfig], num_neutral: int = 8) -> GameState:
        """Khởi tạo game: tạo agent từ config, sinh bản đồ ngẫu nhiên.
        Ghi world_state.json ngay sau khi setup để capture trạng thái ban đầu.
        """
        agents = [
            Agent(id=f"agent_{i}", config=cfg)
            for i, cfg in enumerate(agent_configs)
        ]
        self.state = generate_map(agents, num_neutral=num_neutral)
        world_state_mgr.update(self.state, phase="setup")
        return self.state

    async def run_game(self) -> GameState:
        """Chạy toàn bộ game liên tục cho đến khi có người thắng hoặc hết lượt."""
        if not self.state:
            raise RuntimeError("Game not set up. Call setup() first.")

        self._running = True

        while self._running and not self.state.game_over and self.state.current_turn < MAX_TURNS:
            self.state.current_turn += 1
            chronicle = await self._run_turn()

            # Kiểm tra chiến thắng sau mỗi lượt
            winner = check_victory(self.state)
            if winner:
                self.state.game_over = True
                self.state.winner_id = winner
                winner_name = self.state.agents[winner].name
                chronicle.events.append(f"*** {winner_name} CHIẾN THẮNG! Trò chơi kết thúc! ***")

            # Thông báo frontend qua WebSocket
            if self.on_turn_complete:
                await self.on_turn_complete(self.state, chronicle)

        return self.state

    async def run_single_turn(self) -> TurnChronicle | None:
        """Chạy 1 lượt duy nhất (chế độ step-by-step để debug/demo)."""
        if not self.state or self.state.game_over:
            return None

        self.state.current_turn += 1
        chronicle = await self._run_turn()

        winner = check_victory(self.state)
        if winner:
            self.state.game_over = True
            self.state.winner_id = winner
            winner_name = self.state.agents[winner].name
            chronicle.events.append(f"*** {winner_name} CHIẾN THẮNG! Trò chơi kết thúc! ***")

        if self.on_turn_complete:
            await self.on_turn_complete(self.state, chronicle)

        return chronicle

    def stop(self):
        """Dừng game giữa chừng (set flag, vòng while sẽ thoát)."""
        self._running = False

    async def _run_turn(self) -> TurnChronicle:
        """Xử lý 1 lượt chơi hoàn chỉnh qua 3 pha."""
        state = self.state
        turn = state.current_turn
        chronicle = TurnChronicle(turn=turn)
        alive_agents = state.get_alive_agents()

        # === Phase 0: Thu nhập quân đội ===
        # Mỗi thành tạo thêm TROOPS_PER_CASTLE_PER_TURN quân
        await self._notify_phase("income", turn)
        for agent in alive_agents:
            owned = state.get_agent_castles(agent.id)
            income = TROOPS_PER_CASTLE_PER_TURN * len(owned)
            for castle in owned:
                castle.troops += TROOPS_PER_CASTLE_PER_TURN
            chronicle.events.append(f"{agent.name} thu hoạch +{income} quân ({len(owned)} thành)")

        # Cập nhật world_state.json sau khi quân tăng — LLM sẽ đọc số quân mới nhất
        world_state_mgr.update(state, phase="income")

        # === Phase 1: Ra quyết định quân sự ===
        # Mỗi agent load world_state.json để lấy context, rồi LLM ra lệnh di quân.
        await self._notify_phase("decision", turn)
        decisions: list[AgentDecision] = []
        llm_errors = 0

        for agent in alive_agents:
            decision = await generate_decision(state, agent)
            decisions.append(decision)
            if not decision.move_orders:
                llm_errors += 1
                logger.warning(f"{agent.name} returned no move orders (LLM may have failed)")

            # Ghi nhận định chiến lược tổng thể của agent (nếu có)
            if decision.strategy:
                chronicle.events.append(f"[CHIẾN LƯỢC] {agent.name}: {decision.strategy}")

            for order in decision.move_orders:
                src_name = state.castles[order.from_castle].name if order.from_castle in state.castles else order.from_castle
                dst_name = state.castles[order.to_castle].name if order.to_castle in state.castles else order.to_castle
                chronicle.events.append(f"[LỆNH] {agent.name}: Điều {order.troops} quân từ {src_name} → {dst_name}")
                if order.reason:
                    chronicle.events.append(f"  └> Lý do: {order.reason}")

        if llm_errors == len(alive_agents) and turn <= 2:
            chronicle.events.append(
                "[LỖI] Tất cả LLM calls đều thất bại! Kiểm tra API Key và cấu hình trong file .env"
            )

        # === Phase 2: Giải quyết chiến đấu ===
        # Combat engine xử lý tất cả lệnh di quân, trận đánh, và chiếm thành
        await self._notify_phase("combat", turn)
        battle_results = resolve_combat(state, decisions)
        chronicle.battles = battle_results

        for result in battle_results:
            castle_name = state.castles[result.location_castle].name
            attacker_name = state.agents[result.attacker_id].name
            defender_name = state.agents[result.defender_id].name if result.defender_id else "Trung Lập"

            if result.castle_captured:
                chronicle.events.append(
                    f"TRẬN CHIẾN tại {castle_name}: {attacker_name} ({result.attacker_troops}) "
                    f"đánh bại {defender_name} ({result.defender_troops}). "
                    f"Thành bị chiếm! Còn {result.troops_remaining} quân."
                )
            else:
                chronicle.events.append(
                    f"TRẬN CHIẾN tại {castle_name}: {attacker_name} ({result.attacker_troops}) "
                    f"tấn công {defender_name} ({result.defender_troops}). "
                    f"Phòng thủ giữ vững! Còn {result.troops_remaining} quân thủ."
                )

        # === Kiểm tra loại ===
        # Loại agent mất thủ phủ / hết thành / hết quân
        eliminated = check_eliminations(state)
        for agent_id in eliminated:
            name = state.agents[agent_id].name
            chronicle.events.append(f"*** {name} ĐÃ BỊ LOẠI KHỎI CUỘC CHƠI! ***")

        state.chronicles.append(chronicle)

        # Cập nhật world_state.json sau combat — bản đồ thay đổi chủ được phản ánh cho lượt sau
        world_state_mgr.update(state, phase="combat_complete")

        return chronicle

    async def _notify_phase(self, phase: str, turn: int):
        """Gửi thông báo đổi pha cho frontend (hiển thị trên UI)."""
        if self.on_phase_update:
            await self.on_phase_update(phase, turn)
