/* 多彩黔行 · 前端逻辑 */
const state = {
  days: 3, people: 2, budget: 3000, hours: 10,
  season: "autumn", mode: "public",
  themes: [], tags: [],
  result: null, meta: null,
};

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

/* ---------- 视图切换 ---------- */
function switchView(name) {
  $$(".view").forEach(v => v.classList.toggle("active", v.id === "view-" + name));
  $$(".nav-btn").forEach(b => b.classList.toggle("active", b.dataset.view === name));
  window.scrollTo({ top: 0, behavior: "smooth" });
}

document.addEventListener("click", e => {
  const nav = e.target.closest(".nav-btn");
  if (nav) switchView(nav.dataset.view);
  const brand = e.target.closest(".brand");
  if (brand) switchView("home");
});

/* ---------- 提示 ---------- */
let toastTimer;
function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.hidden = true), 2200);
}

/* ---------- 滑块 ---------- */
function bindRange(id, key, fmt = v => v) {
  const input = $("#" + id), out = $("#" + id + "Val");
  const sync = () => {
    const v = +input.value;
    state[key] = v;
    out.textContent = fmt(v);
    const p = ((v - input.min) / (input.max - input.min)) * 100;
    input.style.setProperty("--p", p + "%");
  };
  input.addEventListener("input", sync);
  sync();
}
bindRange("days", "days");
bindRange("people", "people");
bindRange("budget", "budget");
bindRange("hours", "hours");

/* ---------- 单选芯片 ---------- */
function bindSingleGroup(sel, key, attr) {
  const root = $(sel);
  root.addEventListener("click", e => {
    const chip = e.target.closest(".chip");
    if (!chip) return;
    $$(".chip", root).forEach(c => c.classList.remove("active"));
    chip.classList.add("active");
    state[key] = chip.dataset[attr];
  });
}
bindSingleGroup("#seasonChips", "season", "season");
bindSingleGroup("#modeChips", "mode", "mode");

/* ---------- 多选芯片（主题上限 3） ---------- */
function bindMulti(rootSel, key, limit) {
  $(rootSel).addEventListener("click", e => {
    const chip = e.target.closest(".chip");
    if (!chip) return;
    const id = chip.dataset.id;
    const idx = state[key].indexOf(id);
    if (idx >= 0) {
      state[key].splice(idx, 1);
      chip.classList.remove("active");
    } else {
      if (limit && state[key].length >= limit) {
        toast(`最多选择 ${limit} 个`);
        return;
      }
      state[key].push(id);
      chip.classList.add("active");
    }
  });
}

/* ---------- 初始化元数据 ---------- */
async function loadMeta() {
  const res = await fetch("/api/meta");
  const meta = await res.json();
  state.meta = meta;

  $("#themeChips").innerHTML = meta.themes.map(t =>
    `<button class="chip" data-id="${t.id}" title="${t.desc}">${t.name}</button>`).join("");

  const mainTags = meta.tags.filter(([, n]) => n >= 2).slice(0, 12);
  $("#tagChips").innerHTML = mainTags.map(([name, n]) =>
    `<button class="chip" data-id="${name}">${name}<small>${n}</small></button>`).join("");

  bindMulti("#themeChips", "themes", 3);
  bindMulti("#tagChips", "tags", 6);

  renderExplore(meta);
}

/* ---------- 景点库 ---------- */
let exploreFilter = "全部";
function renderExplore(meta) {
  const cities = ["全部", ...meta.cities.map(c => c.name)];
  $("#exploreFilters").innerHTML = cities.map(c =>
    `<button class="chip ${c === exploreFilter ? "active" : ""}" data-city="${c}">${c}</button>`).join("");
  $("#exploreFilters").onclick = e => {
    const b = e.target.closest(".chip");
    if (!b) return;
    exploreFilter = b.dataset.city;
    renderExplore(meta);
  };
  const cityMap = Object.fromEntries(meta.cities.map(c => [c.id, c.name]));
  const list = meta.spots.filter(s => exploreFilter === "全部" || cityMap[s.city] === exploreFilter);
  $("#spotGrid").innerHTML = list.map(s => `
    <div class="spot-card">
      <h4>${s.name}<span class="badge ${s.level === "5A" ? "a5" : ""}">${s.level}</span></h4>
      <div class="city">${cityMap[s.city]} · ${s.type}</div>
      <p>${s.intro}</p>
      <div class="row"><span>建议 ${s.hours} 小时 · ${s.best}</span><b>${s.ticket > 0 ? "¥" + s.ticket : "免费"}</b></div>
    </div>`).join("");
}

