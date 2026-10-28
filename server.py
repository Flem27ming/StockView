"""StockView price server.

Serves index.html and /api/quotes?symbols=AMD,HELP with live prices fetched from
Yahoo Finance. The browser can't call Yahoo directly (CORS), so this does it for it.

Start:  python server.py      then open http://localhost:8765
"""
import json
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = 8765
CACHE_SECONDS = 4
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
HOSTS = ("query1.finance.yahoo.com", "query2.finance.yahoo.com")

_cache = {}
_lock = threading.Lock()


def fetch_quote(symbol):
    with _lock:
        hit = _cache.get(symbol)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    last_error = None
    for host in HOSTS:
        url = f"https://{host}/v8/finance/chart/{urllib.parse.quote(symbol)}?range=1d&interval=1m&includePrePost=true"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=8) as res:
                meta = json.load(res)["chart"]["result"][0]["meta"]
            quote = {
                "symbol": symbol,
                "price": meta.get("regularMarketPrice"),
                "previousClose": meta.get("previousClose") or meta.get("chartPreviousClose"),
                "currency": meta.get("currency"),
                "time": meta.get("regularMarketTime"),
            }
            with _lock:
                _cache[symbol] = (time.time(), quote)
            return quote
        except Exception as e:  # try the other Yahoo host
            last_error = e
    return {"symbol": symbol, "error": str(last_error)}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(Path(__file__).parent), **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/api/quotes":
            return super().do_GET()
        symbols = urllib.parse.parse_qs(parsed.query).get("symbols", [""])[0]
        symbols = [s.strip().upper() for s in symbols.split(",") if s.strip()][:50]
        with ThreadPoolExecutor(max_workers=8) as pool:
            body = json.dumps(list(pool.map(fetch_quote, symbols))).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")  # lets index.html opened as a file use it
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"StockView kører på http://localhost:{PORT}  (luk vinduet for at stoppe)")
    if "--open" in sys.argv:
        threading.Timer(0.5, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()
    server.serve_forever()
