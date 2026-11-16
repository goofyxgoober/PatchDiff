// patchdiff search page

const TYPES = ["buff", "nerf", "bug_fix", "new_content", "other"];
const NAMES = { buff: "Buff", nerf: "Nerf", bug_fix: "Bug fix", new_content: "New content", other: "Other change" };
const PLURALS = { buff: "buffs", nerf: "nerfs", bug_fix: "fixes", new_content: "additions", other: "other" };
const GLYPHS = { buff: "↑", nerf: "↓", bug_fix: "✓", new_content: "+", other: "~" };

let changeType = "";
let lastQuery = "";

const form = document.getElementById("search-form");
const box = document.getElementById("q");
const status = document.getElementById("status");
const out = document.getElementById("results");

function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function gameName(slug) {
  if (!slug) return "";
  let words = slug.split("-");
  for (let i = 0; i < words.length; i++) {
    words[i] = words[i].charAt(0).toUpperCase() + words[i].slice(1);
  }
  return words.join(" ").replace("Counter Strike", "Counter-Strike");
}

function plural(n, word) {
  if (n === 1) return n + " " + word;
  return n + " " + word + (/(s|ch|sh|x)$/.test(word) ? "es" : "s");
}

function day(d) {
  return `<span class="nowrap">${esc(d)}</span>`;
}

