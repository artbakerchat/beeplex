"""Create a local, browser-based transcript and speech timing editor."""

import html
import json
import re
from datetime import datetime
from pathlib import Path

from .config import DATA_DIR


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
    return {"title": conversation.get("title") or conversation.get("name") or "Bee conversation", "id": str(conversation.get("id") or conversation.get("conversation_id") or "conversation"), "segments": segments, "duration": round(length + 1, 3)}


def create_editor(conversation):
    """Write a self-contained editor page into BeePlex's data folder."""
    data = editor_data(conversation)
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", data["id"]).strip("-") or "conversation"
    folder = DATA_DIR / "voice"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{slug}.html"
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    page = _PAGE.replace("__DATA__", payload)
    path.write_text(page, encoding="utf-8")
    return {"path": str(path), "segments": len(data["segments"])}


_PAGE = r'''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bee voice transcript editor</title>
<style>
:root{color-scheme:light;--bg:#fff;--panel:#fff;--line:#d9dee5;--text:#20252b;--muted:#68717d;--blue:#2878bd;--green:#21865e;--amber:#d98a00}*{box-sizing:border-box}body{margin:0;background:#fff;color:var(--text);font:15px/1.45 system-ui,sans-serif}main{max-width:1100px;margin:auto;padding:24px 16px}h1{font-size:22px;margin:0 0 4px;line-height:1.3}.muted{color:var(--muted)}.panel{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px;margin-top:16px}.toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap}button{background:#f3f5f7;color:var(--text);border:1px solid #cbd2da;border-radius:8px;padding:9px 13px;cursor:pointer;min-height:40px}button:hover{border-color:var(--blue)}.tracks{overflow:auto}.ruler{position:relative;height:27px;margin-left:110px;border-bottom:1px solid var(--line);color:var(--muted);font-size:11px}.tick{position:absolute;bottom:2px;transform:translateX(-50%)}.lane{display:flex;align-items:stretch;border-bottom:1px solid #e5e8ec;padding:6px 0}.speaker{width:110px;flex:none;color:var(--blue);font-weight:600;padding-right:10px}.timeline{position:relative;min-width:0;height:64px;flex:1;background:repeating-linear-gradient(90deg,transparent 0,transparent calc(10% - 1px),#e5e8ec calc(10% - 1px),#e5e8ec 10%);border-radius:8px;touch-action:pan-y}.clip{position:absolute;top:10px;height:44px;border-radius:8px;background:#d8ebfa;border:1px solid #509be0;cursor:grab;overflow:hidden;min-width:10px;touch-action:none;user-select:none}.clip .wave{height:100%;display:flex;align-items:center;justify-content:space-around;gap:2px;padding:4px 8px;opacity:.65;pointer-events:none}.bar{width:2px;background:#2878bd;border-radius:2px}.clip .label{position:absolute;inset:0;display:flex;align-items:center;padding:0 8px;font-size:11px;color:#20252b;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;pointer-events:none}.handle{position:absolute;top:0;bottom:0;width:9px;cursor:ew-resize;z-index:2}.handle.left{left:0}.handle.right{right:0}.playhead{position:absolute;top:0;bottom:0;width:2px;background:var(--amber);z-index:4;pointer-events:none}.list{display:grid;gap:10px}.item{display:grid;grid-template-columns:115px 1fr 90px;gap:10px;align-items:center;border-bottom:1px solid var(--line);padding:9px 0}.item input[type=text]{width:100%;background:#fff;border:1px solid var(--line);border-radius:7px;color:var(--text);padding:9px}.times{display:flex;gap:5px}.times input{width:76px;background:#fff;color:var(--text);border:1px solid var(--line);padding:7px;border-radius:6px}.footer{font-size:12px;color:var(--muted);margin-top:14px}@media(max-width:700px){main{padding:16px 10px}h1{font-size:19px}.panel{padding:12px;border-radius:12px}.item{grid-template-columns:1fr}.speaker{width:72px;font-size:12px}.ruler{margin-left:72px}.timeline{height:60px}.clip{top:8px;height:44px}.clip .label{font-size:10px}button{min-height:44px}}
</style><body><main><h1 id="title"></h1><div class="muted">Bee transcript · browser generated voice · drag clips to move, drag edges to trim</div>
<section class="panel"><div class="toolbar"><button id="play">▶ Play all</button><button id="stop">■ Stop</button><div id="speakerVoices" class="toolbar" aria-label="Voice for each speaker"></div><label class="muted">Rate <input id="rate" type="range" min="0.65" max="1.4" step="0.05" value="1"></label><span class="muted" id="status">Choose a voice for each speaker, then play or tap a segment.</span></div><div class="tracks" style="margin-top:20px"><div id="ruler" class="ruler"></div><div id="lanes"></div></div><div class="footer">Bee’s original recording is not included in this transcript response. Playback uses your browser’s speech synthesis; segment lengths are editable estimates, positioned from Bee timestamps when present.</div></section>
<section class="panel"><h2 style="font-size:17px;margin:0 0 12px">Transcript and timing</h2><div id="list" class="list"></div></section></main>
<script>
const original=__DATA__, key='beeplex-voice-'+original.id;let data=JSON.parse(localStorage.getItem(key)||'null')||original;let duration=Math.max(original.duration,...data.segments.map(s=>s.end),1);let playhead=0,playing=false,timer=null,availableVoices=[];const colors=['#6bb7ff','#53d6a0','#d59cff','#ff927d','#f1bc55'];
document.getElementById('title').textContent=data.title;function voiceFor(speaker){return availableVoices.find(v=>v.voiceURI===data.voiceBySpeaker?.[speaker])||null}function renderVoiceChoices(){availableVoices=speechSynthesis.getVoices();const box=document.getElementById('speakerVoices');box.innerHTML='';[...new Set(data.segments.map(s=>s.speaker))].forEach(speaker=>{const label=document.createElement('label');label.className='muted';label.textContent=speaker;const select=document.createElement('select');select.setAttribute('aria-label','Voice for '+speaker);const fallback=document.createElement('option');fallback.value='';fallback.textContent='Default voice';select.append(fallback);availableVoices.forEach(v=>{const option=document.createElement('option');option.value=v.voiceURI;option.textContent=v.name+' ('+v.lang+')';select.append(option)});select.value=data.voiceBySpeaker?.[speaker]||'';select.onchange=()=>{data.voiceBySpeaker=data.voiceBySpeaker||{};data.voiceBySpeaker[speaker]=select.value;try{localStorage.setItem(key,JSON.stringify(data))}catch(e){}};label.append(select);box.append(label)})}speechSynthesis.onvoiceschanged=renderVoiceChoices;
function save(){localStorage.setItem(key,JSON.stringify(data));render()}
function render(){renderVoiceChoices();duration=Math.max(original.duration,...data.segments.map(s=>s.end),1);let ruler=document.getElementById('ruler');ruler.innerHTML='';for(let i=0;i<=10;i++){let t=document.createElement('span');t.className='tick';t.style.left=i*10+'%';t.textContent=(duration*i/10).toFixed(1)+'s';ruler.append(t)}let lanes=document.getElementById('lanes');lanes.innerHTML='';let speakers=[...new Set(data.segments.map(s=>s.speaker))];if(!speakers.length)speakers=['Speaker 1'];speakers.forEach((speaker,si)=>{let row=document.createElement('div');row.className='lane';let name=document.createElement('div');name.className='speaker';name.textContent=speaker;name.style.color=colors[si%colors.length];let tl=document.createElement('div');tl.className='timeline';tl.dataset.lane=speaker;data.segments.filter(s=>s.speaker===speaker).forEach(s=>{let clip=document.createElement('div');clip.className='clip';clip.style.background=colors[si%colors.length]+'33';clip.style.borderColor=colors[si%colors.length];clip.style.left=(s.start/duration*100)+'%';clip.style.width=Math.max(1,(s.end-s.start)/duration*100)+'%';clip.title=s.text;let wave=document.createElement('div');wave.className='wave';for(let n=0;n<30;n++){let b=document.createElement('i');b.className='bar';b.style.height=(18+((s.text.charCodeAt(n%s.text.length)*13+n*7)%70))+'%';wave.append(b)}clip.append(wave);let label=document.createElement('div');label.className='label';label.textContent=s.text;clip.append(label);['left','right'].forEach(side=>{let h=document.createElement('i');h.className='handle '+side;clip.append(h);h.onpointerdown=e=>drag(e,s,side)});clip.onpointerdown=e=>{if(e.target.classList.contains('handle'))return;drag(e,s,'move')};clip.ondblclick=()=>speak(s);tl.append(clip)});let line=document.createElement('div');line.className='playhead';line.style.left=(playhead/duration*100)+'%';tl.append(line);tl.onclick=e=>{if(e.target===tl){playhead=((e.clientX-tl.getBoundingClientRect().left)/tl.clientWidth)*duration;render()}};row.append(name,tl);lanes.append(row)});let list=document.getElementById('list');list.innerHTML='';data.segments.forEach((s,i)=>{let row=document.createElement('div');row.className='item';let who=document.createElement('input');who.value=s.speaker;who.setAttribute('aria-label','Speaker');who.onchange=()=>{s.speaker=who.value||'Speaker 1';save()};let text=document.createElement('input');text.type='text';text.value=s.text;text.setAttribute('aria-label','Transcript');text.onchange=()=>{s.text=text.value;save()};let times=document.createElement('div');times.className='times';['start','end'].forEach(k=>{let input=document.createElement('input');input.type='number';input.min=0;input.step='.01';input.value=s[k].toFixed(2);input.title=k+' seconds';input.onchange=()=>{s[k]=Math.max(0,Number(input.value)||0);if(s.end<=s.start)s.end=s.start+.1;save()};times.append(input)});let btn=document.createElement('button');btn.textContent='▶';btn.title='Speak segment';btn.onclick=()=>speak(s);row.append(who,text,times,btn);list.append(row)})}
function drag(e,s,mode){e.preventDefault();e.stopPropagation();let target=e.currentTarget,startX=e.clientX,oldA=s.start,oldB=s.end,tl=target.closest('.timeline'),clip=target.closest('.clip'),scale=duration/tl.clientWidth;target.setPointerCapture(e.pointerId);function move(ev){let delta=(ev.clientX-startX)*scale;if(mode==='left')s.start=Math.max(0,Math.min(oldA+delta,oldB-.1));else if(mode==='right')s.end=Math.max(oldA+.1,oldB+delta);else{s.start=Math.max(0,oldA+delta);s.end=Math.max(s.start+.1,oldB+delta)}clip.style.left=(s.start/duration*100)+'%';clip.style.width=Math.max(1,(s.end-s.start)/duration*100)+'%'}function up(){target.removeEventListener('pointermove',move);target.removeEventListener('pointerup',up);save()}target.addEventListener('pointermove',move);target.addEventListener('pointerup',up)}
function speak(s){speechSynthesis.cancel();let u=new SpeechSynthesisUtterance(s.text);u.voice=voiceFor(s.speaker);u.rate=Number(document.getElementById('rate').value);speechSynthesis.speak(u);document.getElementById('status').textContent=s.speaker+': '+s.text}
function stop(){playing=false;clearTimeout(timer);speechSynthesis.cancel();document.getElementById('play').textContent='▶ Play all'}function playNext(){if(!playing)return;let s=data.segments.find(x=>x.start>=playhead-.02);if(!s){stop();return}playhead=s.start;render();let u=new SpeechSynthesisUtterance(s.text);u.voice=voiceFor(s.speaker);u.rate=Number(document.getElementById('rate').value);document.getElementById('status').textContent=s.speaker+': '+s.text;u.onend=()=>{playhead=s.end;render();timer=setTimeout(playNext,Math.max(0,(s.end-s.start)*300))};speechSynthesis.speak(u)}document.getElementById('play').onclick=()=>{stop();playing=true;document.getElementById('play').textContent='❚❚ Playing';playNext()};document.getElementById('stop').onclick=stop;render();
</script></body></html>'''
