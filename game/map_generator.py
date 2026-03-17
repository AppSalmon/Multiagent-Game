"""Sinh bản đồ game dạng đồ thị (graph) với các tòa thành và đường kết nối.

Thuật toán:
  1. Tạo tọa độ ngẫu nhiên cho các thành (rejection sampling để đảm bảo khoảng cách tối thiểu)
  2. Nối các thành lân cận (proximity edges, tối đa 4 kết nối/thành)
  3. Đảm bảo đồ thị liên thông (thêm cạnh nối các thành phần rời)
  4. Gán thủ phủ ngẫu nhiên cho mỗi lãnh chúa
"""

from __future__ import annotations

import math
import random
from typing import Optional

from game.models import Agent, Castle, CastleType, GameState
from config import INITIAL_TROOPS

# Danh sách tên thành phong cách Việt — lấy ngẫu nhiên khi tạo bản đồ
CASTLE_NAMES = [
    "Thành Long Vương", "Thành Hổ Phách", "Thành Phượng Hoàng",
    "Thành Rồng Đen", "Thành Bạch Hổ", "Thành Thanh Long",
    "Thành Chu Tước", "Thành Huyền Vũ", "Thành Kim Ưng",
    "Thành Ngọc Lân", "Thành Thiên Sơn", "Thành Vạn Lý",
    "Thành Bình Minh", "Thành Hoàng Hôn", "Thành Trăng Khuyết",
    "Thành Sao Mai", "Thành Gió Bấc", "Thành Mây Trắng",
    "Thành Sấm Sét", "Thành Biển Đông", "Thành Núi Tuyết",
    "Thành Hỏa Diệm", "Thành Băng Hà", "Thành Lôi Đình",
]


def _distance(x1: float, y1: float, x2: float, y2: float) -> float:
    """Khoảng cách Euclid giữa 2 điểm."""
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)


def _generate_positions(count: int, width: float, height: float, min_dist: float) -> list[tuple[float, float]]:
    """Tạo tọa độ ngẫu nhiên bằng rejection sampling.

    Thử đặt điểm ngẫu nhiên, chỉ chấp nhận nếu cách tất cả điểm đã có >= min_dist.
    Có giới hạn max_attempts để tránh vòng lặp vô hạn khi bản đồ quá chật.
    """
    positions: list[tuple[float, float]] = []
    margin = 60  # Cách viền bản đồ tối thiểu 60px
    attempts = 0
    max_attempts = count * 200

    while len(positions) < count and attempts < max_attempts:
        x = random.uniform(margin, width - margin)
        y = random.uniform(margin, height - margin)
        if all(_distance(x, y, px, py) >= min_dist for px, py in positions):
            positions.append((x, y))
        attempts += 1

    return positions


def _build_proximity_edges(positions: list[tuple[float, float]], max_distance: float) -> list[tuple[int, int]]:
    """Tạo cạnh kết nối giữa các thành gần nhau.

    Mỗi thành nối tối đa 4 thành lân cận trong phạm vi max_distance.
    Cạnh lưu dưới dạng (i, j) với i < j để tránh trùng lặp.
    """
    edges: list[tuple[int, int]] = []
    n = len(positions)

    for i in range(n):
        # Sắp xếp tất cả thành khác theo khoảng cách tăng dần
        distances = []
        for j in range(n):
            if i != j:
                d = _distance(positions[i][0], positions[i][1], positions[j][0], positions[j][1])
                distances.append((d, j))
        distances.sort()
        connected = 0
        for d, j in distances:
            if d <= max_distance and connected < 4:
                edge = (min(i, j), max(i, j))
                if edge not in edges:
                    edges.append(edge)
                connected += 1

    return edges


