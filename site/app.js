(() => {
  "use strict";
  const LS = { get: (k, d) => localStorage.getItem("gp-" + k) || d, set: (k, v) => localStorage.setItem("gp-" + k, v) };
  const S = {
    data: null, hist: {}, cur: LS.get("cur", "usd"), view: LS.get("view", "simple"),
    tab: "all", sort: "rank", q: "", sheet: null, pushed: false, dtab: {}, variant: {}, showAll: {},
  };
  const FLAGSHIPS = ["b300", "b200", "h200", "h100", "rtx-pro-6000", "rtx-5090"];
  const TIERS = { all: "全部型号", dc: "数据中心", ws: "工作站", gaming: "消费级", cn: "国内特供" };
  const KIND = {
    "on-demand": ["按需", "od"], secure: ["按需·安全云", "od"], community: ["社区云", "cheap"],
    spot: ["竞价 Spot", "cheap"], marketplace: ["竞价市场", "cheap"], reserved: ["预留/包年", "ref"], serverless: ["Serverless", "ref"],
  };
  const PAGE = 15;
  // 上游英文成色/库存 -> 中文
  const ZH = {
    "new": "全新", "used": "二手", "refurbished": "翻新", "not stated": "成色未注明", "open box": "开箱",
    "in stock": "有货", "in-stock": "有货", "out of stock": "缺货", "out-of-stock": "缺货", "not reported": "", "limited": "库存紧张",
  };
  const zh = (s) => { const k = String(s || "").trim().toLowerCase(); return Object.hasOwn(ZH, k) ? ZH[k] : s; };
  const wide = matchMedia("(min-width: 900px)");

  // ---------- 工具 ----------
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const safeUrl = (u) => (/^https?:\/\//i.test(u || "") ? esc(u) : "");
  const fx = () => S.data.fx.usdcny;
  function usd(v, hourly) {
    if (v == null) return null;
    const c = S.cur === "cny", x = c ? v * fx() : v, sym = c ? "¥" : "$";
    if (hourly) return sym + x.toFixed(2);
    if (c && x >= 1e4) return sym + (x / 1e4).toLocaleString("zh-CN", { maximumFractionDigits: x >= 1e6 ? 0 : 1 }) + "万";
    if (x >= 1e6) return sym + (x / 1e6).toFixed(2) + "M";
    return sym + Math.round(x).toLocaleString("en-US");
  }
  const hr = (v) => usd(v, true);
  const cny = (v) => (v == null ? null : v >= 1e4 ? "¥" + (v / 1e4).toLocaleString("zh-CN", { maximumFractionDigits: 1 }) + "万" : "¥" + Math.round(v).toLocaleString());
  const na = '<span class="na">—</span>';
  const tag = (text, cls = "") => `<span class="tag ${cls}">${esc(text)}</span>`;
  const gpuTag = (n, server) => {
    if (!n) return "";
    if (server) return tag(n >= 32 ? `${n}卡整柜` : `${n}卡整机`, "gpu");
    return n > 1 ? tag(`${n}卡起租`, "gpu") : tag("单卡", "gpu");
  };
  const famMap = {};
  const familyOf = (gid) => famMap[gid] || gid;

  // ---------- 走势 ----------
  function spark(series, w = 120, h = 28) {
    const pts = series.filter((p) => p != null);
    if (pts.length < 2) return `<svg class="sp" viewBox="0 0 ${w} ${h}"></svg>`;
    const min = Math.min(...pts), max = Math.max(...pts), span = max - min || 1, step = w / (series.length - 1);
    let d = "";
    series.forEach((v, i) => {
      if (v == null) return;
      d += (d ? "L" : "M") + (i * step).toFixed(1) + " " + (h - 3 - ((v - min) / span) * (h - 6)).toFixed(1);
    });
    const last = pts[pts.length - 1], first = pts[0];
    const col = last > first * 1.02 ? "var(--up)" : last < first * 0.98 ? "var(--down)" : "var(--info)";
    return `<svg class="sp" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"><path d="${d}" fill="none" stroke="${col}" stroke-width="1.8" stroke-linejoin="round" vector-effect="non-scaling-stroke"/></svg>`;
  }
  const histSeries = (id) => (S.hist[id] || []).slice(-90).map((r) => r[1]);
  function change7(id) {
    const rows = (S.hist[id] || []).filter((r) => r[1] != null);
    if (rows.length < 2) return null;
    const last = rows[rows.length - 1];
    const cutoff = new Date(Date.parse(last[0]) - 7 * 864e5).toISOString().slice(0, 10);
    const base = [...rows].reverse().find((r) => r[0] <= cutoff);
    return base && base[1] ? (last[1] - base[1]) / base[1] : null;
  }
  function chgHtml(c) {
    if (c == null) return "";
    const cls = Math.abs(c) < 0.005 ? "flat" : c > 0 ? "up" : "down";
    return `<span class="chg ${cls}">${c > 0 ? "↑" : c < 0 ? "↓" : ""}${Math.abs(c * 100).toFixed(1)}% 7日</span>`;
  }

  // ---------- 购买摘要（整卡优先，其次整机每卡，再次国内） ----------
  function buyInfo(g) {
    const b = g.buy, c = g.cn;
    if (b.card_min != null) return { lbl: "购买<small>单卡</small>", lo: usd(b.card_min), loP: b.card_min_p, hi: usd(b.card_max), hiP: b.card_max_p };
    if (b.srv_per_min != null) return { lbl: `整机<small>${b.srv_n ? b.srv_n + "卡·" : ""}每卡</small>`, lo: usd(b.srv_per_min), loP: b.srv_min_p, hi: usd(b.srv_per_max), hiP: b.srv_max_p };
    if (c.min != null) return { lbl: "国内<small>现货</small>", lo: cny(c.min), loP: c.min_p, hi: cny(c.max), hiP: c.max_p };
    return null;
  }

  // ---------- 顶部 ----------
  function renderMeta() {
    const d = S.data, ok = d.sources.filter((s) => s.ok).length;
    $("meta").textContent = `${d.date} 更新 · ${d.offers.length.toLocaleString()} 条报价 · ${ok}/${d.sources.length} 源正常 · 1$=${fx().toFixed(2)}¥`;
  }
  function renderTicker() {
    const by = Object.fromEntries(S.data.gpus.map((g) => [g.id, g]));
    $("ticker").innerHTML = FLAGSHIPS.filter((id) => by[id]).map((id) => {
      const g = by[id], r = g.rent, b = buyInfo(g);
      const line = (label, lo, loP, hi, hiP, big) => `<div class="mm${big ? " big" : ""}"><div class="lbl">${label}</div>
        <div class="lo"><b>${lo ?? "—"}</b><span>${esc(loP || "")}</span></div><div class="hi"><b>${hi ?? "—"}</b><span>${esc(hiP || "")}</span></div></div>`;
      return `<div class="tk" data-id="${esc(id)}">
        <div class="tk-h"><b>${esc(g.name)}</b>${chgHtml(change7(id))}</div>
        <div class="mm-head"><span></span><span>最低</span><span>最高</span></div>
        ${line("租用<small>/卡·时</small>", hr(r.od_min), r.od_min_p, hr(r.od_max), r.od_max_p, true)}
        ${b ? line(b.lbl, b.lo, b.loP, b.hi, b.hiP)
            : `<div class="mm"><div class="lbl">购买</div><div class="lo na">暂无</div><div></div></div>`}
        ${spark(histSeries(id), 160, 26)}
      </div>`;
    }).join("");
  }

  // ---------- 列表 ----------
  function matches(g) {
    if (S.tab !== "all" && g.tier !== S.tab) return false;
    if (!S.q) return true;
    if (g.name.toLowerCase().includes(S.q) || g.id.includes(S.q)) return true;
    return S.data.offers.some((o) => familyOf(o.g) === g.id && (o.provider || "").toLowerCase().includes(S.q));
  }
  function sorted(list) {
    const big = Number.MAX_VALUE;
    const by = {
      rank: (a, b) => a.rank - b.rank || (b.rent.median || 0) - (a.rent.median || 0),
      rent: (a, b) => (a.rent.od_min ?? a.rent.any_min ?? big) - (b.rent.od_min ?? b.rent.any_min ?? big),
      buy: (a, b) => (a.buy.card_min ?? a.buy.srv_per_min ?? big) - (b.buy.card_min ?? b.buy.srv_per_min ?? big),
      count: (a, b) => (b.rent.n + b.buy.n + b.cn.n) - (a.rent.n + a.buy.n + a.cn.n),
    }[S.sort];
    return [...list].sort(by);
  }
  const subOf = (g) => [g.arch, g.vram ? g.vram + "GB" : "", g.variants.length > 1 ? `${g.variants.length} 种规格` : ""].filter(Boolean).join(" · ") || TIERS[g.tier];

  function stat(k, v, s, hi) {
    return `<div class="stat${v == null ? " empty" : ""}"><div class="k">${k}</div><div class="v${hi ? " hi" : ""}">${v ?? "—"}</div><div class="s">${esc(s || "")}</div></div>`;
  }
  function card(g, rich) {
    const r = g.rent, b = g.buy;
    const rent = r.od_min != null ? [hr(r.od_min), r.od_min_p] : r.cheap_min != null ? [hr(r.cheap_min), "仅竞价/社区"] : [null, ""];
    const buy = b.card_min != null ? [usd(b.card_min), "单卡"]
      : b.srv_per_min != null ? [usd(b.srv_per_min), `${b.srv_n}卡机·每卡`] : [null, ""];
    let extra = "";
    if (rich) {
      const rows = [
        ["租用中位", hr(r.median)], ["租用最高", hr(r.od_max)],
        ["竞价·社区", hr(r.cheap_min)], ["租用厂商", r.providers ? r.providers + " 家" : null],
        ["整卡最高", usd(b.card_max)], ["整机总价起", b.srv_min ? `${b.srv_n}卡 ${usd(b.srv_min)}` : null],
      ];
      extra = `<div class="extra">${rows.map(([k, v]) => `<div><span>${k}</span><b>${v ?? "—"}</b></div>`).join("")}</div>
        <div class="spark-row"><span>90 天</span>${spark(histSeries(g.id))}${chgHtml(change7(g.id))}</div>`;
    }
    return `<div class="card" data-id="${esc(g.id)}">
      <div class="card-h"><b>${esc(g.name)}</b><span class="sub">${esc(subOf(g))}</span><span class="chev">›</span></div>
      <div class="stats">
        ${stat("租用起 /卡·时", rent[0], rent[1], true)}
        ${stat("购买起", buy[0], buy[1])}
        ${stat("国内现货起", cny(g.cn.min), g.cn.min_p)}
      </div>${extra}</div>`;
  }
  function table(list) {
    const td = (v, s, hi) => `<td>${v != null ? `<span class="pv${hi ? " hi" : ""}">${v}</span>${s ? `<span class="ps">${esc(s)}</span>` : ""}` : na}</td>`;
    return `<div class="tbl-wrap"><table class="main"><thead><tr>
      <th>型号</th><th>按需租用 最低</th><th>最高</th><th>中位</th><th>竞价·社区</th><th>单卡购买 最低~最高</th><th>整机折合每卡</th><th>国内现货</th><th>90 天走势</th>
      </tr></thead><tbody>${list.map((g) => {
        const r = g.rent, b = g.buy;
        return `<tr data-id="${esc(g.id)}">
          <td class="m-name"><b>${esc(g.name)}</b><div>${esc(subOf(g))}</div></td>
          ${td(hr(r.od_min), r.od_min_p, true)}${td(hr(r.od_max), r.od_max_p)}
          ${td(hr(r.median), r.n ? `${r.providers} 家厂商` : "")}${td(hr(r.cheap_min), r.cheap_min_p)}
          ${td(b.card_min != null ? `${usd(b.card_min)}${b.card_max > b.card_min ? " ~ " + usd(b.card_max) : ""}` : null, b.card_min_p)}
          ${td(usd(b.srv_per_min), b.srv_per_min != null ? `${b.srv_n}卡整机 ${usd(b.srv_min)}` : "")}
          ${td(cny(g.cn.min), g.cn.min_p)}
          <td class="sp">${spark(histSeries(g.id), 110, 26)}</td></tr>`;
      }).join("")}</tbody></table></div>`;
  }
  function renderList() {
    const list = sorted(S.data.gpus.filter(matches));
    $("list-h").innerHTML = `${TIERS[S.tab]} <span>${list.length} 个</span>`;
    if (!list.length) { $("list").innerHTML = `<div class="empty">没有匹配的型号</div>`; return; }
    $("list").innerHTML = S.view === "full" && wide.matches ? table(list)
      : `<div class="cards">${list.map((g) => card(g, S.view === "full")).join("")}</div>`;
  }
  function renderTabs() {
    const n = { all: 0, dc: 0, ws: 0, gaming: 0, cn: 0 };
    S.data.gpus.forEach((g) => { n.all++; n[g.tier]++; });
    document.querySelectorAll("#tabs button").forEach((b) => {
      const t = b.dataset.t;
      b.classList.toggle("on", t === S.tab);
      b.innerHTML = `${t === "all" ? "全部" : TIERS[t]}<i>${n[t]}</i>`;
    });
  }

  // ---------- 详情面板 ----------
  function flags(o) {
    return (o.stale ? tag("过期", "warn") : "") + (o.est ? tag("估算", "warn") : "") + (o.ref ? tag("官方价", "ref") : "");
  }
  const name = (o) => { const u = safeUrl(o.url); return u ? `<a class="name" href="${u}" target="_blank" rel="noopener nofollow">${esc(o.provider)}</a>` : `<span class="name">${esc(o.provider)}</span>`; };
  const foot = (...xs) => { const t = xs.filter(Boolean).map(esc).join(" · "); return t ? `<div class="o-foot">${t}</div>` : ""; };
  const desc = (t) => (t ? `<div class="o-desc">${esc(t)}</div>` : "");

  function rentItem(o, best, vname) {
    const [kt, kc] = Object.hasOwn(KIND, o.kind) ? KIND[o.kind] : [o.kind || "—", ""];
    return `<div class="offer${best ? " best" : ""}"><div class="o-top">
      <div class="o-who">${name(o)}${best ? '<span class="best-badge">最低</span>' : ""}
        <div class="o-tags">${o.cn ? tag("国内云", "cn") : ""}${tag(kt, kc)}${gpuTag(o.n, false)}${vname ? tag(vname) : ""}${flags(o)}</div></div>
      <div class="o-price"><b>${hr(o.usd)}</b><small>/卡·时</small>${o.cny_hr != null && S.cur === "usd" ? `<small class="per">¥${o.cny_hr.toFixed(2)}/卡·时</small>` : ""}${o.n > 1 ? `<small class="per">${o.n}卡整机 ${hr(o.usd * o.n)}/时</small>` : ""}</div>
    </div>${desc(o.cfg)}${foot(o.region, zh(o.stock), o.at)}</div>`;
  }
  function buyItem(o, best, vname) {
    const server = o.server || o.n > 1;
    return `<div class="offer${best ? " best" : ""}"><div class="o-top">
      <div class="o-who">${name(o)}${best ? '<span class="best-badge">最低</span>' : ""}
        <div class="o-tags">${gpuTag(o.n || 1, server)}${zh(o.cond) ? tag(zh(o.cond)) : ""}${vname ? tag(vname) : ""}${flags(o)}</div></div>
      <div class="o-price"><b>${usd(o.usd)}</b>${server && o.n > 1 ? `<small class="per">每卡 ${usd(o.per)}</small>` : "<small>单卡</small>"}</div>
    </div>${desc(o.cfg)}${foot(zh(o.stock), o.at)}</div>`;
  }
  function cnItem(o, best, vname) {
    return `<div class="offer${best ? " best" : ""}"><div class="o-top">
      <div class="o-who">${name(o)}${best ? '<span class="best-badge">最低</span>' : ""}
        <div class="o-tags">${o.server ? tag("8卡整机", "gpu") : ""}${o.kind ? tag(o.kind) : ""}${vname ? tag(vname) : ""}${flags(o)}</div></div>
      <div class="o-price"><b>${cny(o.cny)}${o.cny_hi ? `<span style="font-weight:500;font-size:13px"> ~ ${cny(o.cny_hi)}</span>` : ""}</b><small>≈ $${Math.round(o.cny / fx()).toLocaleString("en-US")}</small></div>
    </div>${desc(o.cfg)}${foot(o.stock, o.at)}</div>`;
  }

  // 统计框：有最高价时左右并列"最低 | 最高"；无数据返回空串（不渲染）
  function box(k, lo, hi, s) {
    if (lo == null) return "";
    const range = hi && hi !== lo
      ? `<div class="lohi"><div><span>最低</span><b class="hi">${lo}</b></div><div><span>最高</span><b>${hi}</b></div></div>`
      : `<div class="lohi one"><div><b class="hi">${lo}</b></div></div>`;
    return `<div class="d-box"><div class="k"><span>${k}</span></div>${range}${s ? `<div class="s">${esc(s)}</div>` : ""}</div>`;
  }

  function renderSheet() {
    const g = S.data.gpus.find((x) => x.id === S.sheet);
    if (!g) return;
    const r = g.rent, b = g.buy, c = g.cn;
    const v = S.variant[g.id] || "all";
    const vname = Object.fromEntries(g.variants.map((x) => [x.id, x.name]));
    const multi = g.variants.length > 1;
    const mine = S.data.offers.filter((o) => familyOf(o.g) === g.id && (v === "all" || o.g === v));
    const lists = {
      rent: mine.filter((o) => o.type === "rent").sort((a, b2) => a.usd - b2.usd),
      buy: mine.filter((o) => o.type === "buy").sort((a, b2) => (a.per ?? a.usd) - (b2.per ?? b2.usd)),
      cn: mine.filter((o) => o.type === "cn").sort((a, b2) => a.cny - b2.cny),
    };
    let dt = S.dtab[g.id];
    if (!dt || !lists[dt].length) dt = ["rent", "buy", "cn"].find((k) => lists[k].length) || "rent";
    S.dtab[g.id] = dt;

    const head = `<div class="d-h"><h3 id="sheet-title">${esc(g.name)}</h3><div class="sub">${esc(subOf(g))} · ${esc(TIERS[g.tier])}</div></div>`;
    const boxes = [
      box("按需租用 /卡·时", hr(r.od_min), hr(r.od_max), r.median != null ? `中位 ${hr(r.median)} · ${r.providers} 家厂商` : ""),
      box("竞价·社区 /卡·时", hr(r.cheap_min), null, r.cheap_min_p),
      box("单卡购买", usd(b.card_min), usd(b.card_max), b.card_min_p ? `最低 ${b.card_min_p}` : ""),
      box(b.srv_n ? `${b.srv_n}卡整机 · 折合每卡` : "整机 · 折合每卡", usd(b.srv_per_min), usd(b.srv_per_max), b.srv_min ? `整机总价 ${usd(b.srv_min)} 起` : ""),
      box("国内现货", cny(c.min), cny(c.max), c.min_p ? `最低 ${c.min_p}` : ""),
    ].filter(Boolean);
    if (boxes.length % 2) boxes[boxes.length - 1] = boxes[boxes.length - 1].replace('class="d-box"', 'class="d-box wide"');
    const trend = histSeries(g.id).some((x) => x != null)
      ? `<div class="d-box wide"><div class="k"><span>按需最低价 · 近 90 天</span>${chgHtml(change7(g.id))}</div>${spark(histSeries(g.id), 300, 46)}</div>` : "";
    const grid = `<div class="d-grid">${boxes.join("")}${trend}</div>`;
    const chips = multi ? `<div class="chips">${[{ id: "all", name: "全部规格" }, ...g.variants].map((x) =>
      `<button class="chip${x.id === v ? " on" : ""}" data-variant="${esc(x.id)}">${esc(x.name)}</button>`).join("")}</div>` : "";
    const labels = { rent: "租用", buy: "购买", cn: "国内现货" };
    const tabs = `<div class="d-tabs"><div class="seg">${Object.keys(labels).map((k) =>
      `<button data-dtab="${k}" class="${k === dt ? "on" : ""}"${lists[k].length ? "" : " disabled"}>${labels[k]} ${lists[k].length}</button>`).join("")}</div></div>`;

    const items = lists[dt], key = `${g.id}:${v}:${dt}`, all = S.showAll[key];
    const fn = { rent: rentItem, buy: buyItem, cn: cnItem }[dt];
    const body = items.length
      ? `<div class="offers">${(all ? items : items.slice(0, PAGE)).map((o, i) => fn(o, i === 0 && !o.ref, multi && v === "all" ? vname[o.g] : "")).join("")}</div>
         ${items.length > PAGE ? `<button class="more" data-more="${esc(key)}">${all ? "收起" : `展开全部 ${items.length} 条`}</button>` : ""}`
      : `<div class="empty">该规格暂无报价</div>`;
    $("sheet-body").innerHTML = head + grid + chips + tabs + body;
  }
  function showSheet(id) {
    S.sheet = id;
    renderSheet();
    $("sheet").hidden = false;
    document.body.classList.add("lock");
    document.querySelector("#sheet .panel").scrollTop = 0;
  }
  function hideSheet() {
    S.sheet = null;
    $("sheet").hidden = true;
    document.body.classList.remove("lock");
  }
  function openSheet(id) {
    if (location.hash.slice(1) === id) return showSheet(id);
    S.pushed = true;
    location.hash = id;  // 触发 hashchange；手机返回键即可关闭
  }
  function closeSheet() {
    if (S.pushed) { S.pushed = false; history.back(); }
    else { history.replaceState(null, "", location.pathname + location.search); hideSheet(); }
  }
  function onHash() {
    let id = "";
    try { id = decodeURIComponent(location.hash.slice(1)); } catch { /* 非法 hash 忽略 */ }
    if (id && S.data.gpus.some((g) => g.id === id)) showSheet(id);
    else { S.pushed = false; hideSheet(); }
  }

  // ---------- 数据源 ----------
  function renderSources() {
    $("sources").innerHTML = S.data.sources.map((s) => `<div class="src${s.ok ? "" : " bad"}">
      <b><i class="dot"></i>${s.url ? `<a href="${safeUrl(s.url)}" target="_blank" rel="noopener">${esc(s.name)}</a>` : esc(s.name)}</b>
      <span>${s.ok ? `正常 · ${s.count} 条` : `本次失败，沿用 ${esc(s.at || "旧")} 的 ${s.count} 条`}</span></div>`).join("");
  }

  // ---------- 主题 ----------
  const SUN = '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="4.5"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';
  const MOON = '<svg viewBox="0 0 24 24"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/></svg>';
  const isDark = () => (document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")) === "dark";
  function paintThemeBtn() { $("theme").innerHTML = isDark() ? SUN : MOON; }

  // ---------- 交互 ----------
  function setSeg(id, attr, val) { document.querySelectorAll(`#${id} button`).forEach((b) => b.classList.toggle("on", b.dataset[attr] === val)); }
  function render() { renderTicker(); renderList(); if (S.sheet) renderSheet(); }
  function bind() {
    const openFrom = (e) => { const el = e.target.closest("[data-id]"); if (el) openSheet(el.dataset.id); };
    $("list").addEventListener("click", openFrom);
    $("ticker").addEventListener("click", openFrom);
    $("sheet").addEventListener("click", (e) => {
      if (e.target.closest("[data-close]")) return closeSheet();
      const chip = e.target.closest("[data-variant]");
      if (chip) { S.variant[S.sheet] = chip.dataset.variant; return renderSheet(); }
      const t = e.target.closest("[data-dtab]");
      if (t && !t.disabled) { S.dtab[S.sheet] = t.dataset.dtab; return renderSheet(); }
      const more = e.target.closest("[data-more]");
      if (more) { S.showAll[more.dataset.more] = !S.showAll[more.dataset.more]; renderSheet(); }
    });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && S.sheet) closeSheet(); });
    window.addEventListener("hashchange", onHash);
    $("tabs").addEventListener("click", (e) => { const b = e.target.closest("button"); if (!b) return; S.tab = b.dataset.t; renderTabs(); renderList(); });
    $("view").addEventListener("click", (e) => { const b = e.target.closest("button"); if (!b) return; S.view = b.dataset.v; LS.set("view", S.view); setSeg("view", "v", S.view); renderList(); });
    $("cur").addEventListener("click", (e) => { const b = e.target.closest("button"); if (!b) return; S.cur = b.dataset.c; LS.set("cur", S.cur); setSeg("cur", "c", S.cur); render(); });
    $("sort").addEventListener("change", (e) => { S.sort = e.target.value; renderList(); });
    $("theme").addEventListener("click", () => {
      const t = isDark() ? "light" : "dark";
      document.documentElement.dataset.theme = t; LS.set("theme", t); paintThemeBtn();
    });
    wide.addEventListener("change", renderList);
    let timer;
    $("q").addEventListener("input", (e) => { clearTimeout(timer); timer = setTimeout(() => { S.q = e.target.value.trim().toLowerCase(); renderList(); }, 120); });
  }

  async function init() {
    paintThemeBtn();
    setSeg("view", "v", S.view);
    setSeg("cur", "c", S.cur);
    try {
      const [d, h] = await Promise.all([
        fetch("data/latest.json", { cache: "no-cache" }).then((r) => r.json()),
        fetch("data/history.json", { cache: "no-cache" }).then((r) => (r.ok ? r.json() : {})).catch(() => ({})),
      ]);
      S.data = d; S.hist = h;
      d.gpus.forEach((g) => g.variants.forEach((v) => (famMap[v.id] = g.id)));
      renderMeta(); renderTabs(); renderSources(); render(); bind();
      onHash();
    } catch (err) {
      $("meta").textContent = "数据加载失败，请稍后刷新";
      console.error(err);
    }
  }
  init();
})();
