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


RESULT_SEEN_FILE = os.path.join(HERE, "eventos_seen.json")


def _clave_ev(e):
    return f"{e['fecha']:%Y-%m-%d}|{e['titulo']}"


def _load_result_seen():
    try:
        return set(json.load(open(RESULT_SEEN_FILE)))
    except Exception:
        return set()


def _save_result_seen(seen):
    try:
        json.dump(list(seen)[-300:], open(RESULT_SEEN_FILE, "w"))
    except Exception:
        pass


def resultados_para_alertar():
    """Reportes de HOY, ALTO impacto, que YA tienen resultado y NO se han
    alertado todavia. No los marca: eso lo hace quien los envie."""
    seen = _load_result_seen()
    out = []
    for e in resultados_hoy():
        if e["impacto"] != "High" or not e["actual"]:
            continue
        if _clave_ev(e) in seen:
            continue
        out.append(e)
    return out


def marcar_resultados_vistos(evs):
    seen = _load_result_seen()
    for e in evs:
        seen.add(_clave_ev(e))
    _save_result_seen(seen)


def sembrar_resultados():
    """Marca como vistos TODOS los resultados ya publicados de hoy (para no
    alertar retroactivamente en la primera corrida)."""
    marcar_resultados_vistos([e for e in resultados_hoy() if e["actual"]])


def alerta_resultado_telegram(e, contexto=""):
    """Formatea el resultado de un reporte como alerta instantanea (HTML)."""
    tag = "🥇" if e["es_cobre"] else "💵"
    interp = f" — <b>{e['interp']}</b>" if e["interp"] else ""
    ref = []
    if e["forecast"]:
        ref.append(f"esperado {e['forecast']}")
    if e["previous"]:
        ref.append(f"previo {e['previous']}")
    ref = f" ({', '.join(ref)})" if ref else ""
    L = [f"🚨 {tag} <b>RESULTADO: {e['titulo']}</b>",
         f"<b>{e['actual']}</b>{interp}{ref}"]
    if contexto:
        L.append(contexto)
    return "\n".join(L)


def _num(s):
    """Convierte '3.75%', '250K', '2.1M' a numero. None si no se puede."""
    if not s:
        return None
    s = str(s).replace("%", "").replace(",", "").strip()
    mult = 1
    if s and s[-1] in "KkMmBbTt":
        mult = {"k": 1e3, "m": 1e6, "b": 1e9, "t": 1e12}[s[-1].lower()]
        s = s[:-1]
    try:
        return float(s) * mult
    except Exception:
        return None


def _interpretar(titulo, actual, forecast, previous):
    """Traduce el resultado a algo legible: mantuvo/subio/bajo + si sorprendio."""
    a, p, fc = _num(actual), _num(previous), _num(forecast)
    partes = []
    low = titulo.lower()
    if any(k in low for k in ("rate", "funds")) and a is not None and p is not None:
        if abs(a - p) < 1e-9:
            partes.append("mantuvo")
        elif a > p:
            partes.append("subió")
        else:
            partes.append("bajó")
    if a is not None and fc is not None:
        if abs(a - fc) < 1e-9:
            partes.append("en línea con lo esperado")
        elif a > fc:
            partes.append("por encima de lo esperado")
        else:
            partes.append("por debajo de lo esperado")
    return ", ".join(partes)


def resultados_hoy():
    """Reportes de HOY cuya hora YA PASO. Devuelve dicts con actual/forecast/
    previous e interpretacion. Los que aun no tienen dato van con actual=''."""
    data = _get(force=True)   # refresca: el 'actual' se llena al salir el dato
    ahora = dt.datetime.now()
    out = []
    for e in data:
        if e.get("country") not in PAISES:
            continue
        imp = e.get("impact", "")
        if imp not in ("High", "Medium"):
            continue
        titulo = e.get("title", "")
        if imp == "Medium" and not any(k in titulo.lower() for k in CLAVE):
            continue
        f = _parse_fecha(e.get("date", ""))
        if not f or f.date() != ahora.date() or f > ahora:
            continue   # solo HOY y que ya haya ocurrido
        actual = e.get("actual", "")
        out.append({
            "hora": f"{f:%H:%M}", "fecha": f, "pais": e["country"], "impacto": imp,
            "titulo": titulo, "actual": actual, "forecast": e.get("forecast", ""),
            "previous": e.get("previous", ""), "es_cobre": e["country"] == "CNY",
            "interp": _interpretar(titulo, actual, e.get("forecast", ""), e.get("previous", "")),
        })
    out.sort(key=lambda x: x["fecha"])
    return out


def bloque_resultados_telegram():
    """Bloque 'Reportes de HOY ya publicados' para Telegram (HTML). '' si no hay."""
    evs = resultados_hoy()
    if not evs:
        return ""
    L = ["📊 <b>Reportes de HOY</b> (ya salieron)"]
    for e in evs[:6]:
        alto = "🔴" if e["impacto"] == "High" else "🟡"
        tag = "🥇" if e["es_cobre"] else "💵"
        if e["actual"]:
            interp = f" — <i>{e['interp']}</i>" if e["interp"] else ""
            esp = f" (esp. {e['forecast']})" if e["forecast"] else ""
            L.append(f"  {alto}{tag} {e['hora']} {e['titulo']}: <b>{e['actual']}</b>{esp}{interp}")
        else:
            esp = f" · esperado {e['forecast']}" if e["forecast"] else ""
            L.append(f"  {alto}{tag} {e['hora']} {e['titulo']}: ⏳ resultado pendiente{esp}")
    return "\n".join(L)


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
