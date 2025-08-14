cat > app.js <<'EOF'
const API = "https://apuestas-backend.onrender.com";

const rows = document.getElementById("rows");
const lastUpdate = document.getElementById("lastUpdate");
const refreshBtn = document.getElementById("refreshBtn");

const kelly = document.getElementById("kelly");
const stakeMin = document.getElementById("stakeMin");
const stakeMax = document.getElementById("stakeMax");
const pageLimit = document.getElementById("pageLimit");
const autoRefresh = document.getElementById("autoRefresh");
const autoSecs = document.getElementById("autoSecs");
const saveSettings = document.getElementById("saveSettings");

let autoTimer = null;

async function getJSON(url, opts){
  const res = await fetch(url, opts);
  if(!res.ok) throw new Error(await res.text());
  return res.json();
}

function kellyStake(kellyFrac, odds, edge, minS, maxS){
  const bankroll = 100; // base de referencia para sugerencia
  if(odds<=1 || edge<=0) return 0;
  const base = kellyFrac * (edge / (odds - 1)) * bankroll;
  return Math.max(minS, Math.min(maxS, Math.round(base*100)/100));
}

async function loadSettings(){
  const s = await getJSON(`${API}/settings`);
  kelly.value = Math.round(s.kelly_fraction*100);
  stakeMin.value = s.stake_min;
  stakeMax.value = s.stake_max;
  pageLimit.value = s.page_limit;

  // Auto-refresh: lo guardamos solo en localStorage (no en backend)
  const ar = localStorage.getItem("autoRefresh") === "1";
  const secs = Number(localStorage.getItem("autoSecs") || "10");
  autoRefresh.checked = ar;
  autoSecs.value = secs;
  setAutoTimer();
}

function setAutoTimer(){
  if(autoTimer) clearInterval(autoTimer);
  if(autoRefresh.checked){
    const ms = Math.max(5, Number(autoSecs.value)||10) * 1000;
    autoTimer = setInterval(loadAndRender, ms);
  }
}

async function saveSettingsFn(){
  const payload = {
    kelly_fraction: Number(kelly.value)/100,
    stake_min: Number(stakeMin.value),
    stake_max: Number(stakeMax.value),
    page_limit: Number(pageLimit.value),
  };
  await getJSON(`${API}/settings`, {
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify(payload)
  });
  localStorage.setItem("autoRefresh", autoRefresh.checked ? "1" : "0");
  localStorage.setItem("autoSecs", String(Number(autoSecs.value)||10));
  setAutoTimer();
  await loadAndRender();
}

async function loadAndRender(){
  const s = await getJSON(`${API}/settings`);
  const data = await getJSON(`${API}/bets`);
  rows.innerHTML = "";
  data.forEach(b=>{
    const tr = document.createElement("tr");
    const suggested = kellyStake(s.kelly_fraction, b.odds, b.edge, s.stake_min, s.stake_max);
    tr.innerHTML = `
      <td>${b.event}</td>
      <td>${b.bookmaker}</td>
      <td>${b.market}</td>
      <td>${b.selection}</td>
      <td>${Number(b.odds).toFixed(2)}</td>
      <td>${(Number(b.edge)*100).toFixed(1)}%</td>
      <td><input type="number" min="0" step="0.1" value="${suggested}" style="width:90px"></td>
      <td><button class="reg">Registrar</button></td>
    `;
    const btn = tr.querySelector(".reg");
    const stakeInput = tr.querySelector("input");
    btn.addEventListener("click", async ()=>{
      btn.disabled = true;
      try{
        await getJSON(`${API}/register`, {
          method:"POST",
          headers:{"Content-Type":"application/json"},
          body: JSON.stringify({bet_id: b.id, stake: Number(stakeInput.value) || 0})
        });
        await loadAndRender(); // repone automáticamente
      }catch(e){
        alert("Error: "+e.message);
        btn.disabled=false;
      }
    });
    rows.appendChild(tr);
  });
  lastUpdate.textContent = "Actualizado: " + new Date().toLocaleTimeString();
}

refreshBtn.addEventListener("click", loadAndRender);
saveSettings.addEventListener("click", saveSettingsFn);
autoRefresh.addEventListener("change", ()=>{ localStorage.setItem("autoRefresh", autoRefresh.checked ? "1":"0"); setAutoTimer(); });
autoSecs.addEventListener("change", ()=>{ localStorage.setItem("autoSecs", String(Number(autoSecs.value)||10)); setAutoTimer(); });

(async function init(){
  try{
    await loadSettings();
    await loadAndRender();
  }catch(e){
    alert("No puedo conectar con el backend.\nRevisa que la URL API sea correcta y que Render esté activo.");
  }
})();
EOF
