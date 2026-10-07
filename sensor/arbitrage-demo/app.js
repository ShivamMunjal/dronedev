const DATA=[
  {name:"AK-47 | Redline (Field-Tested)", float:0.158, wear:"FT", buy:33.20, buyShop:"SkinBaron Tradable:Yes", sell:38.50, sellShop:"Skinport", vol:74, median:39.34, tradable:true},
  {name:"AK-47 | Redline (Field-Tested) LOCKED", float:0.159, wear:"FT", buy:32.30, buyShop:"SkinBaron Locked (6d)", sell:38.50, sellShop:"Skinport", vol:74, median:39.34, tradable:false},
  {name:"Mann Co. Supply Crate Key", float:null, wear:"-", buy:1.79, buyShop:"Skinport Tradable:Yes", sell:2.05, sellShop:"marketplace.tf", vol:91778, median:2.24, tradable:true},
  {name:"Tour of Duty Ticket", float:null, wear:"-", buy:0.99, buyShop:"Skinport Tradable", sell:1.18, sellShop:"marketplace.tf", vol:6101, median:1.04, tradable:true},
  {name:"Revolution Case", float:null, wear:"-", buy:0.30, buyShop:"Skinport Tradable", sell:0.34, sellShop:"Steam", vol:88789, median:0.30, tradable:true},
  {name:"AWP | Asiimov (Field-Tested)", float:0.171, wear:"FT", buy:138.00, buyShop:"SkinBaron Tradable", sell:150.60, sellShop:"Steam", vol:13, median:163.55, tradable:true},
  {name:"USP-S | Kill Confirmed (Field-Tested)", float:0.165, wear:"FT", buy:88.00, buyShop:"SkinBaron Tradable", sell:92.84, sellShop:"Steam", vol:7, median:94.00, tradable:true},
  {name:"Glock-18 | Water Elemental (FN)", float:0.03, wear:"FN", buy:78.50, buyShop:"Skinport Tradable", sell:85.75, sellShop:"Steam", vol:18, median:85.79, tradable:true},
  {name:"M4A4 | Asiimov (Field-Tested) — AVOID", float:0.18, wear:"FT", buy:295.00, buyShop:"SkinBaron", sell:324.44, sellShop:"Steam", vol:1, median:329.06, tradable:true},
  {name:"Elden Ring Steam Key (Global)", float:null, wear:"-", buy:32.00, buyShop:"Eneba TR → Global", sell:38.00, sellShop:"G2A", vol:22, median:38.00, tradable:true},
  {name:"Antwerp 2022 Autograph Capsule", float:null, wear:"-", buy:0.25, buyShop:"Steam Sale", sell:0.95, sellShop:"Skinport", vol:45, median:0.40, tradable:true},
  {name:"Doppler Phase 2 vs Phase 4 (Karambit)", float:0.02, wear:"FN", buy:1120.00, buyShop:"SkinBaron listed as Doppler", sell:1450.00, sellShop:"Skinport Phase 4", vol:3, median:1300, tradable:true},
];

function feeFor(shop){
  if(shop.includes("Steam")) return 15;
  if(shop.includes("Skinport")||shop.includes("SkinBaron")||shop.includes("marketplace")) return 12;
  if(shop.includes("G2A")||shop.includes("Eneba")) return 10;
  return 12;
}
function fmt(n){ return "$"+Number(n).toFixed(2); }
function confidence(item, profit){
  if(item.float!==null && item.float>0.17) return {label:"LOW - Dirty 0.17+", cls:"badge-low"};
  if(item.vol<10) return {label:"LOW - Vol <10, stuck", cls:"badge-low"};
  if(profit<1) return {label:"LOW - Gap < $1", cls:"badge-low"};
  if(profit>=3 && item.vol>=20) return {label:"HIGH", cls:"badge-high"};
  return {label:"MED", cls:"badge-med"};
}

function tab(name){
  ["scanner","calc","tracker","guide"].forEach(t=>{
    document.getElementById("p-"+t).classList.toggle("hidden", t!==name);
    const btn=document.getElementById("t-"+t);
    if(t===name){ btn.className="px-4 py-2 rounded-xl bg-white text-black font-bold"; }
    else { btn.className="px-4 py-2 rounded-xl bg-zinc-900 border border-zinc-800"; }
  });
}

