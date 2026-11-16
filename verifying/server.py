"""검증하기 화면: 분류기, LLM, 프롬프트 안, 돌릴 양을 골라 돌리고 결과 화면을 연다.

이 PC 안에서만 열리는 작은 웹 서버다(파이썬 기본 기능만 쓴다). 결과는 out/verify 에 둔다.
학습·시험·평가와는 따로 돈다: 정답, 분류기, out 폴더의 문서 목록은 읽기만 한다.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlsplit

from marking import core as mcore

from . import core, ollama, prompts, report

TYPES = {".html": "text/html; charset=utf-8", ".json": "application/json; charset=utf-8", ".txt": "text/plain; charset=utf-8"}

PAGE = r"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>LLM으로 한 번 더 검증하기</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--ink:#1c2330;--mute:#5d6878;--line:#d9dee6;--acc:#1f5fbf;--ok:#17803f;--err:#a12626}
@media (prefers-color-scheme:dark){:root{--bg:#14171c;--card:#1d2229;--ink:#e6eaf0;--mute:#9aa5b5;--line:#343c48;--acc:#7fb0ff;--ok:#6fd08f;--err:#ffb3b3}}
*{box-sizing:border-box}
body{margin:0;padding:18px 22px 80px;background:var(--bg);color:var(--ink);font:15px/1.6 -apple-system,"Malgun Gothic","맑은 고딕",sans-serif}
h1{font-size:21px;margin:0 0 4px}
h2{font-size:16px;margin:0 0 8px}
.sub{color:var(--mute);font-size:13px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px 16px;margin:12px 0;max-width:1100px}
button{font:inherit;padding:5px 12px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--ink);cursor:pointer}
button:hover{border-color:var(--acc)}
button.main{background:var(--acc);border-color:var(--acc);color:#fff;font-weight:700}
button.small{padding:1px 8px;font-size:13px}
button:disabled{opacity:.5;cursor:default}
.opt{display:flex;gap:6px 18px;flex-wrap:wrap;margin:2px 0 10px}
.opt.col{flex-direction:column;gap:4px}
.opt label{display:flex;gap:6px;align-items:flex-start;cursor:pointer}
.opt label.off{color:var(--mute);cursor:default}
.opt small{color:var(--mute);display:block;font-size:12px;line-height:1.4}
.opt label.sub2{margin:4px 0 2px 26px}
.grp{margin:0 0 4px;font-weight:700;font-size:14px}
input[type=number],input[type=text]{font:inherit;padding:3px 6px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--ink)}
input[type=number]{width:84px}
#status{min-height:22px;color:var(--mute);font-size:13px;margin-top:8px}
#status.err{color:var(--err);font-weight:700}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.ok{color:var(--ok);font-weight:700}.bad{color:var(--err);font-weight:700}
.bar{height:8px;background:var(--line);border-radius:4px;max-width:520px;margin-top:6px;overflow:hidden}
.bar i{display:block;height:8px;background:var(--acc);width:0}
table{border-collapse:collapse;margin-top:6px}
th,td{text-align:left;padding:4px 14px 4px 0;border-bottom:1px solid var(--line);font-size:14px;vertical-align:top}
th{color:var(--mute);font-weight:400;font-size:13px}
td.n{text-align:right;font-variant-numeric:tabular-nums}
a{color:var(--acc)}
code{font:13px ui-monospace,Consolas,monospace;background:var(--bg);border:1px solid var(--line);border-radius:4px;padding:0 4px}
.done{font-size:16px;font-weight:700;margin-top:10px}
</style></head><body>
<h1>LLM으로 한 번 더 검증하기</h1>
<p class="sub">분류기가 '검토 필요(예)'로 본 글을 이 PC 안의 LLM에 다시 물어, 얼마나 더 걸러지는지와 시간이 얼마나 걸리는지를 모델·프롬프트별로 견줍니다.
자료는 이 PC 밖으로 나가지 않습니다. 정답과 학습 결과는 읽기만 하고 바꾸지 않습니다.</p>

<div class="card"><h2>지금 상태</h2><div id="state" class="sub">확인하는 중…</div></div>

<div class="card"><h2>1. 분류기 <span class="sub" style="font-weight:400">(어느 분류기가 통과시킨 글을 LLM에 넣을지)</span></h2>
<div class="grp">모델</div><div class="opt" id="models"></div>
<div class="grp">넣는 크기</div><div class="opt" id="views"></div>
<div class="grp">문턱 <span class="sub" style="font-weight:400">(분류기 점수가 이 값 이상인 글을 LLM에 넣음)</span></div><div class="opt col" id="thrs"></div></div>

<div class="card"><h2>2. LLM <span class="sub" style="font-weight:400">(이 PC의 Ollama에 받아 둔 모델)</span></h2>
<div class="opt col" id="llms"></div>
<div class="row"><input type="text" id="addname" placeholder="다른 모델 이름" size="30"><button id="add" class="small">목록에 더하기</button></div>
<p class="sub">모델을 받을 때만 Ollama가 인터넷을 씁니다(나가는 것은 모델 이름뿐입니다). 이름에 cloud가 붙은 모델은 밖의 서버에서 도는 것이라 쓰지 않습니다.</p>
<p class="sub"><b>생각 모드에 대해</b>: <code>qwen3:4b-instruct</code>(4B)는 생각 모드가 <b>없는</b> 모델이라 늘 바로 답합니다.
<code>qwen3:8b</code>(8B)는 생각 모드를 켜고 끌 수 있는 모델이고, 기본은 끕니다. 그래서 '켠 것도 함께 돌려 견주기'는 8B에만 나옵니다.
(이름에 instruct가 없는 <code>qwen3:4b</code>는 늘 생각부터 하는 다른 판이라 쓰지 않습니다.)</p>
<p class="sub"><b>속도에 대해</b>: Qwen3 4B와 8B는 바뀌지 않는 지시문을 한 번만 읽고 글마다 달라지는 부분만 새로 읽습니다.
Qwen3.5는 모델 구조상 글마다 프롬프트 전체를 다시 읽어 몇 배 느려서 넣지 않았습니다.</p></div>

<div class="card"><h2>3. 프롬프트 안</h2>
<div class="opt col" id="variants"></div>
<div class="row"><button id="openp" class="small">프롬프트 파일 열기</button><button id="opens" class="small">판단 기준(기준 문장) 파일 열기</button><button id="reload" class="small">고친 내용 다시 읽기</button></div></div>

<div class="card"><h2>4. 얼마나 돌릴지</h2>
<div class="grp">LLM에 넣을 글 수</div><div class="opt" id="samples"></div>
<div class="opt"><label><input type="checkbox" id="rej"><span>분류기가 떨어뜨린 글도 같은 수만큼 넣어 보기<small>분류기가 놓친 '예'를 LLM이 알아보는지 볼 수 있습니다. 시간이 두 배쯤 듭니다.</small></span></label></div></div>

<div class="card"><h2>5. 돌리기</h2>
<div class="row"><button id="plan">몇 번 물어야 하는지 세어 보기</button><button id="run" class="main">돌리기</button><button id="stop" disabled>멈추기</button>
<button id="result">가장 최근 결과 화면 열기</button><button id="folder">결과 폴더 열기</button></div>
<p class="sub">'멈추기'를 누르면 묻고 있던 글도 기다리지 않고 바로 끊고, 그때까지 받은 답으로 결과 화면을 만듭니다. 받은 답은 보관되어 있어서 다시 '돌리기'를 누르면 이어서 받습니다.</p>
<div id="planbox"></div><div class="bar" id="bar" style="display:none"><i></i></div><div id="status"></div><div id="donebox"></div></div>

<script>
const $=id=>document.getElementById(id);
const esc=s=>String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
let S={st:null,busy:false,running:false,extra:[],sel:{classifier:"",view:"line",thr_mode:"test90",threshold:0.5,llms:null,variants:null,sample:200,with_rejected:false}};
const VIEWNOTE={block:"덩어리의 글 전체를 분류기에 넣고, 통과한 덩어리를 LLM에 넣음",agg:"줄마다 분류기에 넣어 가장 높은 줄의 점수로 덩어리를 통과시키고, 통과한 덩어리를 LLM에 넣음",line:"줄마다 분류기에 넣고, 통과한 줄을 LLM에 넣음"};
const SAMPLES=[[50,"50개","빠르게 훑어볼 때"],[100,"100개",""],[200,"200개","기본. 모든 조합을 먼저 견줘 볼 때"],[400,"400개",""],[0,"통과한 글 전부","고른 조합을 제대로 잴 때"]];
async function post(path,body){
  const r=await fetch(path,{method:"POST",headers:{"Content-Type":"application/json","X-Verify":"1"},body:JSON.stringify(body||{})});
  const j=await r.json().catch(()=>({ok:false,error:"응답을 읽지 못했습니다"}));
  if(!r.ok||j.ok===false)throw new Error(j.error||"실패했습니다");
  return j;
}
function say(text,err){const s=$("status");s.textContent=text||"";s.className=err?"err":"";}
function lock(on){S.busy=on;for(const b of document.querySelectorAll("button"))b.disabled=on&&b.id!=="stop";$("stop").disabled=!S.running;}
async function busy(fn){if(S.busy)return;lock(true);try{await fn();}catch(e){say(e.message,true);}finally{if(!S.running)lock(false);}}
function radio(name,value,cur,label,note,off){
  return `<label class="${off?"off":""}"><input type="radio" name="${name}" value="${esc(value)}" ${String(value)===String(cur)?"checked":""} ${off?"disabled":""}><span>${label}${note?`<small>${note}</small>`:""}</span></label>`;
}
function model(){return S.st.choices.models.find(m=>m.key===S.sel.classifier);}
function unit(){return S.sel.view==="block"?"block":"line";}
function saved(){const m=model();const t=m&&m.thresholds&&m.thresholds[S.sel.view];return t&&t.after!=null?t.after:null;}
function llmlist(){
  const st=S.st,out=[],seen={};
  const push=(name,note,think)=>{const k=name.toLowerCase();if(seen[k])return;seen[k]=1;const m=(st.ollama.models||[]).find(x=>x.name.toLowerCase()===k||x.name.toLowerCase()===k+":latest");out.push({name:name,note:note||"",m:m||null,think:m?!!m.thinking:!!think});};
  for(const o of st.offered)push(o[0],o[1],o[2]);
  for(const m of (st.ollama.models||[]))if(!m.cloud)push(m.name,"",false);
  for(const n of S.extra)push(n,"",false);
  return out;
}
async function load(){
  const j=await (await fetch("/state")).json();S.st=j;
  if(!S.sel.classifier){const m=j.choices.models.find(m=>m.key===j.defaults.classifier&&m.ready)||j.choices.models.find(m=>m.ready&&(m.trained.line||m.trained.block))||j.choices.models[0];S.sel.classifier=m?m.key:"";}
  if(S.sel.llms===null)S.sel.llms=j.defaults.llms.slice();
  if(S.sel.variants===null||j.variants.some(v=>S.sel.variants.indexOf(v.key)<0&&!S.known[v.key])){S.sel.variants=j.variants.map(v=>v.key);}
  S.known={};for(const v of j.variants)S.known[v.key]=1;
  S.sel.variants=S.sel.variants.filter(k=>S.known[k]);
  render();
  if(j.run.running&&!S.running){S.running=true;lock(true);watch();}
}
S.known={};
function render(){
  const st=S.st,o=st.ollama;
  let h=o.ok?`<span class="ok">Ollama 연결됨</span> (버전 ${esc(o.version)}, 주소 ${esc(o.url)} — 이 PC 자신)`:`<span class="bad">Ollama에 연결하지 못했습니다.</span> ${esc(o.error||"")}`;
  if(o.ok)h+=`<br>자료를 밖으로 내보내지 않게: 이 프로그램은 이 PC 안의 주소로만 묻고, 클라우드 모델은 거부합니다. Ollama 자체를 로컬 전용으로 두려면 Windows 환경 변수에 <code>OLLAMA_NO_CLOUD=1</code>을 넣고 Ollama를 다시 켜 주세요.`;
  h+=`<br>${esc(st.docs_note)}`;
  if(st.prompt_error)h+=`<br><span class="bad">프롬프트 파일에 문제가 있습니다:</span> ${esc(st.prompt_error)}`;
  $("state").innerHTML=h;
  $("models").innerHTML=st.choices.models.map(m=>{
    const t=["block","line"].map(u=>m.trained[u]?`${u==="block"?"덩어리":"줄"} 분류기: ${esc(m.trained[u].trained)} 학습 (예 ${m.trained[u].yes}, 아니오 ${m.trained[u].no})`:`${u==="block"?"덩어리":"줄"} 분류기: 없음`).join("<br>");
    return radio("classifier",m.key,S.sel.classifier,esc(m.label)+(m.key===st.defaults.classifier?" (기본)":""),m.ready?t:"모델 파일이 없습니다 (download_screen.bat)",!m.ready);}).join("");
  $("views").innerHTML=st.choices.views.map(v=>radio("view",v.key,S.sel.view,esc(v.label),VIEWNOTE[v.key])).join("");
  const sv=saved(),pct=Math.round(st.target*100);
  if(S.sel.thr_mode==="saved"&&sv==null)S.sel.thr_mode="test90";
  $("thrs").innerHTML=radio("thr_mode","test90",S.sel.thr_mode,`시험 문서에서 '예'의 ${pct}%를 찾는 문턱 (기본)`,"걸러내기 비교 화면의 시험 문서 수치와 같은 자리입니다")+
    radio("thr_mode","saved",S.sel.thr_mode,sv!=null?`지난 학습에서 '예'의 ${pct}%를 찾던 문턱 (${sv.toFixed(2)})`:`지난 학습에서 '예'의 ${pct}%를 찾던 문턱`,sv!=null?"학습용 문서의 정답으로 구해 둔 값":"이 조합의 값이 없습니다. '학습하고 결과 보기'를 한 번 하면 생깁니다",sv==null)+
    radio("thr_mode","half",S.sel.thr_mode,"0.5","예와 아니오 가능성이 반반인 자리")+
    `<label><input type="radio" name="thr_mode" value="custom" ${S.sel.thr_mode==="custom"?"checked":""}><span>직접 정하기 <input type="number" id="thrnum" min="0" max="1" step="0.01" value="${S.sel.threshold.toFixed(2)}"></span></label>`;
  let hinted=false;
  $("llms").innerHTML=llmlist().map(x=>{
    const on=S.sel.llms.indexOf(x.name)>=0,m=x.m,tk=x.name+st.think_suffix,ton=S.sel.llms.indexOf(tk)>=0;
    const info=m?`받아 둠 · ${esc(m.params||"")} ${esc(m.quant||"")} · ${(m.size/1e9).toFixed(1)}GB${m.thinking?" · 생각 모드를 켜고 끌 수 있는 모델 (기본은 끔)":" · 생각 모드가 없는 모델 (바로 답함)"}`:`<span class="bad">아직 받지 않았습니다</span> <button class="small" data-pull="${esc(x.name)}">받기</button>`;
    let h=`<div><label><input type="checkbox" data-llm="${esc(x.name)}" ${on?"checked":""}><span><b>${esc(x.name)}</b>${x.note?" — "+esc(x.note):""}<small>${info}</small></span></label>`;
    if(x.think)h+=`<label class="sub2"><input type="checkbox" data-llm="${esc(tk)}" ${ton?"checked":""}><span>${esc(x.name)} — <b>생각 모드를 켠 것</b>도 함께 돌려 견주기<small>${hinted?"위와 같습니다. 매우 느립니다.":"답하기 전에 풀이를 길게 써서 글 하나에 수백 토큰이 더 듭니다. GPU가 없는 PC에서는 글 하나에 몇 분이 걸릴 수 있습니다. 글 수를 50개로, 안을 한두 개로 줄여서 먼저 돌려 보세요. 너무 오래 걸리면 '멈추기'를 누르면 됩니다."}</small></span></label>`;
    if(x.think)hinted=true;
    return h+`</div>`;}).join("");
  $("variants").innerHTML=st.variants.map(v=>`<label><input type="checkbox" data-var="${esc(v.key)}" ${S.sel.variants.indexOf(v.key)>=0?"checked":""}><span><b>${esc(v.key)} ${esc(v.name)}</b> = ${esc(v.parts.join(" + "))}<small>${esc(v.purpose||"")}${v.long?" · 길게 받는 답(느림)":""}</small></span></label>`).join("");
  $("samples").innerHTML=SAMPLES.map(x=>radio("sample",x[0],S.sel.sample,x[1],x[2])).join("");
  $("rej").checked=S.sel.with_rejected;
}
function body(){return Object.assign({},S.sel);}
function planText(j){
  const c=j.counts,word=j.unit==="line"?"줄":"덩어리";
  let h=`<table><tr><th>${j.part==="test"?"시험용 문서":"정답이 붙은 모든 문서"} ${c.docs}개의 정답 붙은 ${word}</th><td class="n">${c.labeled}개 ('예' ${c.yes})</td></tr>`+
    `<tr><th>분류기 문턱 ${j.threshold.toFixed(2)} 이상으로 통과</th><td class="n">${c.passed}개 ('예' ${c.passed_yes})</td></tr>`+
    `<tr><th>LLM에 넣을 글</th><td class="n">${c.chosen}개</td></tr>`+
    `<tr><th>물어야 하는 횟수 (글 × 안 × LLM)</th><td class="n">${j.total}번</td></tr>`+
    `<tr><th>이미 받아 둔 답</th><td class="n">${j.total-j.todo}번</td></tr><tr><th>새로 물을 것</th><td class="n"><b>${j.todo}번</b></td></tr></table>`;
  if(j.part!=="test")h+=`<p class="sub"><span class="bad">주의</span>: 시험용 문서에 '예'와 '아니오' 정답이 모두 있지 않아 정답이 붙은 모든 문서로 잽니다. 분류기가 이미 본 글이 섞여 분류기 쪽 수치가 좋게 나옵니다.</p>`;
  if(j.missing.length)h+=`<p class="sub"><span class="bad">아직 받지 않은 모델</span>: ${esc(j.missing.join(", "))} — 위에서 '받기'를 누르세요.</p>`;
  if(j.est)h+=`<p class="sub">지난번에 잰 시간으로 어림하면 ${esc(j.est)} 걸립니다.</p>`;
  return h;
}
let timer=null;
function watch(){
  if(timer)clearInterval(timer);
  $("bar").style.display="block";
  timer=setInterval(async()=>{
    let j;try{j=await (await fetch("/status")).json();}catch(e){return;}
    if(j.text)say(j.text,false);
    $("bar").firstChild.style.width=(j.total?Math.round(100*j.done/j.total):0)+"%";
    if(!j.running){
      clearInterval(timer);timer=null;S.running=false;lock(false);$("bar").style.display="none";
      if(j.error){say(j.error,true);}
      else if(j.result){say("");$("donebox").innerHTML=`<p class="done">${esc(j.text||"끝났습니다.")} <a href="${esc(j.result)}" target="_blank">결과 화면 열기</a></p>`;window.open(j.result,"_blank");}
      else say(j.text||"");
      load().catch(()=>{});
    }
  },1000);
}
$("plan").onclick=()=>busy(async()=>{say("분류기 점수를 모으고 세는 중입니다…");const j=await post("/plan",body());$("planbox").innerHTML=planText(j);say("");});
$("run").onclick=()=>busy(async()=>{
  if(!S.sel.llms.length)throw new Error("LLM을 하나 이상 골라 주세요.");
  if(!S.sel.variants.length)throw new Error("프롬프트 안을 하나 이상 골라 주세요.");
  $("donebox").innerHTML="";say("시작하는 중입니다…");
  await post("/run",body());S.running=true;lock(true);watch();
});
$("stop").onclick=async()=>{try{$("stop").disabled=true;say("멈추는 중입니다…");await post("/stop",{});}catch(e){say(e.message,true);}};
$("result").onclick=()=>window.open("/out/verify/index.html","_blank");
$("folder").onclick=()=>busy(async()=>{await post("/open",{what:"folder"});});
$("openp").onclick=()=>busy(async()=>{await post("/open",{what:"prompts"});say("메모장에서 고친 뒤 저장하고 '고친 내용 다시 읽기'를 누르세요.");});
$("opens").onclick=()=>busy(async()=>{await post("/open",{what:"sentences"});say("메모장에서 고친 뒤 저장하고 '고친 내용 다시 읽기'를 누르세요. 기준 문장은 걸러내기(학습 전 점수)에도 쓰입니다.");});
$("reload").onclick=()=>busy(async()=>{S.sel.variants=null;await load();say("다시 읽었습니다.");});
$("add").onclick=()=>{const n=$("addname").value.trim();if(!n)return;if(/cloud/i.test(n)){say("클라우드 모델은 쓰지 않습니다. 자료가 이 PC 밖으로 나가기 때문입니다.",true);return;}
  if(S.extra.indexOf(n)<0)S.extra.push(n);if(S.sel.llms.indexOf(n)<0)S.sel.llms.push(n);$("addname").value="";render();};
document.addEventListener("click",e=>{const t=e.target;
  if(t.dataset&&t.dataset.pull){e.preventDefault();const name=t.dataset.pull;busy(async()=>{say(name+" 을(를) 받기 시작합니다…");await post("/pull",{name:name});S.running=true;lock(true);watch();});}
});
document.addEventListener("change",e=>{const t=e.target;
  if(t.name==="classifier"||t.name==="view"||t.name==="thr_mode"){S.sel[t.name]=t.value;render();}
  if(t.name==="sample"){S.sel.sample=parseInt(t.value,10);}
  if(t.id==="thrnum"){const v=parseFloat(t.value);if(!isNaN(v)){S.sel.thr_mode="custom";S.sel.threshold=Math.min(1,Math.max(0,v));render();}}
  if(t.id==="rej")S.sel.with_rejected=t.checked;
  if(t.dataset&&t.dataset.llm){const n=t.dataset.llm,i=S.sel.llms.indexOf(n);if(t.checked&&i<0)S.sel.llms.push(n);if(!t.checked&&i>=0)S.sel.llms.splice(i,1);}
  if(t.dataset&&t.dataset.var){const n=t.dataset.var,i=S.sel.variants.indexOf(n);if(t.checked&&i<0)S.sel.variants.push(n);if(!t.checked&&i>=0)S.sel.variants.splice(i,1);}
});
load().catch(e=>say(e.message,true));
</script></body></html>
"""


