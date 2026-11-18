"""표시하기 화면: 파일을 올리고, 모델·넣는 크기·판단 방법·문턱을 골라 미리 본 뒤, 표시한 파일을 만든다.

이 PC 안에서만 열리는 작은 웹 서버다(파이썬 기본 기능만 쓴다). 올린 파일은 out/mark/in 에, 결과는 out/mark 에 둔다.
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
from typing import Dict, List
from urllib.parse import parse_qs, unquote, urlsplit

from . import core, make, times

TYPES = {".html": "text/html; charset=utf-8", ".json": "application/json; charset=utf-8", ".txt": "text/plain; charset=utf-8",
         ".csv": "text/csv; charset=utf-8", ".png": "image/png", ".jpg": "image/jpeg", ".pdf": "application/pdf",
         ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation"}
MAX_UPLOAD = 600 * 1024 * 1024

PAGE = r"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>검토 필요 표시하기</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--ink:#1c2330;--mute:#5d6878;--line:#d9dee6;--acc:#1f5fbf;--hl:#fff3a0;--hl-ink:#5a4a00;--hl-edge:#d9a400;--err:#a12626}
@media (prefers-color-scheme:dark){:root{--bg:#14171c;--card:#1d2229;--ink:#e6eaf0;--mute:#9aa5b5;--line:#343c48;--acc:#7fb0ff;--hl:#5a4d10;--hl-ink:#ffe98a;--err:#ffb3b3}}
*{box-sizing:border-box}
body{margin:0;padding:18px 22px 80px;background:var(--bg);color:var(--ink);font:15px/1.6 -apple-system,"Malgun Gothic","맑은 고딕",sans-serif}
h1{font-size:21px;margin:0 0 4px}
h2{font-size:16px;margin:0 0 8px}
.sub{color:var(--mute);font-size:13px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px 16px;margin:12px 0;max-width:1100px}
.drop{border:2px dashed var(--line);border-radius:8px;padding:16px;text-align:center;color:var(--mute)}
.drop.over{border-color:var(--acc);color:var(--acc)}
table{border-collapse:collapse;width:100%;margin-top:8px}
th,td{text-align:left;padding:5px 10px 5px 0;border-bottom:1px solid var(--line);font-size:14px;vertical-align:top}
th{color:var(--mute);font-weight:400;font-size:13px}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
button{font:inherit;padding:5px 12px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--ink);cursor:pointer}
button:hover{border-color:var(--acc)}
button.main{background:var(--acc);border-color:var(--acc);color:#fff;font-weight:700}
button:disabled{opacity:.5;cursor:default}
.opt{display:flex;gap:6px 18px;flex-wrap:wrap;margin:2px 0 10px}
.opt label{display:flex;gap:6px;align-items:flex-start;cursor:pointer}
.opt label.off{color:var(--mute);cursor:default}
.opt small{color:var(--mute);display:block;font-size:12px;line-height:1.4}
.grp{margin:0 0 4px;font-weight:700;font-size:14px}
input[type=number]{font:inherit;width:84px;padding:3px 6px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--ink)}
input[type=range]{width:240px;vertical-align:middle}
select{font:inherit;padding:3px 6px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--ink)}
#status{min-height:22px;color:var(--mute);font-size:13px;margin-top:6px}
#status.err{color:var(--err);font-weight:700}
.yes{background:var(--hl);color:var(--hl-ink);border-radius:3px;padding:0 4px}
details{margin:4px 0}
details summary{cursor:pointer}
ol.items{list-style:none;margin:6px 0 0;padding:0;max-height:420px;overflow:auto;border:1px solid var(--line);border-radius:6px}
ol.items li{display:flex;gap:10px;padding:4px 8px;border-bottom:1px solid var(--line);font-size:14px}
ol.items li:last-child{border-bottom:0}
ol.items .pg{flex:0 0 46px;color:var(--mute);font-size:12px;padding-top:2px}
ol.items .sc{flex:0 0 40px;font-weight:700;font-variant-numeric:tabular-nums}
ol.items .tx{white-space:pre-wrap;word-break:break-word;min-width:0}
.res a{font-weight:700}
.note{color:var(--mute);font-size:13px}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
a{color:var(--acc)}
.tres{border:1px solid var(--line);border-radius:8px;padding:8px 12px;margin:8px 0}
/*TIMECSS*/
</style></head><body class="tm">
<h1>'검토 필요' 표시하기</h1>
<p class="sub">학습해 둔 모델로 PDF·PPTX에 점수를 매겨, '예'로 본 글을 표시한 사본을 만듭니다. 정답과 학습 결과는 읽기만 하고 바꾸지 않습니다. 이 PC 안에서만 열리는 화면입니다.</p>

<div class="card"><h2>1. 표시할 파일</h2>
<div class="drop" id="drop">PDF·PPTX 파일을 여기에 끌어다 놓거나 <button id="pick">파일 고르기</button>
<input type="file" id="file" multiple accept=".pdf,.pptx" style="display:none"></div>
<div id="files"></div></div>

<div class="card"><h2>2. 무엇으로 표시할지</h2>
<div class="grp">모델</div><div class="opt" id="models"></div>
<div class="grp">넣는 크기</div><div class="opt" id="views"></div>
<div class="grp">판단 방법</div><div class="opt" id="stages"></div>
<div class="grp">문턱 <span class="sub" style="font-weight:400">(점수가 이 값 이상이면 '예'로 표시)</span></div>
<div class="opt" id="thrs"></div>
<div class="row" style="margin:-4px 0 10px"><input type="range" id="thrbar" min="0" max="1" step="0.01" value="0.5"><span class="sub">지금 문턱 <b id="thrnow">0.50</b></span></div>
<div class="grp">PDF에 표시하는 방식</div><div class="opt" id="methods"></div>
<p class="sub" id="titlew"></p></div>

<div class="card"><h2>3. 미리 보기와 만들기</h2>
<div class="opt"><label><input type="checkbox" id="fresh"><span>보관해 둔 계산을 쓰지 않고 처음부터 다시 계산하기 <b>(걸린 시간을 재려면 체크)</b><small>한 번 계산한 글의 점수는 보관해 두고 다시 씁니다. 그래서 학습에 쓴 문서나 두 번째로 돌리는 문서는 분류기 시간이 거의 0으로 나옵니다. 체크하면 모두 새로 계산해서, 처음 보는 문서에 걸리는 시간이 나옵니다.</small></span></label></div>
<div class="row"><button id="score">점수 매기고 미리 보기</button><button id="make" class="main">표시한 파일 만들기</button><button id="folder">결과 폴더 열기</button><button id="timelog">걸린 시간 기록 열기</button></div>
<div id="status"></div><div id="preview"></div><div id="results"></div></div>

<script>
const $=id=>document.getElementById(id);
const esc=s=>String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
let S={files:[],ch:null,preview:null,pkey:"",busy:false,sel:{model:"",view:"line",stage:"after",thrmode:"half",thr:0.5,method:"annot"}};
const METHODS=[["annot","형광펜 주석","PDF 프로그램에서 하나씩 지울 수 있고, 메모에 점수가 들어갑니다"],["paint","쪽에 직접 칠하기","주석을 보여 주지 않는 프로그램이나 인쇄에서도 보입니다. 지울 수 없습니다"]];
const VIEWNOTE={block:"덩어리의 글 전체를 한 번에 넣어 덩어리에 표시",agg:"줄마다 넣고, 가장 높은 줄의 점수로 덩어리에 표시",line:"줄마다 넣어 줄에 표시"};

const TSTAGES=[["extract","글 뽑기",0],["classify","분류기",1],["write","파일 만들기",3]];
function fmt(s){
  if(s==null)return "-";s=Math.max(0,s);
  if(s>0&&s<0.005)return "0.01초 미만";
  if(s<0.995)return s.toFixed(2)+"초";
  if(s<10)return s.toFixed(1)+"초";
  if(s<60)return Math.round(s)+"초";
  if(s<3600){const w=Math.round(s);return Math.floor(w/60)+"분 "+String(w%60).padStart(2,"0")+"초";}
  const w=Math.round(s/60);return Math.floor(w/60)+"시간 "+String(w%60).padStart(2,"0")+"분";
}
function share(part,total){if(total<=0)return "-";const p=100*part/total;return p>0&&p<1?"1% 미만":Math.round(p)+"%";}
function timeBar(t){
  const total=TSTAGES.reduce((a,x)=>a+t[x[0]].sec,0);if(total<=0)return "";
  const cells=TSTAGES.map(x=>t[x[0]].sec>0?`<i class="t${x[2]}" style="flex:${(t[x[0]].sec/total).toFixed(4)} 1 0" title="${x[1]} ${fmt(t[x[0]].sec)} (${share(t[x[0]].sec,total)})"></i>`:"").join("");
  const key=TSTAGES.map(x=>`<span><i class="t${x[2]}"></i>${x[1]} <b>${fmt(t[x[0]].sec)}</b> (${share(t[x[0]].sec,total)})</span>`).join("")+`<span>합계 <b>${fmt(total)}</b></span>`;
  return `<div class="tbar2" role="img" aria-label="단계별 걸린 시간">${cells}</div><div class="tkey">${key}</div>`;
}
async function post(path,body){
  const r=await fetch(path,{method:"POST",headers:{"Content-Type":"application/json","X-Mark":"1"},body:JSON.stringify(body||{})});
  const j=await r.json().catch(()=>({ok:false,error:"응답을 읽지 못했습니다"}));
  if(!r.ok||j.ok===false)throw new Error(j.error||"실패했습니다");
  return j;
}
function say(text,err){const s=$("status");s.textContent=text||"";s.className=err?"err":"";}
let timer=null;
function watch(on){
  if(timer){clearInterval(timer);timer=null;}
  if(on)timer=setInterval(async()=>{try{const j=await (await fetch("/status")).json();if(S.busy&&j.text)say(j.text);}catch(e){}},1000);
}
async function busy(fn){
  if(S.busy)return;S.busy=true;watch(true);
  for(const b of document.querySelectorAll("button"))b.disabled=true;
  try{await fn();}catch(e){say(e.message,true);}
  finally{S.busy=false;watch(false);for(const b of document.querySelectorAll("button"))b.disabled=false;}
}
async function load(){const j=await (await fetch("/state")).json();S.files=j.files;S.ch=j.choices;if(!S.sel.model){const m=S.ch.models.find(m=>m.ready&&(m.trained.line||m.trained.block))||S.ch.models.find(m=>m.ready);S.sel.model=m?m.key:"";}fix();render();}
function model(){return S.ch.models.find(m=>m.key===S.sel.model);}
function unit(){return S.sel.view==="block"?"block":"line";}
function saved(){const m=model();const t=m&&m.thresholds&&m.thresholds[S.sel.view];return t&&t[S.sel.stage]!=null?t[S.sel.stage]:null;}
function fix(){
  const m=model();
  if(m&&S.sel.stage==="after"&&!m.trained[unit()])S.sel.stage="before";
  if(S.sel.thrmode==="saved"){const v=saved();if(v==null)S.sel.thrmode="half";else S.sel.thr=v;}
  if(S.sel.thrmode==="half")S.sel.thr=0.5;
}
function key(){return [S.sel.model,S.sel.view,S.sel.stage].join("|");}
function radio(name,value,cur,label,note,off){
  return `<label class="${off?"off":""}"><input type="radio" name="${name}" value="${esc(value)}" ${value===cur?"checked":""} ${off?"disabled":""}><span>${label}${note?`<small>${note}</small>`:""}</span></label>`;
}
function render(){
  // 파일
  if(!S.files.length)$("files").innerHTML=`<p class="sub">아직 올린 파일이 없습니다.</p>`;
  else $("files").innerHTML=`<table><tr><th>파일</th><th class="n">쪽</th><th class="n">덩어리</th><th class="n">줄</th><th class="n">글 뽑는 데</th><th>상태</th><th></th></tr>`+S.files.map(f=>
    `<tr><td>${esc(f.name)}</td><td class="n">${f.error?"-":f.pages}</td><td class="n">${f.error?"-":f.blocks}</td><td class="n">${f.error?"-":f.lines}</td><td class="n">${f.error?"-":fmt(f.seconds)}</td>`+
    `<td>${f.error?`<span style="color:var(--err)">${esc(f.error)}</span>`:(f.blocks?"글을 뽑았습니다":"뽑힌 글이 없습니다")}</td><td><button data-rm="${esc(f.name)}">빼기</button></td></tr>`).join("")+`</table>`;
  // 모델
  $("models").innerHTML=S.ch.models.map(m=>{
    const t=["block","line"].map(u=>m.trained[u]?`${u==="block"?"덩어리":"줄"} 분류기: ${esc(m.trained[u].trained)} 학습 (예 ${m.trained[u].yes}, 아니오 ${m.trained[u].no})`:`${u==="block"?"덩어리":"줄"} 분류기: 없음`).join("<br>");
    return radio("model",m.key,S.sel.model,esc(m.label),m.ready?t:"모델 파일이 없습니다 (download_screen.bat)",!m.ready);}).join("");
  $("views").innerHTML=S.ch.views.map(v=>radio("view",v.key,S.sel.view,esc(v.label),VIEWNOTE[v.key])).join("");
  const m=model(),has=m&&m.trained[unit()];
  $("stages").innerHTML=radio("stage","after",S.sel.stage,"학습한 분류기",has?`${esc(has.trained)}에 학습한 것`:"이 모델·크기로 학습한 분류기가 아직 없습니다 (label.bat 에서 학습)",!has)+
    radio("stage","before",S.sel.stage,"기준 문장 (학습 전)","screen_sentences.txt 의 문장과 견줘 판단");
  const sv=saved(),pct=S.ch.target?Math.round(S.ch.target*100):90;
  $("thrs").innerHTML=radio("thrmode","half",S.sel.thrmode,"0.5","예와 아니오 가능성이 반반인 자리")+
    radio("thrmode","saved",S.sel.thrmode,sv!=null?`지난 학습에서 '예'의 ${pct}%를 찾던 문턱 (${sv.toFixed(2)})`:`지난 학습에서 '예'의 ${pct}%를 찾던 문턱`,
      sv!=null?`${esc(S.ch.thresholds_made)}에 학습용 문서의 정답으로 구한 값. 덜 놓치는 쪽`:"이 조합의 값이 없습니다. '학습하고 결과 보기'를 한 번 하면 생깁니다",sv==null)+
    `<label><input type="radio" name="thrmode" value="custom" ${S.sel.thrmode==="custom"?"checked":""}><span>직접 정하기 <input type="number" id="thrnum" min="0" max="1" step="0.01" value="${S.sel.thr.toFixed(2)}"></span></label>`;
  $("thrbar").value=S.sel.thr;$("thrnow").textContent=S.sel.thr.toFixed(2);
  $("methods").innerHTML=METHODS.map(x=>radio("method",x[0],S.sel.method,x[1],x[2])).join("");
  $("titlew").textContent=S.ch.title_weight?`쪽 제목 반영: 켜짐 (비율 ${S.ch.title_weight}). 걸러내기 설정(screen_options.txt)을 그대로 따릅니다.`:"쪽 제목 반영: 꺼짐 (걸러내기 설정을 그대로 따릅니다)";
  drawPreview();
}
function drawPreview(){
  const p=S.preview;
  if(!p||S.pkey!==key()){$("preview").innerHTML=S.files.length?`<p class="sub">'점수 매기고 미리 보기'를 누르면 지금 고른 조합으로 몇 개가 '예'가 되는지 보여 줍니다.</p>`:"";return;}
  const byLine=S.sel.view==="line",thr=S.sel.thr,word=byLine?"줄":"덩어리";
  let h=`<table><tr><th>파일</th><th class="n">'예'로 볼 ${word}</th><th class="n">전체</th><th class="n">비율</th></tr>`,lists="";
  for(const f of p.files){
    if(f.error){h+=`<tr><td>${esc(f.name)}</td><td colspan="3" style="color:var(--err)">${esc(f.error)}</td></tr>`;continue;}
    const all=[];
    for(const b of f.items){
      if(byLine){for(const l of (b.lines||[]))if(l.score!=null)all.push({page:b.page,score:l.score,text:l.text});}
      else if(b.score!=null)all.push({page:b.page,score:b.score,text:b.text});
    }
    const yes=all.filter(x=>x.score>=thr);
    h+=`<tr><td>${esc(f.name)}</td><td class="n"><b class="yes">${yes.length}</b></td><td class="n">${all.length}</td><td class="n">${all.length?Math.round(100*yes.length/all.length):0}%</td></tr>`;
    lists+=`<details><summary>${esc(f.name)}: '예'로 볼 ${word} ${yes.length}개 보기</summary><ol class="items">`+
      (yes.length?yes.slice(0,300).map(x=>`<li><span class="pg">${x.page}쪽</span><span class="sc">${x.score.toFixed(2)}</span><span class="tx">${esc(x.text)}</span></li>`).join(""):`<li class="sub">문턱 이상인 것이 없습니다.</li>`)+
      (yes.length>300?`<li class="sub">… 나머지 ${yes.length-300}개는 요약 화면에서 볼 수 있습니다.</li>`:"")+`</ol></details>`;
  }
  $("preview").innerHTML=h+`</table>`+lists+`<p class="sub">문턱을 움직이면 위 숫자가 바로 바뀝니다. 정했으면 '표시한 파일 만들기'를 누르세요.</p>`;
}
function body(){return {model:S.sel.model,view:S.sel.view,stage:S.sel.stage};}
async function doScore(){
  if(!S.files.length)throw new Error("먼저 파일을 올려 주세요.");
  if(!S.sel.model)throw new Error("쓸 수 있는 모델이 없습니다. install_screen.bat 과 download_screen.bat 을 확인해 주세요.");
  say("점수를 매기는 중입니다. 처음 보는 글은 시간이 걸립니다…");
  const j=await post("/score",body());S.preview=j;S.pkey=key();say(j.note||"");drawPreview();
}
$("score").onclick=()=>busy(doScore);
$("make").onclick=()=>busy(async()=>{
  const fresh=$("fresh").checked;
  if(!fresh&&(!S.preview||S.pkey!==key()))await doScore();
  if(fresh&&!S.files.length)throw new Error("먼저 파일을 올려 주세요.");
  say(fresh?"보관해 둔 계산을 쓰지 않고 처음부터 계산해 표시하는 중입니다…":"표시한 파일을 만드는 중입니다…");
  const note=S.sel.thrmode==="saved"?`지난 학습에서 '예'의 ${S.ch.target?Math.round(S.ch.target*100):90}%를 찾던 문턱`:"";
  const j=await post("/make",Object.assign(body(),{threshold:S.sel.thr,method:S.sel.method,note:note,fresh:fresh}));
  $("results").innerHTML=`<h2 style="margin-top:14px">만든 결과</h2><table class="res"><tr><th>파일</th><th class="n">'예'</th><th>표시한 사본</th><th>요약 화면</th></tr>`+j.results.map(r=>
    r.error?`<tr><td>${esc(r.name)}</td><td colspan="3" style="color:var(--err)">${esc(r.error)}</td></tr>`:
    `<tr><td>${esc(r.name)}</td><td class="n">${r.yes} / ${r.total}</td><td>${r.marked?`<a href="/out/mark/${encodeURIComponent(r.marked)}" target="_blank">${esc(r.marked)}</a> <button data-open="${esc(r.marked)}">기본 프로그램으로 열기</button>`:"-"}</td>`+
    `<td><a href="/out/mark/${encodeURIComponent(r.page)}" target="_blank">열기</a>${(r.notes||[]).map(n=>`<div class="note">${esc(n)}</div>`).join("")}</td></tr>`).join("")+
    `</table><p class="sub">결과는 <code>${esc(j.folder)}</code> 에 있습니다. 모델이나 크기를 바꿔 다시 만들면 다른 이름으로 따로 쌓여서 서로 견줘 볼 수 있습니다.</p>`+
    `<h2 style="margin-top:14px">단계마다 걸린 시간</h2>`+j.results.filter(r=>!r.error&&r.timing).map(r=>{const c=r.timing.classify;
      return `<div class="tres"><b>${esc(r.name)}</b>`+timeBar(r.timing)+
        (c.reused?`<div class="note">분류기: 보관해 둔 계산 ${c.reused}개를 다시 써서 그만큼 짧게 나왔습니다. 처음부터 재려면 위의 '처음부터 다시 계산하기'에 체크하고 다시 만드세요.</div>`:
          (c["new"]?`<div class="note">분류기: 글 ${c["new"]}개를 새로 계산 · 모델을 불러오는 데 ${fmt(Math.max(0,c.sec-c.compute))}, 점수 계산에 ${fmt(c.compute)}</div>`:""))+`</div>`;}).join("")+
    `<p class="sub">막대에서 칸의 너비가 그 단계에 걸린 시간에 비례합니다. 표시하기에는 LLM 단계가 없습니다(LLM에 걸리는 시간은 verify.bat 결과 화면에 나옵니다). 자세한 표는 요약 화면에, 실행마다의 기록은 '걸린 시간 기록'에 있습니다.</p>`;
  say("만들었습니다.");
});
$("folder").onclick=()=>busy(async()=>{await post("/open",{});say("");});
$("timelog").onclick=()=>window.open("/out/mark/times.html","_blank");
document.addEventListener("click",e=>{
  const t=e.target;
  if(t.dataset&&t.dataset.rm)busy(async()=>{await post("/remove",{name:t.dataset.rm});S.preview=null;await load();say("");});
  if(t.dataset&&t.dataset.open)busy(async()=>{await post("/open",{name:t.dataset.open});say("");});
});
document.addEventListener("change",e=>{
  const t=e.target;
  if(t.name==="model"||t.name==="view"||t.name==="stage"||t.name==="method"||t.name==="thrmode"){S.sel[t.name]=t.value;fix();render();}
  if(t.id==="thrnum"){const v=parseFloat(t.value);if(!isNaN(v)){S.sel.thrmode="custom";S.sel.thr=Math.min(1,Math.max(0,v));render();}}
});
$("thrbar").addEventListener("input",e=>{S.sel.thrmode="custom";S.sel.thr=parseFloat(e.target.value);const n=$("thrnum");if(n)n.value=S.sel.thr.toFixed(2);
  for(const r of document.querySelectorAll('input[name=thrmode]'))r.checked=r.value==="custom";$("thrnow").textContent=S.sel.thr.toFixed(2);drawPreview();});
async function upload(list){
  const files=[...list].filter(f=>/\.(pdf|pptx)$/i.test(f.name));
  if(!files.length)throw new Error("PDF나 PPTX 파일만 올릴 수 있습니다.");
  for(const f of files){
    say(`올리고 글을 뽑는 중: ${f.name}`);
    const r=await fetch("/upload?name="+encodeURIComponent(f.name),{method:"POST",headers:{"Content-Type":"application/octet-stream","X-Mark":"1"},body:f});
    const j=await r.json().catch(()=>({ok:false,error:"응답을 읽지 못했습니다"}));
    if(!r.ok||j.ok===false)throw new Error(f.name+": "+(j.error||"올리지 못했습니다"));
  }
  S.preview=null;await load();say("");
}
$("pick").onclick=()=>$("file").click();
$("file").onchange=e=>{const l=e.target.files;busy(async()=>{await upload(l);e.target.value="";});};
const d=$("drop");
d.addEventListener("dragover",e=>{e.preventDefault();d.classList.add("over");});
d.addEventListener("dragleave",()=>d.classList.remove("over"));
d.addEventListener("drop",e=>{e.preventDefault();d.classList.remove("over");const l=e.dataTransfer.files;busy(()=>upload(l));});
load().catch(e=>say(e.message,true));
</script></body></html>
""".replace("/*TIMECSS*/", times.CSS)