def _ensure_connectivity(positions: list[tuple[float, float]], edges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Đảm bảo đồ thị liên thông — tất cả thành phải đi được tới nhau.

    Dùng DFS tìm các thành phần liên thông (connected components),
    rồi nối chúng bằng cạnh ngắn nhất cho đến khi chỉ còn 1 thành phần.
    """
    n = len(positions)
    adj: dict[int, set[int]] = {i: set() for i in range(n)}
    for a, b in edges:
        adj[a].add(b)
        adj[b].add(a)

    # Tìm tất cả thành phần liên thông bằng DFS
    visited = set()
    components: list[set[int]] = []

    for start in range(n):
        if start in visited:
            continue
        component: set[int] = set()
        stack = [start]
        while stack:
            node = stack.pop()
            if node in component:
                continue
            component.add(node)
            visited.add(node)
            for nb in adj[node]:
                if nb not in component:
                    stack.append(nb)
        components.append(component)

    # Nối các thành phần rời bằng cạnh ngắn nhất (giống thuật toán Kruskal đơn giản)
    while len(components) > 1:
        best_dist = float("inf")
        best_edge: Optional[tuple[int, int]] = None
        c1 = components[0]
        for c2 in components[1:]:
            for a in c1:
                for b in c2:
                    d = _distance(positions[a][0], positions[a][1], positions[b][0], positions[b][1])
                    if d < best_dist:
                        best_dist = d
                        best_edge = (min(a, b), max(a, b))

        if best_edge:
            edges.append(best_edge)
            merged = components[0]
            to_remove = None
            for c2 in components[1:]:
                if best_edge[0] in c2 or best_edge[1] in c2:
                    merged = merged | c2
                    to_remove = c2
                    break
            if to_remove:
                components.remove(to_remove)
            components[0] = merged

    return edges


def generate_map(agents: list[Agent], num_neutral: int = 8, width: float = 900, height: float = 600) -> GameState:
    """Sinh bản đồ hoàn chỉnh: tọa độ → cạnh → gán tên → gán thủ phủ.

    Args:
        agents: Danh sách lãnh chúa tham gia
        num_neutral: Số thành trung lập
        width, height: Kích thước bản đồ (px)
    """
    total_castles = len(agents) + num_neutral

    # Tính khoảng cách tối thiểu giữa các thành dựa trên diện tích bản đồ
    min_dist = min(120, (width * height / total_castles) ** 0.5 * 0.6)
    max_conn_dist = min_dist * 2.5  # Phạm vi tối đa để 2 thành có thể kết nối

    # Tạo tọa độ, nếu không đủ thì giảm min_dist và thử lại
    positions = _generate_positions(total_castles, width, height, min_dist)
    if len(positions) < total_castles:
        min_dist *= 0.7
        positions = _generate_positions(total_castles, width, height, min_dist)

    # Tạo cạnh và đảm bảo liên thông
    edges = _build_proximity_edges(positions, max_conn_dist)
    edges = _ensure_connectivity(positions, edges)

    # Gán tên thành ngẫu nhiên
    names = random.sample(CASTLE_NAMES, min(total_castles, len(CASTLE_NAMES)))
    while len(names) < total_castles:
        names.append(f"Thành Vô Danh {len(names) + 1}")

    # Tạo đối tượng Castle cho mỗi tọa độ
    castles: dict[str, Castle] = {}
    castle_ids: list[str] = []

    for i, (x, y) in enumerate(positions):
        cid = f"castle_{i}"
        castle_ids.append(cid)
        castles[cid] = Castle(id=cid, name=names[i], x=x, y=y)

    # Thiết lập kết nối 2 chiều giữa các thành
    for a, b in edges:
        id_a, id_b = castle_ids[a], castle_ids[b]
        if id_b not in castles[id_a].connections:
            castles[id_a].connections.append(id_b)
        if id_a not in castles[id_b].connections:
            castles[id_b].connections.append(id_a)

    # Chọn ngẫu nhiên thành làm thủ phủ cho mỗi lãnh chúa
    agent_indices = random.sample(range(total_castles), len(agents))
    for agent, idx in zip(agents, agent_indices):
        cid = castle_ids[idx]
        castle = castles[cid]
        castle.owner_id = agent.id
        castle.troops = INITIAL_TROOPS
        castle.castle_type = CastleType.CAPITAL
        agent.capital_id = cid

    state = GameState(
        castles=castles,
        agents={a.id: a for a in agents},
    )
    return state