class App:
    def __init__(self, env: core.Env):
        self.env = env
        self.scorer = mcore.Scorer(env.cfg, "verify")
        self.lock = threading.RLock()               # 무거운 일(점수 모으기)은 한 번에 하나만
        self.status = ""
        self.running = False
        self.error = ""
        self.result = ""
        self.done = 0
        self.total = 0
        self.stop = core.Stop()                     # 멈추기: 묻고 있던 요청도 바로 끊는다
        self._data: dict = {}                       # (분류기, 크기, 파일들의 지문) → 모아 둔 글과 점수
        self._seen = 0
        self.first = ollama.ensure_running(self.log)

    def log(self, msg: str) -> None:
        self.status = msg.strip()
        if "번째 글" in msg:                        # 글마다의 진행 줄은 창에 스무 번에 한 번만 찍는다
            self._seen += 1
            if self._seen % 20 != 1:
                return
        print(msg, flush=True)

    # ------------------------------------------------------------ 상태
    def _ollama(self) -> dict:
        out = {"ok": False, "version": "", "url": ollama.base_url(), "error": "", "models": []}
        try:
            out["version"] = ollama.version()
            out["models"] = ollama.models()
            out["ok"] = True
        except ollama.OllamaError as exc:
            out["error"] = str(exc)
        return out

    def state(self) -> dict:
        cfg = self.env.cfg
        variants, prompt_error = [], ""
        try:
            _, vs = prompts.load(self.env.prompts_file)
            variants = [{"key": v.key, "name": v.name, "parts": v.parts, "long": v.long, "purpose": prompts.PURPOSE.get(v.key, "")} for v in vs]
        except ValueError as exc:
            prompt_error = str(exc)
        from screening import learn, testdocs
        from screening.items import load_docs
        docs = load_docs(cfg.out_dir)
        labels = learn.load_labels(cfg.labels)
        wanted = set(testdocs.read_test_docs(cfg.test_docs))
        test = [d for d in docs if d.name in wanted]
        lines = [l for d in test for b in d.blocks for l in b.lines]
        yes = sum(1 for l in lines if labels.get(l.key) == 1)
        no = sum(1 for l in lines if labels.get(l.key) == 0)
        if not docs:
            note = "아직 추출한 문서가 없습니다. run.bat 으로 문서를 먼저 추출해 주세요."
        elif not test:
            note = "시험용 문서가 정해져 있지 않습니다. label.bat 화면에서 '시험용'에 체크해 두면 그 문서로 공정하게 잽니다(지금은 정답이 붙은 모든 문서로 잽니다)."
        else:
            note = "시험용 문서 %d개 · 정답이 붙은 줄 %d개 ('예' %d, '아니오' %d)" % (len(test), yes + no, yes, no)
        return {"ok": True, "ollama": self._ollama(), "choices": mcore.choices(cfg), "variants": variants, "prompt_error": prompt_error,
                "offered": [list(x) for x in core.OFFERED_LLMS], "think_suffix": core.THINK_SUFFIX, "docs_note": note, "target": float(cfg.target),
                "defaults": {"classifier": core.DEFAULT_CLASSIFIER, "llms": list(core.DEFAULT_LLMS), "sample": core.DEFAULT_SAMPLE},
                "run": {"running": self.running}}

    def progress(self) -> dict:
        return {"ok": True, "running": self.running, "text": self.status, "done": self.done, "total": self.total,
                "error": self.error, "result": self.result}

    # ------------------------------------------------------------ 고른 것 읽기
    def _setup(self, body: dict) -> core.Setup:
        view = str(body.get("view") or core.DEFAULT_VIEW)
        if view not in mcore.VIEW_NAME:
            raise ValueError("넣는 크기를 알 수 없습니다")
        mode = str(body.get("thr_mode") or "test90")
        if mode not in ("test90", "saved", "half", "custom"):
            raise ValueError("문턱을 정하는 방법을 알 수 없습니다")
        llms = [str(n).strip() for n in (body.get("llms") or []) if str(n).strip()][:12]
        for n in llms:
            if ollama.is_cloud_name(core.split_entry(n)[0]):
                raise ValueError("'%s' 은(는) 클라우드 모델이라 쓰지 않습니다. 자료가 이 PC 밖으로 나가기 때문입니다." % n)
        try:
            sample = max(0, int(body.get("sample") or 0))
        except (TypeError, ValueError):
            raise ValueError("글 수는 숫자여야 합니다")
        return core.Setup(classifier=str(body.get("classifier") or core.DEFAULT_CLASSIFIER), view=view, thr_mode=mode,
                          threshold=mcore.safe_threshold(body.get("threshold")) if mode == "custom" else None, llms=llms,
                          variants=[str(k) for k in (body.get("variants") or [])][:40], sample=sample,
                          with_rejected=bool(body.get("with_rejected")))

    def _signature(self, setup: core.Setup) -> tuple:
        cfg = self.env.cfg
        unit = "block" if setup.view == "block" else "line"
        files = [Path(cfg.labels), Path(cfg.test_docs), mcore.classifier_file(cfg.labels, setup.classifier, unit)]
        units = sorted(Path(cfg.out_dir).glob("*.units.json"))
        stamp = lambda p: p.stat().st_mtime_ns if p.exists() else 0
        return (setup.classifier, setup.view, float(cfg.title_weight or 0.0), tuple(stamp(p) for p in files),
                len(units), max([stamp(p) for p in units] or [0]))

    def _load(self, setup: core.Setup) -> dict:
        """글과 분류기 점수. 정답·분류기·문서가 바뀌지 않았으면 모아 둔 것을 다시 쓴다(다시 학습했으면 새로 모은다)."""
        sig = self._signature(setup)
        if sig not in self._data:
            self._data = {sig: core.load_data(self.env, self.scorer, setup.classifier, setup.view, self.log)}
        return self._data[sig]

    # ------------------------------------------------------------ 세어 보기, 돌리기
    def plan(self, body: dict) -> dict:
        setup = self._setup(body)
        if self.running:
            raise ValueError("지금 돌리는 중입니다. 끝난 뒤에 해 주세요.")
        with self.lock:
            prep = core.prepare(self.env, setup, self.scorer, self.log, self._load(setup))
            answers = core.Answers(self.env.out / "cache" / "answers.jsonl")
            listed = []
            try:
                listed = ollama.models()
            except ollama.OllamaError:
                pass
            llms = core.llm_entries(setup.llms, listed, strict=False)
            missing = sorted({m["name"] for m in llms if not m["digest"]})
            todo = core.todo_counts(prep, llms, answers)
            total = len(prep["chosen"]) * len(prep["plans"]) * len(llms)
            est = self._estimate(prep, llms, answers, todo)
            self.status = ""
        return {"ok": True, "counts": prep["counts"], "threshold": prep["threshold"], "thr_note": prep["thr_note"],
                "unit": prep["data"]["unit"], "part": prep["data"]["part"], "total": total, "todo": sum(todo.values()),
                "missing": missing, "est": est}

    def _estimate(self, prep: dict, llms: list, answers: core.Answers, todo: dict) -> str:
        """받아 둔 답의 시간으로 남은 시간을 어림한다(같은 모델·같은 안의 답이 있을 때만)."""
        seconds, known = 0.0, True
        for m in llms:
            for plan in prep["plans"]:
                v = plan["variant"]
                n = todo.get("%s|%s" % (m["id"], v.key), 0)
                if not n:
                    continue
                secs = [r["sec"] for u in plan["users"] for r in [answers.get(core._key(m, plan, u))] if r]
                if len(secs) < 3:
                    known = False
                    continue
                seconds += n * sum(secs) / len(secs)
        return core._left(seconds) + ("" if known else " + 아직 재 보지 않은 조합의 시간") if seconds else ""

    def start(self, body: dict) -> dict:
        setup = self._setup(body)
        if not setup.llms:
            raise ValueError("LLM을 하나 이상 골라 주세요.")
        with self.lock:
            if self.running:
                raise ValueError("이미 돌리는 중입니다.")
            self.running, self.error, self.result, self.done, self.total = True, "", "", 0, 0
            self.stop.clear()
        threading.Thread(target=self._run, args=(setup,), daemon=True).start()
        return {"ok": True}

    def _run(self, setup: core.Setup) -> None:
        try:
            def progress(done: int, total: int) -> None:
                self.done, self.total = done, total
            with self.lock:
                data = self._load(setup)
            res = core.run(self.env, setup, self.scorer, self.log, self.stop, data, progress)
            self.log("결과 화면을 만드는 중…")
            report.write(self.env, res)
            self.result = "/out/verify/index.html"
            self.status = "멈췄습니다. 받은 답까지로 결과 화면을 만들었습니다." if res["stopped"] else "끝났습니다."
            print(self.status, flush=True)
        except (ValueError, ollama.OllamaError) as exc:
            self.error = str(exc)
        except Exception as exc:
            traceback.print_exc()
            self.error = "%s: %s" % (type(exc).__name__, exc)
        finally:
            self.running = False

    def halt(self) -> dict:
        """멈추기. 지금 묻고 있는 글도 기다리지 않고 끊는다. 그때까지 받은 답은 보관되어 있고, 그것으로 결과 화면을 만든다."""
        if self.running:
            self.status = "멈추는 중입니다…"
        self.stop.set()
        return {"ok": True}

    def pull(self, body: dict) -> dict:
        name = str(body.get("name") or "").strip()
        if not name or len(name) > 120 or any(c in name for c in " \t\r\n\"'\\"):
            raise ValueError("모델 이름이 올바르지 않습니다")
        if ollama.is_cloud_name(name):
            raise ValueError("클라우드 모델은 받지 않습니다")
        with self.lock:
            if self.running:
                raise ValueError("지금 다른 일을 하는 중입니다. 끝난 뒤에 해 주세요.")
            self.running, self.error, self.result, self.done, self.total = True, "", "", 0, 0
            self.stop.clear()

        def work() -> None:
            try:
                state = ollama.ensure_running(self.log)
                if not state["ok"]:
                    raise ollama.OllamaError(state["error"])
                last = {"text": ""}

                def show(text: str) -> None:
                    self.status = text
                    if text.split(":")[0] != last["text"]:
                        last["text"] = text.split(":")[0]
                        print(text, flush=True)
                ollama.pull(name, show, self.stop)
                self.status = "%s 을(를) 받았습니다." % name
                print(self.status, flush=True)
            except ollama.Cancelled:
                self.status = "받기를 멈췄습니다. 받던 부분은 남아 있어서, 다시 '받기'를 누르면 이어서 받습니다."
                print(self.status, flush=True)
            except ollama.OllamaError as exc:
                self.error = str(exc)
            except Exception as exc:
                traceback.print_exc()
                self.error = "%s: %s" % (type(exc).__name__, exc)
            finally:
                self.running = False
        threading.Thread(target=work, daemon=True).start()
        return {"ok": True}

    def open(self, body: dict) -> dict:
        """결과 폴더, 프롬프트 파일, 기준 문장 파일을 이 PC의 기본 프로그램으로 연다."""
        what = str(body.get("what") or "folder")
        if what == "prompts":
            prompts.read_text(self.env.prompts_file)            # 없으면 기본 내용으로 만든다
            target = Path(self.env.prompts_file).resolve()
        elif what == "sentences":
            from screening.sentences import read_text
            read_text(self.env.cfg.sentences)
            target = Path(self.env.cfg.sentences).resolve()
        else:
            target = self.env.out.resolve()
            target.mkdir(parents=True, exist_ok=True)
        if sys.platform.startswith("win"):
            os.startfile(str(target))               # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-t", str(target)] if target.is_file() else ["open", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target)])
        return {"ok": True}


