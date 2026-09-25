"""Create a local, browser-based transcript and speech timing editor."""

import html
import json
import re
from datetime import datetime
from pathlib import Path

from .config import DATA_DIR
from .transcription_guidelines import validate_segments


def _seconds(value):
    if isinstance(value, (int, float)):
        number = float(value)
        return number / 1000 if number > 10_000_000_000 else number
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            try:
                return float(value)
            except ValueError:
                return None
    return None


def editor_data(conversation):
    """Normalize Bee utterances to editable speaker segments in seconds."""
    utterances = conversation.get("utterances") or conversation.get("transcript") or []
    if isinstance(utterances, str):
        utterances = [{"text": utterances}]
    raw = []
    for item in utterances:
        if isinstance(item, str):
            text, speaker, timestamp = item, "Speaker 1", None
        elif isinstance(item, dict):
            text = item.get("text") or item.get("content") or item.get("utterance") or ""
            speaker = str(item.get("speaker") or item.get("role") or "Speaker 1")
            timestamp = next((_seconds(item.get(k)) for k in ("timestamp", "start_time", "startTime", "ts", "time", "t") if item.get(k) is not None), None)
        else:
            continue
        if text.strip():
            raw.append({"text": str(text).strip(), "speaker": speaker, "stamp": timestamp})
    stamps = [u["stamp"] for u in raw if u["stamp"] is not None]
    origin = min(stamps) if stamps else 0
    cursor = 0.0
    segments = []
    for i, utterance in enumerate(raw):
        start = max(0, utterance["stamp"] - origin) if utterance["stamp"] is not None else cursor
        duration = max(1.2, len(utterance["text"].split()) / 2.7)
        # Use the next timestamp to estimate this utterance's end when possible.
        next_stamp = next((u["stamp"] for u in raw[i + 1:] if u["stamp"] is not None), None)
        end = max(start + 0.5, min(start + duration, next_stamp - origin if next_stamp is not None else start + duration))
        segments.append({"id": i, "speaker": utterance["speaker"], "text": utterance["text"], "start": round(start, 3), "end": round(end, 3)})
        cursor = end + 0.35
    length = max([s["end"] for s in segments] + [1.0])
    return {
        "title": conversation.get("title") or conversation.get("name") or "Bee conversation",
        "id": str(conversation.get("id") or conversation.get("conversation_id") or "conversation"),
        "segments": segments,
        "duration": round(length + 1, 3),
        "guidelines": validate_segments(segments),
    }


