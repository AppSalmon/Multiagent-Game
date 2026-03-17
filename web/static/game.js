const AGENT_COLORS = [
    "#f0b429", "#ef4444", "#3b82f6", "#22c55e",
    "#a855f7", "#06b6d4", "#f97316", "#ec4899",
];

const PHASE_LABELS = {
    income: "Thu Hoạch",
    decision: "Quyết Định",
    combat: "Chiến Đấu",
};

class LLMWarlords {
    constructor() {
        this.state = null;
        this.ws = null;
        this.canvas = null;
        this.ctx = null;
        this.agentColorMap = {};
        this.hoveredCastle = null;

        this.zoom = 1;
        this.panX = 0;
        this.panY = 0;
        this._isPanning = false;
        this._panStartX = 0;
        this._panStartY = 0;
        this._panStartPanX = 0;
        this._panStartPanY = 0;
        this._baseTransform = null;
        this._mapBackgroundPattern = null;

        this.initDOM();
        this.initCanvas();
        this.connectWS();
    }

    initDOM() {
        this.setupModal = document.getElementById("setupModal");
        this.agentFormsContainer = document.getElementById("agentForms");
        this.addAgentBtn = document.getElementById("addAgentBtn");
        this.startGameBtn = document.getElementById("startGameBtn");
        this.runBtn = document.getElementById("runBtn");
        this.stepBtn = document.getElementById("stepBtn");
        this.stopBtn = document.getElementById("stopBtn");
        this.newGameBtn = document.getElementById("newGameBtn");
        this.turnDisplay = document.getElementById("turnDisplay");
        this.phaseBadge = document.getElementById("phaseBadge");
        this.agentList = document.getElementById("agentList");
        this.eventsPane = document.getElementById("eventsPane");
        this.tooltip = document.getElementById("castleTooltip");
        this.victoryBanner = document.getElementById("victoryBanner");

        this.addAgentBtn.onclick = () => this.addAgentForm();
        this.startGameBtn.onclick = () => this.startGame();
        this.runBtn.onclick = () => this.runGame();
        this.stepBtn.onclick = () => this.stepGame();
        this.stopBtn.onclick = () => this.stopGame();
        this.newGameBtn.onclick = () => this.newGame();

        this.addAgentForm(
        "Hoàng Dũng",
            "Bạo chúa quyết đoán, trọng danh dự nhưng đa nghi. Thích dùng lời lẽ bề trên.",
            "Ưu tiên kinh tế. Chỉ tấn công kẻ yếu nhất bản đồ. Sẵn sàng ký hiệp ước hòa bình giả để đâm sau lưng.",
            "Dễ bị chọc giận nếu ai đó xúc phạm tên của mình."
        );
        this.addAgentForm(
            "Minh Hải",
            "Nhà ngoại giao khôn ngoan, lời ngọt nhưng tâm sâu. Luôn tỏ ra thân thiện.",
            "Xây dựng liên minh với người mạnh nhất. Không bao giờ tấn công trước. Chờ đợi thời cơ để phản bội đồng minh khi họ suy yếu.",
            "Quá tham lam, đôi khi mở rộng quá nhanh dẫn đến phòng thủ mỏng."
        );
        this.addAgentForm(
            "Linh Chi",
            "Nữ tướng lạnh lùng, ít nói nhưng hành động quyết liệt. Khinh thường kẻ yếu đuối.",
            "Tấn công chớp nhoáng (blitz). Tập trung toàn bộ lực lượng vào một hướng. Không bao giờ chia quân.",
            "Bỏ qua ngoại giao, dễ bị nhiều người cùng đánh."
        );
    }