class App:
    def __init__(self, cfg, files: List[Path]):
        self.cfg = cfg
        self.scorer = core.Scorer(cfg)
        self.lock = threading.RLock()               # 무거운 일(글 뽑기, 점수 매기기, 만들기)은 한 번에 하나만
        self.docs: Dict[str, core.Extracted] = {}   # 파일 이름 → 뽑은 것
        self.errors: Dict[str, str] = {}
        self.order: List[str] = []
        self.scores: Dict[tuple, dict] = {}         # (파일 이름, 모델, 크기, 판단 방법) → 점수
        self.status = ""
        self.in_dir = make.mark_dir(cfg) / "in"
        for f in files:
            self.add(Path(f))

    def log(self, msg: str) -> None:
        self.status = msg.strip()
        print(msg, flush=True)

    def add(self, path: Path) -> None:
        """파일 하나에서 글을 뽑아 목록에 올린다. 같은 이름이 있으면 바꾼다."""
        name = path.name
        with self.lock:
            self.log("글을 뽑는 중: %s" % name)
            for k in [k for k in self.scores if k[0] == name]:
                del self.scores[k]
            self.docs.pop(name, None)
            self.errors.pop(name, None)
            if name not in self.order:
                self.order.append(name)
            try:
                self.docs[name] = core.extract(path)
            except Exception as exc:
                traceback.print_exc()
                self.errors[name] = "글을 뽑지 못했습니다 (%s: %s)" % (type(exc).__name__, str(exc)[:160])
            self.status = ""

    def remove(self, name: str) -> dict:
        with self.lock:
            self.docs.pop(name, None)
            self.errors.pop(name, None)
            self.order = [n for n in self.order if n != name]
            for k in [k for k in self.scores if k[0] == name]:
                del self.scores[k]
        return {"ok": True}

    def state(self) -> dict:
        files = []
        for name in self.order:
            ex = self.docs.get(name)
            item = {"name": name, "error": self.errors.get(name, "")}
            if ex is not None:
                item.update(ex.counts, kind=ex.kind, seconds=round(ex.seconds, 3))
            files.append(item)
        return {"ok": True, "files": files, "choices": core.choices(self.cfg)}

    def _scores(self, ex: core.Extracted, model: str, view: str, stage: str, fresh: bool = False) -> dict:
        """fresh: 보관해 둔 계산을 쓰지 않고 다시 계산한다(걸린 시간을 잴 때)."""
        key = (ex.name, model, view, stage)
        if fresh or key not in self.scores:
            self.scores[key] = self.scorer.score(ex, model, view, stage, self.log, fresh)
        return self.scores[key]

    def score(self, body: dict) -> dict:
        model, view, stage = str(body.get("model", "")), str(body.get("view", "")), str(body.get("stage", ""))
        out, new, seconds = [], 0, 0.0
        with self.lock:
            for name in self.order:
                ex = self.docs.get(name)
                if ex is None:
                    out.append({"name": name, "error": self.errors.get(name, "글이 없습니다")})
                    continue
                self.log("점수를 매기는 중: %s" % name)
                fresh = (name, model, view, stage) not in self.scores
                sc = self._scores(ex, model, view, stage)
                if fresh:
                    new, seconds = new + sc["new"], seconds + sc["seconds"]
                rnd = lambda v: None if v is None else round(v, 4)
                items = []
                for b in (ex.doc.blocks if ex.doc else []):
                    it = {"page": b.page, "text": b.text[:600], "score": rnd(sc["block"].get(b.id))}
                    if view == "line":
                        it["lines"] = [{"text": l.text[:600], "score": rnd(sc["line"].get(l.id))} for l in b.lines]
                    items.append(it)
                out.append({"name": name, "items": items})
            self.status = ""
        note = "새로 계산한 글 %d개 · %.0f초" % (new, seconds) if new else "계산해 둔 결과를 다시 썼습니다."
        return {"ok": True, "files": out, "note": note}

    def make(self, body: dict) -> dict:
        model, view, stage = str(body.get("model", "")), str(body.get("view", "")), str(body.get("stage", ""))
        threshold = core.safe_threshold(body.get("threshold"))
        method = str(body.get("method") or "annot")
        if method not in ("annot", "paint"):
            raise ValueError("표시 방식을 알 수 없습니다")
        note = str(body.get("note") or "")[:120]
        fresh = bool(body.get("fresh"))
        results = []
        with self.lock:
            for name in self.order:
                ex = self.docs.get(name)
                if ex is None:
                    results.append({"name": name, "error": self.errors.get(name, "글이 없습니다")})
                    continue
                self.log("표시하는 중: %s" % name)
                try:
                    sc = self._scores(ex, model, view, stage, fresh)
                    res = make.make(self.scorer, ex, model, view, stage, threshold, method, self.log, sc, note, fresh)
                    results.append(res)
                    t = res["timing"]
                    print("  %s: 글 뽑기 %s · 분류기 %s · 파일 만들기 %s · 합계 %s" % (
                        name, times.fmt(t["extract"]["sec"]), times.fmt(t["classify"]["sec"]), times.fmt(t["write"]["sec"]), times.fmt(t["total"])), flush=True)
                except ValueError:
                    raise
                except Exception as exc:
                    traceback.print_exc()
                    results.append({"name": name, "error": "%s: %s" % (type(exc).__name__, str(exc)[:200])})
            self.status = ""
        return {"ok": True, "results": results, "folder": str(make.mark_dir(self.cfg).resolve())}

    def open(self, body: dict) -> dict:
        """결과 폴더나 그 안의 파일을 이 PC의 기본 프로그램으로 연다."""
        folder = make.mark_dir(self.cfg).resolve()
        folder.mkdir(parents=True, exist_ok=True)
        target = folder
        name = str(body.get("name") or "")
        if name:
            target = (folder / Path(name).name).resolve()
            if target.parent != folder or not target.is_file():
                raise ValueError("없는 파일입니다")
        if sys.platform.startswith("win"):
            os.startfile(str(target))               # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target)])
        return {"ok": True}

    def save_upload(self, name: str, stream, size: int) -> dict:
        name = Path(unquote(name)).name
        if not name or name.startswith("~$") or Path(name).suffix.lower() not in (".pdf", ".pptx"):
            raise ValueError("PDF나 PPTX 파일만 올릴 수 있습니다")
        if size <= 0:
            raise ValueError("빈 파일입니다")
        if size > MAX_UPLOAD:
            raise ValueError("파일이 너무 큽니다 (600MB까지)")
        self.in_dir.mkdir(parents=True, exist_ok=True)
        target = self.in_dir / name
        tmp = self.in_dir / (name + ".part")
        left = size
        with open(tmp, "wb") as f:
            while left > 0:
                chunk = stream.read(min(left, 1024 * 1024))
                if not chunk:
                    break
                f.write(chunk)
                left -= len(chunk)
        if left:
            tmp.unlink(missing_ok=True)
            raise ValueError("파일을 끝까지 받지 못했습니다")
        tmp.replace(target)
        self.add(target)
        return {"ok": True, "name": name, "error": self.errors.get(name, "")}


