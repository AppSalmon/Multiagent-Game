"""Cấu hình chung cho toàn bộ ứng dụng.

Đọc API key và model từ file .env, đồng thời định nghĩa các hằng số
cân bằng gameplay (quân/vòng, chi phí chiếm thành, điều kiện thắng...).
"""

import os
from dotenv import load_dotenv

load_dotenv()

# === Cấu hình LLM ===
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gemma-3-27b-it")

# === Hằng số cân bằng gameplay ===
TROOPS_PER_CASTLE_PER_TURN = 10   # Mỗi thành tạo thêm bao nhiêu quân mỗi lượt
NEUTRAL_CAPTURE_COST = 10          # Chi phí tối thiểu để chiếm thành trung lập
INITIAL_TROOPS = 30                # Quân ban đầu tại thủ phủ mỗi lãnh chúa
WIN_TERRITORY_PERCENT = 95         # Chiếm >= 80% bản đồ → thắng ngay
MAX_TURNS = 50                     # Số lượt tối đa trước khi game kết thúc