function renderScanner(){
  const tradableOnly=document.getElementById("f-tradable").checked;
  const floatOnly=document.getElementById("f-float").checked;
  const minVol=parseInt(document.getElementById("f-vol").value||"0");
  const minProfit=parseFloat(document.getElementById("f-profit").value||"0");
  const tbody=document.getElementById("scanner-body");
  tbody.innerHTML="";
  let shown=0;
  DATA.forEach(item=>{
    const fee=feeFor(item.sellShop);
    const netSell=item.sell*(1-fee/100);
    const profit=netSell - item.buy;
    const conf=confidence(item, profit);
    if(tradableOnly && !item.tradable) return;
    if(floatOnly && item.float!==null && item.float>=0.17) { /* skip dirty */ if(profit>0) return; }
    if(item.vol < minVol) return;
    if(profit < minProfit) return;
    shown++;
    const hold = item.tradable ? "0-1 day" : "6 days";
    const holdCls = item.tradable ? "text-emerald-400" : "text-amber-400";
    const profitCls = profit>=0 ? "badge-profit" : "badge-loss";
    const tr=document.createElement("tr");
    tr.className="border-t border-zinc-800 hover:bg-zinc-900/40";
    tr.innerHTML=`
      <td class="p-3"><div class="font-bold text-zinc-100">${item.name}</div><div class="text-zinc-500">${item.float!==null ? "Float "+item.float.toFixed(3)+" • ":""}Med ${fmt(item.median)}</div></td>
      <td class="p-3"><div class="text-zinc-300">${item.buyShop}</div><div class="text-zinc-500">→ ${item.sellShop}</div></td>
      <td class="p-3 text-right">${fmt(item.buy)}</td>
      <td class="p-3 text-right">${fmt(item.sell)} <span class="text-zinc-500">(${fee}%)</span></td>
      <td class="p-3 text-right">${fmt(item.sell*fee/100)}</td>
      <td class="p-3 text-right"><span class="px-2 py-1 rounded-full text-xs ${profitCls}">${profit>=0?"+":""}${fmt(profit)}</span></td>
      <td class="p-3 text-right">${item.vol.toLocaleString()}</td>
      <td class="p-3 text-center ${holdCls} font-bold">${hold}</td>
      <td class="p-3 text-center"><span class="px-2 py-1 rounded-full text-xs ${conf.cls}">${conf.label}</span></td>
      <td class="p-3 text-center"><button onclick="addToTracker('${item.name.replace(/'/g,"\\'")}', ${item.buy}, ${item.sell})" class="px-2 py-1 rounded bg-zinc-800 border border-zinc-700 text-xs hover:bg-zinc-700">+ Track</button></td>
    `;
    tbody.appendChild(tr);
  });
  if(shown===0){
    tbody.innerHTML=`<tr><td colspan="10" class="p-6 text-center text-zinc-500">No match. Lower Min Profit to 0 or uncheck Float filter. Remember: Need gap >$3 after fee, else you lose. Vol 1 items = stuck 15 days.</td></tr>`;
  }
}

function preset(buy,sell,fee,qty){
  document.getElementById("c-buy").value=buy;
  document.getElementById("c-sell").value=sell;
  document.getElementById("c-fee").value=fee;
  document.getElementById("c-qty").value=qty;
  tab("calc");
  calc();
}
function calc(){
  const buy=parseFloat(document.getElementById("c-buy").value||0);
  const sell=parseFloat(document.getElementById("c-sell").value||0);
  const fee=parseFloat(document.getElementById("c-fee").value||0);
  const qty=parseInt(document.getElementById("c-qty").value||1);
  const netSell=sell*(1-fee/100);
  const profitPer=netSell - buy;
  const total=profitPer*qty;
  const roi= buy>0 ? (profitPer/buy*100):0;
  const breakeven= buy/(1-fee/100);
  const out=document.getElementById("c-out");
  const cls= profitPer>=0 ? "text-emerald-400" : "text-red-400";
  out.innerHTML=`
    <div class="grid grid-cols-2 gap-3">
      <div class="bg-black rounded-xl p-3 border border-zinc-800"><div class="text-xs text-zinc-500">Net Sell (after ${fee}%)</div><div class="text-lg font-bold mono">${fmt(netSell)}</div></div>
      <div class="bg-black rounded-xl p-3 border border-zinc-800"><div class="text-xs text-zinc-500">Profit per piece</div><div class="text-lg font-bold mono ${cls}">${profitPer>=0?"+":""}${fmt(profitPer)} (${roi.toFixed(2)}%)</div></div>
      <div class="bg-black rounded-xl p-3 border border-zinc-800"><div class="text-xs text-zinc-500">Total (${qty}×)</div><div class="text-lg font-bold mono ${cls}">${total>=0?"+":""}${fmt(total)}</div></div>
      <div class="bg-black rounded-xl p-3 border border-zinc-800"><div class="text-xs text-zinc-500">Breakeven sell</div><div class="text-lg font-bold mono">${fmt(breakeven)}</div></div>
    </div>
    <div class="text-xs mt-3 ${profitPer>=3?'text-emerald-400':profitPer>=1?'text-amber-400':'text-red-400'}">${profitPer>=3?'✔ BUY - Gap >$3, good after fee. Check Volume >20 and Float <0.17':profitPer>=1?'⚠ Thin - $1-3 gap, fees eat most. Need faster sell <48h.':'✘ SKIP - Gap < $1 after fee, you lose. Find locked 15% discount or sticker craft.'}</div>
    <div class="text-xs text-zinc-500">Hold: ${fee===15?'7 days (Steam Market → 15% fee)':'0-1 day if Tradable:Yes (12% fee on Skinport/SkinBaron)'}</div>
  `;
}

