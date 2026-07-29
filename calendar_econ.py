"""
Calendario de REPORTES economicos que mueven al USD/CLP.

Fuente: ForexFactory JSON gratis (sin API key), la misma que usa tu news-bot:
    https://nfs.faireconomy.media/ff_calendar_thisweek.json

Filtra lo que de verdad mueve al dolar/peso:
  - USD (Fed/FOMC, CPI, PCE, empleo/NFP, GDP...) -> el motor #1 del dolar global.
  - CNY (China) -> mueve al COBRE, y el cobre mueve al peso.

Un reporte de alto impacto proximo = RIESGO de evento: el USD/CLP puede pegar
un salto brusco cuando salga el dato. El agente lo avisa para que no te agarre
desprevenido.
"""
import os
import json
import time
import datetime as dt
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(HERE, "calendar_cache.json")
URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
UA = {"User-Agent": "Mozilla/5.0"}
TTL = 3 * 3600   # refresca cada 3 horas

PAISES = ("USD", "CNY")

# Palabras de los reportes que mas mueven al dolar/cobre (para priorizar).
CLAVE = ("federal funds", "fomc", "cpi", "pce", "non-farm", "nonfarm", "payroll",
         "unemployment", "gdp", "powell", "interest rate", "retail sales",
         "ism", "pmi", "jobless", "inflation", "manufacturing")


def _fetch():
    try:
        r = requests.get(URL, headers=UA, timeout=20)
        data = r.json()
        json.dump({"ts": time.time(), "data": data}, open(CACHE_FILE, "w"))
        return data
    except Exception as e:
        print("  (aviso) calendario:", str(e)[:80])
        try:
            return json.load(open(CACHE_FILE)).get("data", [])
        except Exception:
            return []


def _get(force=False):
    if not force and os.path.exists(CACHE_FILE):
        try:
            c = json.load(open(CACHE_FILE))
            if time.time() - c.get("ts", 0) < TTL:
                return c.get("data", [])
        except Exception:
            pass
    return _fetch()


def _parse_fecha(s):
    """Parsea la fecha ISO del evento (puede traer offset). Devuelve datetime naive local-ish."""
    try:
        d = dt.datetime.fromisoformat(s)
        if d.tzinfo is not None:
            d = d.astimezone().replace(tzinfo=None)
        return d
    except Exception:
        return None


def proximos(dias=3, solo_alto=False):
    """Reportes proximos (desde ahora hasta `dias` adelante) que mueven al peso.
    Devuelve lista de dicts {cuando, fecha, pais, impacto, titulo, forecast, previous, es_cobre}."""
    data = _get()
    ahora = dt.datetime.now()
    limite = ahora + dt.timedelta(days=dias)
    out = []
    for e in data:
        if e.get("country") not in PAISES:
            continue
        imp = e.get("impact", "")
        if imp not in ("High", "Medium"):
            continue
        if solo_alto and imp != "High":
            continue
        f = _parse_fecha(e.get("date", ""))
        if not f or f < ahora - dt.timedelta(hours=1) or f > limite:
            continue
        titulo = e.get("title", "")
        # Medium solo si es un reporte clave (evita ruido); High siempre entra.
        if imp == "Medium" and not any(k in titulo.lower() for k in CLAVE):
            continue
        dias_falta = (f.date() - ahora.date()).days
        cuando = "hoy" if dias_falta == 0 else ("mañana" if dias_falta == 1 else f"{f:%a %d}")
        out.append({
            "cuando": cuando,
            "fecha": f,
            "hora": f"{f:%H:%M}",
            "pais": e["country"],
            "impacto": imp,
            "titulo": titulo,
            "forecast": e.get("forecast", ""),
            "previous": e.get("previous", ""),
            "es_cobre": e["country"] == "CNY",
        })
    out.sort(key=lambda x: x["fecha"])
    return out


def bloque_telegram(dias=3):
    """Arma el bloque de proximos reportes para Telegram (HTML). '' si no hay."""
    evs = proximos(dias=dias)
    if not evs:
        return ""
    L = ["🗓️ <b>Próximos reportes</b> (mueven el dólar)"]
    for e in evs[:6]:
        alto = "🔴" if e["impacto"] == "High" else "🟡"
        tag = "🥇" if e["es_cobre"] else "💵"
        fc = f" · fc {e['forecast']}" if e["forecast"] else ""
        L.append(f"  {alto}{tag} <b>{e['cuando']} {e['hora']}</b> · {e['titulo']}{fc}")
    return "\n".join(L)
