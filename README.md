# LLM Warlords: Lãnh Chúa Prompt

Zero-player AI Simulation Grand Strategy game. Người chơi "đúc" (mint) Agent bằng System Prompt — sau đó ngồi xem các AI Lãnh Chúa tự ngoại giao, mưu tính và chiến đấu trên bản đồ.

## Cài đặt

```bash
pip install -r requirements.txt
cp .env.example .env
# Điền OPENAI_API_KEY vào file .env
```

## Chạy

```bash
python server.py
```

Mở trình duyệt tại **http://localhost:8000**

## Cách chơi

1. Thiết lập từ 2-8 Lãnh Chúa (AI Agent) với Tên, Tính cách, Chiến lược và Điểm yếu
2. Nhấn **Khởi Chiến** để tạo bản đồ
3. Nhấn **Bước Tiếp** để chạy từng vòng, hoặc **Tự Động** để game tự chạy
4. Theo dõi Biên Niên Sử và Ngoại Giao ở panel phải

## Kiến trúc

```
game/
  models.py          # Data models (Agent, Castle, GameState, ...)
  map_generator.py   # Graph-based map generation
  combat.py          # Combat resolution engine
  engine.py          # 4-phase game loop
llm/
  prompts.py         # Prompt templates cho Central LLM
  client.py          # OpenAI API client
web/
  templates/         # HTML
  static/            # CSS + JS
server.py            # FastAPI + WebSocket server
config.py            # Configuration
```