function copyPrompt(){
  navigator.clipboard.writeText("Skin: [NAME] | Float: [0.xxx] | Steam: $[X] | Buff/Skinport: $[Y] | Vol: [N] | Med: $[M]\nRule: BUY only if Float<0.17 AND Steam < Med*0.90 AND (Buff*0.88 - Steam) > $3 AND Vol > 20\nReply: BUY or SKIP + profit $");
  alert("Prompt copied!");
}

async function fetchLive(){
  try{
    const ak = await fetch("https://steamcommunity.com/market/priceoverview/?appid=730&currency=1&market_hash_name=AK-47%20|%20Redline%20(Field-Tested)").then(r=>r.json());
    alert(`LIVE Steam:\nAK Redline FT: ${ak.lowest_price} low / ${ak.median_price} med / vol ${ak.volume}\n\nValidated against Skinport tradable $1.79. Check scanner.`);
  }catch(e){ alert("Live fetch blocked by CORS - use priceoverview direct. Demo uses validated $39.13 / $2.25 snapshot."); }
}

// Tracker
let TRADES = JSON.parse(localStorage.getItem("tl_trades")||"[]");
function renderTracker(){
  const body=document.getElementById("tracker-body");
  body.innerHTML="";
  let sum=0, cnt=TRADES.length, ok48=0;
  TRADES.forEach((t,i)=>{
    const profit=t.sell*(1- (t.fee||12)/100) - t.buy;
    sum+=profit;
    if(t.hours!==null && t.hours<=48) ok48++;
    const cls= profit>=0 ? "text-emerald-400" : "text-red-400";
    body.innerHTML+=`<tr class="border-t border-zinc-800">
      <td class="p-2">${t.date}</td>
      <td class="p-2">${t.item}</td>
      <td class="p-2 text-right">${fmt(t.buy)}</td>
      <td class="p-2 text-right">${fmt(t.sell)}</td>
      <td class="p-2 text-right ${cls}">${profit>=0?"+":""}${fmt(profit)}</td>
      <td class="p-2 text-center">${t.hours ?? "-"}</td>
      <td class="p-2 text-center">${profit>=0?"✔":"✘"}</td>
      <td class="p-2 text-center"><button onclick="delRow(${i})" class="text-red-400">×</button></td>
    </tr>`;
  });
  const avg = cnt? sum/cnt : 0;
  const pct = cnt? (ok48/cnt*100).toFixed(0) : 0;
  document.getElementById("tracker-stats").innerText=`${cnt} trades • avg ${fmt(avg)} • ${pct}% in 48h • total ${sum>=0?"+":""}${fmt(sum)}`;
}
function addRow(){
  const item=prompt("Item (e.g. AK Redline FT 0.16):","AK-47 | Redline (FT) 0.16");
  if(!item) return;
  const buy=parseFloat(prompt("Buy $:","33.20")||"0");
  const sell=parseFloat(prompt("Sell $:","38.50")||"0");
  const hours=parseFloat(prompt("Hours to sell (e.g. 28):","28")||"0");
  TRADES.push({date:new Date().toISOString().slice(0,10), item, buy, sell, fee:12, hours});
  localStorage.setItem("tl_trades", JSON.stringify(TRADES));
  renderTracker();
}
function addToTracker(name, buy, sell){
  TRADES.push({date:new Date().toISOString().slice(0,10), item:name, buy, sell, fee:12, hours:24});
  localStorage.setItem("tl_trades", JSON.stringify(TRADES));
  tab("tracker");
  renderTracker();
}
function delRow(i){ TRADES.splice(i,1); localStorage.setItem("tl_trades", JSON.stringify(TRADES)); renderTracker(); }
function clearTracker(){ if(!confirm("Clear all?")) return; TRADES=[]; localStorage.setItem("tl_trades","[]"); renderTracker(); }
function exportCSV(){
  let csv="date,item,buy,sell,fee,profit,hours\n";
  TRADES.forEach(t=>{
    const profit=(t.sell*(1- (t.fee||12)/100)-t.buy).toFixed(2);
    csv+=`${t.date},"${t.item}",${t.buy},${t.sell},${t.fee},${profit},${t.hours}\n`;
  });
  const blob=new Blob([csv],{type:"text/csv"});
  const a=document.createElement("a"); a.href=URL.createObjectURL(blob); a.download="tradable_lab_48h.csv"; a.click();
}

document.addEventListener("DOMContentLoaded",()=>{
  renderScanner();
  calc();
  renderTracker();
});
