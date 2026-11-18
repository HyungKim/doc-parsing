"""표시하기 화면: 파일을 올리고, 최종 모델(분류기 → LLM)로 표시한 사본 두 개와 요약 화면을 만든다. 단계마다 걸린 시간을 함께 보여 준다.

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
from typing import Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlsplit

from verifying import core as vcore
from verifying import ollama, prompts

from . import core, final, times
from . import rules as mrules

TYPES = {".html": "text/html; charset=utf-8", ".json": "application/json; charset=utf-8", ".txt": "text/plain; charset=utf-8",
         ".csv": "text/csv; charset=utf-8", ".png": "image/png", ".jpg": "image/jpeg", ".pdf": "application/pdf",
         ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation"}
MAX_UPLOAD = 600 * 1024 * 1024

PAGE = r"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>검토 필요 표시하기 · 최종 모델</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--ink:#1c2330;--mute:#5d6878;--line:#d9dee6;--acc:#1f5fbf;--hl:#fff3a0;--hl-ink:#5a4a00;--hl-edge:#d9a400;--ok:#17803f;--err:#a12626}
@media (prefers-color-scheme:dark){:root{--bg:#14171c;--card:#1d2229;--ink:#e6eaf0;--mute:#9aa5b5;--line:#343c48;--acc:#7fb0ff;--hl:#5a4d10;--hl-ink:#ffe98a;--ok:#6fd08f;--err:#ffb3b3}}
*{box-sizing:border-box}
body{margin:0;padding:18px 22px 80px;background:var(--bg);color:var(--ink);font:15px/1.6 -apple-system,"Malgun Gothic","맑은 고딕",sans-serif}
h1{font-size:21px;margin:0 0 4px}
h2{font-size:16px;margin:0 0 8px}
h3{font-size:15px;margin:0 0 4px}
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
button.small{padding:1px 8px;font-size:13px}
button:disabled{opacity:.5;cursor:default}
.opt{display:flex;gap:6px 18px;flex-wrap:wrap;margin:2px 0 10px}
.opt.col{flex-direction:column;gap:4px}
.opt label{display:flex;gap:6px;align-items:flex-start;cursor:pointer}
.opt label.off{color:var(--mute);cursor:default}
.opt small{color:var(--mute);display:block;font-size:12px;line-height:1.4}
.grp{margin:0 0 4px;font-weight:700;font-size:14px}
input[type=number]{font:inherit;width:84px;padding:3px 6px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--ink)}
input[type=range]{width:240px;vertical-align:middle}
#status{min-height:22px;color:var(--mute);font-size:13px;margin-top:6px}
#status.err{color:var(--err);font-weight:700}
.yes{background:var(--hl);color:var(--hl-ink);border-radius:3px;padding:0 4px}
.ok{color:var(--ok);font-weight:700}.bad{color:var(--err);font-weight:700}
details{margin:4px 0}
details summary{cursor:pointer}
ol.items{list-style:none;margin:6px 0 0;padding:0;max-height:420px;overflow:auto;border:1px solid var(--line);border-radius:6px}
ol.items li{display:flex;gap:10px;padding:4px 8px;border-bottom:1px solid var(--line);font-size:14px}
ol.items li:last-child{border-bottom:0}
ol.items .pg{flex:0 0 46px;color:var(--mute);font-size:12px;padding-top:2px}
ol.items .sc{flex:0 0 40px;font-weight:700;font-variant-numeric:tabular-nums}
ol.items .tx{white-space:pre-wrap;word-break:break-word;min-width:0}
.note{color:var(--mute);font-size:13px}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
a{color:var(--acc)}
code{font:13px ui-monospace,Consolas,monospace;background:var(--bg);border:1px solid var(--line);border-radius:4px;padding:0 4px}
.flow{display:flex;gap:8px;align-items:stretch;flex-wrap:wrap;margin:4px 0 12px}
.flow .st{flex:1 1 200px;border:1px solid var(--line);border-radius:8px;padding:8px 10px;background:var(--bg)}
.flow .st b{display:block;font-size:14px}
.flow .st span{display:block;font-size:13px}
.flow .ar{align-self:center;color:var(--mute);font-size:18px}
.pbar{height:8px;background:var(--line);border-radius:4px;max-width:520px;margin-top:6px;overflow:hidden}
.pbar i{display:block;height:8px;background:var(--acc);width:0}
.res{border:1px solid var(--line);border-radius:8px;padding:10px 12px;margin:10px 0}
.res ul{margin:4px 0;padding-left:20px}
.res li{margin:2px 0}
.cnt{font-variant-numeric:tabular-nums}
/*TIMECSS*/
</style></head><body class="tm">
<h1>'검토 필요' 표시하기 · 최종 모델</h1>
<p class="sub">PDF·PPTX를 올리면 최종 모델로 '검토 필요(예)'를 가려, <b>분류기 출력으로 표시한 사본</b>과 <b>LLM까지 거친 결과로 표시한 사본</b>을 만들고, 단계마다 걸린 시간을 보여 줍니다.
자료는 이 PC 밖으로 나가지 않습니다. 정답과 학습 결과는 읽기만 하고 바꾸지 않습니다. 이 PC 안에서만 열리는 화면입니다.</p>

<div class="card"><h2>1. 표시할 파일</h2>
<div class="drop" id="drop">PDF·PPTX 파일을 여기에 끌어다 놓거나 <button id="pick">파일 고르기</button>
<input type="file" id="file" multiple accept=".pdf,.pptx" style="display:none"></div>
<div id="files"></div></div>

<div class="card"><h2>2. 최종 모델 <span class="sub" style="font-weight:400">(5.0에서 정한 조합. 바꿀 수 없고, 아래 세 가지만 고릅니다)</span></h2>
<div class="flow" id="flow"></div>
<div class="grp">5.1에서 달라진 것</div>
<ul class="sub" style="margin:0 0 10px;padding-left:20px">
<li><b>표는 행 하나씩 판단합니다.</b> 표 전체가 아니라 '예'로 본 행에만 표시합니다. 분류기 · 문턱 · LLM은 글 덩어리와 같습니다. 행마다 LLM에 물으므로 표가 많은 문서는 묻는 수가 늘 수 있습니다.</li>
<li id="rules">표시하지 않는 규칙을 읽는 중…</li>
</ul>
<div class="grp">분류기의 문턱 <span class="sub" style="font-weight:400">(분류기 점수가 이 값 이상인 글을 '예'로 보고 LLM에 넘김)</span></div>
<div class="opt col" id="thrs"></div>
<div class="row" style="margin:-4px 0 10px"><input type="range" id="thrbar" min="0" max="1" step="0.01" value="0.5"><span class="sub">지금 문턱 <b id="thrnow">0.50</b></span></div>
<div class="grp">PDF에 표시하는 방식</div><div class="opt" id="methods"></div>
<div class="grp">돌리는 방법</div>
<div class="opt col">
<label><input type="checkbox" id="usellm" checked><span>LLM 단계까지 돌리기<small>끄면 분류기 출력으로 표시한 사본만 만듭니다(LLM은 글 하나에 몇 초에서 몇십 초가 걸립니다).</small></span></label>
<label><input type="checkbox" id="fresh"><span>보관해 둔 계산을 쓰지 않고 처음부터 다시 계산하기 <b>(걸린 시간을 재려면 체크)</b><small>한 번 계산한 글의 점수와 LLM의 답은 보관해 두고 다시 씁니다. 그래서 같은 문서를 두 번째로 돌리면 시간이 거의 0으로 나옵니다. 체크하면 보관해 둔 것을 쓰지 않고 모두 새로 계산해서, 처음 보는 문서에 걸리는 시간이 나옵니다.</small></span></label>
</div>
<p class="sub" id="titlew"></p></div>

<div class="card"><h2>3. 미리 보기와 만들기</h2>
<div class="row"><button id="score">분류기 점수 미리 보기</button><button id="make" class="main">표시한 파일 만들기</button><button id="stop" disabled>멈추기</button>
<button id="folder">결과 폴더 열기</button><button id="timelog">걸린 시간 기록 열기</button></div>
<p class="sub">'멈추기'를 누르면 LLM에 묻고 있던 덩어리도 기다리지 않고 바로 끊습니다. 받은 답은 보관되어 있어서, 다시 만들면 이어서 받습니다.</p>
<div class="pbar" id="pbar" style="display:none"><i></i></div>
<div id="status"></div><div id="preview"></div><div id="results"></div></div>

<script>
const $=id=>document.getElementById(id);
const esc=s=>String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
let S={files:[],fin:null,preview:null,busy:false,running:false,sel:{thrmode:null,thr:0.5,method:"annot"}};
const METHODS=[["annot","형광펜 주석","PDF 프로그램에서 하나씩 지울 수 있고, 메모에 점수와 LLM의 답이 들어갑니다"],["paint","쪽에 직접 칠하기","주석을 보여 주지 않는 프로그램이나 인쇄에서도 보입니다. 지울 수 없습니다"]];
const STAGES=[["extract","글 뽑기"],["classify","분류기"],["llm","LLM"],["write","파일 만들기"]];

async function post(path,body){
  const r=await fetch(path,{method:"POST",headers:{"Content-Type":"application/json","X-Mark":"1"},body:JSON.stringify(body||{})});
  const j=await r.json().catch(()=>({ok:false,error:"응답을 읽지 못했습니다"}));
  if(!r.ok||j.ok===false)throw new Error(j.error||"실패했습니다");
  return j;
}
function say(text,err){const s=$("status");s.textContent=text||"";s.className=err?"err":"";}
function lock(on){S.busy=on;for(const b of document.querySelectorAll("button"))b.disabled=on&&b.id!=="stop";$("stop").disabled=!S.running;}
let timer=null,ptimer=null;
function poll(on){
  if(ptimer){clearInterval(ptimer);ptimer=null;}
  if(on)ptimer=setInterval(async()=>{try{const j=await (await fetch("/status")).json();if(S.busy&&!S.running&&j.text)say(j.text);}catch(e){}},1000);
}
async function busy(fn){
  if(S.busy)return;lock(true);poll(true);
  try{await fn();}catch(e){say(e.message,true);}
  finally{poll(false);if(!S.running)lock(false);}
}
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
  const total=STAGES.reduce((a,x)=>a+t[x[0]].sec,0);if(total<=0)return "";
  const cells=STAGES.map((x,n)=>t[x[0]].sec>0?`<i class="t${n}" style="flex:${(t[x[0]].sec/total).toFixed(4)} 1 0" title="${x[1]} ${fmt(t[x[0]].sec)} (${share(t[x[0]].sec,total)})"></i>`:"").join("");
  const key=STAGES.map((x,n)=>`<span><i class="t${n}"></i>${x[1]} <b>${fmt(t[x[0]].sec)}</b> (${share(t[x[0]].sec,total)})</span>`).join("")+`<span>합계 <b>${fmt(total)}</b></span>`;
  return `<div class="tbar2" role="img" aria-label="단계별 걸린 시간">${cells}</div><div class="tkey">${key}</div>`;
}
async function load(){
  const j=await (await fetch("/state")).json();S.files=j.files;S.fin=j.final;
  if(S.sel.thrmode===null)S.sel.thrmode=S.fin.threshold.saved!=null?"saved":"half";
  fix();render();
  if(j.run.running&&!S.running){S.running=true;lock(true);watch();}
}
function fix(){
  const sv=S.fin.threshold.saved;
  if(S.sel.thrmode==="saved"){if(sv==null)S.sel.thrmode="half";else S.sel.thr=sv;}
  if(S.sel.thrmode==="half")S.sel.thr=0.5;
}
function radio(name,value,cur,label,note,off){
  return `<label class="${off?"off":""}"><input type="radio" name="${name}" value="${esc(value)}" ${value===cur?"checked":""} ${off?"disabled":""}><span>${label}${note?`<small>${note}</small>`:""}</span></label>`;
}
function thrNote(){const pct=Math.round((S.fin.threshold.target||0.9)*100);return S.sel.thrmode==="saved"?`지난 학습(${S.fin.threshold.made})에서 '예'의 ${pct}%를 찾던 문턱`:S.sel.thrmode==="half"?"0.5 (예와 아니오 가능성이 반반인 자리)":"직접 정한 문턱";}
function render(){
  if(!S.files.length)$("files").innerHTML=`<p class="sub">아직 올린 파일이 없습니다.</p>`;
  else $("files").innerHTML=`<table><tr><th>파일</th><th class="n">쪽</th><th class="n">판단할 글</th><th class="n">글 뽑는 데</th><th>상태</th><th></th></tr>`+S.files.map(f=>
    `<tr><td>${esc(f.name)}</td><td class="n">${f.error?"-":f.pages}</td><td class="n">${f.error?"-":`${f.units} <span class="sub">(글 덩어리 ${f.units-f.rows}${f.rows?` + 표 ${f.tables}개의 행 ${f.rows}`:""})</span>`}</td><td class="n">${f.error?"-":fmt(f.seconds)}</td>`+
    `<td>${f.error?`<span class="bad">${esc(f.error)}</span>`:(f.blocks?"글을 뽑았습니다":"뽑힌 글이 없습니다")}</td><td><button data-rm="${esc(f.name)}">빼기</button></td></tr>`).join("")+`</table>`;
  const c=S.fin.classifier,l=S.fin.llm;
  let cs=!c.ready?`<span class="bad">모델 파일이 없습니다</span> (install_screen.bat 또는 download_screen.bat)`:
    (c.trained?`<span class="ok">준비됨</span> · ${esc(c.trained.trained)}에 학습 (정답 예 ${c.trained.yes}, 아니오 ${c.trained.no})`:`<span class="bad">덩어리 분류기가 아직 없습니다</span> (label.bat 에서 '학습하고 결과 보기')`);
  let ls=!l.ok?`<span class="bad">Ollama에 연결하지 못했습니다</span> ${esc(l.error||"")}`:
    (!l.pulled?`<span class="bad">${esc(l.name)} 모델을 아직 받지 않았습니다</span> (verify.bat 화면의 '받기' 또는 <code>ollama pull ${esc(l.name)}</code>)`:
     (l.prompt_error?`<span class="bad">프롬프트 파일에 문제가 있습니다</span> ${esc(l.prompt_error)}`:`<span class="ok">준비됨</span> · Ollama ${esc(l.version)} · 이 PC 안(127.0.0.1)에서만 돕니다`));
  $("flow").innerHTML=`<div class="st"><b>① 글 뽑기</b><span>PDF·PPTX → 덩어리</span><span class="sub">1단계와 같은 규칙</span></div><div class="ar">→</div>`+
    `<div class="st"><b>② 분류기</b><span>${esc(c.label)} · 덩어리 (표는 행)</span><span class="sub">${cs}</span></div><div class="ar">→</div>`+
    `<div class="st"><b>③ LLM</b><span>${esc(l.name)} · 프롬프트 안 ${esc(l.variant)}${l.variant_name?" "+esc(l.variant_name):""} · 생각 모드 ${l.think?"켬":"끔"}</span><span class="sub">${ls}</span></div><div class="ar">→</div>`+
    `<div class="st"><b>④ 표시한 파일</b><span>분류기 표시 사본 · LLM 표시 사본 · 요약 화면</span><span class="sub">out\\mark 폴더에 만듭니다</span></div>`;
  const sv=S.fin.threshold.saved,pct=Math.round((S.fin.threshold.target||0.9)*100);
  $("thrs").innerHTML=radio("thrmode","saved",S.sel.thrmode,(sv!=null?`지난 학습에서 '예'의 ${pct}%를 찾던 문턱 (${sv.toFixed(2)})`:`지난 학습에서 '예'의 ${pct}%를 찾던 문턱`)+" — 기본",
      sv!=null?`${esc(S.fin.threshold.made)}에 학습용 문서의 정답으로 구한 값. 분류기는 넓게 잡고 LLM이 덜어 내도록, 덜 놓치는 쪽입니다`:"이 값이 없습니다. label.bat 에서 '학습하고 결과 보기'를 한 번 하면 생깁니다. 그때까지는 0.5를 씁니다",sv==null)+
    radio("thrmode","half",S.sel.thrmode,"0.5","예와 아니오 가능성이 반반인 자리. 분류기가 '예'로 보는 덩어리가 줄어 LLM 시간이 줄지만, 놓치는 '예'가 늘 수 있습니다")+
    `<label><input type="radio" name="thrmode" value="custom" ${S.sel.thrmode==="custom"?"checked":""}><span>직접 정하기 <input type="number" id="thrnum" min="0" max="1" step="0.01" value="${S.sel.thr.toFixed(2)}"></span></label>`;
  $("thrbar").value=S.sel.thr;$("thrnow").textContent=S.sel.thr.toFixed(2);
  $("methods").innerHTML=METHODS.map(x=>radio("method",x[0],S.sel.method,x[1],x[2])).join("");
  const ru=S.fin.rules,q=a=>a.map(w=>`'${esc(w)}'`).join(" · ");
  $("rules").innerHTML=ru.error?`<span class="bad">표시하지 않는 규칙을 읽지 못했습니다</span> ${esc(ru.error)}`:
    `<b>표시하지 않는 규칙</b>: 쪽 제목에 든 말 ${ru.title_words.length?q(ru.title_words):"(없음)"} → 그 쪽 전체 · 문장에 든 단어 ${ru.line_words.length?q(ru.line_words):"(없음)"} → 그 문장(줄 하나, 표는 행 하나). `+
    `걸린 것은 LLM에도 묻지 않습니다. 프로그램 폴더의 <code>${esc(ru.file)}</code> 파일을 메모장으로 고치면 다음에 만들 때 반영됩니다.`;
  $("titlew").textContent=S.fin.title_weight?`쪽 제목 반영: 켜짐 (비율 ${S.fin.title_weight}). 걸러내기 설정(screen_options.txt)을 그대로 따릅니다.`:"쪽 제목 반영: 꺼짐 (걸러내기 설정을 그대로 따릅니다)";
  drawPreview();
}
function drawPreview(){
  const p=S.preview;
  if(!p){$("preview").innerHTML=S.files.length?`<p class="sub">'분류기 점수 미리 보기'를 누르면 지금 문턱에서 몇 개가 분류기의 '예'가 되는지(= LLM에 몇 개를 물어야 하는지) 보여 줍니다. 건너뛰고 바로 만들어도 됩니다.</p>`:"";return;}
  const thr=S.sel.thr;
  let h=`<table><tr><th>파일</th><th class="n">분류기가 '예'로 볼 글 (LLM에 물을 수)</th><th class="n">그 가운데 표의 행</th><th class="n">규칙으로 뺄 것</th><th class="n">전체</th><th class="n">비율</th></tr>`,lists="";
  for(const f of p.files){
    if(f.error){h+=`<tr><td>${esc(f.name)}</td><td colspan="5" class="bad">${esc(f.error)}</td></tr>`;continue;}
    const all=f.items.filter(b=>b.score!=null),over=all.filter(x=>x.score>=thr),yes=over.filter(x=>!x.skip),cut=over.filter(x=>x.skip);
    h+=`<tr><td>${esc(f.name)}</td><td class="n"><b class="yes">${yes.length}</b></td><td class="n">${yes.filter(x=>x.row).length}</td><td class="n">${cut.length}</td><td class="n">${all.length}</td><td class="n">${all.length?Math.round(100*yes.length/all.length):0}%</td></tr>`;
    lists+=`<details><summary>${esc(f.name)}: 분류기가 '예'로 볼 글 ${yes.length}개 보기</summary><ol class="items">`+
      (yes.length?yes.slice(0,300).map(x=>`<li><span class="pg">${x.page}쪽${x.row?" · 표의 행":""}</span><span class="sc">${x.score.toFixed(2)}</span><span class="tx">${esc(x.text)}</span></li>`).join(""):`<li class="sub">문턱 이상인 것이 없습니다.</li>`)+
      (yes.length>300?`<li class="sub">… 나머지 ${yes.length-300}개는 요약 화면에서 볼 수 있습니다.</li>`:"")+`</ol></details>`;
  }
  $("preview").innerHTML=h+`</table>`+lists+`<p class="sub">문턱을 움직이면 위 숫자가 바로 바뀝니다. '규칙으로 뺄 것'은 문턱 이상이지만 표시하지 않는 규칙에 통째로 걸린 수입니다. 정했으면 '표시한 파일 만들기'를 누르세요.</p>`;
}
function link(name){return `<a href="/out/mark/${encodeURIComponent(name)}" target="_blank">${esc(name)}</a>`;}
function showResults(j){
  let h=`<h2 style="margin-top:14px">만든 결과</h2>`;
  for(const r of j.results){
    if(r.error){h+=`<div class="res"><b>${esc(r.name)}</b> <span class="bad">${esc(r.error)}</span></div>`;continue;}
    const c=r.counts,f=r.files;
    h+=`<div class="res"><h3>${esc(r.name)}</h3>`+
      `<div class="cnt">판단한 글 ${c.blocks}개 (글 덩어리 ${c.text_blocks}${c.rows?` + 표 ${c.tables}개의 행 ${c.rows}`:""}) → 분류기 문턱 이상 ${c.scored_yes}개`+(c.ruled?` → 규칙으로 ${c.ruled}개를 뺌`:"")+` → 분류기 '예' <b class="yes">${c.passed}개</b>`+(c.kept!=null?` → LLM까지 거쳐 남은 것 <b class="yes">${c.kept}개</b> (LLM '예' ${c.llm_yes} · '아니오' ${c.llm_no}${c.llm_unknown?" · 읽지 못한 답 "+c.llm_unknown:""})`:"")+`</div>`+
      (r.llm.why?`<div class="${r.llm.stopped||r.llm.error?"bad":"note"}">${esc(r.llm.why)}</div>`:"")+
      `<ul><li>① 분류기 출력으로 표시한 사본: ${f.classifier?link(f.classifier)+` <button class="small" data-open="${esc(f.classifier)}">기본 프로그램으로 열기</button>`:"만들지 않음"}</li>`+
      `<li>② LLM까지 거친 결과로 표시한 사본: ${f.llm?link(f.llm)+` <button class="small" data-open="${esc(f.llm)}">기본 프로그램으로 열기</button>`:"만들지 않음"}</li>`+
      `<li>요약 화면(두 결과를 나란히, 단계별 시간 표): <a href="/out/mark/${encodeURIComponent(f.page)}" target="_blank"><b>열기</b></a></li></ul>`+
      `<div class="grp" style="margin-top:6px">단계마다 걸린 시간</div>`+timeBar(r.timing)+
      (r.timing.llm.mean!=null?`<div class="note">LLM: 글 ${r.timing.llm.asked}개 · 하나에 평균 ${fmt(r.timing.llm.mean)}${r.timing.llm.reused?` · 보관해 둔 답 ${r.timing.llm.reused}개를 다시 써서 그만큼 짧게 나왔습니다`:""}</div>`:"")+
      (r.timing.classify.reused?`<div class="note">분류기: 보관해 둔 계산 ${r.timing.classify.reused}개를 다시 써서 그만큼 짧게 나왔습니다</div>`:"")+
      (r.notes||[]).map(n=>`<div class="note">${esc(n)}</div>`).join("")+`</div>`;
  }
  h+=`<p class="sub">결과는 <code>${esc(j.folder)}</code> 에 있습니다. 실행마다의 시간은 '걸린 시간 기록'에 쌓입니다.</p>`;
  $("results").innerHTML=h;
}
function watch(){
  if(timer)clearInterval(timer);
  $("pbar").style.display="block";
  timer=setInterval(async()=>{
    let j;try{j=await (await fetch("/status")).json();}catch(e){return;}
    if(j.text)say(j.text,false);
    $("pbar").firstChild.style.width=(j.total?Math.round(100*j.done/j.total):0)+"%";
    if(!j.running){
      clearInterval(timer);timer=null;S.running=false;lock(false);$("pbar").style.display="none";
      if(j.results&&j.results.length)showResults(j);
      if(j.error)say(j.error,true);else say(j.stopped?"멈췄습니다. 그때까지의 결과를 만들었습니다.":"만들었습니다.");
      load().catch(()=>{});
    }
  },1000);
}
async function doScore(){
  if(!S.files.length)throw new Error("먼저 파일을 올려 주세요.");
  say("분류기 점수를 매기는 중입니다. 처음 보는 글은 시간이 걸립니다…");
  const j=await post("/score",{});S.preview=j;say(j.note||"");drawPreview();
}
$("score").onclick=()=>busy(doScore);
$("make").onclick=()=>busy(async()=>{
  if(!S.files.length)throw new Error("먼저 파일을 올려 주세요.");
  $("results").innerHTML="";say("시작하는 중입니다…");
  await post("/make",{threshold:S.sel.thr,note:thrNote(),method:S.sel.method,llm:$("usellm").checked,fresh:$("fresh").checked});
  S.running=true;lock(true);watch();
});
$("stop").onclick=async()=>{try{$("stop").disabled=true;say("멈추는 중입니다…");await post("/stop",{});}catch(e){say(e.message,true);}};
$("folder").onclick=()=>busy(async()=>{await post("/open",{});say("");});
$("timelog").onclick=()=>window.open("/out/mark/times.html","_blank");
document.addEventListener("click",e=>{
  const t=e.target;
  if(t.dataset&&t.dataset.rm)busy(async()=>{await post("/remove",{name:t.dataset.rm});S.preview=null;await load();say("");});
  if(t.dataset&&t.dataset.open)busy(async()=>{await post("/open",{name:t.dataset.open});say("");});
});
document.addEventListener("change",e=>{
  const t=e.target;
  if(t.name==="method"||t.name==="thrmode"){S.sel[t.name]=t.value;fix();render();}
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
    def __init__(self, cfg, files: List[Path], prompts_file: Path, rules_file: Optional[Path] = None):
        self.cfg = cfg
        self.prompts_file = Path(prompts_file)
        self.rules_file = Path(rules_file) if rules_file else None      # 표시하지 않는 규칙. 만들 때마다 새로 읽는다(메모장으로 고친 것이 바로 반영되게)
        self.scorer = core.Scorer(cfg)
        self.lock = threading.RLock()               # 무거운 일(글 뽑기, 점수 매기기, 만들기)은 한 번에 하나만
        self.docs: Dict[str, core.Extracted] = {}   # 파일 이름 → 뽑은 것
        self.errors: Dict[str, str] = {}
        self.order: List[str] = []
        self.scores: Dict[str, dict] = {}           # 파일 이름 → 분류기 점수
        self.status = ""
        self.running = False                        # 만들기를 돌리는 중인가
        self.error = ""
        self.results: List[dict] = []
        self.stopped = False
        self.done = 0
        self.total = 0
        self.stop = vcore.Stop()                    # 멈추기: LLM에 묻고 있던 요청도 바로 끊는다
        self._seen = 0
        self.in_dir = final.mark_dir(cfg) / "in"
        self.first = ollama.ensure_running(self.log)
        for f in files:
            self.add(Path(f))

    def log(self, msg: str) -> None:
        self.status = msg.strip()
        if "번째 덩어리" in msg:                    # 덩어리마다의 진행 줄은 창에 열 번에 한 번만 찍는다
            self._seen += 1
            if self._seen % 10 != 1:
                return
        print(msg, flush=True)

    def add(self, path: Path) -> None:
        """파일 하나에서 글을 뽑아 목록에 올린다. 같은 이름이 있으면 바꾼다."""
        name = path.name
        with self.lock:
            self.log("글을 뽑는 중: %s" % name)
            self.scores.pop(name, None)
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
        if self.running:
            raise ValueError("지금 만드는 중입니다. 끝난 뒤에 해 주세요.")
        with self.lock:
            self.docs.pop(name, None)
            self.errors.pop(name, None)
            self.order = [n for n in self.order if n != name]
            self.scores.pop(name, None)
        return {"ok": True}

    # ------------------------------------------------------------ 상태
    def _final(self) -> dict:
        """최종 모델의 구성과 지금 쓸 수 있는지."""
        cfg = self.cfg
        ch = core.choices(cfg)
        m = next((x for x in ch["models"] if x["key"] == final.FINAL["classifier"]), None) or {"label": final.FINAL["classifier"], "ready": False, "trained": {}}
        name, key = final.FINAL["llm"], final.FINAL["variant"]
        llm = {"name": name, "think": False, "variant": key, "variant_name": "", "ok": False, "pulled": False, "version": "",
               "error": "", "prompt_error": ""}
        try:
            llm["version"] = ollama.version()
            llm["pulled"] = ollama.find_model(name, ollama.models()) is not None
            llm["ok"] = True
        except ollama.OllamaError as exc:
            llm["error"] = str(exc)
        try:
            _, v = prompts.load(self.prompts_file, key)
            llm["variant_name"] = v.name
        except ValueError as exc:
            llm["prompt_error"] = str(exc)
        rules = {"title_words": [], "line_words": [], "file": self.rules_file.name if self.rules_file else "", "error": ""}
        try:
            r = self._rules()
            rules.update(title_words=list(r.title_words), line_words=list(r.line_words))
        except ValueError as exc:
            rules["error"] = str(exc)
        return {"classifier": {"label": m["label"], "ready": bool(m.get("ready")), "trained": (m.get("trained") or {}).get(final.VIEW)},
                "llm": llm, "title_weight": float(cfg.title_weight or 0.0), "rules": rules,
                "threshold": {"saved": final.saved_threshold(cfg), "made": ch.get("thresholds_made", ""), "target": ch.get("target") or 0.9}}

    def _rules(self) -> mrules.Rules:
        return mrules.read_rules(self.rules_file) if self.rules_file else mrules.no_rules()

    def state(self) -> dict:
        files = []
        for name in self.order:
            ex = self.docs.get(name)
            item = {"name": name, "error": self.errors.get(name, "")}
            if ex is not None:
                us = core.units(ex)
                item.update(ex.counts, kind=ex.kind, seconds=round(ex.seconds, 3), units=len(us), rows=sum(1 for u in us if u.row),
                            tables=sum(1 for b in (ex.doc.blocks if ex.doc else []) if b.kind == "table"))
            files.append(item)
        return {"ok": True, "files": files, "final": self._final(), "run": {"running": self.running}}

    def progress(self) -> dict:
        out = {"ok": True, "running": self.running, "text": self.status, "done": self.done, "total": self.total, "error": self.error,
               "stopped": self.stopped}
        if not self.running:
            out.update(results=self.results, folder=str(final.mark_dir(self.cfg).resolve()))
        return out

    # ------------------------------------------------------------ 분류기 점수
    def _scores(self, ex: core.Extracted, fresh: bool = False) -> dict:
        if fresh or ex.name not in self.scores:
            self.scores[ex.name] = final.score(self.scorer, ex, self.log, fresh)      # 표는 행마다도 점수를 매긴다
        return self.scores[ex.name]

    def score(self, body: dict) -> dict:
        """분류기 점수 미리 보기."""
        if self.running:
            raise ValueError("지금 만드는 중입니다. 끝난 뒤에 해 주세요.")
        out, new, seconds = [], 0, 0.0
        rules = self._rules()
        with self.lock:
            for name in self.order:
                ex = self.docs.get(name)
                if ex is None:
                    out.append({"name": name, "error": self.errors.get(name, "글이 없습니다")})
                    continue
                self.log("분류기 점수를 매기는 중: %s" % name)
                was = name in self.scores
                sc = self._scores(ex)
                if not was:
                    new, seconds = new + sc["new_items"], seconds + sc["wall"]
                items = []
                for u in core.units(ex):           # 판단 단위: 글 덩어리 하나, 표는 행 하나
                    v = core.unit_score(sc, u)
                    items.append({"page": u.page, "text": u.text[:600], "score": None if v is None else round(v, 4), "row": u.row,
                                  "skip": core.whole_skip(ex, u, rules)})
                out.append({"name": name, "items": items})
            self.status = ""
        note = "새로 계산한 글 %d개 · %s" % (new, times.fmt(seconds)) if new else "계산해 둔 결과를 다시 썼습니다."
        return {"ok": True, "files": out, "note": note}

    # ------------------------------------------------------------ 만들기
    def start(self, body: dict) -> dict:
        threshold = core.safe_threshold(body.get("threshold"))
        method = str(body.get("method") or "annot")
        if method not in ("annot", "paint"):
            raise ValueError("표시 방식을 알 수 없습니다")
        opts = {"threshold": threshold, "method": method, "note": str(body.get("note") or "")[:120],
                "llm": bool(body.get("llm", True)), "fresh": bool(body.get("fresh"))}
        if not self.order:
            raise ValueError("먼저 파일을 올려 주세요.")
        with self.lock:
            if self.running:
                raise ValueError("이미 만드는 중입니다.")
            self.running, self.error, self.results, self.stopped, self.done, self.total = True, "", [], False, 0, 0
            self.stop.clear()
        threading.Thread(target=self._run, args=(opts,), daemon=True).start()
        return {"ok": True}

    def _run(self, opts: dict) -> None:
        llm = None
        results: List[dict] = []
        try:
            with self.lock:
                answers = None
                rules = self._rules()
                if opts["llm"]:
                    self.log("LLM을 준비하는 중…")
                    llm = final.prepare_llm(self.cfg, self.prompts_file, self.log)
                    answers = vcore.Answers(final.answers_file(self.cfg))

                def tick(done: int, total: int) -> None:
                    self.done, self.total = done, total
                for n, name in enumerate(self.order):
                    ex = self.docs.get(name)
                    if ex is None:
                        results.append({"name": name, "error": self.errors.get(name, "글이 없습니다")})
                        continue
                    if self.stop.is_set():
                        results.append({"name": name, "error": "멈춰서 이 파일은 처리하지 않았습니다."})
                        continue
                    self.done, self.total = 0, 0
                    self.log("표시하는 중 (%d/%d): %s" % (n + 1, len(self.order), name))
                    try:
                        sc = self._scores(ex, opts["fresh"])
                        res = final.run_document(self.scorer, ex, llm, answers, opts["threshold"], opts["note"], opts["method"], self.log,
                                                 self.stop, opts["fresh"], sc, tick, rules)
                        results.append(final.public(res))
                        t = res["timing"]
                        print("  %s: 판단한 글 %d → 분류기 '예' %d%s%s · 글 뽑기 %s · 분류기 %s · LLM %s · 파일 만들기 %s · 합계 %s" % (
                            name, res["counts"]["blocks"], res["counts"]["passed"],
                            " (규칙으로 뺀 것 %d)" % res["counts"]["ruled"] if res["counts"]["ruled"] else "",
                            "" if res["counts"]["kept"] is None else " → LLM까지 %d" % res["counts"]["kept"],
                            times.fmt(t["extract"]["sec"]), times.fmt(t["classify"]["sec"]), times.fmt(t["llm"]["sec"]) if t["llm"]["ran"] else "-",
                            times.fmt(t["write"]["sec"]), times.fmt(t["total"])), flush=True)
                    except ValueError:
                        raise
                    except Exception as exc:
                        if type(exc).__name__ == "ModelMissing":
                            raise ValueError(str(exc))
                        traceback.print_exc()
                        results.append({"name": name, "error": "%s: %s" % (type(exc).__name__, str(exc)[:200])})
        except (ValueError, ollama.OllamaError) as exc:
            self.error = str(exc)
        except Exception as exc:
            traceback.print_exc()
            self.error = "%s: %s" % (type(exc).__name__, exc)
        finally:
            if llm is not None:
                ollama.unload(llm.model["name"])        # 끝나면 메모리를 돌려준다
            self.results = results
            self.stopped = self.stop.is_set()
            self.status = ""
            self.running = False

    def halt(self) -> dict:
        """멈추기. LLM에 묻고 있는 덩어리도 기다리지 않고 끊는다. 그때까지 받은 답은 보관되어 있다."""
        if self.running:
            self.status = "멈추는 중입니다…"
        self.stop.set()
        return {"ok": True}

    def open(self, body: dict) -> dict:
        """결과 폴더나 그 안의 파일을 이 PC의 기본 프로그램으로 연다."""
        folder = final.mark_dir(self.cfg).resolve()
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
        if self.running:
            raise ValueError("지금 만드는 중입니다. 끝난 뒤에 올려 주세요.")
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
                    return self._json(200, app.progress())
                if path.startswith("/out/"):
                    target = (out_root / path[len("/out/"):]).resolve()
                    if out_root in target.parents and target.is_file() and target.suffix.lower() in TYPES:
                        return self._send(200, target.read_bytes(), TYPES[target.suffix.lower()])
                self._send(404, "없는 주소입니다. 아직 만든 것이 없으면 먼저 만들어 주세요.".encode("utf-8"), TYPES[".txt"])
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
                    return self._json(200, app.start(body))
                if parts.path == "/stop":
                    return self._json(200, app.halt())
                if parts.path == "/remove":
                    return self._json(200, app.remove(str(body.get("name") or "")))
                if parts.path == "/open":
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


def serve(cfg, files: List[Path], prompts_file: Path, port: int = 8775, open_browser: bool = True, rules_file: Optional[Path] = None) -> None:
    app = App(cfg, files, prompts_file, rules_file)
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
    if not app.first["ok"]:
        print("[알림] %s (분류기까지만 만들 수는 있습니다)" % app.first["error"])
    print("결과 폴더: %s" % final.mark_dir(cfg).resolve(), flush=True)
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