def make_handler(app: App):
    out_root = Path(app.cfg.out_dir).resolve()

    class Handler(BaseHTTPRequestHandler):
        server_version = "docparse-mark"

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
                    return self._json(200, {"ok": True, "text": app.status})
                if path.startswith("/out/"):
                    target = (out_root / path[len("/out/"):]).resolve()
                    if out_root in target.parents and target.is_file() and target.suffix.lower() in TYPES:
                        return self._send(200, target.read_bytes(), TYPES[target.suffix.lower()])
                self._send(404, "없는 주소입니다".encode("utf-8"), TYPES[".txt"])
            except Exception as exc:
                traceback.print_exc()
                self._json(500, {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)})

        def do_POST(self) -> None:
            # 다른 웹 페이지가 몰래 보낸 요청은 받지 않는다(이 화면만 붙일 수 있는 표시를 확인)
            ctype = self.headers.get("Content-Type") or ""
            if not self._local() or self.headers.get("X-Mark") != "1":
                return self._send(403, b"forbidden", TYPES[".txt"])
            parts = urlsplit(self.path)
            try:
                size = int(self.headers.get("Content-Length") or 0)
                if parts.path == "/upload":
                    if "application/octet-stream" not in ctype:
                        return self._send(403, b"forbidden", TYPES[".txt"])
                    name = (parse_qs(parts.query).get("name") or [""])[0]
                    return self._json(200, app.save_upload(name, self.rfile, size))
                if "application/json" not in ctype:
                    return self._send(403, b"forbidden", TYPES[".txt"])
                if size > 8 * 1024 * 1024:
                    return self._json(413, {"ok": False, "error": "너무 큰 요청"})
                body = json.loads(self.rfile.read(size).decode("utf-8") or "{}")
                if parts.path == "/score":
                    return self._json(200, app.score(body))
                if parts.path == "/make":
                    return self._json(200, app.make(body))
                if parts.path == "/remove":
                    return self._json(200, app.remove(str(body.get("name") or "")))
                if parts.path == "/open":
                    return self._json(200, app.open(body))
                self._json(404, {"ok": False, "error": "없는 주소입니다"})
            except ValueError as exc:
                self._json(400, {"ok": False, "error": str(exc)})
            except SystemExit as exc:
                self._json(400, {"ok": False, "error": str(exc)})
            except Exception as exc:
                traceback.print_exc()
                self._json(500, {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)})

    return Handler


def serve(cfg, files: List[Path], port: int = 8775, open_browser: bool = True) -> None:
    app = App(cfg, files)
    server = None
    for p in range(port, port + 20):               # 쓰고 있는 번호면 다음 번호로
        try:
            server = ThreadingHTTPServer(("127.0.0.1", p), make_handler(app))
            break
        except OSError:
            continue
    if server is None:
        raise SystemExit("[오류] 화면을 열 포트를 찾지 못했습니다 (%d~%d)" % (port, port + 19))
    url = "http://127.0.0.1:%d/" % server.server_address[1]
    print("표시하기 화면: %s" % url)
    print("이 PC 안에서만 열립니다. 이 창을 닫으면(또는 Ctrl+C) 끝납니다.")
    print("결과 폴더: %s" % make.mark_dir(cfg).resolve(), flush=True)
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
