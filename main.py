# -*- coding: utf-8 -*-
# 爆款视频 → Brief 分析工具(网页版 · 单文件)
# 部署在 Replit:粘链接 → Gemini 看视频 → 出填好的 brief
#
# 需要在 Replit 的 Secrets 里加一个:
#   GEMINI_API_KEY = 你的 key(去 https://aistudio.google.com/apikey 免费领)

import os
import re
import json
import time
import tempfile
from flask import Flask, request, jsonify

app = Flask(__name__)

# ============================================================
# 配置 —— 随时改
# ============================================================
DEFAULT_MODEL = "gemini-3-flash-preview"  # 报错就换最新 flash 型号

PRODUCT_CONTEXT = """
我方产品:
- GMGN:多链加密货币交易终端。卖点:快速交易、跟单、安全检测、钱包追踪、多链支持。
- Future:基于 Polymarket 的预测市场交易终端。卖点:预测市场行情、快速下注、数据看板。
目标用户:加密货币交易者、meme 币交易者、KOL 粉丝群体。
主要竞品:Axiom、Sigma、BasedBot、FOMO、PumpFun。
渠道:短视频/长视频 KOL,含巴西/拉美地区(需要时输出可用于葡语改编)。
"""
# ============================================================


def detect_platform(url):
    u = url.lower()
    if "youtube.com" in u or "youtu.be" in u:
        return "youtube"
    if "tiktok.com" in u:
        return "tiktok"
    if "instagram.com" in u:
        return "instagram"
    if "x.com" in u or "twitter.com" in u:
        return "x"
    return "other"