# _VOICE_PAGE is the single canonical editor design. The checked-in slack.html
# at the repo root is the hand-maintained benchmark copy of this exact template:
# any improvement made to slack.html must be ported here (keeping the
# __TITLE__/__SUBTITLE__/__DATA__ placeholders), so every generated page --
# single-conversation and aggregate -- ships the same design. The page adapts
# itself at load: with one scenario the picker hides and the heading takes the
# conversation's title.
_VOICE_PAGE = r'''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
:root{color-scheme:light;--bg:#fff;--panel:#fff;--line:#d9dee5;--text:#20252b;--muted:#68717d;--blue:#2878bd;--green:#21865e;--amber:#d98a00}
*{box-sizing:border-box}
body{margin:0;background:#fff;color:var(--text);font:15px/1.45 system-ui,sans-serif}
main{max-width:1100px;margin:auto;padding:24px 16px}
h1{font-size:22px;margin:0 0 4px;line-height:1.3}
.muted{color:var(--muted)}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px;margin-top:16px}
.toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.toolbar select,.toolbar input[type=range]{max-width:100%}
select,input[type=text],input[type=number]{font:inherit}
button{background:#f3f5f7;color:var(--text);border:1px solid #cbd2da;border-radius:8px;padding:9px 13px;cursor:pointer;min-height:40px}
button:hover{border-color:var(--blue)}
.pickrow{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:12px}
.pickrow select{background:#fff;color:var(--text);border:1px solid var(--line);border-radius:8px;padding:10px;max-width:100%;flex:1;min-width:200px}
.summary{font-size:13px;color:var(--muted);margin-top:8px}
.tracks{overflow-x:auto;-webkit-overflow-scrolling:touch}
.ruler{position:relative;height:26px;margin-left:96px;border-bottom:1px solid var(--line);color:var(--muted);font-size:11px;min-width:0}
.tick{position:absolute;bottom:2px;transform:translateX(-50%);white-space:nowrap}
.lane{display:flex;align-items:stretch;border-bottom:1px solid #e5e8ec;padding:6px 0;gap:0}
.speaker{width:96px;flex:none;color:var(--blue);font-weight:600;padding:18px 8px 18px 0;font-size:13px;word-break:break-word}
.timeline{position:relative;height:64px;flex:1;min-width:0;background:repeating-linear-gradient(90deg,transparent 0,transparent calc(10% - 1px),#e5e8ec calc(10% - 1px),#e5e8ec 10%);border-radius:8px;touch-action:pan-y}
.clip{position:absolute;top:10px;height:44px;border-radius:8px;background:#23507b;border:1px solid #509be0;cursor:grab;overflow:hidden;min-width:10px;touch-action:none;user-select:none;-webkit-user-select:none}
.clip .wave{position:absolute;inset:0;display:flex;align-items:center;justify-content:space-around;gap:2px;padding:4px 6px;opacity:.28;pointer-events:none}
.bar{width:2px;background:#d4e9ff;border-radius:2px;flex:none}
.clip .ctext{position:absolute;inset:0;display:flex;align-items:center;padding:0 10px;font-size:12px;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;pointer-events:none;color:#fff}
.handle{position:absolute;top:0;bottom:0;width:14px;cursor:ew-resize;z-index:3;touch-action:none}
.handle.left{left:0}.handle.right{right:0}
.handle::after{content:"";position:absolute;top:8px;bottom:8px;left:5px;width:3px;border-radius:2px;background:rgba(255,255,255,.55)}
.playhead{position:absolute;top:0;bottom:0;width:2px;background:var(--amber);z-index:4;pointer-events:none}
.list{display:grid;gap:10px}
.item{display:grid;grid-template-columns:110px 1fr auto;gap:10px;align-items:center;border:1px solid var(--line);border-radius:10px;padding:10px;background:#fff}
.item.segment-focus{outline:2px solid var(--blue);outline-offset:2px}
.item .who{background:#fff;border:1px solid var(--line);border-radius:7px;color:var(--text);padding:9px;width:100%}
.item .txt{background:#fff;border:1px solid var(--line);border-radius:7px;color:var(--text);padding:9px;width:100%}
.times{display:flex;gap:6px;align-items:center;flex-wrap:wrap}
.times input{width:74px;background:#fff;color:var(--text);border:1px solid var(--line);padding:8px;border-radius:6px}
.segplay{flex:none}
.footer{font-size:12px;color:var(--muted);margin-top:14px}
.count{font-size:12px;color:var(--muted)}
.guide{font-size:13px;color:var(--muted);line-height:1.55}
.guide code{background:#f3f5f7;border:1px solid var(--line);border-radius:4px;padding:1px 4px;color:var(--text)}
.valid{color:var(--green);font-weight:600}.invalid{color:#b42318;font-weight:600}
.issues{font-size:12px;color:#b42318;grid-column:2 / -1;margin-top:-4px}
@media(max-width:700px){
  main{padding:16px 10px}
  h1{font-size:19px}
  .panel{padding:12px;border-radius:12px}
  .ruler{margin-left:72px}
  .speaker{width:72px;font-size:12px;padding:16px 6px 16px 0}
  .timeline{height:60px}
  .clip{top:8px;height:44px}
  .clip .ctext{font-size:11px;padding:0 8px}
  .item{grid-template-columns:1fr;gap:8px}
  .times input{width:70px;flex:1}
  button{min-height:44px}
}
</style>
<body><main>
<h1 id="pageTitle">Bee voice transcript editor</h1>
<div class="muted">__SUBTITLE__</div>
<div class="pickrow" id="pickrow">
  <label class="muted" for="scenarioPick">Scenario</label>
  <select id="scenarioPick"></select>
  <span class="count" id="segCount"></span>
</div>
<div class="summary" id="scenarioSummary"></div>
<section class="panel">
  <div class="toolbar">
    <button id="play">▶ Play all</button>
    <button id="stop">■ Stop</button>
    <div id="speakerVoices" class="toolbar" aria-label="Voice for each speaker"></div>
    <label class="muted">Rate <input id="rate" type="range" min="0.65" max="1.4" step="0.05" value="1"></label>
    <span class="muted" id="status">Pick a scenario, then tap a segment to hear it.</span>
  </div>
  <div class="tracks" style="margin-top:14px"><div id="ruler" class="ruler"></div><div id="lanes"></div></div>
  <div class="footer">Bee's original recording is not included in this transcript response. Playback uses your browser's speech synthesis; segment lengths are editable estimates. Edits are saved per-scenario in this browser's local storage.</div>
</section>
<section class="panel"><h2 style="font-size:16px;margin:0 0 10px">Transcript and timing</h2><div id="list" class="list"></div></section>
<section class="panel guide">
  <h2 style="font-size:16px;margin:0 0 8px">Annotation guideline</h2>
  <div id="guidelineStatus" aria-live="polite"></div>
  <p>Listen first, then transcribe every audible event. Put fillers in square brackets, such as <code>[uh]</code>; non-verbal sounds and pauses in angle brackets, such as <code>&lt;cough&gt;</code> and <code>&lt;pause&gt;</code>; uncertain guesses in <code>((double parentheses))</code>; and foreign-language speech in <code>{curly braces}</code>.</p>
  <p>Use consistent <code>Speaker 1</code> labels, preserve false starts with a trailing hyphen, and use only the supported punctuation. Reject only when overlapping speakers or persistent noise makes the primary speech unintelligible.</p>
</section>
</main>
<script>
const SCENARIOS=__DATA__;
const pick=document.getElementById('scenarioPick');
SCENARIOS.forEach((s,i)=>{const o=document.createElement('option');o.value=s.id;o.textContent=(i+1)+'. '+s.title;pick.append(o);});
let original=SCENARIOS[0], data=null, key='', duration=1, playhead=0, playing=false, timer=null;
let lastClipPointer=null, pendingSegmentFocus=null;
const colors=['#6bb7ff','#53d6a0','#d59cff','#ff927d','#f1bc55','#7dd3fc','#f0abfc'];
// The same page serves the multi-scenario aggregate and single-conversation
// views: one scenario hides the picker and takes the conversation's title.
const multi=SCENARIOS.length>1;
if(!multi)document.getElementById('pickrow').style.display='none';
document.getElementById('pageTitle').textContent=multi?'Bee voice transcript editor':(SCENARIOS[0].title||'Bee voice transcript editor');
function focusSegment(s){
  const row=[...document.querySelectorAll('.item')].find(item=>item.dataset.segmentId===String(s.id));
  if(!row)return;
  row.scrollIntoView({behavior:'instant',block:'center'});
  row.classList.add('segment-focus');setTimeout(()=>row.classList.remove('segment-focus'),1400);
  const transcript=row.querySelector('.txt');
  if(transcript){transcript.focus({preventScroll:true});transcript.setSelectionRange(0,transcript.value.length);}
}
function loadScenario(idx){
  stop();
  original=SCENARIOS[idx]; key='beeplex-voice-'+original.id;
  let saved=null; try{saved=JSON.parse(localStorage.getItem(key)||'null');}catch(e){}
  data=(saved && saved.id===original.id && Array.isArray(saved.segments))?saved:JSON.parse(JSON.stringify(original));
  data.voiceBySpeaker=data.voiceBySpeaker||{};
  playhead=0;
  const sumEl=document.getElementById('scenarioSummary');
  sumEl.textContent=original.summary||'';
  sumEl.style.display=original.summary?'':'none';
  document.getElementById('segCount').textContent=data.segments.length+' segments · '+data.duration.toFixed(1)+'s';
  render();
}

const allowedFillers=new Set(['uh-huh','mm-hmm','psst','pfft','uhm','ugh','hmm','yeah','yep','yup','ooh','huh','shh','uh','oh','aw','eh','ah']);
const allowedTags=new Set(['laugh','cry','gag','throatclear','gasp','cough','swallow','noise','inaudible','pause']);
function checkText(text){
  const issues=[];
  for(const m of text.matchAll(/<([^<>]*)>/g)) if(!allowedTags.has(m[1].trim().toLowerCase())) issues.push('unknown tag '+m[0]);
  for(const m of text.matchAll(/\[([^\[\]]*)\]/g)) if(!allowedFillers.has(m[1].trim().toLowerCase())) issues.push('unsupported filler '+m[0]);
  if(/(?<![\w\[])\b(uh-huh|mm-hmm|psst|pfft|uhm|ugh|hmm|yeah|yep|yup|ooh|huh|shh|uh|oh|aw|eh|ah)\b(?!\])/i.test(text)) issues.push('put fillers in [square brackets]');
  const plain=text.replace(/<[^<>]*>|\[[^\[\]]*\]|\(\([^()]*\)\)|\{[^{}]*\}/g,'').replace(/!\?/g,'');
  const bad=[...new Set([...plain].filter(ch=>!/[\p{L}\p{N}\s.?!,\"'\-]/u.test(ch)))];
  if(bad.length) issues.push('unsupported punctuation: '+bad.join(' '));
  return issues;
}
function updateGuidelineStatus(){
  const problems=data.segments.flatMap(s=>checkText(s.text).map(issue=>'#'+(Number(s.id)+1)+' '+issue));
  const el=document.getElementById('guidelineStatus');
  el.className=problems.length?'invalid':'valid';
  el.textContent=problems.length?(problems.length+' item(s) need review: '+problems.slice(0,3).join('; ')+(problems.length>3?'…':'')):'No automatic guideline issues detected. Confirm every audible event by listening.';
}
pick.onchange=()=>loadScenario(pick.selectedIndex);
let availableVoices=[];
function loadVoices(){try{availableVoices=speechSynthesis.getVoices();}catch(e){availableVoices=[];}renderVoiceChoices();}
if('speechSynthesis' in window){loadVoices();speechSynthesis.onvoiceschanged=loadVoices;}
function renderVoiceChoices(){
  const box=document.getElementById('speakerVoices'); if(!box||!data)return;
  // Rebuilding the selects on every render would collapse an open dropdown
  // mid-playback (render runs per segment); rebuild only when speakers change.
  const speakers=[...new Set(data.segments.map(s=>s.speaker))];
  const sig=speakers.join('');
  if(box.dataset.sig===sig){
    [...box.querySelectorAll('select')].forEach((sel,i)=>{sel.value=data.voiceBySpeaker?.[speakers[i]]||'';});
    return;
  }
  box.dataset.sig=sig;
  box.innerHTML='';
  speakers.forEach(speaker=>{
    const label=document.createElement('label'); label.className='muted'; label.textContent=speaker+' ';
    const select=document.createElement('select'); select.setAttribute('aria-label',speaker+' voice');
    const automatic=document.createElement('option'); automatic.value=''; automatic.textContent='Default voice'; select.append(automatic);
    availableVoices.forEach(v=>{const option=document.createElement('option');option.value=v.voiceURI;option.textContent=v.name+' ('+v.lang+')';select.append(option);});
    select.value=data.voiceBySpeaker?.[speaker]||'';
    select.onchange=()=>{data.voiceBySpeaker=data.voiceBySpeaker||{};data.voiceBySpeaker[speaker]=select.value;try{localStorage.setItem(key,JSON.stringify(data));}catch(e){}};
    label.append(select);box.append(label);
  });
}
function voiceFor(speaker){return availableVoices.find(v=>v.voiceURI===data.voiceBySpeaker?.[speaker])||null;}
function save(){try{localStorage.setItem(key,JSON.stringify(data));}catch(e){} render();}
function render(){
  // Keep the timeline anchored to the scenario's original duration.  Expanding
  // it to fit a dragged clip makes the clip appear to barely move.
  duration=Math.max(original.duration,1);
  document.getElementById('segCount').textContent=data.segments.length+' segments · '+duration.toFixed(1)+'s';
  const ruler=document.getElementById('ruler'); ruler.innerHTML='';
  for(let i=0;i<=10;i++){const t=document.createElement('span');t.className='tick';t.style.left=(i*10)+'%';t.textContent=(duration*i/10).toFixed(1)+'s';ruler.append(t);}
  const lanes=document.getElementById('lanes'); lanes.innerHTML='';
  let speakers=[...new Set(data.segments.map(s=>s.speaker))]; if(!speakers.length)speakers=['Speaker 1'];
  speakers.forEach((speaker,si)=>{
    const row=document.createElement('div'); row.className='lane';
    const name=document.createElement('div'); name.className='speaker'; name.textContent=speaker; name.style.color=colors[si%colors.length];
    const tl=document.createElement('div'); tl.className='timeline'; tl.dataset.lane=speaker;
    data.segments.filter(s=>s.speaker===speaker).forEach(s=>{
      const clip=document.createElement('div'); clip.className='clip';
      clip.style.left=(s.start/duration*100)+'%';
      clip.style.width=Math.max(0.8,(s.end-s.start)/duration*100)+'%';
      clip.style.background=colors[si%colors.length]+'33';
      clip.style.borderColor=colors[si%colors.length];
      clip.title=s.speaker+': '+s.text;
      const wave=document.createElement('div'); wave.className='wave';
      for(let n=0;n<24;n++){const b=document.createElement('i');b.className='bar';const ch=s.text.length?s.text.charCodeAt(n%s.text.length):65;b.style.height=(20+((ch*13+n*7)%60))+'%';wave.append(b);}
      const ct=document.createElement('div'); ct.className='ctext'; ct.textContent=s.text;
      clip.append(wave,ct);
      ['left','right'].forEach(side=>{const h=document.createElement('i');h.className='handle '+side;clip.append(h);h.addEventListener('pointerdown',e=>drag(e,s,side));});
      clip.addEventListener('pointerdown',e=>{
        if(e.target.classList.contains('handle'))return;
        const now=Date.now();
        if(lastClipPointer&&lastClipPointer.id===String(s.id)&&now-lastClipPointer.time<500){pendingSegmentFocus=String(s.id);lastClipPointer=null;}
        else lastClipPointer={id:String(s.id),time:now};
        drag(e,s,'move');
      });
      tl.append(clip);
    });
    const line=document.createElement('div'); line.className='playhead'; line.style.left=(playhead/duration*100)+'%'; tl.append(line);
    tl.addEventListener('click',e=>{if(e.target===tl){const r=tl.getBoundingClientRect();playhead=Math.max(0,Math.min(duration,((e.clientX-r.left)/r.width)*duration));render();}});
    row.append(name,tl); lanes.append(row);
  });
  const list=document.getElementById('list'); list.innerHTML='';
  data.segments.forEach((s,i)=>{
    const row=document.createElement('div'); row.className='item'; row.dataset.segmentId=s.id;
    const transcript=document.createElement('input'); transcript.className='txt'; transcript.value=s.text; transcript.setAttribute('aria-label','Transcript '+(i+1));
    transcript.onchange=()=>{s.text=transcript.value;save();};
    const speakerInput=document.createElement('input'); speakerInput.className='who'; speakerInput.type='text'; speakerInput.value=s.speaker; speakerInput.setAttribute('aria-label','Speaker '+(i+1));
    speakerInput.onchange=()=>{s.speaker=speakerInput.value.trim()||'Speaker 1';save();};
    const times=document.createElement('div'); times.className='times';
    [['start','Start'],['end','End']].forEach(([k])=>{const input=document.createElement('input');input.type='number';input.min=0;input.step='0.01';input.value=(+s[k]).toFixed(2);input.title=k+' seconds';input.setAttribute('aria-label',k+' '+(i+1));input.onchange=()=>{s[k]=Math.max(0,Number(input.value)||0);if(s.end<=s.start)s.end=+(s.start+0.1).toFixed(2);save();};times.append(input);});
    const btn=document.createElement('button'); btn.className='segplay'; btn.textContent='▶'; btn.title='Speak segment '+(i+1); btn.onclick=()=>speak(s);
    const idx=document.createElement('div'); idx.className='muted'; idx.style.fontSize='12px'; idx.textContent='#'+(i+1);
    const issues=document.createElement('div'); issues.className='issues';
    const found=checkText(s.text); issues.textContent=found.join(' · ');
    row.append(idx,transcript,speakerInput,times,btn,issues); list.append(row);
  });
  renderVoiceChoices();
  updateGuidelineStatus();
}
function drag(e,s,mode){
  e.preventDefault(); e.stopPropagation();
  const target=e.currentTarget, startX=e.clientX, startY=e.clientY, oldA=s.start, oldB=s.end;
  const tl=target.closest('.timeline'), clip=target.closest('.clip');
  if(!tl||!clip) return;
  const scale=duration/tl.clientWidth; let moved=false; clip._moved=false;
  try{target.setPointerCapture(e.pointerId);}catch(err){}
  function move(ev){
    if(Math.abs(ev.clientX-startX)+Math.abs(ev.clientY-startY)>4) moved=true;
    const delta=(ev.clientX-startX)*scale;
    if(mode==='left') s.start=Math.max(0,Math.min(oldA+delta,oldB-0.1));
    else if(mode==='right') s.end=Math.min(duration,Math.max(oldA+0.1,oldB+delta));
    else { const len=oldB-oldA; const maxStart=Math.max(0,duration-len); let ns=Math.max(0,Math.min(maxStart,oldA+delta)); s.start=+ns.toFixed(3); s.end=+(ns+len).toFixed(3); }
    clip.style.left=(s.start/duration*100)+'%';
    clip.style.width=Math.max(0.8,(s.end-s.start)/duration*100)+'%';
  }
  function up(){
    target.removeEventListener('pointermove',move); target.removeEventListener('pointerup',up); target.removeEventListener('pointercancel',up);
    clip._moved=moved;
    if(moved) save(); else render();
    if(pendingSegmentFocus===String(s.id)){pendingSegmentFocus=null;setTimeout(()=>focusSegment(s),30);}
    setTimeout(()=>{clip._moved=false;},300);
  }
  target.addEventListener('pointermove',move); target.addEventListener('pointerup',up); target.addEventListener('pointercancel',up);
}
function speak(s){
  try{speechSynthesis.cancel();}catch(e){}
  const u=new SpeechSynthesisUtterance(s.text);
  u.voice=voiceFor(s.speaker);
  u.rate=Number(document.getElementById('rate').value)||1;
  document.getElementById('status').textContent=s.speaker+': '+s.text;
  try{speechSynthesis.speak(u);}catch(e){}
}
function stop(){playing=false;clearTimeout(timer);try{speechSynthesis.cancel();}catch(e){}document.getElementById('play').textContent='▶ Play all';}
function playNext(){
  if(!playing) return;
  const s=data.segments.filter(x=>x.start>=playhead-0.02).sort((a,b)=>a.start-b.start)[0];
  if(!s){stop();return;}
  playhead=s.start; render();
  const u=new SpeechSynthesisUtterance(s.text);
  u.voice=voiceFor(s.speaker);
  u.rate=Number(document.getElementById('rate').value)||1;
  document.getElementById('status').textContent=s.speaker+': '+s.text;
  u.onend=()=>{playhead=s.end;render();timer=setTimeout(playNext,250);};
  u.onerror=()=>{playhead=s.end;timer=setTimeout(playNext,250);};
  try{speechSynthesis.speak(u);}catch(e){playhead=s.end;timer=setTimeout(playNext,250);}
}
document.getElementById('play').onclick=()=>{stop();playing=true;document.getElementById('play').textContent='❚❚ Playing';playhead=0;playNext();};
document.getElementById('stop').onclick=stop;
loadScenario(0);
</script></body></html>
'''


