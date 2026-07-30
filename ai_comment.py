"""
Comentario con IA (Claude) sobre el estado del USD/CLP.

Toma el analisis por reglas (analysis.analizar) y lo convierte en un parrafo
corto en español para leer y reaccionar rapido.

Si NO hay API key o la llamada falla, devuelve None -> el bot usa solo el
formato por reglas. Asi nunca se rompe por culpa de la IA.
"""
import os
import json
import time
import requests
import config as C

API_URL = "https://api.anthropic.com/v1/messages"

HERE = os.path.dirname(os.path.abspath(__file__))
_BREAKER_FILE = os.path.join(HERE, "ai_breaker.json")
_BREAKER_TTL = 6 * 3600   # 6 horas apagada tras un fallo de saldo/permiso


def _breaker_open():
    try:
        until = json.load(open(_BREAKER_FILE)).get("until", 0)
        return time.time() < until
    except Exception:
        return False


def _trip_breaker():
    try:
        json.dump({"until": time.time() + _BREAKER_TTL}, open(_BREAKER_FILE, "w"))
    except Exception:
        pass


def _call(prompt, max_tokens=350):
    if not C.USE_AI or not C.ANTHROPIC_API_KEY or _breaker_open():
        return None
    headers = {
        "x-api-key": C.ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": C.AI_MODEL,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    try:
        r = requests.post(API_URL, headers=headers, data=json.dumps(body), timeout=30)
        if r.status_code != 200:
            print("IA respondio", r.status_code, r.text[:200])
            if r.status_code in (400, 401, 403):
                _trip_breaker()
            return None
        return r.json()["content"][0]["text"].strip()
    except Exception as e:
        print("IA error:", e)
        return None


def comentar(a, noticias=None):
    """Recibe el dict de analysis.analizar() (y opcionalmente titulares) y
    devuelve un parrafo corto en español, o None."""
    cobre = a.get("cobre") or {}
    dxy = a.get("dxy") or {}
    brl = a.get("brl") or {}
    cr = a.get("correls") or {}
    v = a.get("valor")
    corr_txt = ", ".join(f"{k} {cr[k]:+.2f}" for k in ("cobre", "dxy", "brl") if k in cr) or "n/d"
    valor_txt = "n/d"
    if v:
        estado = "caro" if v["z"] >= 1 else ("barato" if v["z"] <= -1 else "en línea")
        valor_txt = f"valor justo {v['predicho']:.0f}, precio {v['real']:.0f} ({v['gap']:+.0f}, {estado})"
    datos = (
        f"USD/CLP: {a['price']:.2f} ({a['change_pct']:+.2f}% hoy), "
        f"tendencia propia {a['trend_clp'][0]}.\n"
        f"RSI: {a.get('rsi') and round(a['rsi']) or 'n/d'} (sobre 70 = sobrecompra, bajo 30 = sobreventa). "
        f"Volatilidad diaria ~{a.get('atr_pct') and round(a['atr_pct'],1) or '?'}%.\n"
        f"Cobre: {cobre.get('price', '?')} USD/lb, tendencia {a['trend_cu'][0]}.\n"
        f"DXY (dolar global): {dxy.get('price', '?')}, tendencia {a['trend_dxy'][0]}.\n"
        f"Real brasileño (USD/BRL): {brl.get('price', '?')}, tendencia {a['trend_brl'][0]}.\n"
        f"Correlaciones USD/CLP con cada motor (40 dias): {corr_txt}. "
        f"Un motor con correlacion fuerte es el que mas manda ahora.\n"
        f"Valor relativo (regresion cobre+DXY+real): {valor_txt}.\n"
        f"Estado actual (presión de los motores, nowcast): {a['sesgo']} (fuerza {a['score']:+d} de -100 a +100).\n"
        f"Soportes: {', '.join(f'{p:.0f}' for p in a['soportes']) or 'n/d'}. "
        f"Resistencias: {', '.join(f'{p:.0f}' for p in a['resistencias']) or 'n/d'}."
    )
    fib = a.get("fib")
    if fib:
        rc, pc = fib["cerca"]
        datos += f"\nFibonacci: precio cerca del nivel {rc:.3f} ({pc:.0f}), impulso {fib['dir']}."
    if a.get("riesgos"):
        datos += "\nRiesgos detectados:\n" + "\n".join(f"- {x}" for x in a["riesgos"][:4])
    ev = a.get("eventos") or []
    altos = [e for e in ev if e["impacto"] == "High"][:3]
    if altos:
        datos += "\nReportes de alto impacto próximos:\n" + "\n".join(
            f"- {e['cuando']} {e['hora']} {e['titulo']}" for e in altos)
    if noticias:
        titulares = "\n".join(f"- {n['titulo']}" for n in noticias[:5])
        datos += f"\n\nTitulares recientes de prensa chilena:\n{titulares}"
    prompt = (
        "Eres un analista de mercado especializado en el peso chileno (USD/CLP). "
        "Recuerda las relaciones: el COBRE mueve al peso de forma INVERSA (cobre "
        "sube -> peso se fortalece -> USD/CLP baja) porque Chile es el mayor "
        "productor de cobre; el DXY (dolar global) y el REAL brasileño (USD/BRL) "
        "lo mueven de forma DIRECTA (el CLP sigue de cerca al real por ser ambas "
        "monedas emergentes ligadas a materias primas). "
        "Con los datos y titulares de abajo, escribe en español un comentario de "
        "3-5 frases, claro y para alguien sin formacion tecnica, DESCRIBIENDO el "
        "ESTADO ACTUAL: que motor esta mandando ahora, por que el peso esta donde "
        "esta, el RIESGO o REPORTE proximo mas importante si lo hay, y como encajan "
        "las noticias. "
        "IMPORTANTE: esto es un NOWCAST (foto del momento), NO un pronostico. NO "
        "predigas si el dolar va a subir o bajar; describe el presente, no el futuro. "
        "Puedes senalar que NIVELES o EVENTOS vigilar (eso es prudencia, no prediccion). "
        "No inventes datos que no esten aca. No des consejo de inversion.\n\n"
        f"DATOS:\n{datos}"
    )
    return _call(prompt, max_tokens=450)
