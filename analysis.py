"""
EL CEREBRO DEL AGENTE.

Combina los 3 motores del USD/CLP en un SESGO direccional con su "por que":

    USD/CLP  : su propia tendencia (medias moviles) y momentum del dia.
    COBRE    : relacion INVERSA. Cobre fuerte -> peso fuerte -> USD/CLP a la baja.
    DXY      : relacion DIRECTA. Dolar global fuerte -> USD/CLP al alza.

Devuelve un puntaje de -100 (dolar deberia BAJAR / peso fuerte) a
+100 (dolar deberia SUBIR / peso debil), con las senales que lo explican.

HONESTO: esto es un mapa de probabilidades basado en reglas y correlaciones
historicas, NO una prediccion garantizada. El mercado puede ir en contra.
"""
import config as C
import datasource as ds


# --------------------------- utilidades ------------------------------
def _sma(candles, n):
    """Media movil simple de los ultimos n cierres."""
    cierres = [c["c"] for c in candles]
    if len(cierres) < n:
        return None
    return sum(cierres[-n:]) / n


def _trend(d):
    """Clasifica la tendencia de un instrumento por sus medias moviles.
    Devuelve (etiqueta, signo) donde signo = +1 sube, -1 baja, 0 lateral."""
    if not d or not d.get("candles"):
        return ("sin dato", 0)
    price = d["price"]
    s_corta = _sma(d["candles"], C.SMA_CORTA)
    s_larga = _sma(d["candles"], C.SMA_LARGA)
    if not s_corta or not s_larga:
        return ("dato insuficiente", 0)
    if price > s_corta and s_corta > s_larga:
        return ("alcista", +1)
    if price < s_corta and s_corta < s_larga:
        return ("bajista", -1)
    return ("lateral", 0)


def niveles_sr(candles, price, max_niveles=3):
    """Soportes y resistencias: donde el precio giro varias veces.
    (misma idea que tu technical.py, adaptada a velas diarias)."""
    highs, lows = [], []
    k = 3
    for i in range(k, len(candles) - k):
        win = candles[i - k:i + k + 1]
        h, l = candles[i]["h"], candles[i]["l"]
        if h == max(c["h"] for c in win):
            highs.append(h)
        if l == min(c["l"] for c in win):
            lows.append(l)
    # agrupa niveles cercanos (dentro de 0.6%)
    grupos = []
    for p in sorted(highs + lows):
        for g in grupos:
            if abs(p - g["price"]) / price <= 0.006:
                g["price"] = (g["price"] * g["n"] + p) / (g["n"] + 1)
                g["n"] += 1
                break
        else:
            grupos.append({"price": p, "n": 1})
    sop = sorted([g["price"] for g in grupos if g["price"] < price * 0.999], reverse=True)
    res = sorted([g["price"] for g in grupos if g["price"] > price * 1.001])
    return sop[:max_niveles], res[:max_niveles]


def evaluar_riesgos(a, eventos):
    """Sintetiza los peligros que debe vigilar un trader. Devuelve lista de
    strings (cada uno una alerta de riesgo). a = dict parcial del analisis."""
    r = []
    price = a["price"]

    # 1) Evento economico de alto impacto proximo (el riesgo #1)
    altos = [e for e in (eventos or []) if e["impacto"] == "High"]
    if altos:
        e0 = altos[0]
        r.append(f"Reporte de alto impacto {e0['cuando']} {e0['hora']}: {e0['titulo']} "
                 f"→ el USD/CLP puede saltar brusco")

    # 2) RSI extremo (agotamiento)
    rsi = a.get("rsi")
    if rsi is not None:
        if rsi >= 70:
            r.append(f"RSI {rsi:.0f}: sobrecompra, el dólar puede estar agotándose al alza")
        elif rsi <= 30:
            r.append(f"RSI {rsi:.0f}: sobreventa, riesgo de rebote del dólar")

    # 3) Precio pegado a un nivel clave (posible quiebre o rechazo)
    for nivel in C.NIVELES_CLAVE:
        if abs(price - nivel) / price <= 0.004:   # a menos de 0.4%
            r.append(f"Precio pegado a nivel clave {nivel:,.0f}: puede rebotar o romper con fuerza")
            break

    # 4) Estirado vs valor justo (posible reversion)
    v = a.get("valor")
    if v and abs(v["z"]) >= 1.3:
        lado = "caro (peso muy débil)" if v["z"] > 0 else "barato (peso muy fuerte)"
        r.append(f"Dólar estirado vs sus motores: {lado} (~{v['gap']:+.0f}), riesgo de corrección")

    # 5) Volatilidad alta (movimientos mas grandes de lo normal)
    atrp = a.get("atr_pct")
    if atrp and atrp >= 1.4:
        r.append(f"Volatilidad elevada (~{atrp:.1f}%/día): movimientos más amplios, ajusta tamaño")

    # 6) Motores desconectados (el modelo pierde poder predictivo)
    cr = a.get("correls") or {}
    if cr and all(abs(x) < 0.3 for x in cr.values()):
        r.append("Los motores (cobre/DXY/real) están desconectados del peso: manda algo local "
                 "(política/flujos); el análisis técnico pesa más que el fundamental")

    return r


