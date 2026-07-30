"""
Pulso INTRADÍA: hacia dónde se mueve el USD/CLP en las últimas horas (velas de
60 min), como nowcast de la SESIÓN actual — el informe diario casi no cambia
dentro del día, esto sí refleja el momento.

Datos de Yahoo (gratis). HONESTO: describe el movimiento reciente, NO predice.
Si el mercado está cerrado, las velas quedan rancias -> el que llama debe evitar
mostrarlo (ya tenemos el estado de mercado para eso).
"""
import time
import requests
import model as M
import config as C

UA = {"User-Agent": "Mozilla/5.0"}
_CACHE = {}
TTL = 600   # 10 min: el informe corre cada 30, no hace falta más seguido


def _closes(sym, interval="60m", rng="5d"):
    now = time.time()
    c = _CACHE.get(sym)
    if c and now - c["ts"] < TTL:
        return c["closes"]
    try:
        r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}",
                         params={"interval": interval, "range": rng}, headers=UA, timeout=20)
        res = r.json()["chart"]["result"][0]
        q = res["indicators"]["quote"][0]["close"]
        closes = [x for x in q if x is not None]
        _CACHE[sym] = {"ts": now, "closes": closes}
        return closes
    except Exception:
        return c["closes"] if c else []


def _chg(closes, n):
    return (closes[-1] / closes[-1 - n] - 1) * 100 if len(closes) > n else None


def pulso():
    """Pulso intradía del USD/CLP + movimiento de la sesión de cobre y DXY.
    Devuelve dict o None si no hay datos."""
    clp = _closes(C.SYM_USDCLP)
    if len(clp) < 8:
        return None
    r3, r8 = _chg(clp, 3), _chg(clp, 8)     # ~3h y ~8h
    rsi = M.rsi(clp) if len(clp) > 15 else None
    base = r3 if r3 is not None else 0.0
    direccion = "subiendo" if base > 0.15 else ("bajando" if base < -0.15 else "plano/lateral")
    cu = _closes(C.SYM_COBRE)
    dx = _closes(C.SYM_DXY)
    return {"r3": r3, "r8": r8, "rsi": rsi, "dir": direccion,
            "cobre_3h": _chg(cu, 3) if cu else None,
            "dxy_3h": _chg(dx, 3) if dx else None}


def linea_telegram():
    """Línea lista para el informe (HTML). '' si no hay datos."""
    p = pulso()
    if not p:
        return ""
    flecha = "🔼" if p["dir"] == "subiendo" else ("🔽" if p["dir"] == "bajando" else "▪️")
    partes = [f"{flecha} <b>Pulso intradía</b>: dólar {p['dir']}"]
    if p["r3"] is not None:
        partes.append(f"{p['r3']:+.2f}% (3h)")
    if p["rsi"] is not None:
        partes.append(f"RSI 1h {p['rsi']:.0f}")
    linea = "  ·  ".join(partes)
    mot = []
    if p["cobre_3h"] is not None:
        mot.append(f"cobre {p['cobre_3h']:+.2f}%")
    if p["dxy_3h"] is not None:
        mot.append(f"DXY {p['dxy_3h']:+.2f}%")
    if mot:
        linea += "\n   <i>sesión: " + " · ".join(mot) + "</i>"
    return linea