def make_handler(app: App):
    out_root = Path(app.env.cfg.out_dir).resolve()

    class Handler(BaseHTTPRequestHandler):
        server_version = "docparse-verify"

        def log_message(self, *args) -> None:       # 요청마다 창에 찍지 않는다
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj: dict) -> None:
            self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), TYPES[".json"])

        def _local(self) -> bool:
            """이 PC의 브라우저가 이 주소로 직접 연 요청만 받는다."""
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
            return host in ("127.0.0.1", "localhost")

        def do_GET(self) -> None:
            if not self._local():
                return self._send(403, b"forbidden", TYPES[".txt"])
            path = unquote(urlsplit(self.path).path)
            try:
                if path in ("/", "/index.html"):
                    return self._send(200, PAGE.encode("utf-8"), TYPES[".html"])
                if path == "/state":
                    return self._json(200, app.state())
                if path == "/status":
                    return self._json(200, app.progress())
                if path.startswith("/out/"):
                    target = (out_root / path[len("/out/"):]).resolve()
                    if out_root in target.parents and target.is_file() and target.suffix.lower() in TYPES:
                        return self._send(200, target.read_bytes(), TYPES[target.suffix.lower()])
                self._send(404, "없는 주소입니다. 아직 결과가 없으면 먼저 돌려 주세요.".encode("utf-8"), TYPES[".txt"])
            except Exception as exc:
                traceback.print_exc()
                self._json(500, {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)})

        def do_POST(self) -> None:
            # 다른 웹 페이지가 몰래 보낸 요청은 받지 않는다(이 화면만 붙일 수 있는 표시를 확인)
            ctype = self.headers.get("Content-Type") or ""
            if not self._local() or self.headers.get("X-Verify") != "1" or "application/json" not in ctype:
                return self._send(403, b"forbidden", TYPES[".txt"])
            path = urlsplit(self.path).path
            try:
                size = int(self.headers.get("Content-Length") or 0)
                if size > 1024 * 1024:
                    return self._json(413, {"ok": False, "error": "너무 큰 요청"})
                body = json.loads(self.rfile.read(size).decode("utf-8") or "{}")
                if not isinstance(body, dict):
                    raise ValueError("요청을 읽을 수 없습니다")
                if path == "/plan":
                    return self._json(200, app.plan(body))
                if path == "/run":
                    return self._json(200, app.start(body))
                if path == "/stop":
                    return self._json(200, app.halt())
                if path == "/pull":
                    return self._json(200, app.pull(body))
                if path == "/open":
                    return self._json(200, app.open(body))
                self._json(404, {"ok": False, "error": "없는 주소입니다"})
            except (ValueError, ollama.OllamaError) as exc:
                self._json(400, {"ok": False, "error": str(exc)})
            except SystemExit as exc:
                self._json(400, {"ok": False, "error": str(exc)})
            except Exception as exc:
                if type(exc).__name__ == "ModelMissing":
                    return self._json(400, {"ok": False, "error": str(exc)})
                traceback.print_exc()
                self._json(500, {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)})

    return Handler


def serve(env: core.Env, port: int = 8785, open_browser: bool = True) -> None:
    app = App(env)
    server: Optional[ThreadingHTTPServer] = None
    for p in range(port, port + 20):               # 쓰고 있는 번호면 다음 번호로
        try:
            server = ThreadingHTTPServer(("127.0.0.1", p), make_handler(app))
            break
        except OSError:
            continue
    if server is None:
        raise SystemExit("[오류] 화면을 열 포트를 찾지 못했습니다 (%d~%d)" % (port, port + 19))
    url = "http://127.0.0.1:%d/" % server.server_address[1]
    print("검증하기 화면: %s" % url)
    print("이 PC 안에서만 열립니다. 이 창을 닫으면(또는 Ctrl+C) 끝납니다.")
    if not app.first["ok"]:
        print("[알림] %s" % app.first["error"])
    print("결과 폴더: %s" % env.out.resolve(), flush=True)
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