// wrap query terms in <mark>, text is escaped first
function highlight(text, terms) {
  let html = esc(text);
  let parts = [];
  for (let t of terms || []) {
    if (t.length > 1) parts.push(t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  }
  if (parts.length === 0) return html;
  let re = new RegExp("\\b(" + parts.join("|") + ")", "gi");
  return html.replace(re, "<mark>$1</mark>");
}

function typeOf(rec) {
  if (!rec.extracted) return "unknown";
  return rec.change_type || "other";
}

// only show numbers or a real before/after, a lone "increased" says nothing the type doesn't
function values(rec) {
  if (!rec.new_value) return "";
  if (!rec.old_value && !/\d/.test(rec.new_value)) return "";
  let old = rec.old_value ? `<span class="old">${esc(rec.old_value)}</span><span class="to">→</span>` : "";
  return `<div class="values">${old}<span class="new">${esc(rec.new_value)}</span></div>`;
}

function changeRow(rec, terms) {
  let t = typeOf(rec);
  let glyph = GLYPHS[t] || "?";
  let item = rec.item
    ? `<button class="item" data-item="${esc(rec.item_canon)}" data-game="${esc(rec.game)}" title="Show every change to ${esc(rec.item)}">${esc(rec.item)}</button>`
    : `<span class="item none">No item found</span>`;
  let kind = t === "unknown" ? "Not labeled yet" : NAMES[t];
  let stat = rec.stat ? `<span class="stat">${esc(rec.stat)}</span>` : "";
  let trail = [];
  if (rec.section) trail.push(rec.section);
  if (rec.parent) trail.push(rec.parent);
  let trailHtml = trail.length ? `<p class="trail">Under ${esc(trail.join(" / "))}</p>` : "";
  let warn = rec.flags
    ? `<span class="unverified" title="Failed check: ${esc(rec.flags.replace(/,/g, ", ").replace(/_/g, " "))}">⚠ Part of this extraction isn't in the original text, check the patch</span>`
    : "";
  let score = rec.score != null ? `<span class="score">BM25 ${rec.score.toFixed(2)}</span>` : "";
  let patch = rec.version ? `${rec.post_title} (${rec.version})` : rec.post_title;
  return `
    <article class="change ${t}">
      <div class="gutter" aria-hidden="true">${glyph}</div>
      <div>
        ${trailHtml}
        <div class="headline">${item}<span class="kind">${kind}</span>${stat}</div>
        ${values(rec)}
        <p class="bullet">${highlight(rec.text, terms)}</p>
        ${warn}
      </div>
      <div class="source">
        <span class="date">${esc(rec.date)}</span>
        <span class="game">${gameName(rec.game)}</span>
        <a href="${esc(rec.url)}" target="_blank" rel="noopener" title="${esc(patch)}">Read the patch</a>
        ${score}
      </div>
    </article>`;
}

function diffstat(types) {
  let html = "";
  for (let t of types) html += `<i class="${t}" title="${NAMES[t] || t}"></i>`;
  return `<span class="diffstat">${html}</span>`;
}

function emptyState(query) {
  return `<div class="empty">
    <h2>Nothing matched &ldquo;${esc(query)}&rdquo;.</h2>
    <p>Patch notes name things exactly, so try the item's in-game name, a stat like &ldquo;recoil&rdquo; or &ldquo;cooldown&rdquo;, or clear the game and year filters on the left.</p>
  </div>`;
}

function showList(data) {
  let n = data.results.length;
  if (n === 0) {
    status.innerHTML = "";
    out.innerHTML = emptyState(data.query);
    return;
  }
  let line = `<b>${plural(n, "change")}</b> for &ldquo;${esc(data.query)}&rdquo;`;
  if (data.expanded_to.length) {
    line += `, also searching for <span class="also">${esc(data.expanded_to.join(", "))}</span>`;
  }
  status.innerHTML = line;
  let html = "";
  for (let rec of data.results) html += changeRow(rec, data.terms);
  out.innerHTML = html;
}

// newest patch first, each patch shows its changes to this item
function showHistory(tl, fromQuery) {
  if (tl.changes.length === 0) {
    status.innerHTML = "";
    out.innerHTML = emptyState(tl.item);
    return;
  }
  status.innerHTML = fromQuery ? `Your question was answered as the history of <b>${esc(tl.item)}</b>.` : "";

  let byDate = {};
  let dates = [];
  for (let rec of tl.changes) {
    if (!byDate[rec.date]) {
      byDate[rec.date] = [];
      dates.push(rec.date);
    }
    byDate[rec.date].push(rec);
  }
  dates.sort().reverse();

  let tally = "";
  for (let t of TYPES) {
    if (tl.counts[t]) tally += `<span class="kind ${t}"><b>${tl.counts[t]}</b>${PLURALS[t]}</span>`;
  }

  let patches = "";
  for (let d of dates) {
    let types = [];
    let rows = "";
    for (let rec of byDate[d]) {
      types.push(typeOf(rec) === "unknown" ? "other" : typeOf(rec));
      rows += changeRow(rec, []);
    }
    patches += `
      <section class="patch">
        <div class="patch-date"><b>${d}</b>${diffstat(types)}<small>${esc(byDate[d][0].post_title)}</small></div>
        <div>${rows}</div>
      </section>`;
  }

  let back = fromQuery ? "" : `<button class="back" id="back">Back to the results for &ldquo;${esc(lastQuery)}&rdquo;</button>`;
  out.innerHTML = `
    ${back}
    <header class="history-head">
      <h2>${esc(tl.item)}</h2>
      <p>${gameName(tl.changes[0].game)}. Changed ${plural(tl.changes.length, "time")} across ${plural(dates.length, "patch")}, from ${day(dates[dates.length - 1])} to ${day(dates[0])}. This counts every record that names it, including grouped lines like &ldquo;Sg553 and AUG&rdquo;.</p>
      <div class="tally">${tally}</div>
    </header>
    ${patches}`;
  if (!fromQuery) document.getElementById("back").onclick = () => run(lastQuery);
}

function showBoard(board, query) {
  let what = board.change_type ? PLURALS[board.change_type] : "changes";
  if (board.items.length === 0) {
    status.innerHTML = "";
    out.innerHTML = emptyState(query);
    return;
  }
  status.innerHTML = `Your question was answered as a count: <b>${plural(board.items.length, "item")}</b> with ${board.at_least} or more ${what}.`;
  let rows = "";
  for (let r of board.items) {
    rows += `<tr>
      <td><button class="item" data-item="${esc(r.item)}" data-game="${esc(r.game)}">${esc(r.item)}</button></td>
      <td>${diffstat(r.types)}</td>
      <td class="n">${r.count}</td>
      <td class="when">${gameName(r.game)}, last on ${esc(r.last)}</td>
    </tr>`;
  }
  out.innerHTML = `<table class="board">
    <thead><tr><th>Item</th><th>Changes by type</th><th class="n">Total</th><th class="when">Latest</th></tr></thead>
    <tbody>${rows}</tbody>
  </table>`;
}

function params(query) {
  let p = new URLSearchParams();
  p.set("q", query);
  let game = document.getElementById("game").value;
  let from = document.getElementById("from").value;
  let to = document.getElementById("to").value;
  if (game) p.set("game", game);
  if (from) p.set("from", from);
  if (to) p.set("to", to);
  if (changeType) p.set("type", changeType);
  return p;
}

async function run(query) {
  query = query.trim();
  if (!query) return;
  lastQuery = query;
  box.value = query;
  document.body.classList.add("searched");
  let p = params(query);
  history.replaceState(null, "", "?" + p.toString());
  let res = await fetch("/api/search?" + p.toString());
  let data = await res.json();
  if (data.mode === "timeline") showHistory(data.timeline, true);
  else if (data.mode === "leaderboard") showBoard(data.leaderboard, query);
  else showList(data);
}

async function openItem(item, game) {
  let res = await fetch("/api/timeline?item=" + encodeURIComponent(item) + "&game=" + encodeURIComponent(game));
  let data = await res.json();
  document.body.classList.add("searched");
  showHistory(data.timeline, false);
  window.scrollTo(0, 0);
}

// a real record with a before and after value, shown on the landing page
async function loadSpecimen() {
  let res = await fetch("/api/search?q=c4+radius&k=10");
  let data = await res.json();
  let pick = null;
  for (let rec of data.results || []) {
    if (!pick && rec.old_value && rec.new_value && /\d/.test(rec.new_value)) pick = rec;
  }
  if (!pick) return;
  let spot = document.getElementById("specimen");
  spot.innerHTML = changeRow(pick, ["c4", "radius"]);
  spot.hidden = false;
}

async function loadGames() {
  let res = await fetch("/api/stats");
  let s = await res.json();
  let select = document.getElementById("game");
  for (let g of s.games) {
    let opt = document.createElement("option");
    opt.value = g.game;
    opt.textContent = gameName(g.game);
    select.appendChild(opt);
  }
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  run(box.value);
});

