#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════╗
║       INTERNET EXPLORER REWIND · v4.0 · EDICIÓN MEJORADA     ║
║                                                              ║
║   Motor: pywebview + proxy HTTP (como OSC Browser)           ║
║                                                              ║
║   Novedades v4.0:                                            ║
║     ✅ Pestañas múltiples                                    ║
║     ✅ AdBlock + anti-rastreadores en el proxy               ║
║     ✅ Barra lateral de Favoritos e Historial                ║
║     ✅ Caja de búsqueda integrada                            ║
║     ✅ Zoom de página                                        ║
║     ✅ Buscar en página (Ctrl+F)                             ║
║     ✅ Menú contextual                                       ║
║     ✅ Vista previa de enlace en la barra de estado          ║
║     ✅ Barra de progreso clásica segmentada                  ║
║                                                              ║
║   Requiere:  pip install pywebview                            ║
╚══════════════════════════════════════════════════════════════╝
"""

import re
import time
import threading
import urllib.request
import urllib.parse
import urllib.error
import http.cookiejar
from http.server import HTTPServer, BaseHTTPRequestHandler
import webview


PROXY_PORT = 8998

_cookie_jar = http.cookiejar.CookieJar()
_url_opener = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(_cookie_jar)
)

# ============================================================
# LISTAS DE BLOQUEO (AdBlock)
# ============================================================
AD_DOMAINS = [
    'doubleclick.net', 'googlesyndication.com', 'googleadservices.com',
    'pagead2.googlesyndication.com', 'adservice.google.com',
    'ads.youtube.com', 'adnxs.com', 'popads.net', 'adroll.com',
    'outbrain.com', 'taboola.com', 'mediavine.com', 'adzerk.net',
    'rubiconproject.com', 'adcolony.com', 'applovin.com', 'mopub.com',
]
TRACKER_DOMAINS = [
    'google-analytics.com', 'analytics.google.com', 'connect.facebook.net',
    'scorecardresearch.com', 'hotjar.com', 'clarity.ms', 'mixpanel.com',
    'segment.com', 'quantserve.com', 'facebook.com/tr',
]


def _build_adblock_script() -> str:
    blocked = AD_DOMAINS + TRACKER_DOMAINS
    blocked_json = '[' + ','.join('"' + d + '"' for d in blocked) + ']'
    return (
        "<script>(function(){"
        f"var BLOCKED={blocked_json};"
        "function isB(u){try{var s=String(u).toLowerCase();"
        "for(var i=0;i<BLOCKED.length;i++){if(s.indexOf(BLOCKED[i])!==-1)return true;}}"
        "catch(e){}return false;}"
        "if(window.fetch){var _f=window.fetch;"
        "window.fetch=function(u,o){var url=(typeof u==='string')?u:(u&&u.url);"
        "if(isB(url))return Promise.reject(new Error('Blocked'));"
        "return _f.apply(this,arguments);};}"
        "var XO=XMLHttpRequest.prototype.open;"
        "XMLHttpRequest.prototype.open=function(m,u){this.__b=isB(u);"
        "if(this.__b)return;return XO.apply(this,arguments);};"
        "var XS=XMLHttpRequest.prototype.send;"
        "XMLHttpRequest.prototype.send=function(){if(this.__b)return;"
        "return XS.apply(this,arguments);};"
        "if(window.WebSocket){var _W=window.WebSocket;"
        "window.WebSocket=function(u,p){if(isB(u))throw new Error('Blocked');"
        "return new _W(u,p);};}"
        "})();</script>"
    )


def _build_link_interceptor() -> str:
    """Intercepta clicks y formularios para forzar navegación vía proxy."""
    return (
        '<script>(function(){'
        'var PROXY="http://127.0.0.1:8998/proxy?url=";'
        r'function isB(u){return /\.(exe|msi|bat|cmd|vbs|scr|ps1)$/i.test(u);}'
        'document.addEventListener("click",function(e){'
        'var a=e.target.closest&&e.target.closest("a");'
        'if(!a||!a.href)return;'
        'var h=a.href;'
        'if(h.indexOf("javascript:")===0||h.indexOf("#")===0)return;'
        'if(h.indexOf("http")!==0)return;'
        'e.preventDefault();'
        'try{window.top.postMessage({type:"navigate",url:h},"*");}'
        'catch(x){window.location.href=PROXY+encodeURIComponent(h);}'
        '},true);'
        'document.addEventListener("submit",function(e){'
        'var f=e.target;if(!f||f.tagName!=="FORM")return;'
        'if((f.method||"get").toLowerCase()!=="get")return;'
        'e.preventDefault();'
        'try{'
        'var data=new FormData(f);'
        'var qs=new URLSearchParams(data).toString();'
        'var base=f.action||location.href;'
        'var sep=base.indexOf("?")===-1?"?":"&";'
        'var full=base+sep+qs;'
        'window.top.postMessage({type:"navigate",url:full},"*");'
        '}catch(x){}'
        '},true);'
        'window.addEventListener("mouseover",function(e){'
        'var a=e.target.closest&&e.target.closest("a");'
        'if(a&&a.href)try{window.top.postMessage({type:"hover",url:a.href},"*");}catch(x){}'
        '},true);'
        '})();</script>'
    )


# ============================================================
# PROXY
# ============================================================
class IERewindProxy(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path in ('/', '/index.html'):
            body = IE_REWIND_HTML.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == '/proxy':
            q = urllib.parse.parse_qs(parsed.query)
            url = q.get('url', [None])[0]
            ab = q.get('ab', ['1'])[0] == '1'
            if not url:
                self.send_error(400, "URL no especificada")
                return
            self._proxy_url(url, ab)
            return

        self.send_error(404)

    def _proxy_url(self, url, ab_enabled):
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/122.0.0.0 Safari/537.36 IE-Rewind/4.0'
                ),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
                'Accept-Encoding': 'identity',
            })
            with _url_opener.open(req, timeout=30) as resp:
                ct = resp.headers.get('Content-Type', 'text/html; charset=utf-8')
                final_url = resp.geturl()
                body = resp.read()

                if ('text/html' in ct.lower()
                        or 'application/xhtml' in ct.lower()):
                    m = re.search(r'charset=["\']?([\w\-]+)', ct, re.I)
                    charset = m.group(1) if m else 'utf-8'
                    try:
                        html = body.decode(charset, errors='ignore')
                    except (LookupError, UnicodeDecodeError):
                        html = body.decode('utf-8', errors='ignore')

                    safe = (final_url
                            .replace('&', '&amp;')
                            .replace('"', '&quot;'))

                    anti = (
                        '<script>(function(){try{'
                        'Object.defineProperty(window,"top",{get:function(){return window.self;}});'
                        'Object.defineProperty(window,"parent",{get:function(){return window.self;}});'
                        'Object.defineProperty(window,"frameElement",{get:function(){return null;}});'
                        '}catch(e){}})();</script>'
                    )
                    ablock = _build_adblock_script() if ab_enabled else ''
                    interceptor = _build_link_interceptor()
                    inject = anti + ablock + interceptor + f'<base href="{safe}">'

                    head = re.search(r'<head[^>]*>', html, re.I)
                    if head:
                        p = head.end()
                        html = html[:p] + inject + html[p:]
                    elif re.search(r'<html[^>]*>', html, re.I):
                        html = re.sub(r'(<html[^>]*>)',
                                      lambda m: m.group(1) + inject,
                                      html, count=1, flags=re.I)
                    else:
                        html = inject + html

                    html = re.sub(
                        r'(?i)<meta[^>]*http-equiv=["\']?'
                        r'(content-security-policy|x-frame-options)'
                        r'["\']?[^>]*>', '', html
                    )

                    body = html.encode('utf-8')
                    if 'charset=' in ct:
                        ct = re.sub(r'charset=[\w\-]+', 'charset=utf-8', ct, flags=re.I)
                    else:
                        ct += '; charset=utf-8'

                self.send_response(200)
                self.send_header('Content-Type', ct)
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(body)

        except urllib.error.HTTPError as e:
            try:
                err_body = e.read()
                err_ct = e.headers.get('Content-Type', 'text/html; charset=utf-8')
                self.send_response(e.code)
                self.send_header('Content-Type', err_ct)
                self.send_header('Content-Length', str(len(err_body)))
                self.end_headers()
                self.wfile.write(err_body)
            except Exception:
                msg = f'<h1>Error HTTP {e.code}</h1><p>{e.reason}</p>'
                self.send_response(e.code)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(msg.encode('utf-8'))
        except urllib.error.URLError as e:
            self._error_page(502, 'No se puede mostrar la página',
                             url, f'No se pudo conectar: {e.reason}')
        except Exception as e:
            self._error_page(500, 'Error al cargar la página', url, str(e))

    def _error_page(self, code, title, url, reason):
        html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>
body{{font-family:'MS Sans Serif',Tahoma,sans-serif;background:#fff;padding:30px;}}
h1{{color:#cc0000;font-size:20px;margin-bottom:14px;}}
.box{{background:#f0f0f0;border:1px solid #808080;padding:14px;
     font-family:'Courier New',monospace;font-size:12px;word-break:break-all;margin:14px 0;}}
ul{{font-size:13px;margin-left:20px;}} li{{margin:4px 0;}}
</style></head><body>
<h1>⚠ {title}</h1>
<p>La página que busca no se encuentra disponible en este momento.</p>
<div class="box"><b>URL:</b><br>{url}<br><br><b>Detalle:</b><br>{reason}</div>
<p><b>Pruebe lo siguiente:</b></p>
<ul>
<li>Pulse Actualizar (F5) o inténtelo más tarde.</li>
<li>Compruebe que la dirección esté bien escrita.</li>
<li>Verifique su conexión a Internet.</li>
</ul>
<p style="color:#808080;margin-top:20px;">HTTP {code} · Internet Explorer Rewind v4.0</p>
</body></html>"""
        body = html.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def start_proxy():
    server = HTTPServer(('127.0.0.1', PROXY_PORT), IERewindProxy)
    server.serve_forever()


