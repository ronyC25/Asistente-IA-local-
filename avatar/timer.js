// Widget de temporizador/pomodoro compartido (avatar, ventana y web).
// Uso: <script src="/avatar/timer.js"></script> y JarvisTimer.mount("contenedor").
(function () {
  if (window.JarvisTimer) return;

  const CSS = `
  .jt { font-family: "Segoe UI", system-ui, sans-serif; color: #eaf1ff; }
  .jt h3 { margin: 0 0 8px; font-size: 14px; color: #35d0ba; }
  .jt .jt-card { background: rgba(11,16,32,.72); border: 1px solid #2a3a63; border-radius: 12px; padding: 10px 12px; margin-bottom: 10px; }
  .jt label { font-size: 12px; color: #8b97b3; display: block; margin-bottom: 2px; }
  .jt input { background: #1b2440; border: 1px solid #2a3a63; color: #eaf1ff; border-radius: 8px; padding: 6px 8px; font-size: 13px; width: 100%; box-sizing: border-box; }
  .jt .jt-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .jt button { border: none; border-radius: 8px; padding: 7px 12px; cursor: pointer; font-size: 13px; font-weight: 600; color: #041024; background: #4f9cf9; }
  .jt button.ghost { background: #33405f; color: #eaf1ff; }
  .jt button:disabled { opacity: .5; cursor: default; }
  .jt .jt-row { display: flex; gap: 6px; align-items: center; margin-top: 8px; }
  .jt .jt-item { display: flex; align-items: center; gap: 10px; padding: 8px 0; border-bottom: 1px solid #22314f; }
  .jt .jt-item:last-child { border-bottom: none; }
  .jt .jt-time { font-size: 22px; font-variant-numeric: tabular-nums; min-width: 74px; }
  .jt .jt-meta { flex: 1; font-size: 12px; color: #b9c6e6; }
  .jt .jt-pill { font-size: 11px; padding: 2px 8px; border-radius: 999px; background: #33405f; }
  .jt .jt-pill.pausado { background: #f5b942; color: #241a00; }
  .jt .jt-empty { color: #8b97b3; font-size: 13px; }
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

  function mount(el) {
    const root = typeof el === "string" ? document.getElementById(el) : el;
    if (!root || root.dataset.jtMounted) return null;
    root.dataset.jtMounted = "1";
    root.classList.add("jt");
    root.innerHTML = `
      <div class="jt-card">
        <h3>Pomodoro</h3>
        <div class="jt-grid">
          <div><label>Trabajo (min)</label><input id="jt-trabajo" type="number" min="1" value="25"></div>
          <div><label>Descanso (min)</label><input id="jt-descanso" type="number" min="1" value="5"></div>
          <div><label>Descanso largo</label><input id="jt-largo" type="number" min="1" value="15"></div>
          <div><label>Ciclos</label><input id="jt-ciclos" type="number" min="1" value="4"></div>
        </div>
        <div class="jt-row"><button id="jt-ini-pom">Iniciar pomodoro</button></div>
      </div>
      <div class="jt-card">
        <h3>Temporizador</h3>
        <div class="jt-grid">
          <div><label>Minutos</label><input id="jt-min" type="number" min="1" value="10"></div>
          <div><label>Nombre (opcional)</label><input id="jt-etq" type="text" placeholder="horno"></div>
        </div>
        <div class="jt-row"><button id="jt-ini-tim">Iniciar temporizador</button></div>
      </div>
      <div class="jt-card">
        <h3>Activos</h3>
        <div id="jt-list"><div class="jt-empty">Sin temporizadores.</div></div>
      </div>`;

    const q = (id) => root.querySelector("#" + id);
    const num = (id) => parseInt(q(id).value, 10) || null;
    let inited = false;

    const state = { temporizadores: [] };

    function tick() {
      const now = Date.now();
      root.querySelectorAll(".jt-time").forEach((el2) => {
        const estado = el2.dataset.estado;
        let seg;
        if (estado === "pausado") {
          seg = Number(el2.dataset.restante || 0);
        } else {
          const fin = el2.dataset.fin ? Date.parse(el2.dataset.fin) : 0;
          seg = fin ? (fin - now) / 1000 : 0;
        }
        el2.textContent = fmt(seg);
      });
    }

    function render() {
      const list = q("jt-list");
      if (!state.temporizadores.length) {
        list.innerHTML = '<div class="jt-empty">Sin temporizadores.</div>';
        return;
      }
      list.innerHTML = state.temporizadores
        .map((t) => {
          const etq = t.etiqueta
            ? esc(t.etiqueta)
            : t.tipo === "pomodoro"
            ? "Pomodoro"
            : "Temporizador";
          const fase =
            t.tipo === "pomodoro"
              ? ` · ${esc((t.fase || "").replace("_", " "))} (ciclo ${t.ciclo})`
              : "";
          const pausado = t.estado === "pausado";
          const play = pausado
            ? `<button class="ghost" data-act="reanudar" data-id="${t.id}">Reanudar</button>`
            : `<button class="ghost" data-act="pausar" data-id="${t.id}">Pausar</button>`;
          return `<div class="jt-item">
            <div class="jt-time" data-fin="${t.fin}" data-restante="${t.restante_seg || ""}" data-estado="${t.estado}">--:--</div>
            <div class="jt-meta">${etq}${fase} ${pausado ? '<span class="jt-pill pausado">pausado</span>' : ""}</div>
            ${play}
            <button data-act="cancelar" data-id="${t.id}">Detener</button>
          </div>`;
        })
        .join("");
      tick();
    }

    async function cargar() {
      try {
        const r = await fetch("/temporizadores", { cache: "no-store" });
        const data = await r.json();
        state.temporizadores = data.temporizadores || [];
        if (data.config && !inited) {
          inited = true;
          q("jt-trabajo").value = data.config.trabajo_min ?? 25;
          q("jt-descanso").value = data.config.descanso_min ?? 5;
          q("jt-largo").value = data.config.descanso_largo_min ?? 15;
          q("jt-ciclos").value = data.config.ciclos ?? 4;
        }
        render();
      } catch (e) {
        /* sin conexion */
      }
    }

    async function post(body) {
      try {
        await fetch("/temporizadores", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
      } catch (e) {
        /* ignore */
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
        await fetch(`/temporizadores/${b.dataset.id}/${b.dataset.act}`, {
          method: "POST",
        });
      } catch (err) {
        /* ignore */
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