# --------------------------- el analisis -----------------------------
def analizar():
    """Junta los 3 instrumentos y calcula el sesgo. Devuelve un dict con todo."""
    usdclp = ds.get(C.SYM_USDCLP)
    cobre = ds.get(C.SYM_COBRE)
    dxy = ds.get(C.SYM_DXY)
    brl = ds.get(C.SYM_BRL)
    bono = ds.get(C.SYM_BONO)

    if not usdclp or not usdclp.get("price"):
        return None   # sin el dato principal no hay analisis

    price = usdclp["price"]
    t_clp = _trend(usdclp)
    t_cu = _trend(cobre)
    t_dxy = _trend(dxy)
    t_brl = _trend(brl)
    t_bono = _trend(bono)

    # ----- motor cuantitativo: alinear series y medir de verdad -----
    import model as M
    import math
    series = {"clp": usdclp["candles"]}
    if cobre and cobre.get("candles"):
        series["cobre"] = cobre["candles"]
    if dxy and dxy.get("candles"):
        series["dxy"] = dxy["candles"]
    if brl and brl.get("candles"):
        series["brl"] = brl["candles"]
    if bono and bono.get("candles"):
        series["bono"] = bono["candles"]
    _, arr = M.alinear(series)

    rsi = M.rsi([c["c"] for c in usdclp["candles"]]) if len(usdclp["candles"]) > 15 else None
    atrp = M.atr_pct(usdclp["candles"])

    correls = {}      # {motor: correlacion medida}
    valor = None      # dict de valor justo
    r_clp = None
    if arr is not None and "clp" in arr:
        r_clp = M.retornos(arr["clp"])
        for k in ("cobre", "dxy", "brl", "bono"):
            if k in arr:
                correls[k] = M.correlacion(r_clp, M.retornos(arr[k]))
        valor = M.valor_justo(arr)

    # ----- construccion del puntaje (senales que suman o restan) -----
    senales = []   # cada una: (texto, aporte)  aporte>0 empuja USD/CLP arriba
    score = 0.0

    # 1) TENDENCIA propia, modulada por FUERZA (distancia a la media en ATR)
    if t_clp[1] != 0:
        s20 = _sma(usdclp["candles"], C.SMA_CORTA)
        fuerza = 1.0
        if s20 and atrp:
            dist = abs(price - s20)
            atr_abs = atrp / 100 * price
            fuerza = max(0.35, min(1.0, dist / (1.5 * atr_abs))) if atr_abs else 1.0
        ap = t_clp[1] * 30 * fuerza
        score += ap
        senales.append((f"Tendencia propia {t_clp[0]} (medias {C.SMA_CORTA}/{C.SMA_LARGA}, fuerza {fuerza:.0%})", ap))

    # 2) RSI: momentum + aviso de sobrecompra/sobreventa
    if rsi is not None:
        ap = (rsi - 50) / 50 * 12
        score += ap
        senales.append((f"RSI {rsi:.0f} → momentum {'alcista' if rsi >= 50 else 'bajista'}", ap))
        if rsi >= 70:
            score -= 5   # sobrecompra: riesgo de techo (empuja a la baja)
            senales.append((f"RSI {rsi:.0f} en SOBRECOMPRA → riesgo de agotamiento al alza", -5))
        elif rsi <= 30:
            score += 5
            senales.append((f"RSI {rsi:.0f} en SOBREVENTA → riesgo de rebote del dólar", +5))

    # 3) MOTORES con PESO DINAMICO por correlacion medida
    #    contribucion = correlacion * (fuerza del movimiento reciente del motor)
    #    La correlacion ya trae el signo (cobre negativo, DXY/real positivos),
    #    y su MAGNITUD hace que un motor "pese" mas o menos segun cuanto este
    #    explicando al peso ESTAS semanas.
    nombres = {"cobre": ("Cobre", cobre), "dxy": ("DXY", dxy), "brl": ("Real (USD/BRL)", brl),
               "bono": ("Bono 10Y USA", bono)}
    aportes = {}   # {motor: contribucion al puntaje} para mostrar el empuje de cada uno
    for k, (etq, dat) in nombres.items():
        if k not in correls or not dat or not dat.get("price"):
            continue
        corr = correls[k]
        # z = el movimiento de HOY del motor (el mismo % que se muestra),
        # normalizado por su volatilidad diaria tipica. Asi la direccion del
        # empuje SIEMPRE es coherente con el % mostrado.
        sd = float(M.retornos(arr[k]).std()) if (arr is not None and k in arr) else 0.0
        z = (dat["change_pct"] / 100.0 / sd) if sd > 0 else 0.0
        ap = max(-16, min(16, corr * z * 12))
        aportes[k] = ap
        if abs(ap) < 1:
            continue
        score += ap
        fuerza_corr = "fuerte" if abs(corr) >= 0.5 else ("media" if abs(corr) >= 0.3 else "débil")
        senales.append((
            f"{etq} {dat['change_pct']:+.2f}% (corr {corr:+.2f} {fuerza_corr}) → "
            f"empuja el dólar {'al alza' if ap > 0 else 'a la baja'}", ap))

    # 4) VALOR JUSTO (valor relativo): mean-reversion suave
    if valor:
        z = max(-2, min(2, valor["z"]))
        ap = -z * 6.5   # si el dolar esta CARO vs motores -> presion a corregir a la baja
        score += ap
        if valor["z"] >= 1:
            senales.append((f"Dólar CARO vs sus motores hoy (~{valor['gap']:+.0f} sobre su valor justo {valor['predicho']:.0f})", ap))
        elif valor["z"] <= -1:
            senales.append((f"Dólar BARATO vs sus motores hoy (~{valor['gap']:+.0f} bajo su valor justo {valor['predicho']:.0f})", ap))

    # 5) FIBONACCI: si el precio esta pegado a un nivel fib, es zona de reaccion
    fib = M.fibonacci(usdclp["candles"])
    if fib:
        ratio, nivel_fib = fib["cerca"]
        if 0 < ratio < 1 and abs(price - nivel_fib) / price <= 0.004:
            senales.append((f"Precio en Fibonacci {ratio:.3f} ({nivel_fib:.0f}) → zona de posible giro", 0))

    score = int(max(-100, min(100, round(score))))

    # ----- traduccion del puntaje a la PRESION ACTUAL (nowcast, no prediccion) -----
    # Describe lo que los motores (cobre/DXY/real) + tendencia estan haciendo
    # AHORA sobre el peso. NO es un pronostico: el backtest mostro que este
    # puntaje no anticipa el movimiento del dia siguiente.
    if score >= 40:
        sesgo, emoji = "Presión AL ALZA fuerte (motores empujan el dólar arriba ahora)", "🔴"
    elif score >= 15:
        sesgo, emoji = "Presión al alza leve", "🟠"
    elif score <= -40:
        sesgo, emoji = "Presión A LA BAJA fuerte (motores empujan el dólar abajo ahora)", "🟢"
    elif score <= -15:
        sesgo, emoji = "Presión a la baja leve", "🟢"
    else:
        sesgo, emoji = "Motores equilibrados / sin presión clara", "⚪"

    sop, res = niveles_sr(usdclp["candles"], price)

    # reportes economicos proximos + evaluacion de riesgos
    try:
        import calendar_econ as CE
        eventos = CE.proximos(dias=3)
    except Exception as e:
        print("  (aviso) calendario falló:", str(e)[:60])
        eventos = []

    parcial = {"price": price, "rsi": rsi, "atr_pct": atrp, "valor": valor,
               "correls": correls}
    riesgos = evaluar_riesgos(parcial, eventos)

    return {
        "price": price,
        "change_pct": usdclp["change_pct"],
        "score": score,
        "sesgo": sesgo,
        "emoji": emoji,
        "senales": sorted(senales, key=lambda s: -abs(s[1])),
        "soportes": sop,
        "resistencias": res,
        "cobre": cobre,
        "dxy": dxy,
        "brl": brl,
        "bono": bono,
        "usdclp": usdclp,
        "trend_clp": t_clp,
        "trend_cu": t_cu,
        "trend_dxy": t_dxy,
        "trend_brl": t_brl,
        "trend_bono": t_bono,
        "rsi": rsi,
        "atr_pct": atrp,
        "correls": correls,
        "aportes": aportes,
        "valor": valor,
        "fib": fib,
        "eventos": eventos,
        "riesgos": riesgos,
    }