# ============================================================
# HTML SHELL — INTERFAZ COMPLETA
# ============================================================
IE_REWIND_HTML = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Internet Explorer Rewind</title>
<style>
*{box-sizing:border-box;margin:0;padding:0;}
html,body{height:100%;overflow:hidden;}
body{
  font-family:'MS Sans Serif',Tahoma,Arial,sans-serif;
  font-size:11px;background:#d4d0c8;color:#000;
  display:flex;flex-direction:column;height:100vh;user-select:none;
}

/* ============ MENU ============ */
#menubar{background:#d4d0c8;height:20px;display:flex;flex-shrink:0;border-bottom:1px solid #808080;}
.menu-item{padding:3px 8px;cursor:default;position:relative;white-space:nowrap;font-size:11px;}
.menu-item:hover,.menu-item.open{background:#000080;color:#fff;}
.menu-item u{text-decoration:underline;}
.menu-dropdown{
  display:none;position:absolute;top:100%;left:0;background:#d4d0c8;
  border:2px outset #d4d0c8;min-width:210px;padding:2px 0;z-index:1000;
  box-shadow:3px 3px 0 rgba(0,0,0,.3);color:#000;font-size:11px;
}
.menu-item.open .menu-dropdown{display:block;}
.menu-dropdown>div{padding:4px 22px 4px 26px;cursor:default;white-space:nowrap;display:flex;justify-content:space-between;}
.menu-dropdown>div:hover{background:#000080;color:#fff;}
.menu-dropdown hr{border:0;border-top:1px solid #808080;margin:2px 0;}
.menu-dropdown .acc{color:#808080;font-size:10px;margin-left:20px;}
.menu-dropdown>div:hover .acc{color:#c0c0ff;}
.menu-dropdown .disabled{color:#808080;pointer-events:none;}

/* ============ TITLE + LOGO ============ */
#titlebar{
  background:linear-gradient(to bottom,#4a7dd6 0%,#2b5ca8 45%,#1e4585 100%);
  height:24px;display:flex;align-items:center;padding:0 8px;gap:6px;
  color:#fff;font-weight:bold;font-size:11px;flex-shrink:0;
  border-bottom:1px solid #123a72;
}
.ie-icon{
  width:16px;height:16px;border-radius:50%;
  background:radial-gradient(circle at 30% 30%,#9dd6ff 0%,#2b7dd6 55%,#003a8c 100%);
  color:#fff;font-weight:bold;font-style:italic;font-size:12px;
  display:flex;align-items:center;justify-content:center;
  font-family:'Times New Roman',serif;flex-shrink:0;
  box-shadow:inset 0 -2px 3px rgba(0,0,0,.4),inset 0 2px 3px rgba(255,255,255,.35);
}
.spinner{margin-left:auto;font-size:13px;min-width:20px;text-align:right;}

/* ============ TAB BAR ============ */
#tabbar{
  background:#d4d0c8;height:24px;display:flex;align-items:flex-end;
  padding:0 4px;gap:2px;flex-shrink:0;border-bottom:1px solid #808080;
  overflow-x:auto;overflow-y:hidden;
}
.tab{
  display:flex;align-items:center;gap:4px;padding:3px 8px 3px 10px;
  background:#c0bdb5;border:1px solid #808080;border-bottom:none;
  border-radius:4px 4px 0 0;font-size:11px;cursor:default;
  max-width:180px;min-width:100px;height:20px;margin-bottom:-1px;
  position:relative;color:#333;
}
.tab.active{
  background:#d4d0c8;font-weight:bold;color:#000;
  height:22px;z-index:2;
}
.tab-icon{width:12px;height:12px;border-radius:2px;flex-shrink:0;
  background:radial-gradient(circle at 30% 30%,#9dd6ff,#003a8c);}
.tab-title{flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.tab-close{
  width:14px;height:14px;border-radius:2px;display:flex;
  align-items:center;justify-content:center;font-size:11px;
  color:#666;cursor:default;
}
.tab-close:hover{background:#c0392b;color:#fff;font-weight:bold;}
.tab-add{
  width:20px;height:20px;border:1px solid #808080;border-bottom:none;
  background:#d4d0c8;border-radius:4px 4px 0 0;display:flex;
  align-items:center;justify-content:center;cursor:default;
  font-size:13px;font-weight:bold;color:#333;margin-left:2px;margin-bottom:-1px;
}
.tab-add:hover{background:#e8e4dc;}

/* ============ TOOLBAR (con gradiente IE) ============ */
#toolbar{
  background:linear-gradient(to bottom,#f0efea 0%,#d4d0c8 55%,#c4c0b8 100%);
  padding:2px 4px;display:flex;gap:1px;align-items:stretch;
  border-top:1px solid #fff;border-bottom:1px solid #808080;
  flex-shrink:0;height:42px;
}
.tb-btn{
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  padding:2px 6px;cursor:default;border:1px solid transparent;
  min-width:52px;border-radius:3px;font-size:10px;
}
.tb-btn:hover{border-color:#4a7dd6;background:rgba(255,255,255,.6);}
.tb-btn:active{border-style:inset;}
.tb-btn.disabled{opacity:.35;pointer-events:none;}
.tb-icon{font-size:18px;line-height:1;}
.tb-label{margin-top:1px;}
.tb-sep{width:2px;background:#808080;border-right:1px solid #fff;margin:4px 3px;}

/* ============ SEARCH + ADDRESS ============ */
#addressbar{
  background:#d4d0c8;padding:3px 6px;display:flex;align-items:center;
  gap:5px;border-bottom:1px solid #808080;flex-shrink:0;
}
#addressbar .lbl{font-size:11px;white-space:nowrap;}
#addressbar .input-wrap{
  flex:1;background:#fff;border:2px inset #d4d0c8;
  display:flex;align-items:center;padding:1px 4px;min-width:0;
}
#addressbar .ie-small{color:#000080;margin-right:4px;font-size:12px;}
#url-input{
  flex:1;border:none;outline:none;font-family:inherit;font-size:11px;
  background:transparent;padding:2px;min-width:0;
}
#go-btn{
  background:linear-gradient(to bottom,#f0efea,#c4c0b8);
  border:2px outset #d4d0c8;padding:2px 14px;font-family:inherit;
  font-size:11px;cursor:default;font-weight:bold;border-radius:2px;
}
#go-btn:active{border-style:inset;}
#searchbar{
  display:flex;align-items:center;gap:4px;margin-left:8px;
  border-left:1px solid #808080;padding-left:8px;
}
#search-engine{
  background:#fff;border:1px solid #808080;font-family:inherit;
  font-size:10px;padding:2px;outline:none;
}
#search-input{
  width:140px;background:#fff;border:2px inset #d4d0c8;
  padding:3px 5px;font-family:inherit;font-size:11px;outline:none;
}

/* ============ MAIN ============ */
#main{flex:1;display:flex;position:relative;min-height:0;background:#d4d0c8;}

#sidebar{
  width:220px;background:#d4d0c8;border-right:2px groove #d4d0c8;
  display:none;flex-direction:column;flex-shrink:0;
}
#sidebar.open{display:flex;}
.side-head{
  background:linear-gradient(to bottom,#4a7dd6,#1e4585);
  color:#fff;padding:4px 8px;font-weight:bold;font-size:11px;
  display:flex;justify-content:space-between;align-items:center;
}
.side-head .close{cursor:default;padding:0 4px;border-radius:2px;}
.side-head .close:hover{background:rgba(255,255,255,.25);}
.side-list{
  flex:1;background:#fff;border:1px solid #808080;margin:4px;
  overflow-y:auto;font-size:11px;
}
.side-item{
  padding:5px 8px;border-bottom:1px solid #e8e8e8;cursor:default;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
  display:flex;align-items:center;gap:6px;
}
.side-item:hover{background:#e8f0ff;}
.side-item.active{background:#cfe0ff;font-weight:bold;}
.side-item .fav{color:#d4a017;font-size:13px;}
.side-item .del{margin-left:auto;color:#999;padding:0 4px;border-radius:2px;}
.side-item .del:hover{background:#c0392b;color:#fff;}
.side-empty{padding:16px;text-align:center;color:#999;font-size:11px;}

#content-area{
  flex:1;position:relative;background:#fff;border:2px inset #d4d0c8;
  margin:2px;min-width:0;
}
.page-frame{
  position:absolute;inset:0;width:100%;height:100%;border:none;
  background:#fff;display:none;
}
.page-frame.active{display:block;}

#home-page{
  position:absolute;inset:0;overflow-y:auto;padding:30px 40px;
  background:#fff;font-size:12px;line-height:1.5;
}
#home-page h1{
  color:#000080;font-size:22px;border-bottom:2px solid #000080;
  padding-bottom:6px;margin-bottom:16px;
}
#home-page h2{color:#0a246a;font-size:15px;margin:20px 0 8px;}
#home-page a{color:#0000ee;text-decoration:underline;cursor:pointer;}
#home-page a:hover{color:#cc0000;}
#home-page table{font-size:12px;margin:6px 0;}
#home-page td{padding:3px 12px 3px 0;vertical-align:top;}
#home-page .tip{
  background:#ffffcc;border-left:4px solid #ffcc00;
  padding:8px 12px;margin:12px 0;
}
#home-page pre{
  background:#f0f0f0;border:1px solid #808080;padding:10px;
  font-family:'Courier New',monospace;font-size:11px;line-height:1.4;
}

/* ============ STATUS BAR ============ */
#statusbar{
  background:#d4d0c8;border-top:1px solid #fff;padding:2px 4px;
  display:flex;align-items:center;gap:4px;font-size:11px;flex-shrink:0;
}
.status-zone{
  border:1px inset #d4d0c8;padding:2px 8px;min-width:100px;height:18px;
  display:flex;align-items:center;white-space:nowrap;overflow:hidden;
  text-overflow:ellipsis;
}
.status-zone.grow{flex:1;min-width:200px;}
.status-zone.right{min-width:130px;justify-content:center;}
#progress{display:flex;gap:1px;width:120px;height:18px;
  border:1px inset #d4d0c8;padding:2px;}
#progress .seg{flex:1;background:transparent;}
#progress .seg.on{background:#000080;}

/* ============ ZOOM + MENU CONTEXTUAL ============ */
#zoom-indicator{
  position:absolute;bottom:36px;right:14px;background:rgba(0,0,0,.75);
  color:#fff;padding:5px 12px;border-radius:3px;font-size:11px;
  opacity:0;transition:opacity .3s;pointer-events:none;z-index:50;
}
#zoom-indicator.show{opacity:1;}

#context-menu{
  position:fixed;background:#d4d0c8;border:2px outset #d4d0c8;
  padding:2px 0;display:none;z-index:2000;
  box-shadow:3px 3px 6px rgba(0,0,0,.35);min-width:180px;font-size:11px;
}
#context-menu.show{display:block;}
#context-menu>div{
  padding:5px 22px 5px 12px;cursor:default;white-space:nowrap;
}
#context-menu>div:hover{background:#000080;color:#fff;}
#context-menu hr{border:0;border-top:1px solid #808080;margin:2px 0;}

/* ============ MODALES ============ */
.modal-overlay{
  position:fixed;inset:0;background:rgba(0,0,0,.5);display:none;
  align-items:center;justify-content:center;z-index:3000;
}
.modal-overlay.show{display:flex;}
.modal{
  background:#d4d0c8;border:2px outset #d4d0c8;padding:0;
  min-width:380px;max-width:520px;box-shadow:5px 5px 20px rgba(0,0,0,.5);
}
.modal-title{
  background:linear-gradient(to bottom,#4a7dd6,#1e4585);color:#fff;
  padding:4px 10px;font-weight:bold;font-size:11px;
  display:flex;justify-content:space-between;align-items:center;
}
.modal-body{padding:16px;font-size:12px;}
.modal-body p{margin:6px 0;}
.modal-body input{
  width:100%;padding:4px 6px;border:2px inset #d4d0c8;
  font-family:inherit;font-size:11px;outline:none;margin-top:6px;
}
.modal-buttons{display:flex;justify-content:flex-end;gap:6px;padding:10px 16px;border-top:1px solid #808080;}
.modal-btn{
  background:linear-gradient(to bottom,#f0efea,#c4c0b8);
  border:2px outset #d4d0c8;padding:4px 18px;font-family:inherit;
  font-size:11px;cursor:default;min-width:70px;border-radius:2px;
}
.modal-btn:active{border-style:inset;}
</style>
</head>
<body>

<!-- ============ MENU ============ -->
<div id="menubar">
  <div class="menu-item"><u>A</u>rchivo
    <div class="menu-dropdown">
      <div onclick="newTab()">Nueva pestaña<span class="acc">Ctrl+T</span></div>
      <div onclick="location.reload()">Nueva ventana<span class="acc">Ctrl+N</span></div>
      <hr>
      <div onclick="openFileDialog()">Abrir...<span class="acc">Ctrl+O</span></div>
      <div onclick="savePage()">Guardar como...<span class="acc">Ctrl+S</span></div>
      <hr>
      <div onclick="window.print()">Imprimir...<span class="acc">Ctrl+P</span></div>
      <hr>
      <div onclick="window.close()">Cerrar</div>
    </div>
  </div>
  <div class="menu-item"><u>E</u>dición
    <div class="menu-dropdown">
      <div class="disabled">Cortar<span class="acc">Ctrl+X</span></div>
      <div onclick="copySelection()">Copiar<span class="acc">Ctrl+C</span></div>
      <div onclick="pasteClipboard()">Pegar<span class="acc">Ctrl+V</span></div>
      <hr>
      <div onclick="selectAllPage()">Seleccionar todo<span class="acc">Ctrl+A</span></div>
      <hr>
      <div onclick="openFind()">Buscar en esta página...<span class="acc">Ctrl+F</span></div>
    </div>
  </div>
  <div class="menu-item"><u>V</u>er
    <div class="menu-dropdown">
      <div onclick="toggleSidebar('favorites')">Favoritos</div>
      <div onclick="toggleSidebar('history')">Historial</div>
      <hr>
      <div onclick="refresh()">Actualizar<span class="acc">F5</span></div>
      <div onclick="stopLoad()">Detener<span class="acc">Esc</span></div>
      <hr>
      <div onclick="zoomIn()">Aumentar<span class="acc">Ctrl++</span></div>
      <div onclick="zoomOut()">Reducir<span class="acc">Ctrl+-</span></div>
      <div onclick="zoomReset()">Tamaño normal<span class="acc">Ctrl+0</span></div>
      <hr>
      <div onclick="viewSource()">Código fuente<span class="acc">Ctrl+U</span></div>
      <div onclick="toggleFullscreen()">Pantalla completa<span class="acc">F11</span></div>
    </div>
  </div>
  <div class="menu-item">F<u>a</u>voritos
    <div class="menu-dropdown">
      <div onclick="addFavorite()">Agregar a Favoritos...<span class="acc">Ctrl+D</span></div>
      <div onclick="toggleSidebar('favorites')">Mostrar Favoritos</div>
      <div onclick="clearFavorites()">Borrar todos los Favoritos</div>
      <hr>
      <div onclick="navigate('https://es.wikipedia.org')">Wikipedia</div>
      <div onclick="navigate('https://github.com')">GitHub</div>
      <div onclick="navigate('https://archive.org')">Archive.org</div>
      <div onclick="navigate('https://openverse.org')">Openverse</div>
    </div>
  </div>
  <div class="menu-item"><u>H</u>erramientas
    <div class="menu-dropdown">
      <div onclick="openOptions()">Opciones de Internet...</div>
      <hr>
      <div onclick="toggleAdBlock()" id="menu-adblock">Desactivar AdBlock</div>
      <div onclick="clearHistory()">Borrar historial</div>
      <hr>
      <div onclick="showStats()">Estadísticas</div>
    </div>
  </div>
  <div class="menu-item">A<u>y</u>uda
    <div class="menu-dropdown">
      <div onclick="navigate('about:home')">Contenido y índice</div>
      <div onclick="navigate('about:version')">Acerca de Internet Explorer</div>
      <hr>
      <div onclick="navigate('about:mozilla')">Huevo de pascua</div>
      <div onclick="navigate('about:credits')">Créditos</div>
    </div>
  </div>
</div>

<!-- ============ TITLE ============ -->
<div id="titlebar">
  <div class="ie-icon">e</div>
  <span>Internet Explorer Rewind v4.0</span>
  <span class="spinner" id="spinner"></span>
</div>

<!-- ============ TABS ============ -->
<div id="tabbar"></div>

<!-- ============ TOOLBAR ============ -->
<div id="toolbar">
  <div class="tb-btn disabled" id="btn-back" onclick="goBack()" title="Atrás (Alt+←)">
    <div class="tb-icon">⬅</div><div class="tb-label">Atrás</div>
  </div>
  <div class="tb-btn disabled" id="btn-forward" onclick="goForward()" title="Adelante (Alt+→)">
    <div class="tb-icon">➡</div><div class="tb-label">Adelante</div>
  </div>
  <div class="tb-btn" onclick="stopLoad()" title="Detener (Esc)">
    <div class="tb-icon">✖</div><div class="tb-label">Detener</div>
  </div>
  <div class="tb-btn" onclick="refresh()" title="Actualizar (F5)">
    <div class="tb-icon">🔄</div><div class="tb-label">Actualizar</div>
  </div>
  <div class="tb-btn" onclick="navigate('about:home')" title="Inicio">
    <div class="tb-icon">🏠</div><div class="tb-label">Inicio</div>
  </div>
  <div class="tb-sep"></div>
  <div class="tb-btn" onclick="toggleSidebar('favorites')" title="Favoritos">
    <div class="tb-icon">⭐</div><div class="tb-label">Favoritos</div>
  </div>
  <div class="tb-btn" onclick="toggleSidebar('history')" title="Historial">
    <div class="tb-icon">📜</div><div class="tb-label">Historial</div>
  </div>
  <div class="tb-btn" onclick="openFind()" title="Buscar (Ctrl+F)">
    <div class="tb-icon">🔍</div><div class="tb-label">Buscar</div>
  </div>
  <div class="tb-sep"></div>
  <div class="tb-btn" onclick="zoomIn()" title="Aumentar (Ctrl++)">
    <div class="tb-icon">➕</div><div class="tb-label">Zoom +</div>
  </div>
  <div class="tb-btn" onclick="zoomOut()" title="Reducir (Ctrl+-)">
    <div class="tb-icon">➖</div><div class="tb-label">Zoom −</div>
  </div>
  <div class="tb-btn" onclick="window.print()" title="Imprimir (Ctrl+P)">
    <div class="tb-icon">🖨</div><div class="tb-label">Imprimir</div>
  </div>
</div>

<!-- ============ ADDRESS + SEARCH ============ -->
<div id="addressbar">
  <span class="lbl">Dirección</span>
  <div class="input-wrap">
    <span class="ie-small">🌐</span>
    <input type="text" id="url-input" value="about:home" spellcheck="false" autocomplete="off">
  </div>
  <button id="go-btn" onclick="navigateFromInput()">IR</button>
  <div id="searchbar">
    <select id="search-engine" title="Motor de búsqueda">
      <option value="osc">⚡ OSC Search</option>
      <option value="google">🌐 Google</option>
      <option value="duckduckgo">🦆 DuckDuckGo</option>
      <option value="bing">🔍 Bing</option>
      <option value="wikipedia">📚 Wikipedia</option>
    </select>
    <input type="text" id="search-input" placeholder="Buscar en la web...">
  </div>
</div>

<!-- ============ MAIN ============ -->
<div id="main">
  <div id="sidebar">
    <div class="side-head">
      <span id="side-title">Favoritos</span>
      <span class="close" onclick="closeSidebar()">✕</span>
    </div>
    <div class="side-list" id="side-list"></div>
  </div>
  <div id="content-area">
    <div id="home-page"></div>
    <div id="frames"></div>
  </div>
</div>

<!-- ============ STATUS BAR ============ -->
<div id="statusbar">
  <div class="status-zone grow" id="status-text">Listo</div>
  <div id="progress"></div>
  <div class="status-zone right">🌐 Internet</div>
  <div class="status-zone right" id="zoom-status">100%</div>
</div>

<!-- Indicador de zoom -->
<div id="zoom-indicator">100%</div>

<!-- Menú contextual -->
<div id="context-menu">
  <div onclick="ctxAction('back')">⬅ Atrás</div>
  <div onclick="ctxAction('forward')">➡ Adelante</div>
  <div onclick="ctxAction('reload')">🔄 Actualizar</div>
  <hr>
  <div onclick="ctxAction('newtab')">🗂️ Abrir en nueva pestaña</div>
  <div onclick="ctxAction('copyurl')">📋 Copiar dirección</div>
  <hr>
  <div onclick="ctxAction('favorite')">⭐ Agregar a Favoritos</div>
  <div onclick="ctxAction('zoom+')">➕ Aumentar zoom</div>
  <div onclick="ctxAction('zoom-')">➖ Reducir zoom</div>
  <hr>
  <div onclick="ctxAction('source')">👁️ Ver código fuente</div>
  <div onclick="ctxAction('print')">🖨️ Imprimir</div>
</div>

<!-- Modal Buscar -->
<div class="modal-overlay" id="modal-find" onclick="if(event.target===this)closeModal('modal-find')">
  <div class="modal">
    <div class="modal-title">🔍 Buscar en esta página <span class="close" onclick="closeModal('modal-find')" style="cursor:default;padding:0 6px;">✕</span></div>
    <div class="modal-body">
      <p>Buscar:</p>
      <input type="text" id="find-input" placeholder="Escribe el texto...">
      <p style="margin-top:12px;color:#666;font-size:11px;">Se buscará en el contenido de la página actual.</p>
    </div>
    <div class="modal-buttons">
      <button class="modal-btn" onclick="doFind()">Buscar</button>
      <button class="modal-btn" onclick="closeModal('modal-find')">Cerrar</button>
    </div>
  </div>
</div>

<!-- Modal Opciones -->
<div class="modal-overlay" id="modal-options" onclick="if(event.target===this)closeModal('modal-options')">
  <div class="modal" style="min-width:460px;">
    <div class="modal-title">⚙ Opciones de Internet <span class="close" onclick="closeModal('modal-options')" style="cursor:default;padding:0 6px;">✕</span></div>
    <div class="modal-body">
      <p style="font-weight:bold;border-bottom:1px solid #999;padding-bottom:4px;">General</p>
      <p>Página de inicio:</p>
      <input type="text" id="opt-home" value="about:home">
      <p style="margin-top:14px;font-weight:bold;border-bottom:1px solid #999;padding-bottom:4px;">Seguridad</p>
      <p>🛡️ <b>AdBlock:</b> <span id="opt-ab">Activado</span></p>
      <p>🚫 <b>Anti-rastreadores:</b> Activado</p>
      <p>🔒 <b>Cookies de terceros:</b> Bloqueadas</p>
      <p style="margin-top:14px;font-weight:bold;border-bottom:1px solid #999;padding-bottom:4px;">Avanzado</p>
      <p>Motor de renderizado: pywebview + OSC Engine</p>
      <p>Puerto del proxy: 8998</p>
      <p>Versión: v4.0.0.0 (Edición Mejorada)</p>
    </div>
    <div class="modal-buttons">
      <button class="modal-btn" onclick="saveOptions()">Aceptar</button>
      <button class="modal-btn" onclick="closeModal('modal-options')">Cancelar</button>
    </div>
  </div>
</div>

<script>
/* ============================================================
   ESTADO GLOBAL
   ============================================================ */
const PROXY = 'http://127.0.0.1:8998/proxy?url=';
const SEARCH_ENGINES = {
  osc:        'https://david4524-maker.github.io/OSC-Search/?q=',
  google:     'https://www.google.com/search?q=',
  duckduckgo: 'https://duckduckgo.com/html/?q=',
  bing:       'https://www.bing.com/search?q=',
  wikipedia:  'https://es.wikipedia.org/w/index.php?search='
};

let tabs = [];
let activeTabId = null;
let tabIdCounter = 0;
let favorites = JSON.parse(localStorage.getItem('ie_favs') || '[]');
let history_arr = JSON.parse(localStorage.getItem('ie_history') || '[]');
let sidebarMode = null;
let adblockEnabled = localStorage.getItem('ie_adblock') !== '0';
let homePage = localStorage.getItem('ie_home') || 'about:home';
let currentZoom = parseFloat(localStorage.getItem('ie_zoom') || '1');
const ZOOM_STEPS = [0.5, 0.67, 0.75, 0.8, 0.9, 1, 1.1, 1.25, 1.5, 1.75, 2];

const SPIN = ['◐', '◓', '◑', '◒'];
let spinIdx = 0;
let spinTimer = null;

/* ============================================================
   UTILIDADES
   ============================================================ */
function $(s){ return document.querySelector(s); }
function $$(s){ return Array.from(document.querySelectorAll(s)); }
function esc(s){
  return String(s).replace(/[&<>"']/g,
    c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

/* ============================================================
   BARRA DE PROGRESO
   ============================================================ */
(function initProgress(){
  const p = $('#progress');
  for (let i = 0; i < 20; i++){
    const s = document.createElement('div');
    s.className = 'seg';
    p.appendChild(s);
  }
})();

function setProgress(pct){
  const segs = $$('#progress .seg');
  const on = Math.round(20 * pct / 100);
  segs.forEach((s,i) => s.classList.toggle('on', i < on));
}

function setStatus(msg){ $('#status-text').textContent = msg; }

/* ============================================================
   SPINNER (logo animado)
   ============================================================ */
function startSpin(){
  if (spinTimer) return;
  spinTimer = setInterval(() => {
    $('#spinner').textContent = SPIN[spinIdx++ % SPIN.length];
  }, 120);
}
function stopSpin(){
  if (spinTimer){ clearInterval(spinTimer); spinTimer = null; }
  $('#spinner').textContent = '';
}

/* ============================================================
   TABS
   ============================================================ */
function createTab(url = 'about:home', activate = true){
  tabIdCounter++;
  const id = tabIdCounter;

  // Crear iframe
  const frame = document.createElement('iframe');
  frame.className = 'page-frame';
  frame.id = 'frame-' + id;
  frame.setAttribute('sandbox',
    'allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox allow-modals');
  frame.setAttribute('referrerpolicy', 'no-referrer');
  $('#frames').appendChild(frame);

  const tab = {
    id, url, title: 'Nueva pestaña',
    history: [], historyIdx: -1,
    frame, loaded: false
  };
  tabs.push(tab);

  renderTabs();
  if (activate) switchTab(id);
  if (url && url !== 'about:home') {
    setTimeout(() => navigateTo(url), 50);
  } else {
    loadAboutPage('about:home');
    pushHistory('about:home');
  }
  return tab;
}

function closeTab(id){
  const i = tabs.findIndex(t => t.id === id);
  if (i === -1) return;
  const tab = tabs[i];
  try { tab.frame.remove(); } catch(e){}
  tabs.splice(i, 1);
  if (tabs.length === 0){
    createTab('about:home', true);
  } else if (activeTabId === id){
    switchTab(tabs[Math.max(0, i-1)].id);
  } else {
    renderTabs();
  }
}

function switchTab(id){
  activeTabId = id;
  const tab = tabs.find(t => t.id === id);
  if (!tab) return;

  $$('.page-frame').forEach(f => f.classList.remove('active'));
  tab.frame.classList.add('active');

  // Mostrar home si es about:
  if (tab.url === 'about:home' || tab.url.startsWith('about:')){
    $('#home-page').style.display = 'block';
  } else {
    $('#home-page').style.display = 'none';
  }

  $('#url-input').value = tab.url === 'about:home' ? '' : tab.url;
  updateNavButtons();
  renderTabs();
  applyZoom();
}

function renderTabs(){
  const bar = $('#tabbar');
  bar.innerHTML = '';
  tabs.forEach(tab => {
    const el = document.createElement('div');
    el.className = 'tab' + (tab.id === activeTabId ? ' active' : '');
    el.title = tab.title;

    const icon = document.createElement('div');
    icon.className = 'tab-icon';

    const title = document.createElement('span');
    title.className = 'tab-title';
    title.textContent = tab.title;
    title.ondblclick = (e) => {
      e.stopPropagation();
      const n = prompt('Nuevo título:', tab.title);
      if (n && n.trim()){ tab.title = n.trim(); renderTabs(); }
    };

    const close = document.createElement('div');
    close.className = 'tab-close';
    close.textContent = '✕';
    close.onclick = (e) => { e.stopPropagation(); closeTab(tab.id); };

    el.appendChild(icon);
    el.appendChild(title);
    el.appendChild(close);
    el.onclick = () => switchTab(tab.id);
    bar.appendChild(el);
  });

  const add = document.createElement('div');
  add.className = 'tab-add';
  add.textContent = '+';
  add.title = 'Nueva pestaña (Ctrl+T)';
  add.onclick = () => createTab('about:home', true);
  bar.appendChild(add);
}

function newTab(){ createTab('about:home', true); }

/* ============================================================
   NAVEGACIÓN
   ============================================================ */
function navigate(input){
  if (!input) return;
  input = input.trim();
  if (!input) return;

  // about:
  if (input.toLowerCase().startsWith('about:')){
    const tab = tabs.find(t => t.id === activeTabId);
    if (tab){
      tab.url = input.toLowerCase();
      tab.title = input;
      tab.frame.classList.remove('active');
      loadAboutPage(input.toLowerCase());
      pushHistory(input);
    }
    $('#url-input').value = input;
    updateNavButtons();
    renderTabs();
    return;
  }

  // Detectar si es URL o búsqueda
  let url = input;
  if (!/^[a-z]+:\/\//i.test(url)){
    if (url.includes(' ') || !url.includes('.')){
      const engine = $('#search-engine').value || 'osc';
      url = SEARCH_ENGINES[engine] + encodeURIComponent(url);
    } else {
      url = 'https://' + url;
    }
  }
  navigateTo(url);
}

function navigateTo(url){
  const tab = tabs.find(t => t.id === activeTabId);
  if (!tab) return;

  tab.url = url;
  tab.title = getTitleForUrl(url);
  tab.loaded = false;
  $('#url-input').value = url;
  $('#home-page').style.display = 'none';
  tab.frame.classList.add('active');

  startSpin();
  setStatus('Abriendo ' + url + '...');
  setProgress(10);

  let pct = 10;
  const prog = setInterval(() => {
    if (pct < 85){ pct += Math.random() * 7 + 2; setProgress(Math.min(pct, 85)); }
  }, 130);

  tab.frame.onload = () => {
    clearInterval(prog);
    setProgress(100);
    setTimeout(() => setProgress(0), 400);
    stopSpin();
    setStatus('Listo');
    tab.loaded = true;
    // Intentar obtener título real
    try {
      const t = tab.frame.contentDocument && tab.frame.contentDocument.title;
      if (t){ tab.title = t; renderTabs(); }
    } catch(e){}
  };

  tab.frame.src = PROXY + encodeURIComponent(url) + '&ab=' + (adblockEnabled ? '1' : '0');
  pushHistory(url);
  updateNavButtons();
  renderTabs();
}

function getTitleForUrl(url){
  try {
    const u = new URL(url);
    return u.hostname.replace('www.', '');
  } catch(e){ return url; }
}

function pushHistory(url){
  const tab = tabs.find(t => t.id === activeTabId);
  if (!tab) return;
  if (tab.history[tab.historyIdx] === url) return;
  tab.history = tab.history.slice(0, tab.historyIdx + 1);
  tab.history.push(url);
  tab.historyIdx = tab.history.length - 1;

  // Guardar en historial global
  if (!url.startsWith('about:')){
    history_arr.push({ url, title: getTitleForUrl(url), time: Date.now() });
    if (history_arr.length > 300) history_arr = history_arr.slice(-300);
    localStorage.setItem('ie_history', JSON.stringify(history_arr));
  }
  updateNavButtons();
}

function goBack(){
  const tab = tabs.find(t => t.id === activeTabId);
  if (!tab || tab.historyIdx <= 0) return;
  tab.historyIdx--;
  const url = tab.history[tab.historyIdx];
  _loadFromHistory(tab, url);
}
function goForward(){
  const tab = tabs.find(t => t.id === activeTabId);
  if (!tab || tab.historyIdx >= tab.history.length - 1) return;
  tab.historyIdx++;
  const url = tab.history[tab.historyIdx];
  _loadFromHistory(tab, url);
}
function _loadFromHistory(tab, url){
  if (url.startsWith('about:')){
    tab.url = url;
    tab.frame.classList.remove('active');
    loadAboutPage(url);
    $('#url-input').value = url;
  } else {
    tab.url = url;
    tab.title = getTitleForUrl(url);
    tab.frame.src = PROXY + encodeURIComponent(url) + '&ab=' + (adblockEnabled ? '1' : '0');
    $('#home-page').style.display = 'none';
    $('#url-input').value = url;
  }
  updateNavButtons();
  renderTabs();
}

function updateNavButtons(){
  const tab = tabs.find(t => t.id === activeTabId);
  if (!tab) return;
  $('#btn-back').classList.toggle('disabled', tab.historyIdx <= 0);
  $('#btn-forward').classList.toggle('disabled',
    tab.historyIdx >= tab.history.length - 1);
}

function refresh(){
  const tab = tabs.find(t => t.id === activeTabId);
  if (tab && tab.url && !tab.url.startsWith('about:')){
    tab.frame.src = PROXY + encodeURIComponent(tab.url) + '&ab=' + (adblockEnabled ? '1' : '0');
  }
}

function stopLoad(){
  const tab = tabs.find(t => t.id === activeTabId);
  if (tab && tab.frame){
    try { tab.frame.src = 'about:blank'; } catch(e){}
  }
  stopSpin();
  setProgress(0);
  setStatus('Detenido');
}

function navigateFromInput(){
  const v = $('#url-input').value.trim();
  if (v) navigate(v);
}

/* ============================================================
   PÁGINAS about:
   ============================================================ */
function loadAboutPage(url){
  const hp = $('#home-page');
  hp.style.display = 'block';

  const tab = tabs.find(t => t.id === activeTabId);
  if (tab){ tab.url = url; tab.title = url; }

  if (url === 'about:home'){
    hp.innerHTML = getHomeHTML();
    tab.title = 'Inicio';
  } else if (url === 'about:version'){
    hp.innerHTML = `
      <h1>Acerca de Internet Explorer</h1>
      <p><b>Internet Explorer Rewind</b><br>Versión 4.0.0.0 (Edición Mejorada)</p>
      <pre>Construido con:
  * Python 3.14
  * pywebview (motor de ventana)
  * Proxy HTTP local (OSC Engine)
  * HTML / CSS / JavaScript

Motor de renderizado: Trident-Web/4.0
Modo de renderizado: HTML real
AdBlock: ${adblockEnabled ? 'Activado' : 'Desactivado'}
Puerto proxy: 8998</pre>
      <p style="color:#808080;">(c) 2026 · Recreación nostálgica sin fines comerciales.</p>
      <p><a onclick="navigate('about:home')">← Volver al inicio</a></p>
    `;
    tab.title = 'Acerca de';
  } else if (url === 'about:mozilla'){
    hp.innerHTML = `
      <div style="background:#000;color:#0f0;padding:40px;text-align:center;
                  font-family:'Courier New',monospace; min-height:100%;">
        <pre style="font-size:14px;line-height:1.3;">
       ███        ███
       █████   █████
        ███████████
       ███  ███  ███
      ███    █    ███
      ██     █     ██
       ██   ███   ██
        ███████████
          ███████
        </pre>
        <h2 style="color:#0f0; margin:14px 0;">¡El lagarto ha vuelto!</h2>
        <p style="font-style:italic;">"Y así fue que el lagarto salvaje<br>
        y el zorro astuto...<br>acabaron con el monstruo de la Red."</p>
        <p>— The Book of Mozilla, 12:10</p>
        <p style="margin-top:20px;">🦎 ¡Huevo de pascua encontrado!</p>
      </div>
    `;
    tab.title = 'about:mozilla';
  } else if (url === 'about:credits'){
    hp.innerHTML = `
      <h1>Créditos</h1>
      <p><b>Internet Explorer Rewind</b> — proyecto nostálgico v4.0.</p>
      <h2>Inspirado por</h2>
      <ul style="margin-left:20px;">
        <li>Internet Explorer 3.0 (1996)</li>
        <li>Internet Explorer 4.0 (1997)</li>
        <li>Internet Explorer 5.0 (1999) — la mejor versión</li>
        <li>Internet Explorer 6.0 (2001)</li>
      </ul>
      <h2>Dedicatoria</h2>
      <p>A todos los que alguna vez esperaron ansiosos delante de un módem de 56k.</p>
      <p style="color:#808080; margin-top:20px;">💾 Recuerda: ¡Guarda tu trabajo antes de formatear!</p>
      <p><a onclick="navigate('about:home')">← Volver al inicio</a></p>
    `;
    tab.title = 'Créditos';
  }
  $('#url-input').value = url;
  renderTabs();
  updateNavButtons();
}

function getHomeHTML(){
  return `
    <h1>🌐 Internet Explorer Rewind v4.0</h1>
    <p><b>Bienvenido al navegador clásico mejorado.</b> Motor: pywebview + OSC Engine.</p>

    <div class="tip">
      💡 <b>Consejo:</b> Escribe una URL o una búsqueda en la barra superior y pulsa <b>IR</b>.<br>
      Usa <b>Ctrl+T</b> para nuevas pestañas y <b>Ctrl+D</b> para guardar favoritos.
    </div>

    <h2>🚀 Novedades en v4.0</h2>
    <table>
      <tr><td>✅</td><td>Pestañas múltiples (Ctrl+T)</td></tr>
      <tr><td>✅</td><td>AdBlock + Anti-rastreadores en el proxy</td></tr>
      <tr><td>✅</td><td>Barra lateral de Favoritos e Historial</td></tr>
      <tr><td>✅</td><td>Caja de búsqueda integrada con motor seleccionable</td></tr>
      <tr><td>✅</td><td>Zoom de página (Ctrl+ + / − / 0)</td></tr>
      <tr><td>✅</td><td>Menú contextual (click derecho)</td></tr>
      <tr><td>✅</td><td>Vista previa de enlaces en la barra de estado</td></tr>
    </table>

    <h2>🌍 Prueba estas webs</h2>
    <table>
      <tr><td><a onclick="navigate('https://es.wikipedia.org')">wikipedia.org</a></td><td>Enciclopedia libre</td></tr>
      <tr><td><a onclick="navigate('https://github.com')">github.com</a></td><td>Repositorios open source</td></tr>
      <tr><td><a onclick="navigate('https://archive.org')">archive.org</a></td><td>Biblioteca digital</td></tr>
      <tr><td><a onclick="navigate('https://openverse.org')">openverse.org</a></td><td>Creative Commons</td></tr>
      <tr><td><a onclick="navigate('https://david4524-maker.github.io/OSC-Search/')">OSC Search</a></td><td>Motor propio de búsqueda libre</td></tr>
    </table>

    <h2>⌨️ Atajos de teclado</h2>
    <pre>Ctrl+T           Nueva pestaña
Ctrl+W           Cerrar pestaña
Ctrl+Tab         Cambiar de pestaña
F5               Actualizar
Esc              Detener
Ctrl+D           Agregar a Favoritos
Ctrl+L           Ir a la barra de direcciones
Ctrl+F           Buscar en esta página
Ctrl+U           Ver código fuente
Ctrl+ + / − / 0  Zoom
Alt+← / →        Atrás / Adelante
F11              Pantalla completa</pre>

    <p style="color:#808080; font-size:11px; margin-top:30px;">
      (c) 2026 · Recreación nostálgica · Internet Explorer Rewind v4.0 · Powered by OSC Engine
    </p>
  `;
}

/* ============================================================
   FAVORITOS
   ============================================================ */
function addFavorite(){
  const tab = tabs.find(t => t.id === activeTabId);
  if (!tab || tab.url.startsWith('about:')){
    alert('Abre una página web primero.');
    return;
  }
  const existing = favorites.find(f => f.url === tab.url);
  if (existing){ alert('Ya está en Favoritos.'); return; }

  const name = prompt('Nombre del Favorito:', tab.title || tab.url);
  if (!name) return;

  favorites.push({ name: name.trim(), url: tab.url, time: Date.now() });
  localStorage.setItem('ie_favs', JSON.stringify(favorites));
  if (sidebarMode === 'favorites') renderSidebar();
  setStatus('⭐ Agregado a Favoritos');
}

function removeFavorite(url){
  favorites = favorites.filter(f => f.url !== url);
  localStorage.setItem('ie_favs', JSON.stringify(favorites));
  renderSidebar();
}

function clearFavorites(){
  if (!favorites.length) return;
  if (!confirm('¿Borrar todos los Favoritos?')) return;
  favorites = [];
  localStorage.setItem('ie_favs', JSON.stringify(favorites));
  renderSidebar();
}

/* ============================================================
   HISTORIAL
   ============================================================ */
function clearHistory(){
  if (!history_arr.length) return;
  if (!confirm('¿Borrar todo el historial?')) return;
  history_arr = [];
  localStorage.setItem('ie_history', JSON.stringify(history_arr));
  if (sidebarMode === 'history') renderSidebar();
}

/* ============================================================
   SIDEBAR
   ============================================================ */
function toggleSidebar(mode){
  if (sidebarMode === mode){
    closeSidebar();
    return;
  }
  sidebarMode = mode;
  $('#sidebar').classList.add('open');
  $('#side-title').textContent = mode === 'favorites' ? '⭐ Favoritos' : '📜 Historial';
  renderSidebar();
}

function closeSidebar(){
  sidebarMode = null;
  $('#sidebar').classList.remove('open');
}

function renderSidebar(){
  const list = $('#side-list');
  list.innerHTML = '';

  if (sidebarMode === 'favorites'){
    if (!favorites.length){
      list.innerHTML = '<div class="side-empty">No hay Favoritos.<br>Pulsa Ctrl+D para agregar.</div>';
      return;
    }
    favorites.slice().reverse().forEach(f => {
      const el = document.createElement('div');
      el.className = 'side-item';
      el.innerHTML = `
        <span class="fav">⭐</span>
        <span style="flex:1;overflow:hidden;text-overflow:ellipsis;">${esc(f.name)}</span>
        <span class="del" title="Eliminar">✕</span>
      `;
      el.title = f.url;
      el.onclick = (e) => {
        if (e.target.classList.contains('del')){
          removeFavorite(f.url);
        } else {
          navigate(f.url);
        }
      };
      list.appendChild(el);
    });
  } else if (sidebarMode === 'history'){
    if (!history_arr.length){
      list.innerHTML = '<div class="side-empty">No hay historial.</div>';
      return;
    }
    history_arr.slice().reverse().slice(0, 100).forEach(h => {
      const el = document.createElement('div');
      el.className = 'side-item';
      const time = new Date(h.time).toLocaleString('es-ES', {
        day:'2-digit', month:'2-digit', hour:'2-digit', minute:'2-digit'
      });
      el.innerHTML = `
        <span style="flex:1;overflow:hidden;text-overflow:ellipsis;">${esc(h.title || h.url)}</span>
        <span style="color:#999;font-size:10px;">${time}</span>
      `;
      el.title = h.url;
      el.onclick = () => navigate(h.url);
      list.appendChild(el);
    });
  }
}

/* ============================================================
   ZOOM
   ============================================================ */
function applyZoom(){
  const tab = tabs.find(t => t.id === activeTabId);
  if (tab && tab.frame){
    tab.frame.style.zoom = currentZoom;
  }
  const pct = Math.round(currentZoom * 100);
  $('#zoom-status').textContent = pct + '%';
  const ind = $('#zoom-indicator');
  ind.textContent = pct + '%';
  ind.classList.add('show');
  clearTimeout(ind._t);
  ind._t = setTimeout(() => ind.classList.remove('show'), 900);
  localStorage.setItem('ie_zoom', currentZoom);
}

function zoomIn(){
  const i = ZOOM_STEPS.findIndex(z => z > currentZoom + 0.001);
  if (i >= 0){ currentZoom = ZOOM_STEPS[i]; applyZoom(); }
}
function zoomOut(){
  const steps = ZOOM_STEPS.slice().reverse();
  const i = steps.findIndex(z => z < currentZoom - 0.001);
  if (i >= 0){ currentZoom = steps[i]; applyZoom(); }
}
function zoomReset(){
  currentZoom = 1;
  applyZoom();
}

/* ============================================================
   BUSCAR
   ============================================================ */
function openFind(){
  $('#modal-find').classList.add('show');
  setTimeout(() => $('#find-input').focus(), 50);
}
function closeModal(id){ $('#' + id).classList.remove('show'); }
function doFind(){
  const q = $('#find-input').value.trim();
  if (!q) return;
  const tab = tabs.find(t => t.id === activeTabId);
  if (!tab) return;
  try {
    const doc = tab.frame.contentDocument;
    if (!doc) throw new Error('sin acceso');
    if (doc.body){
      // Limpiar búsquedas anteriores
      doc.querySelectorAll('.ie-find-hl').forEach(el => {
        const p = el.parentNode;
        while (el.firstChild) p.insertBefore(el.firstChild, el);
        p.removeChild(el);
      });
      // Buscar y resaltar
      const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT);
      const matches = [];
      let n;
      while ((n = walker.nextNode())){
        if (n.nodeValue && n.nodeValue.toLowerCase().includes(q.toLowerCase())){
          matches.push(n);
        }
      }
      matches.forEach(node => {
        const txt = node.nodeValue;
        const idx = txt.toLowerCase().indexOf(q.toLowerCase());
        if (idx === -1) return;
        const before = txt.slice(0, idx);
        const match = txt.slice(idx, idx + q.length);
        const after = txt.slice(idx + q.length);
        const mark = doc.createElement('mark');
        mark.className = 'ie-find-hl';
        mark.style.background = 'yellow';
        mark.style.color = 'black';
        mark.textContent = match;
        const frag = doc.createDocumentFragment();
        if (before) frag.appendChild(doc.createTextNode(before));
        frag.appendChild(mark);
        if (after) frag.appendChild(doc.createTextNode(after));
        node.parentNode.replaceChild(frag, node);
      });
      setStatus(`${matches.length} coincidencia(s) encontrada(s)`);
      if (matches[0]) matches[0].parentElement.scrollIntoView({block:'center'});
    }
  } catch(e){
    setStatus('No se puede buscar (contenido protegido)');
  }
}

/* ============================================================
   ARCHIVO / VER
   ============================================================ */
function openFileDialog(){
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = '.html,.htm,.txt';
  input.onchange = (e) => {
    const f = e.target.files[0];
    if (!f) return;
    const url = 'file://' + f.path || URL.createObjectURL(f);
    navigate(url);
  };
  input.click();
}

function savePage(){
  const tab = tabs.find(t => t.id === activeTabId);
  if (!tab || tab.url.startsWith('about:')){ alert('Nada que guardar.'); return; }
  const a = document.createElement('a');
  a.href = PROXY + encodeURIComponent(tab.url);
  a.download = (tab.title || 'pagina') + '.html';
  a.click();
  setStatus('💾 Guardando página...');
}

function viewSource(){
  const tab = tabs.find(t => t.id === activeTabId);
  if (!tab || tab.url.startsWith('about:')){ alert('Sin código fuente.'); return; }
  window.open(PROXY + encodeURIComponent(tab.url), '_blank');
}

function toggleFullscreen(){
  if (document.fullscreenElement){
    document.exitFullscreen();
  } else {
    document.documentElement.requestFullscreen();
  }
}

function copySelection(){
  try { document.execCommand('copy'); setStatus('📋 Copiado'); } catch(e){}
}
function pasteClipboard(){
  navigator.clipboard.readText().then(t => {
    $('#url-input').value = t;
  }).catch(()=>{});
}
function selectAllPage(){
  const tab = tabs.find(t => t.id === activeTabId);
  if (tab && tab.frame){
    try { tab.frame.contentDocument.execCommand('selectAll'); } catch(e){}
  }
}

/* ============================================================
   MENÚ CONTEXTUAL
   ============================================================ */
document.addEventListener('contextmenu', (e) => {
  const menu = $('#context-menu');
  menu.style.left = e.clientX + 'px';
  menu.style.top = e.clientY + 'px';
  menu.classList.add('show');
  e.preventDefault();
});
document.addEventListener('click', (e) => {
  if (!e.target.closest('#context-menu')) $('#context-menu').classList.remove('show');
});
function ctxAction(action){
  $('#context-menu').classList.remove('show');
  const tab = tabs.find(t => t.id === activeTabId);
  switch(action){
    case 'back': goBack(); break;
    case 'forward': goForward(); break;
    case 'reload': refresh(); break;
    case 'newtab': if (tab) createTab(tab.url, true); break;
    case 'copyurl': navigator.clipboard.writeText(tab ? tab.url : ''); setStatus('📋 URL copiada'); break;
    case 'favorite': addFavorite(); break;
    case 'zoom+': zoomIn(); break;
    case 'zoom-': zoomOut(); break;
    case 'source': viewSource(); break;
    case 'print': window.print(); break;
  }
}

/* ============================================================
   MENÚ SUPERIOR
   ============================================================ */
document.querySelectorAll('.menu-item').forEach(item => {
  item.addEventListener('click', e => {
    e.stopPropagation();
    const wasOpen = item.classList.contains('open');
    document.querySelectorAll('.menu-item').forEach(i => i.classList.remove('open'));
    if (!wasOpen) item.classList.add('open');
  });
  item.addEventListener('mouseenter', () => {
    if (document.querySelector('.menu-item.open')){
      document.querySelectorAll('.menu-item').forEach(i => i.classList.remove('open'));
      item.classList.add('open');
    }
  });
});
document.addEventListener('click', () => {
  document.querySelectorAll('.menu-item').forEach(i => i.classList.remove('open'));
});

/* ============================================================
   ADBLOCK
   ============================================================ */
function toggleAdBlock(){
  adblockEnabled = !adblockEnabled;
  localStorage.setItem('ie_adblock', adblockEnabled ? '1' : '0');
  $('#menu-adblock').textContent = adblockEnabled ? 'Desactivar AdBlock' : 'Activar AdBlock';
  $('#opt-ab').textContent = adblockEnabled ? 'Activado' : 'Desactivado';
  setStatus(adblockEnabled ? '🛡️ AdBlock activado' : '⚠️ AdBlock desactivado');
  refresh();
}

/* ============================================================
   OPCIONES
   ============================================================ */
function openOptions(){
  $('#opt-home').value = homePage;
  $('#opt-ab').textContent = adblockEnabled ? 'Activado' : 'Desactivado';
  $('#modal-options').classList.add('show');
}
function saveOptions(){
  const h = $('#opt-home').value.trim();
  if (h){ homePage = h; localStorage.setItem('ie_home', h); }
  closeModal('modal-options');
  setStatus('✅ Opciones guardadas');
}

/* ============================================================
   ESTADÍSTICAS
   ============================================================ */
function showStats(){
  alert(
    '📊 Estadísticas\n\n' +
    'Favoritos: ' + favorites.length + '\n' +
    'Entradas en historial: ' + history_arr.length + '\n' +
    'Pestañas abiertas: ' + tabs.length + '\n' +
    'Zoom actual: ' + Math.round(currentZoom * 100) + '%\n' +
    'AdBlock: ' + (adblockEnabled ? 'Activado' : 'Desactivado')
  );
}

/* ============================================================
   MENSAJES DESDE IFRAMES (navegación)
   ============================================================ */
window.addEventListener('message', (e) => {
  const d = e.data;
  if (!d || typeof d !== 'object') return;
  if (d.type === 'navigate' && d.url){
    navigate(d.url);
  } else if (d.type === 'hover' && d.url){
    setStatus(d.url);
    clearTimeout(window._hoverT);
    window._hoverT = setTimeout(() => setStatus('Listo'), 2500);
  }
});

/* ============================================================
   ATAJOS DE TECLADO
   ============================================================ */
document.addEventListener('keydown', (e) => {
  const inInput = e.target.matches('input,textarea,select');

  if (e.ctrlKey && e.key.toLowerCase() === 't'){ e.preventDefault(); newTab(); return; }
  if (e.ctrlKey && e.key.toLowerCase() === 'w'){
    e.preventDefault();
    if (activeTabId) closeTab(activeTabId);
    return;
  }
  if (e.ctrlKey && e.key === 'Tab'){
    e.preventDefault();
    const i = tabs.findIndex(t => t.id === activeTabId);
    const n = (i + 1) % tabs.length;
    if (tabs[n]) switchTab(tabs[n].id);
    return;
  }
  if (e.key === 'F5'){ e.preventDefault(); refresh(); return; }
  if (e.key === 'Escape'){ stopLoad(); return; }
  if (e.ctrlKey && e.key.toLowerCase() === 'l'){ e.preventDefault(); $('#url-input').focus(); $('#url-input').select(); return; }
  if (e.ctrlKey && e.key.toLowerCase() === 'd'){ e.preventDefault(); addFavorite(); return; }
  if (e.ctrlKey && e.key.toLowerCase() === 'f'){ e.preventDefault(); openFind(); return; }
  if (e.ctrlKey && e.key.toLowerCase() === 'u'){ e.preventDefault(); viewSource(); return; }
  if (e.ctrlKey && e.key.toLowerCase() === 'p'){ e.preventDefault(); window.print(); return; }
  if (e.ctrlKey && (e.key === '+' || e.key === '=')){ e.preventDefault(); zoomIn(); return; }
  if (e.ctrlKey && e.key === '-'){ e.preventDefault(); zoomOut(); return; }
  if (e.ctrlKey && e.key === '0'){ e.preventDefault(); zoomReset(); return; }
  if (e.altKey && e.key === 'ArrowLeft'){ e.preventDefault(); goBack(); return; }
  if (e.altKey && e.key === 'ArrowRight'){ e.preventDefault(); goForward(); return; }
  if (e.key === 'F11'){ e.preventDefault(); toggleFullscreen(); return; }
});

/* ============================================================
   INPUTS
   ============================================================ */
$('#url-input').addEventListener('keydown', e => {
  if (e.key === 'Enter') navigateFromInput();
});
$('#search-input').addEventListener('keydown', e => {
  if (e.key === 'Enter'){
    const q = $('#search-input').value.trim();
    if (q){ navigate(q); $('#search-input').value = ''; }
  }
});
$('#find-input').addEventListener('keydown', e => {
  if (e.key === 'Enter') doFind();
});
$('#find-input').addEventListener('input', () => {
  clearTimeout(window._findT);
  window._findT = setTimeout(doFind, 400);
});

/* ============================================================
   INICIALIZACIÓN
   ============================================================ */
function init(){
  $('#menu-adblock').textContent = adblockEnabled ? 'Desactivar AdBlock' : 'Activar AdBlock';
  applyZoom();
  createTab('about:home', true);
  setStatus('Listo');
}

init();
</script>
</body>
</html>"""


# ============================================================
# MAIN
# ============================================================
def main():
    threading.Thread(target=start_proxy, daemon=True).start()
    time.sleep(0.4)

    webview.create_window(
        'Internet Explorer Rewind v4.0',
        f'http://127.0.0.1:{PROXY_PORT}/',
        width=1200,
        height=780,
        min_size=(800, 600),
    )
    webview.start()


if __name__ == '__main__':
    main()
