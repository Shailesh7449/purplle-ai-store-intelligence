/* Purplle Store Intelligence dashboard — conversion-first. Polls REST. */
async function getJSON(p){ const r = await fetch(p); if(!r.ok) throw new Error(p); return r.json(); }

const KPIS = [
  {key:"conversion_rate_pct", label:"Conversion Rate", cls:"pink big", suffix:"%"},
  {key:"footfall",            label:"Footfall (CCTV)", cls:"accent"},
  {key:"transactions",        label:"Transactions",    cls:""},
  {key:"unique_customers",    label:"Customers",        cls:""},
  {key:"avg_basket_value",    label:"Avg Basket",       cls:"accent", prefix:"₹"},
  {key:"net_revenue",         label:"Net Revenue",      cls:"", prefix:"₹"},
];

async function refreshMetrics(){
  try{
    const m = await getJSON("/metrics");
    document.getElementById("store").textContent =
      `${m.store_name||"Store"} · ${m.date||""} · ${m.units_sold||0} units sold`;
    document.getElementById("kpis").innerHTML = KPIS.map(k=>{
      let v = m[k.key]; if(v===null||v===undefined) v="—";
      else v = (k.prefix||"") + Number(v).toLocaleString() + (k.suffix||"");
      return `<div class="card kpi"><div class="label">${k.label}</div>
              <div class="value ${k.cls}">${v}</div></div>`;
    }).join("");
  }catch(e){}
}

async function refreshFunnel(){
  try{
    const f = await getJSON("/funnel");
    const stages = f.funnel || [];
    const max = Math.max(1, ...stages.map(s=>s.count));
    const names = {entered_store:"Entered store",browsed_zone:"Browsed a zone",
                   reached_counter:"Reached counter",purchased:"Purchased"};
    document.getElementById("funnel").innerHTML = stages.map(s=>`
      <div class="stage">
        <div class="top">
          <span>${names[s.stage]||s.stage}</span>
          <span class="muted">${s.count.toLocaleString()}
            ${s.conversion_from_prev_pct!=null?`· <span class="drop">${s.conversion_from_prev_pct}% of prev</span>`:""}</span>
        </div>
        <div class="bar"><span style="width:${Math.max(8,s.count/max*100).toFixed(0)}%">${s.count}</span></div>
      </div>`).join("") +
      `<p class="muted" style="margin-top:8px">Overall conversion:
        <b style="color:var(--pink)">${f.overall_conversion_pct ?? "—"}%</b></p>`;
  }catch(e){}
}

let hourlyChart, deptChart;
async function refreshHourly(){
  try{
    const d = await getJSON("/api/conversion/hourly");
    const labels=d.map(x=>x.hour+":00"), foot=d.map(x=>x.footfall), txn=d.map(x=>x.transactions);
    if(!window.Chart) return;
    if(!hourlyChart){
      hourlyChart = new Chart(document.getElementById("hourlyChart"),{
        type:"bar",
        data:{labels,datasets:[
          {label:"Footfall",type:"line",data:foot,borderColor:"#22d3ee",backgroundColor:"rgba(34,211,238,.1)",fill:true,tension:.35,yAxisID:"y"},
          {label:"Transactions",data:txn,backgroundColor:"#a855f7",yAxisID:"y1"}]},
        options:{plugins:{legend:{labels:{color:"#8a97b3"}}},
          scales:{x:{ticks:{color:"#8a97b3"},grid:{color:"#1a2236"}},
            y:{position:"left",ticks:{color:"#8a97b3"},grid:{color:"#1a2236"},beginAtZero:true},
            y1:{position:"right",ticks:{color:"#8a97b3"},grid:{display:false},beginAtZero:true}}}
      });
    } else { hourlyChart.data.labels=labels; hourlyChart.data.datasets[0].data=foot;
             hourlyChart.data.datasets[1].data=txn; hourlyChart.update(); }
  }catch(e){}
}

async function refreshDept(){
  try{
    const b = await getJSON("/api/sales/breakdowns");
    const dep=b.by_department||{};
    const labels=Object.keys(dep), data=Object.values(dep);
    if(!window.Chart) return;
    if(!deptChart){
      deptChart = new Chart(document.getElementById("deptChart"),{
        type:"doughnut",
        data:{labels,datasets:[{data,backgroundColor:
          ["#a855f7","#22d3ee","#ec4899","#34d399","#fbbf24","#60a5fa","#f87171"]}]},
        options:{plugins:{legend:{position:"right",labels:{color:"#8a97b3",font:{size:11}}}}}
      });
    } else { deptChart.data.labels=labels; deptChart.data.datasets[0].data=data; deptChart.update(); }
  }catch(e){}
}

async function refreshZones(){
  try{
    const zones = await getJSON("/api/zones");
    if(!zones.length){ return; }
    const max=Math.max(1,...zones.map(z=>z.current_count));
    document.getElementById("zoneBars").innerHTML = zones.map(z=>`
      <div style="margin-bottom:10px">
        <div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:4px">
          <span>${z.zone}</span><span class="muted">${z.current_count} now · avg dwell ${z.avg_dwell_s}s</span>
        </div>
        <div style="height:8px;background:#222b40;border-radius:5px;overflow:hidden">
          <span style="display:block;height:100%;width:${(z.current_count/max*100).toFixed(0)}%;
            background:linear-gradient(90deg,#a855f7,#22d3ee)"></span>
        </div>
      </div>`).join("");
  }catch(e){}
}

function tick(){ refreshMetrics(); refreshFunnel(); refreshHourly(); refreshDept(); refreshZones(); }
tick();
setInterval(tick, 5000);

async function uploadVideo() {

    const file =
        document.getElementById("videoFile").files[0];

    if (!file) {
        alert("Please select a video");
        return;
    }

    const formData = new FormData();
    formData.append("file", file);

    document.getElementById("uploadStatus").innerText =
        "Uploading...";

    try {

        const response = await fetch("/upload-video", {
            method: "POST",
            body: formData
        });

        const result = await response.json();

        document.getElementById("uploadStatus").innerText =
            result.status;

    } catch (err) {

        document.getElementById("uploadStatus").innerText =
            "Upload failed";

    }
}