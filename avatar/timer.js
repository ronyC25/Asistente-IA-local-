// Widget de temporizador/pomodoro compartido (ventana, avatar y web).
// Uso: <script src="/avatar/timer.js"></script> y JarvisTimer.mount("contenedor").
(function () {
  if (window.JarvisTimer) return;

  const COLORS = {
    trabajo: "#4f9cf9",
    descanso: "#35d0ba",
    descanso_largo: "#2ea8c9",
    pausado: "#f5b942",
    temporizador: "#7c8cf8",
  };

  const CSS = `
  .jt { font-family: "Segoe UI", system-ui, sans-serif; color: #eaf1ff; --c: #4f9cf9; }
  .jt * { box-sizing: border-box; }
  .jt .jt-h { display:flex; align-items:center; gap:8px; margin:0 0 10px; font-size:14px; font-weight:700; letter-spacing:.2px; color:#cfe0ff; }
  .jt .jt-h .jt-ico { font-size:16px; }
  .jt .jt-panel {
    background: linear-gradient(180deg, rgba(23,32,58,.92), rgba(15,21,40,.92));
    border: 1px solid #26365c; border-radius: 16px; padding: 14px; margin-bottom: 12px;
    box-shadow: 0 8px 24px rgba(0,0,0,.28);
  }
  .jt label { font-size: 11px; color: #8b97b3; display: block; margin-bottom: 3px; text-transform: uppercase; letter-spacing: .4px; }
  .jt input {
    background: #131c34; border: 1px solid #2a3a63; color: #eaf1ff; border-radius: 10px;
    padding: 8px 10px; font-size: 14px; width: 100%; outline: none; transition: border-color .15s;
  }
  .jt input:focus { border-color: var(--c); }
  .jt .jt-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .jt button {
    border: none; border-radius: 10px; padding: 9px 14px; cursor: pointer; font-size: 13px;
    font-weight: 700; color: #041024; background: var(--c); transition: transform .08s, filter .15s;
  }
  .jt button:hover { filter: brightness(1.08); }
  .jt button:active { transform: translateY(1px); }
  .jt button.ghost { background: #29375a; color: #dbe6ff; }
  .jt button.danger { background: #2a3550; color: #ff9c9c; }
  .jt button:disabled { opacity: .5; cursor: default; }
  .jt .jt-row { display: flex; gap: 8px; align-items: center; margin-top: 12px; }
  .jt .jt-row button { flex: 1; }

  .jt .jt-list { display: flex; flex-direction: column; gap: 12px; }
  .jt .jt-timer {
    display: flex; align-items: center; gap: 14px; padding: 12px 14px; border-radius: 16px;
    background: linear-gradient(180deg, rgba(23,32,58,.95), rgba(15,21,40,.95));
    border: 1px solid #26365c; box-shadow: 0 8px 24px rgba(0,0,0,.3);
  }
  .jt .jt-ringwrap { position: relative; width: 84px; height: 84px; flex: 0 0 auto; }
  .jt .jt-ring { width: 84px; height: 84px; transform: rotate(-90deg); }
  .jt .jt-ring circle { fill: none; stroke-width: 8; }
  .jt .jt-ring-bg { stroke: #22304f; }
  .jt .jt-ring-fg { stroke: var(--c); stroke-linecap: round; transition: stroke-dashoffset .4s linear, stroke .3s; }
  .jt .jt-ringtime {
    position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
    font-size: 19px; font-weight: 700; font-variant-numeric: tabular-nums; color: #fff;
  }
  .jt .jt-info { flex: 1; min-width: 0; }
  .jt .jt-title { font-size: 14px; font-weight: 700; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .jt .jt-badge {
    font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .4px;
    padding: 2px 8px; border-radius: 999px; color: #041024; background: var(--c);
  }
  .jt .jt-sub { font-size: 12px; color: #8b97b3; margin-top: 3px; }
  .jt .jt-actions { display: flex; gap: 8px; margin-top: 9px; }
  .jt .jt-empty { text-align: center; color: #8b97b3; font-size: 13px; padding: 18px 8px; }
  .jt .jt-empty .jt-ico { display: block; font-size: 30px; margin-bottom: 6px; opacity: .8; }
  .jt .jt-msg {
    display: none; font-size: 12px; color: #ff9c9c; background: rgba(120,30,40,.35);
    border: 1px solid #6a2630; border-radius: 10px; padding: 8px 10px; margin-bottom: 10px;
  }
  .jt .jt-msg.on { display: block; }
  `;
  if (!document.getElementById("jt-style")) {
    const s = document.createElement("style");
    s.id = "jt-style";
    s.textContent = CSS;
    document.head.appendChild(s);
  }

  const esc = (s) =>
    (s || "").replace(/[&<>"]/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  function fmt(seg) {
    seg = Math.max(0, Math.floor(seg));
    const m = Math.floor(seg / 60);
    const s = seg % 60;
    return String(m).padStart(2, "0") + ":" + String(s).padStart(2, "0");
  }

  const CIRC = 2 * Math.PI * 46; // r=46 en viewBox 100

  function mount(el) {
    const root = typeof el === "string" ? document.getElementById(el) : el;
    if (!root || root.dataset.jtMounted) return null;
    root.dataset.jtMounted = "1";
    root.classList.add("jt");
    root.innerHTML = `
      <div id="jt-msg" class="jt-msg"></div>
      <div class="jt-panel">
        <div class="jt-h"><span class="jt-ico">🍅</span> Pomodoro</div>
        <div class="jt-grid">
          <div><label>Trabajo (min)</label><input id="jt-trabajo" type="number" min="1" value="25"></div>
          <div><label>Descanso (min)</label><input id="jt-descanso" type="number" min="1" value="5"></div>
          <div><label>Descanso largo</label><input id="jt-largo" type="number" min="1" value="15"></div>
          <div><label>Ciclos</label><input id="jt-ciclos" type="number" min="1" value="4"></div>
        </div>
        <div class="jt-row"><button id="jt-ini-pom">Iniciar pomodoro</button></div>
      </div>
      <div class="jt-panel">
        <div class="jt-h"><span class="jt-ico">⏱️</span> Temporizador</div>
        <div class="jt-grid">
          <div><label>Minutos</label><input id="jt-min" type="number" min="1" value="10"></div>
          <div><label>Nombre</label><input id="jt-etq" type="text" placeholder="horno"></div>
        </div>
        <div class="jt-row"><button id="jt-ini-tim">Iniciar temporizador</button></div>
      </div>
      <div class="jt-h" style="margin-top:4px"><span class="jt-ico">📋</span> Activos</div>
      <div id="jt-list" class="jt-list"></div>`;

    const q = (id) => root.querySelector("#" + id);
    const num = (id) => parseInt(q(id).value, 10) || null;
    const setMsg = (t) => {
      const m = q("jt-msg");
      m.textContent = t || "";
      m.classList.toggle("on", !!t);
    };
    let inited = false;
    const state = { temporizadores: [] };

    function colorDe(t) {
      if (t.estado === "pausado") return COLORS.pausado;
      if (t.tipo === "pomodoro") return COLORS[t.fase] || COLORS.trabajo;
      return COLORS.temporizador;
    }

    function restanteDe(el2) {
      if (el2.dataset.estado === "pausado") return Number(el2.dataset.restante || 0);
      const fin = el2.dataset.fin ? Date.parse(el2.dataset.fin) : 0;
      return fin ? (fin - Date.now()) / 1000 : 0;
    }

    function tick() {
      root.querySelectorAll(".jt-timer").forEach((card) => {
        const total = Number(card.dataset.total || 0);
        const rest = Math.max(0, restanteDe(card));
        const time = card.querySelector(".jt-ringtime");
        if (time) time.textContent = fmt(rest);
        const fg = card.querySelector(".jt-ring-fg");
        if (fg) {
          const frac = total > 0 ? Math.min(1, rest / total) : 0;
          fg.style.strokeDasharray = String(CIRC);
          fg.style.strokeDashoffset = String(CIRC * (1 - frac));
        }
      });
    }

    function render() {
      const list = q("jt-list");
      if (!state.temporizadores.length) {
        list.innerHTML =
          '<div class="jt-empty"><span class="jt-ico">🕐</span>No hay temporizadores activos.</div>';
        return;
      }
      list.innerHTML = state.temporizadores
        .map((t) => {
          const c = colorDe(t);
          const etq = t.etiqueta
            ? esc(t.etiqueta)
            : t.tipo === "pomodoro"
            ? "Pomodoro"
            : "Temporizador";
          const fase =
            t.tipo === "pomodoro"
              ? `${esc((t.fase || "").replace("_", " "))} · ciclo ${t.ciclo}`
              : t.estado === "pausado"
              ? "pausado"
              : "en curso";
          const pausado = t.estado === "pausado";
          const play = pausado
            ? `<button class="ghost" data-act="reanudar" data-id="${t.id}">▶ Reanudar</button>`
            : `<button class="ghost" data-act="pausar" data-id="${t.id}">⏸ Pausar</button>`;
          return `<div class="jt-timer" data-fin="${t.fin}" data-restante="${t.restante_seg || ""}" data-estado="${t.estado}" data-total="${(t.duracion_min || 0) * 60}" style="--c:${c}">
            <div class="jt-ringwrap">
              <svg class="jt-ring" viewBox="0 0 100 100">
                <circle class="jt-ring-bg" cx="50" cy="50" r="46"></circle>
                <circle class="jt-ring-fg" cx="50" cy="50" r="46"></circle>
              </svg>
              <div class="jt-ringtime">--:--</div>
            </div>
            <div class="jt-info">
              <div class="jt-title">${etq}<span class="jt-badge">${fase}</span></div>
              <div class="jt-actions">${play}
                <button class="danger" data-act="cancelar" data-id="${t.id}">⏹ Detener</button>
              </div>
            </div>
          </div>`;
        })
        .join("");
      tick();
    }

    async function cargar() {
      try {
        const r = await fetch("/temporizadores", { cache: "no-store" });
        if (!r.ok) throw new Error("HTTP " + r.status);
        const data = await r.json();
        state.temporizadores = data.temporizadores || [];
        if (data.config && !inited) {
          inited = true;
          q("jt-trabajo").value = data.config.trabajo_min ?? 25;
          q("jt-descanso").value = data.config.descanso_min ?? 5;
          q("jt-largo").value = data.config.descanso_largo_min ?? 15;
          q("jt-ciclos").value = data.config.ciclos ?? 4;
        }
        setMsg("");
        render();
      } catch (e) {
        setMsg("No se pudo cargar los temporizadores (" + e.message + ").");
      }
    }

    async function post(body) {
      try {
        const r = await fetch("/temporizadores", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        if (!r.ok) throw new Error("HTTP " + r.status);
        setMsg("");
      } catch (e) {
        setMsg("No se pudo iniciar el temporizador (" + e.message + ").");
      }
      await cargar();
    }

    q("jt-ini-pom").addEventListener("click", () =>
      post({
        tipo: "pomodoro",
        trabajo_min: num("jt-trabajo"),
        descanso_min: num("jt-descanso"),
        descanso_largo_min: num("jt-largo"),
        ciclos: num("jt-ciclos"),
      })
    );
    q("jt-ini-tim").addEventListener("click", () =>
      post({
        tipo: "temporizador",
        minutos: num("jt-min"),
        etiqueta: (q("jt-etq").value || "").trim(),
      })
    );
    root.addEventListener("click", async (e) => {
      const b = e.target.closest("button[data-act]");
      if (!b) return;
      b.disabled = true;
      try {
        const r = await fetch(`/temporizadores/${b.dataset.id}/${b.dataset.act}`, {
          method: "POST",
        });
        if (!r.ok) throw new Error("HTTP " + r.status);
        setMsg("");
      } catch (err) {
        setMsg(`No se pudo ${b.dataset.act} el temporizador (${err.message}).`);
      }
      await cargar();
    });

    cargar();
    const t1 = setInterval(tick, 1000);
    const t2 = setInterval(cargar, 3000);
    return {
      cargar,
      detener() {
        clearInterval(t1);
        clearInterval(t2);
      },
    };
  }

  window.JarvisTimer = { mount };
})();