    addAgentForm(name = "", persona = "", directive = "", flaw = "") {
        const idx = this.agentFormsContainer.children.length;
        const color = AGENT_COLORS[idx % AGENT_COLORS.length];

        const div = document.createElement("div");
        div.className = "agent-form";
        div.innerHTML = `
            <div class="form-header">
                <span class="form-number" style="color:${color}">Lãnh Chúa #${idx + 1}</span>
                ${idx >= 2 ? '<button class="remove-agent-btn" onclick="game.removeAgentForm(this)">Xoá</button>' : ''}
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label>Tên</label>
                    <input type="text" class="agent-name" placeholder="VD: Hoàng Tuấn" value="${name}">
                </div>
                <div class="form-group">
                    <label>Điểm yếu (tùy chọn)</label>
                    <input type="text" class="agent-flaw" placeholder="VD: Dễ bị khiêu khích..." value="${flaw}">
                </div>
            </div>
            <div class="form-group">
                <label>Tính cách (Persona)</label>
                <textarea class="agent-persona" rows="2" placeholder="Mô tả tính cách, cách giao tiếp...">${persona}</textarea>
            </div>
            <div class="form-group">
                <label>Chiến lược cốt lõi (Core Directive)</label>
                <textarea class="agent-directive" rows="2" placeholder="Kim chỉ nam cho mọi hành động...">${directive}</textarea>
            </div>
        `;
        this.agentFormsContainer.appendChild(div);
    }

    removeAgentForm(btn) {
        const form = btn.closest(".agent-form");
        form.remove();
        this.reindexForms();
    }

    reindexForms() {
        this.agentFormsContainer.querySelectorAll(".agent-form").forEach((form, i) => {
            const color = AGENT_COLORS[i % AGENT_COLORS.length];
            form.querySelector(".form-number").textContent = `Lãnh Chúa #${i + 1}`;
            form.querySelector(".form-number").style.color = color;
        });
    }