/* ---------- 发起规划 ---------- */
async function doPlan() {
  const btn = $("#planBtn");
  btn.disabled = true;
  btn.querySelector(".btn-text").hidden = true;
  btn.querySelector(".btn-loading").hidden = false;

  const payload = {
    days: state.days, people: state.people, budget: state.budget,
    tags: state.tags, themeIds: state.themes, mode: state.mode,
    season: state.season, maxHoursPerDay: state.hours,
    budgetLevel: state.budget < 2000 ? "low" : state.budget > 6000 ? "high" : "mid",
  };

  try {
    const t0 = performance.now();
    const res = await fetch("/api/plan", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "规划失败");
    const ms = Math.round(performance.now() - t0);
    state.result = data;
    state.lastRequest = payload;
    renderResult(data, ms);
    switchView("result");
  } catch (err) {
    toast(err.message);
  } finally {
    btn.disabled = false;
    btn.querySelector(".btn-text").hidden = false;
    btn.querySelector(".btn-loading").hidden = true;
  }
}
$("#planBtn").addEventListener("click", doPlan);
$("#resetBtn").addEventListener("click", () => location.reload());
$("#backBtn").addEventListener("click", () => switchView("home"));

/* ---------- 渲染结果 ---------- */
const fmtTime = m => {
  const h = Math.floor(m / 60), mi = Math.round(m % 60);
  return `${String(h).padStart(2, "0")}:${String(mi).padStart(2, "0")}`;
};

function renderResult(data, ms) {
  const s = data.summary;
  const req = data.request;
  $("#resultTitle").textContent = `${req.days}天${req.people}人 · 贵州行程方案`;
  $("#resultMeta").textContent =
    `共 ${s.spotCount} 个景点 · 总里程 ${s.totalDistanceKm} km · 规划耗时 ${ms} ms`;

  const b = s.breakdown;
  $("#budgetBar").innerHTML = `
    <div class="budget-cell"><span>门票</span><b>¥${b.ticket}</b></div>
    <div class="budget-cell"><span>住宿</span><b>¥${b.hotel}</b></div>
    <div class="budget-cell"><span>餐饮</span><b>¥${b.meal}</b></div>
    <div class="budget-cell total">
      <span>预估合计 ${s.overBudget ? '<em class="warn">超预算</em>' : "（在预算内）"}</span>
      <b class="${s.overBudget ? "warn" : ""}">¥${s.estimatedTotal}</b>
      <small>人均 ¥${s.perPerson}</small>
    </div>`;

  $("#daysContainer").innerHTML = data.days.map(d => renderDay(d)).join("");
}