document.getElementById("examples").addEventListener("click", (e) => {
  let a = e.target.closest("a");
  if (!a) return;
  e.preventDefault();
  run(a.textContent);
});

document.getElementById("types").addEventListener("click", (e) => {
  let btn = e.target.closest(".type");
  if (!btn) return;
  for (let b of document.querySelectorAll(".type")) b.classList.remove("on");
  btn.classList.add("on");
  changeType = btn.dataset.type;
  if (lastQuery) run(lastQuery);
});

for (let id of ["game", "from", "to"]) {
  document.getElementById(id).addEventListener("change", () => {
    if (lastQuery) run(lastQuery);
  });
}

// item names in rows and tables open that item's history
out.addEventListener("click", (e) => {
  let btn = e.target.closest(".item[data-item]");
  if (btn) openItem(btn.dataset.item, btn.dataset.game);
});

// restore a search from the url so links and refreshes work
loadGames().then(() => {
  let p = new URLSearchParams(location.search);
  if (p.get("game")) document.getElementById("game").value = p.get("game");
  if (p.get("from")) document.getElementById("from").value = p.get("from");
  if (p.get("to")) document.getElementById("to").value = p.get("to");
  if (p.get("type")) {
    changeType = p.get("type");
    for (let b of document.querySelectorAll(".type")) b.classList.toggle("on", b.dataset.type === changeType);
  }
  if (p.get("q")) run(p.get("q"));
  else loadSpecimen();
});