def fetch_metadata(url):
    try:
        import yt_dlp
    except ImportError:
        return {}
    opts = {"quiet": True, "skip_download": True, "no_warnings": True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        return {
            "title": info.get("title", ""),
            "uploader": info.get("uploader") or info.get("channel", ""),
            "view_count": info.get("view_count"),
            "upload_date": info.get("upload_date", ""),
            "duration": info.get("duration"),
            "webpage_url": info.get("webpage_url", url),
        }
    except Exception:
        return {}


def guess_type(url, platform, meta):
    if platform in ("tiktok", "instagram", "x"):
        return "short"
    if "/shorts/" in url.lower():
        return "short"
    dur = meta.get("duration") or 0
    return "short" if 0 < dur <= 90 else "long"


def download_video(url):
    import yt_dlp
    tmp_dir = tempfile.mkdtemp(prefix="vbrief_")
    out_tmpl = os.path.join(tmp_dir, "video.%(ext)s")
    # 单文件 mp4,避免需要 ffmpeg 合并
    opts = {
        "format": "best[ext=mp4]/best",
        "outtmpl": out_tmpl,
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    for f in os.listdir(tmp_dir):
        return os.path.join(tmp_dir, f)
    raise RuntimeError("下载后没找到视频文件")


def build_prompt(video_type, meta):
    meta_line = f"视频标题:{meta.get('title','(未知)')} / 作者:{meta.get('uploader','(未知)')}"
    intro = f"""你是加密货币行业的资深内容策略师,专门拆解爆款短/长视频并产出可执行的内容 brief。
{meta_line}

请「观看」这个视频(画面、语音、屏幕文字、节奏都要看),然后:
1. 拆解这条爆款(第一层)
2. 把成功套路翻译成我方产品的新内容脚本草稿(第二层)

{PRODUCT_CONTEXT}

严格只输出 JSON,不要解释、不要 markdown 代码块。中文为主,保留视频关键原话。
"""
    if video_type == "short":
        schema = """{
"layer1":{"hook":{"opening_line":"开头0-3秒口播原话","screen_text":"屏幕大字","visual_action":"前3秒画面动作","hook_type":"钩子套路"},
"timeline":[{"time":"0-3s","purpose":""},{"time":"3-8s","purpose":""}],
"core":{"product_feature":"讲了什么产品/功能","selling_point":"核心卖点","framing":"怎么包装成好处"},
"evidence":"证据(盈利截图/实测/数字)",
"cta":{"line":"CTA原话","position":"位置","offer":"给什么(邀请码/链接/返现)"},
"form":{"pacing":"节奏/剪辑","subtitle_style":"字幕风格","music":"音乐/音效"},
"why_viral":{"transferable_pattern":"可迁移套路","why_worked":"为什么能爆"}},
"layer2":{"chosen_pattern":"复用的套路","adapted_product":"适配我方哪个产品/功能","new_angle":"新卖点角度",
"script":{"hook":"Hook(0-3s):口播+大字","develop":"展开(3-8s)","demo":"演示(8-20s)","proof":"证明(20-28s)","cta":"CTA(28-30s)"},
"production_notes":{"assets":"素材","subtitle_focus":"字幕重点","target_length":"时长目标"}}}"""
    else:
        schema = """{
"layer1":{"opening":{"summary":"开场0-60秒大意","promise":"承诺了什么","hook_type":"钩子套路"},
"retention_structure":{"chapters":[{"time":"","topic":"","function":"作用/留存手法"}],"density_rhythm":"信息密度节奏","suspense":"悬念/回扣"},
"core":{"feature_explanation":"功能怎么讲的","selling_point":"核心卖点","credibility":"怎么建立可信度"},
"cta_layout":[{"position":"前段/中段/结尾","script":"话术","offer":"给什么"}],
"argument":{"how_built":"论证怎么铺的","evidence":"证据元素"},
"form":{"style":"讲解风格","editing":"剪辑节奏"},
"why_viral":{"transferable_pattern":"可迁移套路","why_worked":"为什么留存高/能爆"}},
"layer2":{"chosen_pattern":"复用套路","adapted_product":"适配产品/功能","new_angle":"新角度",
"script":{"opening":"开场(0-60s)","chapters":["章节1","章节2","章节3"],"cta_layout":"前/中/尾CTA","ending":"结尾"},
"production_notes":{"recording":"录屏/素材","target_length":"目标时长","key_assets":"关键截图/数据"}}}"""
    return intro + "\n按此 JSON 结构输出:\n" + schema


def call_gemini(prompt, platform, url, video_path):
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    if platform == "youtube":
        parts = [types.Part(file_data=types.FileData(file_uri=url)), types.Part(text=prompt)]
    else:
        f = client.files.upload(file=video_path)
        while f.state.name == "PROCESSING":
            time.sleep(2)
            f = client.files.get(name=f.name)
        if f.state.name == "FAILED":
            raise RuntimeError("Gemini 处理视频失败")
        parts = [types.Part(file_data=types.FileData(file_uri=f.uri, mime_type=f.mime_type)),
                 types.Part(text=prompt)]

    resp = client.models.generate_content(
        model=DEFAULT_MODEL,
        contents=types.Content(parts=parts),
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    text = resp.text.strip()
    text = re.sub(r"^```(json)?|```$", "", text, flags=re.MULTILINE).strip()
    return json.loads(text)


# ---------------- HTML 渲染 ----------------
def _meta_row(meta):
    parts = []
    if meta.get("title"): parts.append(meta["title"])
    if meta.get("uploader"): parts.append("@" + meta["uploader"])
    if meta.get("view_count"): parts.append(f"{meta['view_count']:,} 播放")
    d = meta.get("upload_date", "")
    if d and len(d) == 8: parts.append(f"{d[:4]}-{d[4:6]}-{d[6:]}")
    if meta.get("webpage_url"): parts.append(meta["webpage_url"])
    return " · ".join(str(p) for p in parts if p)


def _panel(title, body, color, bg):
    return (f'<div style="background:{bg};border-left:4px solid {color};padding:12px 16px;'
            f'margin:14px 0;border-radius:3px;"><strong>{title}</strong><br>{body}</div>')


def _table(rows, headers=None, widths=None):
    html = '<table style="width:100%;border-collapse:collapse;margin:8px 0 16px;font-size:14px;">'
    if headers:
        html += '<tr style="background:#f4f5f7;">'
        for i, hd in enumerate(headers):
            w = f"width:{widths[i]};" if widths and widths[i] else ""
            html += f'<th style="padding:6px 12px;border:1px solid #dfe1e6;text-align:left;{w}">{hd}</th>'
        html += '</tr>'
    for row in rows:
        html += '<tr>' + ''.join(
            f'<td style="padding:6px 12px;border:1px solid #dfe1e6;">{c}</td>' for c in row) + '</tr>'
    return html + '</table>'


def render_short(data, meta):
    l1, l2 = data.get("layer1", {}), data.get("layer2", {})
    h, core, cta = l1.get("hook", {}), l1.get("core", {}), l1.get("cta", {})
    form, wv = l1.get("form", {}), l1.get("why_viral", {})
    s, pn = l2.get("script", {}), l2.get("production_notes", {})
    return f"""
<h1 style="font-size:24px;border-bottom:3px solid #0052cc;padding-bottom:8px;">短视频爆款拆解 → Brief</h1>
{_table([["参考视频", _meta_row(meta)]], widths=["110px"])}
<h2 style="font-size:18px;color:#0052cc;border-bottom:1px solid #dfe1e6;padding-bottom:4px;">🔍 第一层 · 爆款拆解</h2>
{_panel("Hook(0–3s)", f"· 开头原话:{h.get('opening_line','')}<br>· 屏幕大字:{h.get('screen_text','')}<br>· 视觉动作:{h.get('visual_action','')}<br>· 钩子套路:<span style='background:#e3fcef;color:#006644;padding:1px 8px;border-radius:3px;font-size:12px;'>{h.get('hook_type','')}</span>", "#ff8b00", "#fffae6")}
<p style="font-weight:600;">结构时间轴</p>
{_table([[t.get('time',''), t.get('purpose','')] for t in l1.get('timeline',[])], headers=["时间","段落作用"], widths=["90px",None])}
<p style="font-weight:600;">核心内容</p>
<ul><li>产品/功能:{core.get('product_feature','')}</li><li>卖点/角度:{core.get('selling_point','')}</li><li>怎么框定:{core.get('framing','')}</li></ul>
<p style="font-weight:600;">证据元素</p><ul><li>{l1.get('evidence','')}</li></ul>
<p style="font-weight:600;">CTA</p><ul><li>原话:{cta.get('line','')}</li><li>位置:{cta.get('position','')}</li><li>给什么:{cta.get('offer','')}</li></ul>
<p style="font-weight:600;">形式</p><ul><li>节奏/剪辑:{form.get('pacing','')}</li><li>字幕:{form.get('subtitle_style','')}</li><li>音乐:{form.get('music','')}</li></ul>
{_panel("⭐ 爆点归因(最重要)", f"· 可迁移套路:{wv.get('transferable_pattern','')}<br>· 为什么能爆:{wv.get('why_worked','')}", "#00875a", "#e3fcef")}
<h2 style="font-size:18px;color:#0052cc;border-bottom:1px solid #dfe1e6;padding-bottom:4px;margin-top:24px;">✍️ 第二层 · GMGN / Future 新脚本(草稿)</h2>
{_table([["选定套路", l2.get('chosen_pattern','')],["适配产品/功能", l2.get('adapted_product','')],["新卖点角度", l2.get('new_angle','')]], widths=["120px",None])}
{_panel("逐字脚本(creator 照着拍)", f"· <strong>Hook(0–3s)</strong>:{s.get('hook','')}<br>· <strong>展开(3–8s)</strong>:{s.get('develop','')}<br>· <strong>演示(8–20s)</strong>:{s.get('demo','')}<br>· <strong>证明(20–28s)</strong>:{s.get('proof','')}<br>· <strong>CTA(28–30s)</strong>:{s.get('cta','')}", "#0052cc", "#deebff")}
<p style="font-weight:600;">拍摄备注</p>
<ul><li>素材:{pn.get('assets','')}</li><li>字幕重点:{pn.get('subtitle_focus','')}</li><li>时长目标:{pn.get('target_length','')}</li></ul>
<p style="color:#5e6c84;font-size:13px;margin-top:20px;">💡 第二层是 AI 草稿,发 creator 前人工过一遍卖点。⚠️ 纯视觉细节(无口播的画面/一闪而过的字)可能需你瞄一眼原视频补全。</p>
"""


def render_long(data, meta):
    l1, l2 = data.get("layer1", {}), data.get("layer2", {})
    op, rs = l1.get("opening", {}), l1.get("retention_structure", {})
    core, arg, form, wv = l1.get("core", {}), l1.get("argument", {}), l1.get("form", {}), l1.get("why_viral", {})
    s, pn = l2.get("script", {}), l2.get("production_notes", {})
    return f"""
<h1 style="font-size:24px;border-bottom:3px solid #172b4d;padding-bottom:8px;">长视频爆款拆解 → Brief</h1>
{_table([["参考视频", _meta_row(meta)]], widths=["110px"])}
<h2 style="font-size:18px;color:#172b4d;border-bottom:1px solid #dfe1e6;padding-bottom:4px;">🔍 第一层 · 爆款拆解</h2>
{_panel("开场(0–60s)", f"· 开场大意:{op.get('summary','')}<br>· 承诺了什么:{op.get('promise','')}<br>· 钩子套路:<span style='background:#e3fcef;color:#006644;padding:1px 8px;border-radius:3px;font-size:12px;'>{op.get('hook_type','')}</span>", "#ff8b00", "#fffae6")}
<p style="font-weight:600;">留存结构(章节时间轴)</p>
{_table([[c.get('time',''), c.get('topic',''), c.get('function','')] for c in rs.get('chapters',[])], headers=["时间","主题","作用/留存手法"], widths=["90px","30%",None])}
<ul><li>信息密度节奏:{rs.get('density_rhythm','')}</li><li>悬念/回扣:{rs.get('suspense','')}</li></ul>
<p style="font-weight:600;">核心内容</p>
<ul><li>功能讲解:{core.get('feature_explanation','')}</li><li>卖点/角度:{core.get('selling_point','')}</li><li>可信度:{core.get('credibility','')}</li></ul>
<p style="font-weight:600;">CTA 布局</p>
{_table([[c.get('position',''), c.get('script',''), c.get('offer','')] for c in l1.get('cta_layout',[])], headers=["位置","话术","给什么"], widths=["110px",None,None])}
<p style="font-weight:600;">论证/证据</p>
<ul><li>论证怎么铺:{arg.get('how_built','')}</li><li>证据元素:{arg.get('evidence','')}</li></ul>
<p style="font-weight:600;">形式</p>
<ul><li>讲解风格:{form.get('style','')}</li><li>剪辑节奏:{form.get('editing','')}</li></ul>
{_panel("⭐ 爆点归因", f"· 可迁移套路:{wv.get('transferable_pattern','')}<br>· 为什么能爆:{wv.get('why_worked','')}", "#00875a", "#e3fcef")}
<h2 style="font-size:18px;color:#172b4d;border-bottom:1px solid #dfe1e6;padding-bottom:4px;margin-top:24px;">✍️ 第二层 · GMGN / Future 新脚本(草稿)</h2>
{_table([["选定套路", l2.get('chosen_pattern','')],["适配产品/功能", l2.get('adapted_product','')],["新角度", l2.get('new_angle','')]], widths=["120px",None])}
{_panel("分段脚本", f"· <strong>开场(0–60s)</strong>:{s.get('opening','')}<br>" + "".join(f"· <strong>章节 {i+1}</strong>:{c}<br>" for i, c in enumerate(s.get('chapters',[]))) + f"· <strong>CTA 布局</strong>:{s.get('cta_layout','')}<br>· <strong>结尾</strong>:{s.get('ending','')}", "#172b4d", "#deebff")}
<p style="font-weight:600;">制作备注</p>
<ul><li>录屏/素材:{pn.get('recording','')}</li><li>目标时长:{pn.get('target_length','')}</li><li>关键截图/数据:{pn.get('key_assets','')}</li></ul>
<p style="color:#5e6c84;font-size:13px;margin-top:20px;">💡 第二层是 AI 草稿,发 creator 前人工过一遍卖点。</p>
"""


# ---------------- 网页 ----------------
PAGE = """<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>爆款视频 → Brief</title>
<style>
body{font-family:-apple-system,'Segoe UI',Roboto,Arial,sans-serif;background:#f4f5f7;color:#172b4d;margin:0;padding:24px;}
.wrap{max-width:880px;margin:0 auto;}
.card{background:#fff;border-radius:10px;padding:24px;box-shadow:0 1px 4px rgba(0,0,0,.08);}
h1.top{font-size:22px;margin:0 0 4px;}
p.sub{color:#5e6c84;margin:0 0 20px;font-size:14px;}
input[type=text]{width:100%;padding:12px;font-size:15px;border:1px solid #dfe1e6;border-radius:6px;box-sizing:border-box;}
.row{display:flex;gap:12px;align-items:center;margin:14px 0;flex-wrap:wrap;}
label{font-size:14px;cursor:pointer;}
button{background:#0052cc;color:#fff;border:none;padding:12px 24px;font-size:15px;border-radius:6px;cursor:pointer;font-weight:600;}
button:disabled{background:#a5adba;cursor:not-allowed;}
#status{margin-top:16px;color:#5e6c84;font-size:14px;}
#result{background:#fff;border-radius:10px;padding:24px;margin-top:20px;box-shadow:0 1px 4px rgba(0,0,0,.08);display:none;}
.err{color:#bf2600;}
ul{margin-top:4px;}
</style></head><body><div class="wrap">
<div class="card">
<h1 class="top">爆款视频 → Brief 分析工具</h1>
<p class="sub">粘一个视频链接(YouTube / TikTok / Instagram / X),自动拆解要点,出可执行 brief。</p>
<input id="url" type="text" placeholder="https://www.tiktok.com/@fomo/video/...">
<div class="row">
<span style="font-size:14px;">模板:</span>
<label><input type="radio" name="t" value="auto" checked> 自动判断</label>
<label><input type="radio" name="t" value="short"> 短视频</label>
<label><input type="radio" name="t" value="long"> 长视频</label>
</div>
<button id="go" onclick="run()">分析</button>
<div id="status"></div>
</div>
<div id="result"></div>
</div>
<script>
async function run(){
  const url=document.getElementById('url').value.trim();
  if(!url){alert('先粘个链接');return;}
  const t=document.querySelector('input[name=t]:checked').value;
  const btn=document.getElementById('go'), st=document.getElementById('status'), res=document.getElementById('result');
  btn.disabled=true; res.style.display='none';
  st.innerHTML='⏳ 分析中,长视频可能要 1-2 分钟,别关页面...';
  try{
    const r=await fetch('/analyze',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url,type:t})});
    const d=await r.json();
    if(d.error){st.innerHTML='<span class="err">❌ '+d.error+'</span>';}
    else{st.innerHTML=''; res.innerHTML=d.html; res.style.display='block'; res.scrollIntoView({behavior:'smooth'});}
  }catch(e){st.innerHTML='<span class="err">❌ 出错了:'+e+'</span>';}
  btn.disabled=false;
}
</script></body></html>"""


@app.route("/")
def index():
    return PAGE


@app.route("/analyze", methods=["POST"])
def analyze():
    try:
        body = request.get_json(force=True)
        url = (body.get("url") or "").strip()
        t = body.get("type", "auto")
        if not url:
            return jsonify({"error": "没有链接"})
        if "GEMINI_API_KEY" not in os.environ:
            return jsonify({"error": "还没设置 GEMINI_API_KEY(在 Replit 的 Secrets 里加)"})

        platform = detect_platform(url)
        meta = fetch_metadata(url)
        video_type = t if t in ("short", "long") else guess_type(url, platform, meta)

        video_path = None
        if platform != "youtube":
            video_path = download_video(url)

        prompt = build_prompt(video_type, meta)
        data = call_gemini(prompt, platform, url, video_path)
        html = render_short(data, meta) if video_type == "short" else render_long(data, meta)
        return jsonify({"html": html})
    except Exception as e:
        return jsonify({"error": str(e)})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
