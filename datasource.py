"""
Datos de mercado desde Yahoo Finance (gratis, sin API key).

Trae, para cada instrumento (USD/CLP, cobre, DXY):
    - precio actual
    - % de variacion del dia (vs cierre anterior)
    - velas DIARIAS de los ultimos ~6 meses (para tendencia, medias y grafico)

Cachea en disco unos minutos para no golpear la API de Yahoo de mas.
Honesto: es el dato de mercado, no una prediccion.
"""
import os
import json
import time
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(HERE, "market_cache.json")
TTL = 300   # segundos: no volver a pedir lo mismo antes de 5 min
UA = {"User-Agent": "Mozilla/5.0"}

_MEM = {}   # cache en memoria del proceso: {symbol: {...}}


def _read_disk():
    if os.path.exists(CACHE_FILE):
        try:
            return json.load(open(CACHE_FILE))
        except Exception:
            pass
    return {}


def _write_disk(data):
    try:
        json.dump(data, open(CACHE_FILE, "w"))
    except Exception:
        pass


def _fetch_yahoo(symbol, interval="1d", rng="6mo"):
    """Pide a Yahoo el historico + precio en vivo de un simbolo.
    Devuelve dict {price, prev_close, change_pct, candles:[{t,o,h,l,c}], ts}
    o None si falla."""
    # failover: si query1 falla, se intenta query2 (mismo dato, otro host de Yahoo)
    res = None
    for host in ("query1", "query2"):
        try:
            r = requests.get(
                f"https://{host}.finance.yahoo.com/v8/finance/chart/{symbol}",
                params={"interval": interval, "range": rng},
                headers=UA, timeout=20)
            res = r.json()["chart"]["result"][0]
            break
        except Exception as e:
            err = str(e)[:60]
            continue
    if res is None:
        print(f"  (aviso) fallo Yahoo {symbol} en ambos hosts: {err}")
        return None
    try:
        meta = res["meta"]
        price = meta.get("regularMarketPrice")
        prev = meta.get("chartPreviousClose") or meta.get("previousClose") or price

        ts = res.get("timestamp", []) or []
        q = res["indicators"]["quote"][0]
        candles = []
        for i in range(len(ts)):
            o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
            if None in (o, h, l, c):
                continue   # Yahoo a veces deja huecos: se saltan
            candles.append({"t": ts[i], "o": o, "h": h, "l": l, "c": c})

        # limpiar bad ticks (mechas espurias) antes de cualquier calculo
        try:
            import model as _M
            candles = _M.limpiar_velas(candles)
        except Exception:
            pass

        # precio en vivo mas fiable = ultimo cierre de vela si falta el meta
        if price is None and candles:
            price = candles[-1]["c"]

        # % del dia: OJO, con rango de 6 meses el "chartPreviousClose" de Yahoo
        # es el cierre de hace 6 meses, no el de ayer. Para un % diario correcto
        # comparamos el precio en vivo con el CIERRE DIARIO ANTERIOR (penultima
        # vela, porque la ultima es la de hoy, todavia formandose).
        if len(candles) >= 2:
            prev = candles[-2]["c"]
        elif candles:
            prev = candles[-1]["c"]
        change_pct = ((price - prev) / prev * 100) if prev else 0.0
        return {"symbol": symbol, "price": price, "prev_close": prev,
                "change_pct": change_pct, "candles": candles, "ts": time.time(),
                # datos "del momento" para saber frescura y rango del dia
                "market_time": meta.get("regularMarketTime"),
                "market_state": meta.get("marketState"),
                "day_open": meta.get("regularMarketOpen"),
                "day_high": meta.get("regularMarketDayHigh"),
                "day_low": meta.get("regularMarketDayLow")}
    except Exception as e:
        print(f"  (aviso) fallo Yahoo {symbol}: {str(e)[:80]}")
        return None


def get(symbol, force=False):
    """Devuelve el dict de datos de un simbolo, usando cache si esta fresca."""
    now = time.time()
    m = _MEM.get(symbol)
    if m and not force and (now - m.get("ts", 0)) < TTL:
        return m

    disk = _read_disk()
    d = disk.get(symbol)
    if d and not force and (now - d.get("ts", 0)) < TTL:
        _MEM[symbol] = d
        return d

    fresh = _fetch_yahoo(symbol)
    if fresh:
        disk[symbol] = fresh
        _write_disk(disk)
        _MEM[symbol] = fresh
        return fresh

    # si Yahoo falla, devuelve la ultima copia que tengamos (mejor algo que nada)
    if d:
        _MEM[symbol] = d
        return d
    return None
