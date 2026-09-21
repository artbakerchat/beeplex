"""Coaching dashboard: local HTML report + trend history.

Every fetch_report_data() run regenerates family/dashboard.html and - for
live runs - appends that run's per-conversation scores to
family/history.json. The history stores scores and signal values only,
never transcripts. The dashboard shows:

  * this run's conversations ranked by engagement, with the one-line
    reason each one sits where it does
  * per-conversation cards: domain breakdowns, sub-signal bars,
    plain-language coaching tips derived from the signals, and a trend
    sparkline across runs
  * a weight lab: sliders that re-blend the three domains live, so users
    can feel how the engagement score is built

A local file opened in the browser - no data leaves the machine, same
privacy posture as the generated reports.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from temporal_scoring import top_repeats

OUTPUT_DIR = Path(__file__).resolve().parent / "family"
HISTORY_PATH = OUTPUT_DIR / "history.json"
DASHBOARD_PATH = OUTPUT_DIR / "dashboard.html"
# Bound the history file; oldest runs drop off the end.
MAX_RUNS = 200


def _load_history():
    try:
        data = json.loads(HISTORY_PATH.read_text())
        if isinstance(data, dict) and isinstance(data.get("runs"), list):
            return data
    except (OSError, ValueError):
        pass
    return {"runs": []}


def _save_history(history):
    HISTORY_PATH.write_text(json.dumps(history, indent=1))


def _score(d):
    return d["score"] if d else None


def _history_entry(e):
    """Numeric-only record of one conversation for the trend history."""
    bd = e["breakdown"]
    return {
        "id": e["id"],
        "title": e["title"],
        "engagement": _score(bd["engagement"]),
        "det": _score(bd["det"]),
        "energy": _score(bd["energy"]),
        "fm": _score(bd["fm"]),
        "fm_blended": _score(bd["fm_blended"]),
        "tone": (bd["llm"] or {}).get("tone"),
        "det_signals": (bd["det"] or {}).get("signals"),
        "energy_signals": (bd["energy"] or {}).get("signals"),
        "fm_signals": (bd["fm"] or {}).get("signals"),
    }


def coaching_tips(bd, repeats):
    """Plain-language coaching tips derived from a scoring breakdown.

    ``bd`` is a bee_fetcher.score_breakdown() dict; ``repeats`` is
    [(phrase, count)] from temporal_scoring.top_repeats(). Deterministic,
    free, no API key - the same signals that built the score say how to
    move it. Returned most-severe first, capped at six.
    """
    if bd["engagement"] is None:
        return ["Nothing substantive to score in this recording."]
    tips = []
    det = bd["det"]["signals"]
    n = bd["n_substantive"]
    if n < 5:
        tips.append(("thin",
                     f"Thin evidence \u2014 only {n} substantive turns, so this "
                     "score is capped at Moderate no matter what the signals say."))
    shares = bd["speaker_shares"]
    if shares:
        top_share = max(shares.values())
        if top_share >= 0.7:
            who = max(shares, key=shares.get)
            tips.append(("balance",
                         f"One voice ({who}) is doing {round(top_share * 100)}% "
                         "of the talking \u2014 draw the other person out with "
                         "a direct question."))
        elif det.get("balance", 1) < 0.5:
            tips.append(("balance",
                         "Talk time is lopsided \u2014 invite the quieter "
                         "voice in before moving on."))
    if det.get("interactivity", 1) < 0.5:
        tips.append(("interactivity",
                     "Long solo stretches with few handoffs \u2014 shorter "
                     "turns back and forth build energy."))
    if det.get("curiosity", 1) < 0.4:
        tips.append(("curiosity",
                     "Few follow-up questions \u2014 a well-placed "
                     "\u201cwhy\u201d is the cheapest engagement boost there is."))
    if det.get("depth", 1) < 0.5:
        tips.append(("depth",
                     "Answers are staying surface-level \u2014 ask one question "
                     "that can't be answered in a sentence."))
    energy = bd["energy"]
    if energy:
        es = energy["signals"]
        if es.get("pace", 1) < 0.4:
            tips.append(("pace",
                         "The pace is dragging \u2014 pick up the tempo before "
                         "the energy leaks out."))
        if es.get("responsiveness", 1) < 0.4:
            tips.append(("responsiveness",
                         "Long pauses after substantive turns \u2014 replies "
                         "are landing late."))
    fm = bd["fm"]
    fs = {}
    if fm:
        fs = fm["signals"]
        circ = fs.get("circularity", 0) or 0
        if circ > 0.25:
            if repeats:
                shown = ", ".join(f"\u201c{p}\u201d ({c}\u00d7)"
                                  for p, c in repeats[:2])
                tips.append(("circularity",
                             f"Looping detected \u2014 {shown}. "
                             "Say it once and move on."))
            else:
                tips.append(("circularity",
                             "Looping detected \u2014 the same phrases keep "
                             "coming back. Say it once and move on."))
        nov = fs.get("novelty")
        if nov is not None and nov < 0.7:
            tips.append(("novelty",
                         "Same ground covered repeatedly \u2014 name one thing "
                         "that's new since the last turn."))
    spin = fs.get("spinning", 0) or 0
    if spin > 0.3:
        bits = []
        if (fs.get("question_chains") or 0) >= 0.3:
            bits.append("questions are coming back unanswered")
        if (fs.get("circling_markers") or 0) >= 0.2:
            bits.append("the same charges keep resurfacing")
        if (fs.get("absolutist") or 0) >= 0.2:
            bits.append("absolutes like \u201calways\u201d/\u201cnever\u201d "
                        "are flying")
        detail = "; ".join(bits) if bits else "the exchange is looping"
        tips.append(("spinning",
                     f"Going in circles \u2014 {detail}. Name the one thing "
                     "this conversation needs to decide."))
    fmb = bd["fm_blended"]
    eng = bd["engagement"]
    if fmb and fmb["score"] < 4 <= eng["score"]:
        tips.append(("stuck",
                     "Lots of heat, little movement \u2014 summarize where you "
                     "agree and decide the next step."))
    llm = bd["llm"] or {}
    tone = llm.get("tone")
    if tone is not None and tone <= 4:
        tl = (llm.get("tone_label") or "").strip()
        tips.append(("tone",
                     f"Tone is running tense{f' ({tl})' if tl else ''} "
                     "\u2014 acknowledge the friction before pushing your point."))
    if not tips and eng["score"] >= 7 and (fmb is None or fmb["score"] >= 7):
        tips.append(("keep",
                     "Strong conversation \u2014 balanced, moving, landing. "
                     "Keep doing exactly this."))
    order = {"thin": 0, "spinning": 1, "circularity": 2, "stuck": 3,
             "balance": 4, "tone": 5, "interactivity": 6, "responsiveness": 7,
             "pace": 8, "curiosity": 9, "depth": 10, "novelty": 11,
             "keep": 99}
    tips.sort(key=lambda t: order.get(t[0], 50))
    return [t[1] for t in tips[:6]]


def headline(bd, tips):
    """One-line reason a conversation sits where it does in the ranking."""
    if bd["engagement"] is None:
        return "no substantive turns"
    if tips:
        t = tips[0]
        return t if len(t) <= 72 else t[:69] + "..."
    return "well-rounded"


def _signal_rows(bd):
    """Sub-signal bars for the dashboard: [{domain, name, value, invert}]."""
    rows = []
    for name in ("balance", "interactivity", "curiosity", "depth"):
        if name in bd["det"]["signals"]:
            rows.append({"domain": "Deterministic", "name": name.capitalize(),
                         "value": bd["det"]["signals"][name], "invert": False})
    energy = bd["energy"]
    if energy:
        for name in ("pace", "responsiveness"):
            if name in energy["signals"]:
                rows.append({"domain": "Temporal \u00b7 energy",
                             "name": name.capitalize(),
                             "value": energy["signals"][name], "invert": False})
    fm = bd["fm"]
    if fm:
        rows.append({"domain": "Temporal \u00b7 forward motion",
                     "name": "Circularity",
                     "value": fm["signals"].get("circularity", 0) or 0,
                     "invert": True, "note": "lower is better"})
        if fm["signals"].get("novelty") is not None:
            rows.append({"domain": "Temporal \u00b7 forward motion",
                         "name": "Novelty",
                         "value": fm["signals"]["novelty"], "invert": False})
        rows.append({"domain": "Temporal \u00b7 forward motion",
                     "name": "Spinning",
                     "value": fm["signals"].get("spinning", 0) or 0,
                     "invert": True, "note": "lower is better"})
    return rows


def _tone_display(bd):
    l = bd["llm"] or {}
    tone = l.get("tone")
    if tone is None:
        return "\u2014"
    tl = (l.get("tone_label") or "").strip()
    return f"{tl} ({tone}/10)" if tl else f"{tone}/10"


def _make_card(e, history):
    """Assemble one dashboard card (JSON-serializable) from a scored entry."""
    bd = e["breakdown"]
    repeats = top_repeats(e["parts"])
    tips = coaching_tips(bd, repeats)
    llm = bd["llm"] or {}
    spark = []
    for run in history["runs"]:
        for c in run["conversations"]:
            if c["id"] == e["id"] and c.get("engagement") is not None:
                spark.append(c["engagement"])
                break
    trend = None
    if len(spark) >= 2:
        delta = spark[-1] - spark[-2]
        trend = "up" if delta >= 0.5 else ("down" if delta <= -0.5 else "flat")
    return {
        "id": e["id"], "title": e["title"], "date": e["date"],
        "det": _score(bd["det"]), "detLabel": (bd["det"] or {}).get("label"),
        "energy": _score(bd["energy"]),
        "fm": _score(bd["fm"]),
        "llmEng": llm.get("engagement"), "llmProg": llm.get("progress"),
        "llmProgLabel": (llm.get("progress_label") or "").strip() or None,
        "llmRationale": llm.get("rationale"),
        "toneDisplay": _tone_display(bd),
        "engBase": _score(bd["engagement"]),
        "engBaseLabel": (bd["engagement"] or {}).get("label"),
        "fmBase": _score(bd["fm_blended"]),
        "fmBaseLabel": (bd["fm_blended"] or {}).get("label"),
        "signalRows": _signal_rows(bd),
        "tips": tips, "headline": headline(bd, tips),
        "spark": spark, "trend": trend,
        "nSubstantive": bd["n_substantive"],
    }


def record_run(entries, info):
    """Record one run: append to history (live only) and rebuild the page.

    ``entries`` is [{id, title, date, parts, breakdown}]; ``info`` is
    {"mode": "live"|"mock"}. Mock runs regenerate the dashboard from
    history with a demo banner and never append.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    history = _load_history()
    now = datetime.now(timezone.utc)
    if info.get("mode") == "live" and entries:
        history["runs"].append({
            "ts": now.isoformat(),
            "conversations": [_history_entry(e) for e in entries],
        })
        history["runs"] = history["runs"][-MAX_RUNS:]
        _save_history(history)
    cards = [_make_card(e, history) for e in entries]
    _write_dashboard(cards, info, history, now)