function renderDay(d) {
  const spots = d.spots || [];
  const items = [];
  spots.forEach((sp, i) => {
    items.push({ kind: "move", to: sp.name, min: sp.moveMin, km: sp.moveKm, first: i === 0 });
    items.push({ kind: "spot", data: sp });
  });

  // 重建时间轴：车程块与景点块交替
  let tl = "";
  let lastEnd = null;
  spots.forEach((sp, i) => {
    const moveLabel = i === 0 ? "出发前往" : "乘车前往";
    tl += `
      <div class="tl-item move">
        <div class="tl-time">${lastEnd ? fmtTime(lastEnd) : ""}</div>
        <div class="tl-line"><div class="tl-dot" style="border-color:#a9bcc4"></div></div>
        <div class="tl-body">
          <div class="tl-card" style="background:#f7f9fa;border-color:#eef1f3;padding:8px 12px">
            <span class="badge move">车程 ${sp.moveMin} 分钟</span>
            <span style="font-size:12.5px;color:var(--ink-2);margin-left:6px">${moveLabel} ${sp.name} · ${sp.moveKm} km</span>
          </div>
        </div>
      </div>`;
    tl += `
      <div class="tl-item">
        <div class="tl-time">${fmtTime(sp.start)}</div>
        <div class="tl-line"><div class="tl-dot"></div></div>
        <div class="tl-body">
          <div class="tl-card">
            <div class="tl-top">
              <b>${sp.name}</b>
              <span class="badge ${sp.level === "5A" ? "a5" : ""}">${sp.level}</span>
              ${sp.tags.map(t => `<span class="tag">${t}</span>`).join("")}
            </div>
            <div class="tl-desc">${sp.intro}</div>
            <div class="tl-tip">${sp.tip}</div>
            <div class="tl-meta">
              <span>游玩 ${(sp.dur / 60).toFixed(1)} 小时</span>
              <span>${fmtTime(sp.start)} – ${fmtTime(sp.end)}</span>
              <span>门票 ${sp.ticket > 0 ? "¥" + sp.ticket + "/人" : "免费"}</span>
            </div>
          </div>
        </div>
      </div>`;
    lastEnd = sp.end;
  });

  // 晚餐 + 回酒店
  const lastSpot = spots[spots.length - 1];
  if (lastSpot) {
    tl += `
      <div class="tl-item meal">
        <div class="tl-time">${fmtTime(Math.max(lastEnd, 17.5 * 60))}</div>
        <div class="tl-line"><div class="tl-dot"></div></div>
        <div class="tl-body">
          <div class="tl-card meal-card">
            <div class="tl-top"><b>晚餐 · 地方风味</b></div>
            <div class="tl-desc">${(d.foods || []).map(f => `${f.name}（${f.desc}）`).join("；") || "就近就餐"}</div>
          </div>
        </div>
      </div>`;
  }

  const hotel = d.hotel;
  return `
    <div class="day-card">
      <div class="day-head">
        <div class="day-no"><small>DAY</small><b>${d.day}</b></div>
        <div class="day-title">
          <h3>${d.theme}</h3>
          <span>${d.city ? d.city + " · " : ""}${spots.map(x => x.name).join(" → ") || "休整日"}</span>
        </div>
        <div class="day-stats">
          <span>里程 <b>${d.distanceKm}</b> km</span>
          <span>游玩 <b>${d.activeHours}</b> h</span>
          <span>结束 <b>${d.endClock}</b></span>
        </div>
      </div>
      <div class="timeline">${tl || '<p class="muted" style="padding:16px 0">本日无安排</p>'}</div>
      <div class="day-foot">
        <div class="hotel">
          <div class="hotel-icon">🏡</div>
          <div style="flex:1">
            <h4>${hotel ? hotel.name : "未匹配到住宿"}</h4>
            <p>${hotel ? hotel.desc : ""}</p>
            ${hotel ? `<p style="margin-top:4px">${hotel.tags.map(t => `<span class="tag">${t}</span>`).join(" ")} · 评分 ${hotel.rating}</p>` : ""}
          </div>
          ${hotel ? `<div class="hotel-price">¥${hotel.price}<small style="color:var(--muted);font-weight:400">/间</small></div>` : ""}
        </div>
        <div class="foods">
          ${(d.foods || []).map(f => `<span class="food-chip">${f.name}</span>`).join("")}
        </div>
      </div>
    </div>`;
}

/* ---------- 分享 ---------- */
$("#shareBtn").addEventListener("click", async () => {
  if (!state.result) return;
  const res = await fetch("/api/share", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ request: state.lastRequest, result: state.result }),
  });
  const data = await res.json();
  if (data.url) {
    const full = location.origin + data.url;
    $("#modalTitle").textContent = "行程已生成分享链接";
    $("#modalBody").innerHTML = `任何人打开该链接都能查看这份行程：<br><code style="font-size:12px;color:var(--brand)">${full}</code>`;
    $("#modal").hidden = false;
    $("#modalCopy").onclick = async () => {
      try { await navigator.clipboard.writeText(full); toast("链接已复制"); }
      catch { toast("请手动复制"); }
    };
  } else {
    toast("生成失败，请稍后重试");
  }
});
$("#modalClose").addEventListener("click", () => ($("#modal").hidden = true));
$("#modal").addEventListener("click", e => { if (e.target.id === "modal") $("#modal").hidden = true; });

/* ---------- 导出图片（Canvas 版行程卡） ---------- */
$("#exportBtn").addEventListener("click", () => exportCard());