    async startGame() {
        const forms = this.agentFormsContainer.querySelectorAll(".agent-form");
        const agents = [];

        for (const form of forms) {
            const name = form.querySelector(".agent-name").value.trim();
            const persona = form.querySelector(".agent-persona").value.trim();
            const directive = form.querySelector(".agent-directive").value.trim();
            const flaw = form.querySelector(".agent-flaw").value.trim();

            if (!name || !persona || !directive) {
                alert("Vui lòng điền đầy đủ Tên, Tính cách và Chiến lược cho mỗi Lãnh Chúa!");
                return;
            }

            agents.push({ name, persona, core_directive: directive, flaw });
        }

        if (agents.length < 2) {
            alert("Cần tối thiểu 2 Lãnh Chúa!");
            return;
        }

        this.startGameBtn.disabled = true;
        this.startGameBtn.innerHTML = '<span class="spinner"></span>Đang tạo...';

        try {
            const res = await fetch("/api/setup", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ agents, num_neutral: Math.max(6, agents.length * 3) }),
            });
            const data = await res.json();
            this.updateState(data);
            this.resetView();
            this.setupModal.classList.add("hidden");
            this.enableControls(true);
        } catch (e) {
            alert("Lỗi khi tạo game: " + e.message);
        }

        this.startGameBtn.disabled = false;
        this.startGameBtn.textContent = "Khởi Chiến!";
    }

    async runGame() {
        this.runBtn.disabled = true;
        this.stepBtn.disabled = true;
        this.stopBtn.disabled = false;
        try {
            await fetch("/api/run", { method: "POST" });
        } catch (e) {
            console.error("Run error:", e);
        }
    }

    async stepGame() {
        this.stepBtn.disabled = true;
        this.stepBtn.innerHTML = '<span class="spinner"></span>Đang xử lý...';
        try {
            const res = await fetch("/api/step", { method: "POST" });
            const data = await res.json();
            if (!data.error) this.updateState(data);
        } catch (e) {
            console.error("Step error:", e);
        }
        this.stepBtn.disabled = false;
        this.stepBtn.textContent = "Bước Tiếp";
    }

    async stopGame() {
        await fetch("/api/stop", { method: "POST" });
        this.enableControls(true);
        this.stopBtn.disabled = true;
    }

    newGame() {
        this.setupModal.classList.remove("hidden");
        this.victoryBanner.classList.remove("show");
        this.state = null;
        this.eventsPane.innerHTML = "";
        this.agentList.innerHTML = "";
        this.enableControls(false);
        this.resetView();
        this.drawMap();
    }

    enableControls(enabled) {
        this.runBtn.disabled = !enabled;
        this.stepBtn.disabled = !enabled;
        this.stopBtn.disabled = true;
    }

    // --- WebSocket ---

    connectWS() {
        const protocol = location.protocol === "https:" ? "wss:" : "ws:";
        this.ws = new WebSocket(`${protocol}//${location.host}/ws`);

        this.ws.onmessage = (event) => {
            const msg = JSON.parse(event.data);
            if (msg.type === "turn_complete") {
                this.updateState(msg.state);
            } else if (msg.type === "phase_update") {
                this.updatePhase(msg.phase, msg.turn);
            }
        };

        this.ws.onclose = () => {
            setTimeout(() => this.connectWS(), 3000);
        };
    }

    updatePhase(phase, turn) {
        this.phaseBadge.textContent = PHASE_LABELS[phase] || phase;
        this.phaseBadge.classList.add("active");
    }

    // --- State Update ---

    updateState(data) {
        this.state = data;
        this.buildAgentColorMap();
        this.turnDisplay.textContent = `Vòng ${data.current_turn}`;
        this.phaseBadge.classList.remove("active");
        this.phaseBadge.textContent = "Chờ";
        this.renderAgentList();
        this.renderChronicle();
        this.drawMap();

        if (data.game_over) {
            this.showVictory(data.winner_name);
            this.enableControls(false);
        }
    }

    buildAgentColorMap() {
        if (!this.state) return;
        this.state.agents.forEach((agent, i) => {
            this.agentColorMap[agent.id] = AGENT_COLORS[i % AGENT_COLORS.length];
        });
    }

    // --- Render Agent List ---

    renderAgentList() {
        if (!this.state) return;
        let html = "";

        const sorted = [...this.state.agents].sort((a, b) => b.total_troops - a.total_troops);

        for (const agent of sorted) {
            const color = this.agentColorMap[agent.id] || "#666";
            const statusCls = agent.alive ? "alive" : "dead";
            const statusText = agent.alive ? "Sống" : "Loại";
            const cardCls = agent.alive ? "" : "eliminated";

            html += `
                <div class="agent-card ${cardCls}">
                    <div class="agent-header">
                        <span class="agent-color-dot" style="background:${color}"></span>
                        <span class="agent-name">${agent.name}</span>
                        <span class="agent-status ${statusCls}">${statusText}</span>
                    </div>
                    <div class="agent-stats">
                        <span>Thành: ${agent.num_castles}</span>
                        <span>Quân: ${agent.total_troops}</span>
                    </div>
                </div>
            `;
        }

        this.agentList.innerHTML = html;
    }

    // --- Render Chronicle ---

    renderChronicle() {
        if (!this.state || !this.state.chronicles) return;

        let html = "";

        for (const ch of this.state.chronicles) {
            html += `<div class="turn-separator">Vòng ${ch.turn}</div>`;

            for (const event of ch.events) {
                let cls = "";
                if (event.includes("TRẬN CHIẾN")) cls = "battle";
                else if (event.includes("BỊ LOẠI")) cls = "elimination";
                else if (event.includes("CHIẾN THẮNG")) cls = "victory";
                else if (event.includes("thu hoạch")) cls = "income";
                else if (event.includes("LỆNH")) cls = "order";
                else if (event.includes("CHIẾN LƯỢC")) cls = "strategy";
                else if (event.includes("LỖI")) cls = "error";

                html += `<div class="event-item ${cls}">${event}</div>`;
            }
        }

        this.eventsPane.innerHTML = html;
        this.eventsPane.scrollTop = this.eventsPane.scrollHeight;
    }

    // --- Canvas Map with Pan & Zoom ---

    initCanvas() {
        this.canvas = document.getElementById("mapCanvas");
        this.ctx = this.canvas.getContext("2d");
        this.resizeCanvas();
        window.addEventListener("resize", () => this.resizeCanvas());

        this.canvas.addEventListener("mousedown", (e) => this._onMouseDown(e));
        this.canvas.addEventListener("mousemove", (e) => this._onMouseMove(e));
        this.canvas.addEventListener("mouseup", () => this._onMouseUp());
        this.canvas.addEventListener("mouseleave", () => {
            this._onMouseUp();
            this.hoveredCastle = null;
            this.tooltip.style.display = "none";
            this.drawMap();
        });
        this.canvas.addEventListener("wheel", (e) => this._onWheel(e), { passive: false });
    }

    resetView() {
        this.zoom = 1;
        this.panX = 0;
        this.panY = 0;
        this._baseTransform = null;
    }

    resizeCanvas() {
        const rect = this.canvas.parentElement.getBoundingClientRect();
        this.canvas.width = rect.width * window.devicePixelRatio;
        this.canvas.height = rect.height * window.devicePixelRatio;
        this.canvas.style.width = rect.width + "px";
        this.canvas.style.height = rect.height + "px";
        this.ctx.setTransform(window.devicePixelRatio, 0, 0, window.devicePixelRatio, 0, 0);
        this._baseTransform = null;
        this.drawMap();
    }

    _getBaseTransform() {
        if (this._baseTransform && this.state) return this._baseTransform;
        if (!this.state || !this.state.castles.length) return { sx: 1, sy: 1, ox: 0, oy: 0 };

        const rect = this.canvas.parentElement.getBoundingClientRect();
        const padding = 70;

        let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
        for (const c of this.state.castles) {
            minX = Math.min(minX, c.x);
            maxX = Math.max(maxX, c.x);
            minY = Math.min(minY, c.y);
            maxY = Math.max(maxY, c.y);
        }

        const mapW = maxX - minX || 1;
        const mapH = maxY - minY || 1;
        const availW = rect.width - padding * 2;
        const availH = rect.height - padding * 2;
        const scale = Math.min(availW / mapW, availH / mapH);

        this._baseTransform = {
            sx: scale, sy: scale,
            ox: padding + (availW - mapW * scale) / 2 - minX * scale,
            oy: padding + (availH - mapH * scale) / 2 - minY * scale,
        };
        return this._baseTransform;
    }

    worldToScreen(x, y) {
        const t = this._getBaseTransform();
        const sx = x * t.sx + t.ox;
        const sy = y * t.sy + t.oy;
        return {
            x: sx * this.zoom + this.panX,
            y: sy * this.zoom + this.panY,
        };
    }

    screenToCanvas(clientX, clientY) {
        const rect = this.canvas.getBoundingClientRect();
        return { x: clientX - rect.left, y: clientY - rect.top };
    }

    _onMouseDown(e) {
        if (e.button === 0) {
            this._isPanning = true;
            this._panStartX = e.clientX;
            this._panStartY = e.clientY;
            this._panStartPanX = this.panX;
            this._panStartPanY = this.panY;
            this.canvas.style.cursor = "grabbing";
        }
    }

    _onMouseMove(e) {
        if (this._isPanning) {
            this.panX = this._panStartPanX + (e.clientX - this._panStartX);
            this.panY = this._panStartPanY + (e.clientY - this._panStartY);
            this.tooltip.style.display = "none";
            this.drawMap();
            return;
        }

        this._updateHover(e);
    }

    _onMouseUp() {
        this._isPanning = false;
        this.canvas.style.cursor = "grab";
    }

    _onWheel(e) {
        e.preventDefault();
        const pos = this.screenToCanvas(e.clientX, e.clientY);

        const zoomFactor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
        const newZoom = Math.max(0.3, Math.min(5, this.zoom * zoomFactor));

        this.panX = pos.x - (pos.x - this.panX) * (newZoom / this.zoom);
        this.panY = pos.y - (pos.y - this.panY) * (newZoom / this.zoom);
        this.zoom = newZoom;

        this.drawMap();
    }

    _updateHover(e) {
        if (!this.state) return;

        const pos = this.screenToCanvas(e.clientX, e.clientY);

        let closest = null;
        let closestDist = 30 / this.zoom + 10;

        for (const c of this.state.castles) {
            const sp = this.worldToScreen(c.x, c.y);
            const d = Math.hypot(sp.x - pos.x, sp.y - pos.y);
            if (d < closestDist) {
                closestDist = d;
                closest = c;
            }
        }

        if (closest !== this.hoveredCastle) {
            this.hoveredCastle = closest;
            this.drawMap();

            if (closest) {
                const owner = closest.owner_name || "Trung Lập";
                const color = closest.owner_id ? (this.agentColorMap[closest.owner_id] || "#888") : "#888";
                const capital = closest.castle_type === "capital" ? " [THỦ PHỦ]" : "";
                const capitalAgent = closest.castle_type === "capital" && closest.owner_name
                    ? `<div class="tooltip-capital-agent">Agent thủ phủ: ${closest.owner_name}</div>`
                    : "";

                this.tooltip.innerHTML = `
                    <div class="tooltip-name">${closest.name}${capital}</div>
                    <div class="tooltip-owner" style="color:${color}">Chủ: ${owner}</div>
                    ${capitalAgent}
                    <div class="tooltip-troops">Quân: ${closest.troops}</div>
                `;
                this.tooltip.style.display = "block";
                this.tooltip.style.left = (pos.x + 15) + "px";
                this.tooltip.style.top = (pos.y - 10) + "px";
            } else {
                this.tooltip.style.display = "none";
            }
        } else if (closest) {
            this.tooltip.style.left = (pos.x + 15) + "px";
            this.tooltip.style.top = (pos.y - 10) + "px";
        }
    }

    drawMap() {
        const ctx = this.ctx;
        const rect = this.canvas.parentElement.getBoundingClientRect();
        ctx.clearRect(0, 0, rect.width, rect.height);
        this.drawMapBackground(ctx, rect.width, rect.height);

        if (!this.state || !this.state.castles.length) {
            ctx.fillStyle = "#5a6578";
            ctx.font = "16px system-ui";
            ctx.textAlign = "center";
            ctx.fillText("Thiết lập trò chơi để bắt đầu...", rect.width / 2, rect.height / 2);
            return;
        }

        const castleMap = {};
        for (const c of this.state.castles) {
            castleMap[c.id] = c;
        }

        const scaledLine = Math.max(1, 1.5 * this.zoom);

        // Draw edges
        ctx.strokeStyle = "#2d3a4f";
        ctx.lineWidth = scaledLine;
        const drawnEdges = new Set();

        for (const c of this.state.castles) {
            const p1 = this.worldToScreen(c.x, c.y);
            for (const connId of c.connections) {
                const edgeKey = [c.id, connId].sort().join("-");
                if (drawnEdges.has(edgeKey)) continue;
                drawnEdges.add(edgeKey);

                const conn = castleMap[connId];
                if (!conn) continue;
                const p2 = this.worldToScreen(conn.x, conn.y);

                const gradient = ctx.createLinearGradient(p1.x, p1.y, p2.x, p2.y);
                gradient.addColorStop(0, c.owner_id ? (this.agentColorMap[c.owner_id] || "#2d3a4f") + "66" : "#34425766");
                gradient.addColorStop(1, conn.owner_id ? (this.agentColorMap[conn.owner_id] || "#2d3a4f") + "66" : "#34425766");

                ctx.beginPath();
                ctx.moveTo(p1.x, p1.y);
                ctx.lineTo(p2.x, p2.y);
                ctx.strokeStyle = gradient;
                ctx.stroke();
            }
        }

        // Draw castles
        for (const c of this.state.castles) {
            const pos = this.worldToScreen(c.x, c.y);
            const isHovered = this.hoveredCastle && this.hoveredCastle.id === c.id;
            const isCapital = c.castle_type === "capital";

            let color = "#4a5568";
            let borderColor = "#2d3a4f";

            if (c.owner_id) {
                color = this.agentColorMap[c.owner_id] || "#4a5568";
                borderColor = color;
            }

            const baseRadius = isCapital ? 18 : 14;
            const radius = baseRadius * this.zoom;
            const drawRadius = isHovered ? radius + 4 : radius;

            if (isHovered) {
                ctx.beginPath();
                ctx.arc(pos.x, pos.y, drawRadius + 6, 0, Math.PI * 2);
                ctx.fillStyle = color + "20";
                ctx.fill();
            }

            const coreFill = ctx.createRadialGradient(
                pos.x - drawRadius * 0.35,
                pos.y - drawRadius * 0.35,
                drawRadius * 0.25,
                pos.x,
                pos.y,
                drawRadius
            );
            if (c.owner_id) {
                coreFill.addColorStop(0, color + "95");
                coreFill.addColorStop(1, color + "33");
            } else {
                coreFill.addColorStop(0, "#324156cc");
                coreFill.addColorStop(1, "#1a223550");
            }

            ctx.beginPath();
            ctx.arc(pos.x, pos.y, drawRadius, 0, Math.PI * 2);
            ctx.fillStyle = coreFill;
            ctx.fill();
            ctx.strokeStyle = borderColor;
            ctx.lineWidth = (isCapital ? 3 : 2) * this.zoom;
            ctx.stroke();

            if (isCapital) {
                ctx.beginPath();
                ctx.arc(pos.x, pos.y, drawRadius + 5 * this.zoom, 0, Math.PI * 2);
                ctx.strokeStyle = color + "8c";
                ctx.lineWidth = Math.max(1.2, 2 * this.zoom);
                ctx.stroke();
                this.drawStar(ctx, pos.x, pos.y, 6 * this.zoom, 5, color);
            }

            if (c.troops > 0) {
                ctx.fillStyle = "#e8edf5";
                ctx.font = `bold ${Math.max(9, 11 * this.zoom)}px system-ui`;
                ctx.textAlign = "center";
                ctx.textBaseline = "middle";
                ctx.fillText(c.troops.toString(), pos.x, pos.y);
            }

            ctx.fillStyle = isHovered ? "#e8edf5" : "#9ca8bd";
            ctx.font = `${Math.max(8, 10 * this.zoom)}px system-ui`;
            ctx.textAlign = "center";
            ctx.textBaseline = "top";
            ctx.shadowColor = "rgba(0, 0, 0, 0.7)";
            ctx.shadowBlur = 6;
            ctx.fillText(c.name, pos.x, pos.y + drawRadius + 4);
            ctx.shadowBlur = 0;

            if (isCapital && c.owner_name) {
                ctx.fillStyle = color;
                ctx.font = `600 ${Math.max(8, 9 * this.zoom)}px system-ui`;
                ctx.textBaseline = "top";
                ctx.fillText(`Agent: ${c.owner_name}`, pos.x, pos.y + drawRadius + 16);
            }
        }

        // Zoom indicator
        if (this.zoom !== 1) {
            ctx.fillStyle = "#5a657880";
            ctx.font = "11px system-ui";
            ctx.textAlign = "right";
            ctx.textBaseline = "bottom";
            ctx.fillText(`${Math.round(this.zoom * 100)}%`, rect.width - 12, rect.height - 8);
        }
    }

    drawStar(ctx, cx, cy, r, points, color) {
        ctx.save();
        ctx.fillStyle = color;
        ctx.beginPath();
        for (let i = 0; i < points * 2; i++) {
            const radius = i % 2 === 0 ? r : r * 0.4;
            const angle = (Math.PI * i) / points - Math.PI / 2;
            const x = cx + radius * Math.cos(angle);
            const y = cy + radius * Math.sin(angle);
            i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
        }
        ctx.closePath();
        ctx.fill();
        ctx.restore();
    }

    drawMapBackground(ctx, width, height) {
        if (!this._mapBackgroundPattern) {
            const offscreen = document.createElement("canvas");
            offscreen.width = 80;
            offscreen.height = 80;
            const patternCtx = offscreen.getContext("2d");

            patternCtx.fillStyle = "#0d1424";
            patternCtx.fillRect(0, 0, offscreen.width, offscreen.height);
            patternCtx.strokeStyle = "rgba(148, 163, 184, 0.08)";
            patternCtx.lineWidth = 1;
            patternCtx.beginPath();
            patternCtx.moveTo(0, 0);
            patternCtx.lineTo(0, 80);
            patternCtx.moveTo(0, 0);
            patternCtx.lineTo(80, 0);
            patternCtx.stroke();

            this._mapBackgroundPattern = ctx.createPattern(offscreen, "repeat");
        }

        if (this._mapBackgroundPattern) {
            ctx.fillStyle = this._mapBackgroundPattern;
            ctx.fillRect(0, 0, width, height);
        }

        const glow = ctx.createRadialGradient(
            width * 0.5,
            height * 0.45,
            Math.min(width, height) * 0.12,
            width * 0.5,
            height * 0.45,
            Math.max(width, height) * 0.65
        );
        glow.addColorStop(0, "rgba(56, 189, 248, 0.08)");
        glow.addColorStop(1, "rgba(10, 14, 23, 0)");
        ctx.fillStyle = glow;
        ctx.fillRect(0, 0, width, height);
    }

    showVictory(winnerName) {
        document.getElementById("winnerName").textContent = winnerName || "???";
        this.victoryBanner.classList.add("show");
    }

    hideVictory() {
        this.victoryBanner.classList.remove("show");
    }
}

let game;
document.addEventListener("DOMContentLoaded", () => {
    game = new LLMWarlords();
});