def create_editor(conversation):
    """Write a self-contained editor page into BeePlex's data folder."""
    data = editor_data(conversation)
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", data["id"]).strip("-") or "conversation"
    folder = DATA_DIR / "voice"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{slug}.html"
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    page = (
        _VOICE_PAGE.replace("__TITLE__", "Bee voice transcript editor")
        .replace(
            "__SUBTITLE__",
            "Bee transcript \u00b7 browser generated voice \u00b7 drag clips to move, drag edges to trim",
        )
        .replace("__DATA__", "[" + payload + "]")
    )
    path.write_text(page, encoding="utf-8")
    return {"path": str(path), "segments": len(data["segments"])}


def create_aggregate(conversations, limit=50):
    """Write the multi-scenario editor page (slack.html) into the data folder's voice/.

    Covers every recording available in the current mode: all recent live
    conversations via the Bee CLI, or all demo conversations in demo mode.
    The scenario picker page shares the per-conversation localStorage keys
    (``beeplex-voice-<id>``) with the single-conversation pages, so timing
    edits made in one are visible in the other.
    """
    from .config import DEMO

    scenarios = []
    for conv in conversations[:limit]:
        data = editor_data(conv)
        data["summary"] = conv.get("summary") or conv.get("Summary_Notes") or ""
        scenarios.append(data)
    folder = DATA_DIR / "voice"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "slack.html"
    payload = json.dumps(scenarios, ensure_ascii=False).replace("</", "<\\/")
    if DEMO:
        title = "Bee voice transcript editor \u2014 all demo scenarios"
        subtitle = "All beeplex demo scenarios \u00b7 browser generated voice \u00b7 drag clips to move, drag edges to trim"
    else:
        title = "Bee voice transcript editor \u2014 all recordings"
        subtitle = "All recent Bee recordings \u00b7 browser generated voice \u00b7 drag clips to move, drag edges to trim"
    page = (
        _VOICE_PAGE.replace("__TITLE__", title)
        .replace("__SUBTITLE__", subtitle)
        .replace("__DATA__", payload)
    )
    path.write_text(page, encoding="utf-8")
    return {"path": str(path), "scenarios": len(scenarios)}
