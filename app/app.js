const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const money = n => "$" + Number(n||0).toLocaleString("en-US");
const j = async (u, opt) => (await fetch(u, opt)).json();

// operator token (write actions only; reads are public)
const optoken = $("#optoken");
optoken.value = localStorage.getItem("odc_token") || "";
optoken.onchange = () => localStorage.setItem("odc_token", optoken.value.trim());
const authH = () => { const t = optoken.value.trim(); return t ? { "Authorization": "Bearer " + t } : {}; };

// tabs
document.querySelectorAll(".tabs button").forEach(b => b.onclick = () => {
  document.querySelectorAll(".tabs button").forEach(x => x.classList.toggle("on", x === b));
  document.querySelectorAll(".tab").forEach(t => t.classList.toggle("hide", t.id !== b.dataset.tab));
  if (b.dataset.tab === "give") loadGiving();
});

async function loadStats() {
  const s = await j("/api/stats");
  $("#stats").innerHTML = [
    ["nodes", s.nodes, "donated nodes"],
    ["done", s.jobs_done, "jobs run"],
    ["donated", money(s.donated_usd), "donated"],
    ["given", money(s.given_usd), "given back"],
    ["jobs", s.jobs_funded, "jobs created"],
    ["chain", s.chain_ok ? "✓" : "✗", "chain " + (s.chain_ok ? "intact" : "BROKEN")],
  ].map(([k,v,l]) => `<div class="s"><b class="${k==='chain'?(s.chain_ok?'green':'red'):(k==='given'?'green':'')}">${v}</b><span>${l}</span></div>`).join("");
  $("#chain").className = "pill " + (s.chain_ok ? "ok" : "bad");
  $("#chain").textContent = s.chain_ok ? `chain intact · ${s.chain_len} receipts` : `chain BROKEN @ ${s.chain_len}`;
}

async function loadTables() {
  const {nodes} = await j("/nodes");
  $("#nodes tbody").innerHTML = nodes.length ? nodes.map(n => `<tr>
    <td>${esc(n.id)}</td><td>${esc(n.owner)}</td><td>${esc(n.kind)}</td><td>${esc(n.gpu||"—")}</td>
    <td>${esc(n.status)}</td><td>${n.jobs_done}</td><td>${n.gpu_seconds}</td></tr>`).join("")
    : `<tr><td colspan="7" class="muted">no nodes yet — host a rig</td></tr>`;

  const {jobs} = await j("/jobs");
  $("#jobs tbody").innerHTML = Object.values(jobs).length ? Object.values(jobs).map(g => `<tr>
    <td>${esc(g.id)}</td><td>${esc(g.kind)}</td><td>${esc(g.model)}</td><td class="mono">${esc(g.data)}</td>
    <td>${esc(g.node||"—")}</td><td>${esc(g.status)}</td></tr>`).join("")
    : `<tr><td colspan="6" class="muted">no jobs yet</td></tr>`;

  const {receipts} = await j("/ledger");
  $("#ledger tbody").innerHTML = receipts.length ? receipts.map(r => {
    const detail = r.kind === "donation"
      ? `${esc(r.donor)} — ${esc(r.item)} ${money(r.value_usd)}`
      : `${esc(r.job_kind||"")} ${esc(r.model||"")} · node ${esc(r.node||"")} · ${r.gpu_seconds||0}s`;
    const phi = r.phi_touched === false ? `<span class="green">false ✓</span>` : (r.kind==="donation"?'<span class="muted">n/a</span>':esc(r.phi_touched));
    return `<tr><td>#${r.seq}</td><td>${esc(r.kind)}</td><td>${detail}</td><td>${phi}</td>
      <td class="hash">${esc((r.hash||"").slice(0,16))}…</td></tr>`;
  }).join("") : `<tr><td colspan="5" class="muted">no receipts yet</td></tr>`;
}

async function refresh(){ await loadStats(); await loadTables(); }

async function loadGiving() {
  const { receipts, totals } = await j("/api/giving");
  $("#gchain").className = "pill " + (totals.chain_ok ? "ok" : "bad");
  $("#gchain").textContent = totals.chain_ok ? `chain intact · ${totals.count} receipts` : `BROKEN @ ${totals.count}`;
  const detail = r => ({
    donation: `<b>${esc(r.donor)}</b> donated ${esc(r.item)}`,
    asset: `<b>${esc(r.asset_id)}</b> (${esc(r.asset_type)}) hosted by ${esc(r.hosted_by)}`,
    income: `<b>${esc(r.asset_id)}</b> earned from ${esc(r.source)}`,
    give: `${esc(r.need)} → <b>${esc(r.recipient)}</b> · by ${esc(r.fulfilled_by)}`,
    job: `<b>${esc(r.worker)}</b> — ${esc(r.task)}`,
  }[r.kind] || esc(r.kind));
  const amt = r => r.kind === "donation" ? money(r.value_usd) : r.kind === "income" ? "+" + money(r.amount_usd)
    : r.kind === "give" ? (r.value_usd ? money(r.value_usd) : "in-kind") : r.kind === "job" ? money(r.pay_usd) : "";
  $("#giving tbody").innerHTML = receipts.length ? receipts.map(r => `<tr class="g-${r.kind}">
    <td>#${r.seq}</td><td>${esc(r.kind)}</td><td>${detail(r)}</td><td class="amt">${amt(r)}</td>
    <td class="hash">${esc((r.hash||"").slice(0,16))}…</td></tr>`).join("")
    : `<tr><td colspan="5" class="muted">no gifts recorded yet</td></tr>`;
}

// donate
$("#donateForm").onsubmit = async e => {
  e.preventDefault();
  const f = e.target, r = $("#donateResult");
  const body = {donor:f.donor.value, form:f.form.value, item:f.item.value, value_usd:f.value_usd.value, note:f.note.value};
  try {
    const out = await j("/api/donate", {method:"POST", headers:{"Content-Type":"application/json", ...authH()}, body:JSON.stringify(body)});
    if (out.ok){ r.className="result ok"; r.textContent=`Thank you 🐝 recorded on the giving chain — receipt #${out.seq} (${out.hash.slice(0,12)}…)`; f.reset(); refresh(); loadGiving(); }
    else { r.className="result bad"; r.textContent = out.error || "error"; }
  } catch { r.className="result bad"; r.textContent="could not reach the hive"; }
};

// post job (firewall)
$("#jobForm").onsubmit = async e => {
  e.preventDefault();
  const f = e.target, r = $("#jobResult");
  const body = {kind:f.kind.value, model:f.model.value, data:f.data.value, desc:f.desc.value};
  try {
    const res = await fetch("/jobs/post", {method:"POST", headers:{"Content-Type":"application/json", ...authH()}, body:JSON.stringify(body)});
    const out = await res.json();
    if (res.status === 200){ r.className="result ok"; r.textContent=`Posted ${out.job.id} (phi:false, firewall passed)`; f.reset(); refresh(); }
    else { r.className="result bad"; r.textContent=`🚩 REFUSED — ${out.detail || out.error}`; }
  } catch { r.className="result bad"; r.textContent="could not reach the hive"; }
};

refresh();
setInterval(loadStats, 8000);
