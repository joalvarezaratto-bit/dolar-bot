"""
Contexto ESTRATÉGICO (largo plazo) para el USD/CLP:

  1) RÉGIMEN de riesgo (risk-on / risk-off): VIX + S&P 500. En risk-off, las
     monedas emergentes como el peso sufren aunque el cobre esté bien.
  2) VALORACIÓN de largo plazo: dónde está el USD/CLP vs su propia historia de
     3 años (promedio + percentil).

HONESTO: es marco estratégico (semanas/meses), NO señal para operar hoy. Una
moneda puede quedarse "cara" o "barata" mucho tiempo; esto ubica el punto de
partida, no da timing.
"""
import numpy as np
import requests
import config as C
import datasource as ds

UA = {"User-Agent": "Mozilla/5.0"}


# --------------------------- régimen de riesgo -----------------------
def regimen():
    """Clasifica el apetito por riesgo global. dict o None."""
    vixd = ds.get(C.SYM_VIX)
    spxd = ds.get(C.SYM_SPX)
    if not vixd or vixd.get("price") is None:
        return None
    vix = vixd["price"]
    if vix < 16:
        nivel, emoji = "risk-on (calma)", "🟢"
    elif vix < 22:
        nivel, emoji = "neutral", "⚪"
    elif vix < 30:
        nivel, emoji = "nervioso", "🟠"
    else:
        nivel, emoji = "risk-off (miedo)", "🔴"
    return {"vix": vix, "vix_chg": vixd.get("change_pct", 0.0),
            "spx_chg": (spxd or {}).get("change_pct"), "nivel": nivel, "emoji": emoji}


def regimen_line():
    r = regimen()
    if not r:
        return ""
    subiendo = r["vix_chg"] > 3
    bajando = r["vix_chg"] < -3
    flecha = "↑ subiendo" if subiendo else ("↓ bajando" if bajando else "estable")
    # efecto sobre el peso
    if r["vix"] >= 22:
        efecto = "presión sobre el peso (aversión al riesgo emergente)"
    elif r["vix"] < 16 and not subiendo:
        efecto = "apoyo al peso (apetito por riesgo)"
    else:
        efecto = "sin sesgo claro de riesgo"
    sp = f" · S&P {r['spx_chg']:+.1f}%" if r["spx_chg"] is not None else ""
    return (f"🌡️ <b>Régimen</b>: {r['emoji']} {r['nivel']} · VIX {r['vix']:.1f} ({flecha}){sp}\n"
            f"   → {efecto}")


# --------------------------- valoración largo plazo ------------------
def _closes_largo(sym, rng="3y"):
    for host in ("query1", "query2"):
        try:
            r = requests.get(f"https://{host}.finance.yahoo.com/v8/finance/chart/{sym}",
                             params={"interval": "1d", "range": rng}, headers=UA, timeout=20)
            res = r.json()["chart"]["result"][0]
            return [x for x in res["indicators"]["quote"][0]["close"] if x is not None]
        except Exception:
            continue
    return []


def valoracion(price):
    """Ubica el precio actual vs la historia de 3 años. dict o None."""
    closes = _closes_largo(C.SYM_USDCLP)
    if len(closes) < 200:
        return None
    a = np.array(closes, dtype=float)
    prom = float(a.mean())
    pctl = int((a < price).mean() * 100)
    return {"prom": prom, "pctl": pctl, "min": float(a.min()), "max": float(a.max())}


def valoracion_line(price):
    v = valoracion(price)
    if not v:
        return ""
    if v["pctl"] < 30:
        lectura = "dólar BARATO / peso fuerte vs su historia"
    elif v["pctl"] > 70:
        lectura = "dólar CARO / peso débil vs su historia"
    else:
        lectura = "en rango normal vs su historia"
    return (f"📐 <b>Valoración 3 años</b>: {price:,.0f} vs promedio {v['prom']:,.0f} · "
            f"percentil <b>{v['pctl']}</b>/100 → {lectura}\n"
            f"   <i>puede quedarse así mucho tiempo; ubica el punto de partida, no da timing</i>")