_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Conversation coaching dashboard</title>
<style>
:root{color-scheme:light dark;--bg:#f7f7f8;--card:#fff;--text:#1a1a1a;--muted:#6b7280;--border:#e5e7eb;--accent:#2563eb;--good:#15803d;--warn:#b45309;--bad:#b91c1c}
@media (prefers-color-scheme:dark){:root{--bg:#111214;--card:#1b1d20;--text:#e8eaed;--muted:#9aa0a6;--border:#2e3136;--accent:#7aa2f7;--good:#4ade80;--warn:#fbbf24;--bad:#f87171}}
*{box-sizing:border-box}body{font-family:-apple-system,system-ui,"Segoe UI",sans-serif;background:var(--bg);color:var(--text);margin:0;padding:20px;line-height:1.5}
.wrap{max-width:960px;margin:0 auto}
header{display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px;margin-bottom:4px}
h1{font-size:22px;margin:0}h2{font-size:16px;margin:20px 0 8px}
.meta{color:var(--muted);font-size:13px}
.banner{background:#fef3c7;color:#92400e;border:1px solid #fcd34d;border-radius:10px;padding:10px 14px;margin:12px 0;font-size:14px}
@media (prefers-color-scheme:dark){.banner{background:#3a2f12;color:#fcd34d;border-color:#6b5518}}
.card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:16px;margin:12px 0}
.tiles{display:flex;gap:10px;flex-wrap:wrap;margin:10px 0}
.tile{flex:1 1 140px;border:1px solid var(--border);border-radius:10px;padding:10px}
.tile .k{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
.tile .v{font-size:22px;font-weight:700}
.tile .s{font-size:12px;color:var(--muted)}
.pill{display:inline-block;border-radius:12px;padding:1px 10px;font-size:12px;font-weight:600;border:1px solid}
.hi{color:var(--good);border-color:var(--good)}.md{color:var(--warn);border-color:var(--warn)}.lo{color:var(--bad);border-color:var(--bad)}
.sig{margin:6px 0}.sig .row{display:flex;justify-content:space-between;font-size:13px;margin-bottom:2px}
.sig .dom{color:var(--muted);font-size:11px}
.bar{height:8px;background:var(--border);border-radius:4px;overflow:hidden}
.bar i{display:block;height:100%;border-radius:4px}
.tips{margin:10px 0 0;padding-left:20px;font-size:14px}.tips li{margin:5px 0}
.rat{border-left:3px solid var(--accent);padding:4px 12px;margin-top:10px;font-style:italic;color:var(--muted);font-size:14px}
table{width:100%;border-collapse:collapse;font-size:13px;background:var(--card);border:1px solid var(--border);border-radius:12px;overflow:hidden}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--border)}
th{color:var(--muted);font-weight:600;font-size:12px}
tr:last-child td{border-bottom:none}
.lab{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:16px;margin:12px 0}
.sl{display:flex;align-items:center;gap:10px;margin:8px 0}.sl label{width:170px;flex:none;font-size:14px}.sl input{flex:1}.sl .v{width:40px;text-align:right;font-variant-numeric:tabular-nums}
.tog{display:flex;align-items:center;gap:8px;margin:8px 0;font-size:14px}
.spark{display:block}
footer{color:var(--muted);font-size:12px;margin:24px 0}
</style>
</head>
<body><div class="wrap">
<header><h1>Conversation coaching dashboard</h1><div class="meta" id="runmeta"></div></header>
<div id="mockbanner"></div>

<h2>This run, ranked</h2>
<div class="lab">
<div class="tog"><input type="checkbox" id="llmTog" checked><label for="llmTog">Semantic (LLM) domain active <span class="meta">&mdash; uncheck to see the no-key blend</span></label></div>
<div class="sl"><label>Deterministic weight</label><input type="range" id="sDet" min="0" max="100" value="34"><span class="v" id="vDet">34</span></div>
<div class="sl"><label>Temporal weight</label><input type="range" id="sTmp" min="0" max="100" value="33"><span class="v" id="vTmp">33</span></div>
<div class="sl"><label>Semantic weight</label><input type="range" id="sLlm" min="0" max="100" value="33"><span class="v" id="vLlm">33</span></div>
<div class="meta">Engagement = weighted mean of the active domains. Equal weights reproduce the report scores.</div>
<div class="meta">Without the semantic domain, forward motion is a structural read &mdash; it catches looping phrases, question chains and circling rhetoric, but not paraphrase-level restating. That last part is the LLM&rsquo;s half.</div>
</div>
<table><thead><tr><th>#</th><th>Conversation</th><th>Trend</th><th>Det</th><th>Temp</th><th>Engagement</th><th>Fwd motion</th><th>Why</th></tr></thead><tbody id="rankrows"></tbody></table>

<h2>Coaching</h2>
<div id="cards"></div>

<footer>Scores: deterministic (structure) + temporal (motion) + semantic (meaning, one Gemini call per run, needs API key). Engagement is the heat; forward motion is whether the heat cooks anything. History: the last __NRUNS__ runs, kept locally in <code>family/history.json</code>.</footer>
</div>
<script>
var META=__RUN_META__;
var CARDS=__CARDS__;
var W={d:34,t:33,l:33,llm:true};
function lab(s){return s==null?"\u2014":(s>=7?"High":(s>=4?"Moderate":"Low"));}
function cls(s){return s==null?"":(s>=7?"hi":(s>=4?"md":"lo"));}
function pill(s){return s==null?"\u2014":'<span class="pill '+cls(s)+'">'+lab(s)+" "+s.toFixed(1)+"</span>";}
function num(s){return s==null?"\u2014":s.toFixed(1);}
function blendEng(c){var p=[],w=0;if(W.d>0&&c.det!=null){p.push(c.det*W.d);w+=W.d;}if(W.t>0&&c.energy!=null){p.push(c.energy*W.t);w+=W.t;}if(W.llm&&W.l>0&&c.llmEng!=null){p.push(c.llmEng*W.l);w+=W.l;}return w?p.reduce(function(a,b){return a+b;},0)/w:null;}
function blendFm(c){var p=[],n=0;if(c.fm!=null){p.push(c.fm);n++;}if(W.llm&&c.llmProg!=null){p.push(c.llmProg);n++;}return n?p.reduce(function(a,b){return a+b;},0)/n:null;}
function trendArrow(t){return t=="up"?"\u25b2":(t=="down"?"\u25bc":(t=="flat"?"\u2014":""));}
function sparkSvg(s){if(!s||s.length<2)return '<span class="meta">not enough history</span>';var w=120,h=32,min=Math.min.apply(null,s),max=Math.max.apply(null,s),rg=(max-min)||1;var pts=s.map(function(v,i){var x=(i/(s.length-1)*w).toFixed(1),y=(h-3-((v-min)/rg)*(h-6)).toFixed(1);return x+","+y;}).join(" ");var col=s[s.length-1]>=s[0]?"var(--good)":"var(--bad)";return '<svg class="spark" width="'+w+'" height="'+h+'"><polyline points="'+pts+'" fill="none" stroke="'+col+'" stroke-width="2"/></svg>';}
function barColor(good){return good>=0.7?"var(--good)":(good>=0.4?"var(--warn)":"var(--bad)");}
function render(){
 document.getElementById("runmeta").textContent=META.ts+" \u00b7 "+META.n+" conversations \u00b7 "+META.mode;
 if(META.mode=="mock")document.getElementById("mockbanner").innerHTML='<div class="banner">Demo data \u2014 the Bee CLI isn\u2019t connected, so there\u2019s nothing new to score. Trends below come from your saved history.</div>';
 var rows=CARDS.map(function(c){return{c:c,e:blendEng(c),f:blendFm(c)};});
 rows.sort(function(a,b){return(b.e==null?-1:b.e)-(a.e==null?-1:a.e);});
 var rh="";
 rows.forEach(function(r,i){var c=r.c;
  rh+="<tr><td>"+(i+1)+"</td><td><b>"+esc(c.title)+"</b><br><span class='meta'>"+esc(c.date||"")+"</span></td><td>"+trendArrow(c.trend)+"</td><td>"+num(c.det)+"</td><td>"+num(c.energy)+"</td><td>"+pill(r.e)+"</td><td>"+pill(r.f)+"</td><td class='meta'>"+esc(c.headline)+"</td></tr>";});
 document.getElementById("rankrows").innerHTML=rh||'<tr><td colspan="8" class="meta">No conversations this run.</td></tr>';
 var ch="";
 CARDS.forEach(function(c){
  var e=blendEng(c),f=blendFm(c);
  ch+='<div class="card"><div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap"><div><b style="font-size:16px">'+esc(c.title)+'</b><div class="meta">'+esc(c.date||"")+" \u00b7 "+c.nSubstantive+' substantive turns</div></div>'+sparkSvg(c.spark)+"</div>";
  ch+='<div class="tiles"><div class="tile"><div class="k">Engagement</div><div class="v">'+pill(e)+'</div><div class="s">Det '+num(c.det)+" \u00b7 Temp "+num(c.energy)+(W.llm?" \u00b7 LLM "+num(c.llmEng):"")+'</div></div>';
  ch+='<div class="tile"><div class="k">Forward motion</div><div class="v">'+pill(f)+'</div><div class="s">'+(c.llmProgLabel?"LLM: "+esc(c.llmProgLabel):"structural signal only")+'</div></div>';
  ch+='<div class="tile"><div class="k">Tone</div><div class="v" style="font-size:18px">'+esc(c.toneDisplay)+'</div><div class="s">LLM only</div></div></div>';
  ch+="<div>"+c.signalRows.map(function(s){var good=s.invert?1-s.value:s.value;return '<div class="sig"><div class="row"><span><span class="dom">'+esc(s.domain)+" \u00b7 </span>"+esc(s.name)+(s.note?' <span class="dom">('+esc(s.note)+")</span>":"")+'</span><span>'+s.value.toFixed(2)+"</span></div>"+'<div class="bar"><i style="width:'+(s.value*100).toFixed(0)+"%;background:"+barColor(good)+'"></i></div></div>';}).join("")+"</div>";
  if(c.tips&&c.tips.length)ch+='<ul class="tips">'+c.tips.map(function(t){return "<li>"+esc(t)+"</li>";}).join("")+"</ul>";
  if(c.llmRationale)ch+='<div class="rat">\u201c'+esc(c.llmRationale)+"\u201d</div>";
  ch+="</div>";
 });
 document.getElementById("cards").innerHTML=ch||'<div class="card meta">No conversations this run.</div>';
}
function esc(s){return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}
function upd(){W={d:+document.getElementById("sDet").value,t:+document.getElementById("sTmp").value,l:+document.getElementById("sLlm").value,llm:document.getElementById("llmTog").checked};document.getElementById("vDet").textContent=W.d;document.getElementById("vTmp").textContent=W.t;document.getElementById("vLlm").textContent=W.l;render();}
["sDet","sTmp","sLlm"].forEach(function(id){document.getElementById(id).addEventListener("input",upd);});
document.getElementById("llmTog").addEventListener("change",upd);
render();
</script>
</body>
</html>
"""


def _write_dashboard(cards, info, history, now):
    meta = {
        "ts": now.strftime("%B %d, %Y %H:%M UTC"),
        "mode": info.get("mode", "live"),
        "n": len(cards),
    }
    html = _TEMPLATE.replace("__RUN_META__", json.dumps(meta))
    html = html.replace("__CARDS__", json.dumps(cards))
    html = html.replace("__NRUNS__", str(len(history["runs"])))
    DASHBOARD_PATH.write_text(html)
