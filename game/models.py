"""Định nghĩa tất cả các model dữ liệu (dataclass) của game.

Bao gồm: Agent, Castle, các loại lệnh (MoveOrder),
kết quả trận đánh (BattleResult), biên niên sử (TurnChronicle),
và trạng thái tổng thể (GameState).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# === Loại thành trì ===
class CastleType(str, Enum):
    CAPITAL = "capital"       # Thủ phủ — mất thủ phủ = bị loại
    NEUTRAL = "neutral"       # Thành trung lập — chưa ai chiếm
    CONQUERED = "conquered"   # Thành đã bị chiếm bởi 1 lãnh chúa


# === Cấu hình Agent (do người chơi nhập vào lúc setup) ===
@dataclass
class AgentConfig:
    """Thông tin tính cách của lãnh chúa, được dùng làm prompt cho LLM."""
    name: str               # Tên hiển thị (VD: "Tào Tháo")
    persona: str            # Mô tả tính cách (VD: "Mưu mô, xảo quyệt")
    core_directive: str     # Chiến lược cốt lõi (VD: "Ưu tiên phòng thủ")
    flaw: str = ""          # Điểm yếu (VD: "Hay nghi ngờ đối thủ")


# === Agent (Lãnh Chúa) ===
@dataclass
class Agent:
    """Đại diện cho 1 lãnh chúa trong game, chứa trạng thái sống/chết."""
    id: str
    config: AgentConfig
    alive: bool = True
    capital_id: str = ""    # ID thành thủ phủ, được gán khi generate map

    @property
    def name(self) -> str:
        return self.config.name


# === Tòa Thành ===
@dataclass
class Castle:
    """Một tòa thành trên bản đồ — có tọa độ, chủ sở hữu, quân đội, và danh sách kết nối."""
    id: str
    name: str
    x: float                                 # Tọa độ X trên bản đồ
    y: float                                 # Tọa độ Y trên bản đồ
    owner_id: Optional[str] = None           # None = thành trung lập
    troops: int = 0
    castle_type: CastleType = CastleType.NEUTRAL
    connections: list[str] = field(default_factory=list)  # Danh sách castle_id kề cạnh

    @property
    def is_neutral(self) -> bool:
        """Thành chưa có ai chiếm."""
        return self.owner_id is None


# === Lệnh quân sự ===
@dataclass
class MoveOrder:
    """Lệnh di chuyển/tấn công: điều quân từ thành A sang thành B."""
    agent_id: str
    from_castle: str
    to_castle: str
    troops: int
    reason: str = ""  # Lý do chiến thuật của lệnh này (do LLM trả về)


@dataclass
class AgentDecision:
    """Tập hợp tất cả lệnh quân sự của 1 agent trong 1 lượt."""
    agent_id: str
    move_orders: list[MoveOrder] = field(default_factory=list)
    strategy: str = ""  # Nhận định chiến lược tổng thể của lượt này (do LLM trả về)


# === Kết quả trận đánh ===
@dataclass
class BattleResult:
    """Kết quả 1 trận đánh tại 1 tòa thành."""
    location_castle: str          # Thành bị tấn công
    attacker_id: str
    defender_id: Optional[str]    # None nếu đánh thành trung lập
    attacker_troops: int
    defender_troops: int
    winner_id: Optional[str]      # None nếu tấn công thất bại vào thành trung lập
    troops_remaining: int         # Quân còn lại sau trận
    castle_captured: bool         # True nếu thành đổi chủ


# === Biên niên sử 1 lượt ===
@dataclass
class TurnChronicle:
    """Ghi lại toàn bộ sự kiện xảy ra trong 1 lượt chơi."""
    turn: int
    events: list[str] = field(default_factory=list)           # Mô tả sự kiện dạng text
    battles: list[BattleResult] = field(default_factory=list) # Danh sách trận đánh


# === Trạng thái toàn cục của game ===
@dataclass
class GameState:
    """Chứa toàn bộ trạng thái game: bản đồ, lãnh chúa, lịch sử, kết quả."""
    castles: dict[str, Castle] = field(default_factory=dict)
    agents: dict[str, Agent] = field(default_factory=dict)
    current_turn: int = 0
    chronicles: list[TurnChronicle] = field(default_factory=list)
    game_over: bool = False
    winner_id: Optional[str] = None

    def get_agent_castles(self, agent_id: str) -> list[Castle]:
        """Lấy danh sách thành mà 1 agent đang sở hữu."""
        return [c for c in self.castles.values() if c.owner_id == agent_id]

    def get_agent_total_troops(self, agent_id: str) -> int:
        """Tổng quân của 1 agent trên toàn bản đồ."""
        return sum(c.troops for c in self.get_agent_castles(agent_id))

    def get_alive_agents(self) -> list[Agent]:
        """Danh sách các lãnh chúa còn sống."""
        return [a for a in self.agents.values() if a.alive]

    def get_connections(self, castle_id: str) -> list[str]:
        """Lấy danh sách castle_id kết nối với 1 thành."""
        castle = self.castles.get(castle_id)
        return castle.connections if castle else []