function exportCard() {
  const data = state.result;
  if (!data) return;
  const W = 1080, pad = 56;
  const dayH = 300;
  const H = 280 + data.days.length * dayH + 80;
  const c = document.createElement("canvas");
  c.width = W; c.height = H;
  const ctx = c.getContext("2d");

  ctx.fillStyle = "#f6f8f7"; ctx.fillRect(0, 0, W, H);
  const g = ctx.createLinearGradient(0, 0, W, 260);
  g.addColorStop(0, "#1c6b5c"); g.addColorStop(1, "#124b5e");
  ctx.fillStyle = g; ctx.fillRect(0, 0, W, 240);

  ctx.fillStyle = "#fff";
  ctx.font = "bold 46px 'PingFang SC','Microsoft YaHei',sans-serif";
  ctx.fillText("多彩黔行 · " + data.request.days + " 天行程", pad, 110);
  ctx.font = "22px 'PingFang SC','Microsoft YaHei',sans-serif";
  ctx.fillStyle = "rgba(255,255,255,.82)";
  ctx.fillText(`${data.request.people} 人 · ${data.summary.spotCount} 个景点 · 总里程 ${data.summary.totalDistanceKm} km`, pad, 155);
  ctx.fillStyle = "#e0a63d";
  ctx.font = "bold 34px 'PingFang SC','Microsoft YaHei',sans-serif";
  ctx.fillText(`预估 ¥${data.summary.estimatedTotal}　人均 ¥${data.summary.perPerson}`, pad, 205);

  let y = 290;
  data.days.forEach(d => {
    ctx.fillStyle = "#fff";
    roundRect(ctx, pad, y, W - pad * 2, dayH - 24, 22); ctx.fill();
    ctx.fillStyle = "#1c6b5c";
    roundRect(ctx, pad + 24, y + 26, 84, 34, 10); ctx.fill();
    ctx.fillStyle = "#fff"; ctx.font = "bold 20px 'PingFang SC',sans-serif";
    ctx.fillText("DAY " + d.day, pad + 42, y + 50);

    ctx.fillStyle = "#0e1b22"; ctx.font = "bold 26px 'PingFang SC',sans-serif";
    ctx.fillText(d.theme, pad + 124, y + 50);

    ctx.font = "19px 'PingFang SC',sans-serif"; ctx.fillStyle = "#3c515b";
    const names = d.spots.map(s => s.name).join("  →  ") || "休整";
    ctx.fillText(names.slice(0, 26), pad + 24, y + 106);
    if (names.length > 26) ctx.fillText(names.slice(26, 52), pad + 24, y + 136);

    ctx.fillStyle = "#7b9099"; ctx.font = "17px 'PingFang SC',sans-serif";
    ctx.fillText(`${d.distanceKm} km　游玩 ${d.activeHours} h　结束 ${d.endClock}`, pad + 24, y + 172);
    if (d.hotel) ctx.fillText("住 " + d.hotel.name, pad + 24, y + 204);
    y += dayH;
  });

  ctx.fillStyle = "#9aacb3"; ctx.font = "17px 'PingFang SC',sans-serif";
  ctx.fillText("由「多彩黔行」智能规划生成 · 数据来源：贵州省 A 级景区公开名录", pad, H - 40);

  const a = document.createElement("a");
  a.download = "多彩黔行行程卡.png";
  a.href = c.toDataURL("image/png");
  a.click();
  toast("行程卡已导出");
}
function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

/* ---------- 滚动阴影 ---------- */
window.addEventListener("scroll", () => {
  $(".topbar").classList.toggle("scrolled", window.scrollY > 8);
});

/* ---------- 启动 ---------- */
async function boot() {
  await loadMeta();
  // 分享链接直达：/s/<id> 打开即渲染只读行程
  if (window.__SHARE_ID__) {
    try {
      const res = await fetch("/api/share/" + window.__SHARE_ID__);
      if (!res.ok) throw new Error("行程不存在或已失效");
      const d = await res.json();
      state.result = d.result;
      state.lastRequest = d.request;
      renderResult(d.result, 0);
      $("#shareBtn").style.display = "none";
      $("#resultTitle").textContent = (d.request.days || d.result.request.days) + "天贵州行程分享";
      $("#resultMeta").textContent = `由「多彩黔行」生成 · 浏览 ${d.views} 次`;
      switchView("result");
    } catch (err) {
      toast(err.message);
    }
  }
}
boot();
