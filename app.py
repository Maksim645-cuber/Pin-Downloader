import re
from pathlib import Path
from urllib.parse import urlparse, quote
 
import requests
from flask import Flask, Response, abort, jsonify, request
from werkzeug.exceptions import HTTPException
 
app = Flask(__name__)
app.json.ensure_ascii = False  # русский текст в ответах читается как есть
BASE = Path(__file__).parent
 
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
 
 
class PinError(Exception):
    pass
 
 
def extract_pin_id(text: str) -> str | None:
    """Достаёт ID пина из кода встраивания, обычной ссылки или pin.it."""
    short = re.search(r"pin\.it/[A-Za-z0-9]+", text)
    if short:
        r = requests.get("https://" + short.group(0), headers=HEADERS, timeout=15)
        text = r.url
    m = (
        re.search(r"/pin/(\d+)", text)
        or re.search(r"[?&]id=(\d+)", text)
        or re.search(r"\b(\d{10,})\b", text)
    )
    return m.group(1) if m else None
 
 
def hls_to_mp4(url: str) -> str:
    # Pinterest отдаёт тот же ролик и как mp4: .../hls/xxx.m3u8 -> .../720p/xxx.mp4
    return re.sub(r"/hls/(.+)\.m3u8$", r"/720p/\1.mp4", url)
 
 
def pick_best(video_list: dict) -> str | None:
    mp4 = [v for v in video_list.values() if str(v.get("url", "")).endswith(".mp4")]
    if mp4:
        best = max(mp4, key=lambda v: (v.get("width") or 0) * (v.get("height") or 0))
        return best["url"]
    for v in video_list.values():
        u = str(v.get("url", ""))
        if u.endswith(".m3u8"):
            return hls_to_mp4(u)
    return None
 
 
def from_widget_api(pin_id: str):
    r = requests.get(
        "https://widgets.pinterest.com/v3/pidgets/pins/info/",
        params={"pin_ids": pin_id},
        headers=HEADERS,
        timeout=15,
    )
    r.raise_for_status()
    data = r.json().get("data") or []
    if not data:
        return None, None
    pin = data[0]
    video = pick_best((pin.get("videos") or {}).get("video_list") or {})
    thumb = ((pin.get("images") or {}).get("orig") or {}).get("url")
    return video, thumb
 
 
def from_page(pin_id: str):
    r = requests.get(f"https://www.pinterest.com/pin/{pin_id}/", headers=HEADERS, timeout=15)
    html = r.text.replace("\\/", "/")
    urls = re.findall(r'https://v\d*\.pinimg\.com/videos/[^"\s\\]+?\.(?:mp4|m3u8)', html)
    mp4 = [u for u in urls if u.endswith(".mp4")]
    video = None
    if mp4:
        video = next((u for u in mp4 if "720p" in u), mp4[0])
    elif urls:
        video = hls_to_mp4(urls[0])
    og = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', html)
    return video, og.group(1) if og else None
 
 
@app.errorhandler(Exception)
def on_error(e):
    if isinstance(e, HTTPException):
        return e
    app.logger.exception("Необработанная ошибка")
    return jsonify(error=f"Внутренняя ошибка сервера: {e}"), 500
 
 
@app.get("/")
def index():
    # index.html ищем в templates/, а если его положили рядом с app.py, то и там
    for path in (BASE / "templates" / "index.html", BASE / "index.html"):
        if path.exists():
            return Response(path.read_text(encoding="utf-8"), mimetype="text/html")
    raise FileNotFoundError("не найден index.html: положите его в папку templates рядом с app.py")
 
 
@app.post("/api/resolve")
def resolve():
    code = (request.get_json(silent=True) or {}).get("code", "")
    try:
        pin_id = extract_pin_id(code)
        if not pin_id:
            raise PinError("Не нашёл в этом тексте ID пина. Скопируйте код целиком.")
 
        video = thumb = None
        for source in (from_widget_api, from_page):
            try:
                video, thumb = source(pin_id)
            except Exception as e:  # источник не ответил как ожидалось: пробуем следующий
                app.logger.warning("%s не сработал: %r", source.__name__, e)
                continue
            if video:
                break
        if not video:
            raise PinError("В этом пине нет видео, или Pinterest не отдал его. Проверьте, что это видео-пин.")
 
        link = "/download?url=" + quote(video, safe="")
        return jsonify(preview=link, download=link + "&dl=1", thumb=thumb)
    except PinError as e:
        return jsonify(error=str(e)), 400
    except requests.RequestException:
        return jsonify(error="Не удалось связаться с Pinterest. Попробуйте ещё раз."), 502
 
 
@app.get("/download")
def download():
    url = request.args.get("url", "")
    p = urlparse(url)
    # Разрешаем только файлы с серверов Pinterest, иначе это был бы открытый прокси.
    if p.scheme != "https" or not (p.hostname or "").endswith(".pinimg.com"):
        abort(400)
 
    upstream = requests.get(url, headers=HEADERS, stream=True, timeout=20, allow_redirects=False)
    if upstream.status_code != 200:
        abort(502)
 
    filename = re.sub(r"[^\w.\-]", "_", p.path.rsplit("/", 1)[-1]) or "video.mp4"
    disposition = "attachment" if request.args.get("dl") else "inline"
    headers = {"Content-Disposition": f'{disposition}; filename="pinterest-{filename}"'}
    if "Content-Length" in upstream.headers:
        headers["Content-Length"] = upstream.headers["Content-Length"]
    return Response(
        upstream.iter_content(65536),
        content_type=upstream.headers.get("Content-Type", "video/mp4"),
        headers=headers,
    )
 
 
if __name__ == "__main__":
    app.run(debug=True)
 
