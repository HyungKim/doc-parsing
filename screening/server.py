"""정답 붙이는 화면. 이 PC 안에서만 열리는 작은 웹 서버다(주소 127.0.0.1, 밖에서는 접속할 수 없다).

    줄마다 예/아니오를 누르면 바로 labels/labels.json 에 저장된다.
    기준 문장을 화면에서 고칠 수 있다.
    '학습하고 결과 보기'를 누르면 그 정답으로 분류기를 학습시키고 비교 화면을 새로 만든다.
"""
from __future__ import annotations

import json
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlsplit

from . import learn
from .cli import Config, execute
from .items import load_docs
from .options import MAX_TITLE_WEIGHT, check_title_weight, write_option
from .sentences import parse_sentences, read_text

TYPES = {".html": "text/html; charset=utf-8", ".json": "application/json; charset=utf-8", ".txt": "text/plain; charset=utf-8",
         ".png": "image/png", ".jpg": "image/jpeg", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8"}

PAGE = r"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>정답 붙이기</title><style>
:root{--bg:#f6f6f3;--card:#fff;--ink:#1d1f23;--mute:#6b7280;--line:#dcdcd6;--acc:#1f5fbf;--yes:#17803f;--no:#6b7280;--rm-ink:#a12626;--cur:#fff6d6}
@media (prefers-color-scheme:dark){:root{--bg:#16181c;--card:#1f2228;--ink:#e7e8ea;--mute:#9aa1ad;--line:#343842;--acc:#7fb0ff;--yes:#3fae6a;--no:#8b93a1;--rm-ink:#ffb3b3;--cur:#3b3520}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.55 "Malgun Gothic","Apple SD Gothic Neo","Noto Sans KR",system-ui,sans-serif}
header.top{padding:18px 24px 6px}
h1{font-size:20px;margin:0 0 4px}
.sub{color:var(--mute);font-size:13px}
.bar{position:sticky;top:0;z-index:5;background:var(--bg);border-bottom:1px solid var(--line);padding:8px 24px;display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center;font-size:13px}
.bar label{white-space:nowrap}
a{color:var(--acc)}
select,button,textarea,input{font:inherit;color:inherit}
select,input{background:var(--card);border:1px solid var(--line);border-radius:4px;padding:2px 4px;max-width:260px}
button{background:var(--card);border:1px solid var(--line);border-radius:4px;padding:2px 10px;cursor:pointer}
button:hover{border-color:var(--acc)}
button.main{background:#1f5fbf;border-color:#1f5fbf;color:#fff;font-weight:700;padding:4px 12px}
button:disabled{opacity:.5;cursor:default}
#prog{margin-left:auto;font-variant-numeric:tabular-nums}
#prog b.y{color:var(--yes)}
main{padding:8px 24px 80px;max-width:1200px}
.legend{color:var(--mute);font-size:13px;margin:8px 0}
kbd{border:1px solid var(--line);border-bottom-width:2px;border-radius:4px;padding:0 5px;background:var(--card);font:12px ui-monospace,Consolas,monospace}
details.box,div.box{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px 14px;margin:10px 0}
details.box>summary{cursor:pointer;font-weight:700}
textarea{width:100%;min-height:260px;background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:8px;font:13px/1.6 "Malgun Gothic","Apple SD Gothic Neo",ui-monospace,monospace;margin:8px 0 6px}
pre.log{white-space:pre-wrap;word-break:break-word;background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:8px;font:12px/1.5 ui-monospace,Consolas,monospace;max-height:260px;overflow:auto;margin:8px 0}
.msg{font-size:13px;margin-left:8px}
.msg.ok{color:var(--yes)}.msg.bad{color:var(--rm-ink);font-weight:700}
#err{display:none;position:fixed;left:24px;right:24px;bottom:16px;background:#a12626;color:#fff;padding:10px 14px;border-radius:8px;z-index:9;font-weight:700}
h3.pg{font-size:14px;margin:20px 0 6px;color:var(--mute)}
.blk{background:var(--card);border:1px solid var(--line);border-radius:8px;margin:0 0 10px}
.blk>.hd{display:flex;gap:8px;align-items:center;flex-wrap:wrap;padding:6px 10px;font-size:12px;color:var(--mute)}
.blk>.hd code{font:700 12px ui-monospace,Consolas,monospace;color:var(--acc)}
.blk>.hd .wh{max-width:46%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.blk>.hd .sp{margin-left:auto}
.blk>.hd button{font-size:12px}
.st{display:inline-block;padding:0 6px;border-radius:3px;font-size:11px;font-weight:700;color:#fff;white-space:nowrap}
.st.y{background:var(--yes)}.st.n{background:var(--no)}.st.q{background:none;color:var(--mute);border:1px dashed var(--line);font-weight:400}
.tag2{display:inline-block;padding:0 5px;border-radius:3px;font-size:10px;font-weight:700;color:#fff;background:#1f5fbf}
.ln{display:flex;gap:8px;align-items:flex-start;padding:5px 10px;border-top:1px solid var(--line);border-left:4px solid transparent;cursor:default}
.ln.cur{background:var(--cur)}
.ln.y{border-left-color:var(--yes)}
.ln.n{border-left-color:var(--no)}
.ln.n .t{color:var(--mute)}
.ln .t{flex:1;white-space:pre-wrap;word-break:break-word;min-width:0}
.ln .sc{font-size:12px;color:var(--mute);font-variant-numeric:tabular-nums;white-space:nowrap;width:38px;text-align:right}
.ln .sc.hi{color:var(--yes);font-weight:700}
.ln button{white-space:nowrap;min-width:52px}
.ln.y button.by{background:var(--yes);border-color:var(--yes);color:#fff;font-weight:700}
.ln.n button.bn{background:var(--no);border-color:var(--no);color:#fff;font-weight:700}
#more{display:block;margin:14px auto;padding:6px 20px}
</style></head><body>
<header class="top"><h1>정답 붙이기</h1>
<div class="sub">특허출원 검토가 필요한 줄이면 <b>예</b>, 아니면 <b>아니오</b>를 누릅니다. 누를 때마다 바로 저장됩니다 · 정답 파일: <span id="lf"></span></div></header>
<div class="bar">
<label>문서 <select id="doc"></select></label>
<label>보기 <select id="show"><option value="all">전체</option><option value="todo">정답이 덜 붙은 덩어리만</option><option value="yes">정답 '예'가 있는 덩어리만</option></select></label>
<label>순서 <select id="sort"><option value="doc">문서 순서</option><option value="high">점수 높은 순</option><option value="mid">헷갈리는 순 (0.5에 가까운)</option></select></label>
<label id="mw">점수 모델 <select id="model"></select></label>
<span id="prog"></span>
<button class="main" id="train">학습하고 결과 보기</button>
</div>
<main>
<div class="box" id="tb" hidden><b id="tt">계산 중입니다…</b><span class="msg" id="tl"></span><pre class="log" id="tlog"></pre></div>
<details class="box" id="sd"><summary>기준 문장 보기·고치기 (정답 없이 판단할 때 쓰는 문장)</summary>
<p class="legend"><b>+</b> 로 시작하는 줄은 검토가 <b>필요한</b> 글을 나타내는 문장, <b>-</b> 로 시작하는 줄은 <b>필요 없는</b> 글을 나타내는 문장입니다. <b>#</b> 로 시작하는 줄은 메모입니다.
고친 뒤 저장하고 '학습하고 결과 보기'를 누르면 반영됩니다. 문장을 바꾸면 바뀐 문장만큼 모델을 다시 돌리므로 시간이 걸립니다(문장 판별 모델이 가장 오래 걸립니다).
비교 화면에 <b>고치기 전 → 고친 뒤</b>의 수치 변화가 나옵니다. 파일: <span id="sf"></span></p>
<textarea id="st" spellcheck="false"></textarea>
<button id="ss">기준 문장 저장</button><span class="msg" id="sm"></span></details>
<details class="box" id="od"><summary>쪽 제목 반영 (옵션) · 지금: <span id="ow"></span></summary>
<p class="legend">쪽 제목에 기준 문장으로 점수를 매겨, 그 쪽에 있는 덩어리와 줄의 점수에 섞습니다.
<b>최종 점수 = (1 − 비율) × 글 점수 + 비율 × 제목 점수</b>. 0이면 제목을 반영하지 않습니다(기본). 0.3이면 글 70%, 제목 30%입니다.
켜고 '학습하고 결과 보기'를 누르면 비교 화면에 <b>반영 전 → 후</b>의 수치 변화와 비율을 바꿨을 때의 수치가 나옵니다.
같은 쪽의 글이 함께 오르내리므로, 일정 같은 제목의 쪽에 섞인 기술 내용은 점수가 내려갑니다. 파일: <span id="of"></span></p>
<label>비율 <input id="oi" type="number" min="0" max="0.9" step="0.05" style="width:80px"></label>
<button id="os">저장</button><span class="msg" id="om"></span></details>
<p class="legend">키보드: <kbd>↑</kbd><kbd>↓</kbd> 줄 이동 · <kbd>Y</kbd> 예 · <kbd>N</kbd> 아니오 (누르면 다음 줄로 넘어갑니다) · <kbd>X</kbd> 지우기 · <kbd>A</kbd> 이 덩어리의 남은 줄 모두 아니오.
덩어리의 정답은 줄에서 따옵니다: 줄 하나라도 '예'면 덩어리도 '예', 모든 줄이 '아니오'면 덩어리도 '아니오'. 같은 글은 어느 문서에 있든 한 번만 붙이면 됩니다.
수치를 공정하게 재려면 점수가 높은 것만 골라 붙이지 말고 <b>한 쪽이나 한 문서를 통째로</b> 붙이는 것이 좋습니다.</p>
<div id="list"></div><button id="more" hidden>더 보기</button>
</main><div id="err"></div>
<script>
(function(){
var D=null,L={},rows={},blocks=[],shown=0,STEP=120,cur=null;
function $(id){return document.getElementById(id)}
function esc(s){return String(s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
function post(url,body){return fetch(url,{method:'POST',headers:{'Content-Type':'application/json','X-Label':'1'},body:JSON.stringify(body)}).then(function(r){
  return r.json().then(function(j){if(!r.ok||j.ok===false)throw new Error(j.error||('오류 '+r.status));return j})})}
function fail(e){var el=$('err');el.textContent='저장하지 못했습니다: '+e.message+' (label.bat 창이 켜져 있는지 확인하세요)';el.style.display='block';setTimeout(function(){el.style.display='none'},8000)}
function score(unit,key){var m=$('model').value;if(!D.scores||!m)return null;var v=(D.scores[unit][key]||{})[m];return v==null?null:v}
function blockState(b){var y=0,n=0;b.lines.forEach(function(l){var v=L[l.key];if(v===1)y++;else if(v===0)n++});
  if(y)return['y','정답 예'];if(n===b.lines.length)return['n','정답 아니오'];return['q',n?('덜 붙음 '+n+'/'+b.lines.length):'정답 없음']}
function progress(){var y=0,n=0,t=0,by=0,bn=0;D.docs.forEach(function(d){d.blocks.forEach(function(b){var s=blockState(b)[0];if(s==='y')by++;else if(s==='n')bn++;
  b.lines.forEach(function(l){t++;var v=L[l.key];if(v===1)y++;else if(v===0)n++})})});
  $('prog').innerHTML='줄 '+t+'개 · <b class="y">예 '+y+'</b> · 아니오 '+n+' · 남음 '+(t-y-n)+' <span class="sub">(덩어리: 예 '+by+' · 아니오 '+bn+')</span>'}
function pick(){var di=$('doc').value,show=$('show').value,sort=$('sort').value,out=[];
  D.docs.forEach(function(d,i){if(di!=='all'&&String(i)!==di)return;d.blocks.forEach(function(b){
    var s=blockState(b)[0],todo=b.lines.some(function(l){return L[l.key]==null});
    if(show==='todo'&&!todo)return;if(show==='yes'&&s!=='y')return;out.push({d:d,b:b})})});
  if(sort!=='doc'){out.forEach(function(x){var v=score('block',x.b.key);x.v=v==null?-1:(sort==='high'?v:1-Math.abs(v-0.5)*2)});
    out.sort(function(a,b){return b.v-a.v})}
  return out}
function lineHtml(l){var v=L[l.key],s=score('line',l.key);
  return '<div class="ln'+(v===1?' y':v===0?' n':'')+'" data-key="'+l.key+'"><button class="by">예</button><button class="bn">아니오</button>'+
    '<span class="t">'+esc(l.text)+'</span>'+(s==null?'':'<span class="sc'+(s>=0.5?' hi':'')+'" title="고른 모델이 매긴 점수">'+s.toFixed(2)+'</span>')+'</div>'}
function blockHtml(x,i){var b=x.b,st=blockState(b),s=score('block',b.key);
  return '<div class="blk" data-i="'+i+'"><div class="hd"><code>'+esc(b.id)+'</code><span class="wh" title="'+esc(b.title||'')+'">'+esc(x.d.name)+' · '+b.page+'쪽'+(b.title?' · '+esc(b.title):'')+'</span>'+
    (b.kind==='table'?'<span class="tag2">표</span>':'')+(b.over?'<span class="tag2" style="background:#a15c00">표 위에 얹힌 글</span>':'')+
    '<span class="st '+st[0]+'">'+st[1]+'</span>'+(s==null?'':'<span title="덩어리로 넣었을 때 고른 모델이 매긴 점수">점수 '+s.toFixed(2)+'</span>')+
    '<a href="/out/'+encodeURIComponent(x.d.report)+'#p'+b.page+'" target="_blank">추출 화면에서 보기</a><span class="sp"></span>'+
    '<button class="allno">남은 줄 모두 아니오</button><button class="clr">지우기</button></div>'+b.lines.map(lineHtml).join('')+'</div>'}
function index(el){el.querySelectorAll('.ln').forEach(function(r){(rows[r.dataset.key]=rows[r.dataset.key]||[]).push(r)})}
function render(){blocks=pick();shown=0;rows={};cur=null;$('list').innerHTML='';more();
  if(!blocks.length)$('list').innerHTML='<p class="legend">보여 줄 덩어리가 없습니다.</p>'}
function more(){var part=blocks.slice(shown,shown+STEP),box=document.createElement('div');
  box.innerHTML=part.map(function(x,k){return blockHtml(x,shown+k)}).join('');index(box);
  while(box.firstChild)$('list').appendChild(box.firstChild);shown+=part.length;
  $('more').hidden=shown>=blocks.length;$('more').textContent='더 보기 ('+(blocks.length-shown)+'개 남음)'}
function paint(key){(rows[key]||[]).forEach(function(r){var v=L[key];r.classList.toggle('y',v===1);r.classList.toggle('n',v===0);
  var blk=r.parentNode,x=blocks[+blk.dataset.i],st=blockState(x.b),tag=blk.querySelector('.st');tag.className='st '+st[0];tag.textContent=st[1]})}
function save(items){var old=items.map(function(it){return L[it.key]});
  items.forEach(function(it){if(it.label==null)delete L[it.key];else L[it.key]=it.label;paint(it.key)});progress();
  post('/label',{items:items}).catch(function(e){items.forEach(function(it,i){if(old[i]==null)delete L[it.key];else L[it.key]=old[i];paint(it.key)});progress();fail(e)})}
function lineOf(row){var x=blocks[+row.parentNode.dataset.i],key=row.dataset.key;
  for(var i=0;i<x.b.lines.length;i++)if(x.b.lines[i].key===key)return x.b.lines[i];return null}
function setRow(row,label){var l=lineOf(row);if(!l)return;if(label!=null&&L[l.key]===label)label=null;save([{key:l.key,label:label,text:l.text}])}
function setCur(row,scroll){if(cur)cur.classList.remove('cur');cur=row;if(row){row.classList.add('cur');if(scroll)row.scrollIntoView({block:'nearest'})}}
function step(n){var all=Array.prototype.slice.call(document.querySelectorAll('.ln'));if(!all.length)return;
  var i=cur?all.indexOf(cur)+n:0;if(i<0)i=0;if(i>=all.length){if(shown<blocks.length){more();all=Array.prototype.slice.call(document.querySelectorAll('.ln'))}else i=all.length-1}
  setCur(all[i],true)}
function allNo(blk){var x=blocks[+blk.dataset.i],seen={},items=[];
  x.b.lines.forEach(function(l){if(L[l.key]==null&&!seen[l.key]){seen[l.key]=1;items.push({key:l.key,label:0,text:l.text})}});if(items.length)save(items)}
function clearBlock(blk){var x=blocks[+blk.dataset.i],seen={},items=[];
  x.b.lines.forEach(function(l){if(L[l.key]!=null&&!seen[l.key]){seen[l.key]=1;items.push({key:l.key,label:null,text:l.text})}});if(items.length)save(items)}
$('list').addEventListener('click',function(e){var t=e.target,row=t.closest('.ln'),blk=t.closest('.blk');
  if(row){setCur(row,false);if(t.classList.contains('by'))setRow(row,1);else if(t.classList.contains('bn'))setRow(row,0);return}
  if(blk&&t.classList.contains('allno'))allNo(blk);else if(blk&&t.classList.contains('clr'))clearBlock(blk)});
document.addEventListener('keydown',function(e){var tag=(e.target.tagName||'').toLowerCase();
  if(tag==='textarea'||tag==='select'||tag==='input'||e.ctrlKey||e.metaKey||e.altKey)return;
  var k=e.key.toLowerCase();
  if(k==='arrowdown'||k==='j'){step(1);e.preventDefault()}
  else if(k==='arrowup'||k==='k'){step(-1);e.preventDefault()}
  else if(cur&&(k==='y'||k==='ㅛ')){var l=lineOf(cur);save([{key:l.key,label:1,text:l.text}]);step(1)}
  else if(cur&&(k==='n'||k==='ㅜ')){var m=lineOf(cur);save([{key:m.key,label:0,text:m.text}]);step(1)}
  else if(cur&&(k==='x'||k==='ㅌ')){var c=lineOf(cur);save([{key:c.key,label:null,text:c.text}])}
  else if(cur&&(k==='a'||k==='ㅁ')){allNo(cur.parentNode)}});
['doc','show','sort','model'].forEach(function(id){$(id).addEventListener('change',render)});
$('more').addEventListener('click',more);
$('ss').addEventListener('click',function(){var m=$('sm');m.className='msg';m.textContent='저장 중…';
  post('/sentences',{text:$('st').value}).then(function(j){m.className='msg ok';m.textContent='저장했습니다 (+ '+j.plus+'개, - '+j.minus+'개). \'학습하고 결과 보기\'를 누르면 반영됩니다.'})
  .catch(function(e){m.className='msg bad';m.textContent=e.message})});
function showW(w){$('ow').textContent=w>0?('켜짐, 비율 '+w+' (글 '+Math.round((1-w)*100)+'%, 제목 '+Math.round(w*100)+'%)'):'꺼짐 (제목을 반영하지 않음)'}
$('os').addEventListener('click',function(){var m=$('om');m.className='msg';m.textContent='저장 중…';
  post('/options',{title_weight:$('oi').value}).then(function(j){showW(j.title_weight);$('oi').value=j.title_weight;m.className='msg ok';m.textContent='저장했습니다. \'학습하고 결과 보기\'를 누르면 반영됩니다.'})
  .catch(function(e){m.className='msg bad';m.textContent=e.message})});
$('train').addEventListener('click',function(){var b=$('train');b.disabled=true;$('tb').hidden=false;$('tt').textContent='계산 중입니다… (처음이거나 기준 문장을 바꿨으면 몇 분 걸립니다. label.bat 창에 진행 상황이 나옵니다)';
  $('tl').innerHTML='';$('tlog').textContent='';window.scrollTo(0,0);
  post('/train',{}).then(function(j){$('tt').textContent='끝났습니다.';$('tl').innerHTML='<a href="'+j.index+'" target="_blank"><b>비교 화면 열기</b></a>';$('tlog').textContent=j.log;
    window.open(j.index,'_blank');return load(true)})
  .catch(function(e){$('tt').textContent='하지 못했습니다: '+e.message}).then(function(){b.disabled=false})});
function load(keep){return fetch('/data').then(function(r){return r.json()}).then(function(j){D=j;L=j.labels;$('lf').textContent=j.labels_file;$('sf').textContent=j.sentences_file;
  if(!keep){$('st').value=j.sentences_text;$('oi').value=j.title_weight;$('of').textContent=j.options_file;showW(j.title_weight);$('doc').innerHTML='<option value="all">전체 ('+j.docs.length+'개)</option>'+j.docs.map(function(d,i){return '<option value="'+i+'">'+esc(d.name)+'</option>'}).join('');
    if(j.docs.length===1)$('doc').value='0'}
  var ms=j.scores?j.scores.models:[],sel=$('model').value;
  $('model').innerHTML=ms.map(function(m){return '<option value="'+esc(m.key)+'">'+esc(m.label)+'</option>'}).join('');
  if(sel&&ms.some(function(m){return m.key===sel}))$('model').value=sel;
  $('mw').style.display=ms.length?'':'none';
  ['high','mid'].forEach(function(v){$('sort').querySelector('option[value='+v+']').disabled=!ms.length});
  if(!ms.length)$('sort').value='doc';
  progress();render()})}
load(false).catch(function(e){$('list').innerHTML='<p class="legend">자료를 읽지 못했습니다: '+esc(e.message)+'</p>'});
})();
</script></body></html>
"""


class App:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.busy = threading.Lock()

    # ---- 화면에 보낼 자료
    def data(self) -> dict:
        cfg = self.cfg
        docs = [{"name": d.name, "report": d.report_file,
                 "blocks": [{"id": b.id, "key": b.key, "page": b.page, "kind": b.kind, "title": b.title, "over": b.over_table,
                             "lines": [{"key": l.key, "text": l.text} for l in b.lines]} for b in d.blocks]}
                for d in load_docs(cfg.out_dir)]
        return {"docs": docs, "labels": learn.load_labels(cfg.labels), "scores": self.scores(),
                "labels_file": str(cfg.labels), "sentences_file": str(cfg.sentences), "sentences_text": read_text(cfg.sentences),
                "title_weight": cfg.title_weight, "options_file": str(cfg.options)}

    def scores(self) -> Optional[dict]:
        """지난 계산이 있으면 항목마다의 최신 점수(학습 후가 있으면 그것, 없으면 학습 전)."""
        path = Path(self.cfg.out_dir) / "screen" / "scores.json"
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

        def latest(scores: dict) -> dict:
            return {m: (v["after"] if v.get("after") is not None else v.get("before")) for m, v in (scores or {}).items()}

        out = {"models": [{"key": m["key"], "label": m["label"]} for m in raw.get("models", []) if m.get("ok")], "block": {}, "line": {}}
        for d in raw.get("docs", []):
            for b in d.get("blocks", []):
                out["block"][b["key"]] = latest(b.get("scores"))
                for l in b.get("lines", []):
                    out["line"][l["key"]] = latest(l.get("scores"))
        return out if out["models"] else None

    # ---- 저장
    def save_labels(self, body: dict) -> dict:
        items = []
        for it in body.get("items") or []:
            key, label = str(it.get("key", "")), it.get("label")
            if not key or label not in (0, 1, None):
                raise ValueError("잘못된 정답 값")
            items.append((key, label, str(it.get("text", ""))))
        return {"ok": True, "count": learn.write_labels(self.cfg.labels, items)}

    def save_sentences(self, body: dict) -> dict:
        text = str(body.get("text", "")).replace("\r\n", "\n")
        got = parse_sentences(text)                # 잘못된 내용이면 저장하지 않는다
        path = Path(self.cfg.sentences)
        if path.exists():                          # 고치기 전 파일을 하나 남겨 둔다
            path.with_suffix(".backup.txt").write_bytes(path.read_bytes())
        path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
        return {"ok": True, "plus": sum(1 for s in got if s.positive), "minus": sum(1 for s in got if not s.positive)}

    def save_options(self, body: dict) -> dict:
        w = check_title_weight(body.get("title_weight"))
        write_option(self.cfg.options, "title_weight", ("%g" % w))
        self.cfg.title_weight = w                  # 다음 '학습하고 결과 보기'부터 쓴다
        return {"ok": True, "title_weight": w, "max": MAX_TITLE_WEIGHT}

    def train(self) -> dict:
        if not self.busy.acquire(blocking=False):
            raise ValueError("이미 계산하고 있습니다. 끝날 때까지 기다려 주세요")
        lines = []

        def log(msg: str) -> None:
            lines.append(msg)
            print(msg, flush=True)
        try:
            t0 = time.time()
            res, index = execute(self.cfg, log)
            c = res.counts()
            log("정답: 줄 기준 예 %d개, 아니오 %d개 · 걸린 시간 %.0f초" % (c["line_yes"], c["line_no"], time.time() - t0))
            log("쪽 제목 반영: %s" % ("비율 %g" % res.title_weight if res.title_weight else "꺼짐"))
            for r in res.runs:
                if not r.ok:
                    log("실행하지 못한 모델: %s (%s)" % (r.spec["label"], r.error))
                elif r.spec["kind"] == "embed":
                    for unit, name in (("block", "덩어리"), ("line", "줄")):
                        log("%s · %s: %s" % (r.spec["label"], name, "학습함" if r.after[unit] is not None else r.train_note[unit]))
            return {"ok": True, "log": "\n".join(lines), "index": "/out/screen/index.html"}
        finally:
            self.busy.release()


def make_handler(app: App):
    out_root = Path(app.cfg.out_dir).resolve()

    class Handler(BaseHTTPRequestHandler):
        server_version = "docparse-label"

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
                if path == "/data":
                    return self._json(200, app.data())
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
            if not self._local() or self.headers.get("X-Label") != "1" or "application/json" not in (self.headers.get("Content-Type") or ""):
                return self._send(403, b"forbidden", TYPES[".txt"])
            path = urlsplit(self.path).path
            try:
                size = int(self.headers.get("Content-Length") or 0)
                if size > 8 * 1024 * 1024:
                    return self._json(413, {"ok": False, "error": "너무 큰 요청"})
                body = json.loads(self.rfile.read(size).decode("utf-8") or "{}")
                if path == "/label":
                    return self._json(200, app.save_labels(body))
                if path == "/sentences":
                    return self._json(200, app.save_sentences(body))
                if path == "/options":
                    return self._json(200, app.save_options(body))
                if path == "/train":
                    return self._json(200, app.train())
                self._json(404, {"ok": False, "error": "없는 주소입니다"})
            except ValueError as exc:
                self._json(400, {"ok": False, "error": str(exc)})
            except SystemExit as exc:
                self._json(400, {"ok": False, "error": str(exc)})
            except Exception as exc:
                traceback.print_exc()
                self._json(500, {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)})

    return Handler


def serve(cfg: Config, port: int = 8765, open_browser: bool = True) -> None:
    app = App(cfg)
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
    print("정답 붙이는 화면: %s" % url)
    print("이 PC 안에서만 열립니다. 이 창을 닫으면(또는 Ctrl+C) 끝납니다. 정답은 누를 때마다 저장됩니다.")
    print("정답 파일: %s" % cfg.labels, flush=True)
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
