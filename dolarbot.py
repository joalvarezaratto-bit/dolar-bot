#!/usr/bin/env python3
"""
Agente del DOLAR/CLP -> analisis para trading enviado a Telegram.

El agente mira el USD/CLP y sus 2 motores (cobre y DXY), calcula un SESGO
direccional con su "por que", y te lo manda a Telegram.

Comandos:
    python3 dolarbot.py test      -> manda un mensaje de prueba a tu Telegram
    python3 dolarbot.py chatid    -> descubre tu CHAT_ID (escribele "hola" al bot antes)
    python3 dolarbot.py print     -> imprime el analisis en la consola (no manda nada)
    python3 dolarbot.py once      -> hace UN analisis y lo manda (util para cron)
    python3 dolarbot.py report    -> analisis + GRAFICO a Telegram
    python3 dolarbot.py watch     -> vigila cada 30 min y alerta niveles clave (deja corriendo)

HONESTO: es un mapa de probabilidades por reglas y correlaciones, NO una
prediccion. El mercado puede ir en contra. No es consejo de inversion.
"""
import sys
import os
import json
import time
import datetime as dt
import requests

import config as C
import analysis as A
import ai_comment
import chart as CH
import news as NW
import calendar_econ as CE

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(HERE, "state.json")
API = "https://api.telegram.org/bot{token}/{method}"


# --------------------------- Telegram --------------------------------
def tg(method, **params):
    url = API.format(token=C.TELEGRAM_TOKEN, method=method)
    r = requests.get(url, params=params, timeout=20)
    return r.json()


def send(text):
    if not C.CHAT_ID:
        print("ERROR: CHAT_ID = 0. Corre primero: python3 dolarbot.py chatid")
        return False
    res = tg("sendMessage", chat_id=C.CHAT_ID, text=text,
             parse_mode="HTML", disable_web_page_preview="true")
    if not res.get("ok"):
        print("Telegram error:", res)
        return False
    return True


def send_photo(path, caption=""):
    if not C.CHAT_ID:
        print("ERROR: CHAT_ID = 0.")
        return False
    url = API.format(token=C.TELEGRAM_TOKEN, method="sendPhoto")
    try:
        with open(path, "rb") as f:
            r = requests.post(url,
                              data={"chat_id": C.CHAT_ID, "caption": caption[:1024],
                                    "parse_mode": "HTML"},
                              files={"photo": f}, timeout=60)
        res = r.json()
    except Exception as e:
        print("Error enviando foto:", e)
        return False
    if not res.get("ok"):
        print("Telegram error (foto):", res)
        return False
    return True


# --------------------------- estado ----------------------------------
def _load_state():
    try:
        return json.load(open(STATE_FILE))
    except Exception:
        return {"last_price": None, "alerted_levels": [], "move_date": "", "report_date": ""}


def _save_state(s):
    try:
        json.dump(s, open(STATE_FILE, "w"))
    except Exception:
        pass


def _hoy():
    return dt.datetime.now().strftime("%Y-%m-%d")


# --------------------------- info "del momento" ----------------------
try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo(C.TIMEZONE)
except Exception:
    _TZ = dt.timezone(dt.timedelta(hours=-4))   # respaldo: Chile continental


def _estado_mercado_line(a):
    """Dice si el mercado CLP está abierto y qué tan fresco es el precio, para
    no mostrar un precio 'rancio' como si fuera en vivo."""
    d = a.get("usdclp") or {}
    ahora = dt.datetime.now(_TZ)
    feriado = (ahora.strftime("%m-%d") in C.FERIADOS_CL
               or ahora.strftime("%Y-%m-%d") in C.FERIADOS_CL)
    abierto = ahora.weekday() < 5 and 9 <= ahora.hour < 17 and not feriado
    txt = ""
    fresco = True
    mt = d.get("market_time")
    if mt:
        t_dato = dt.datetime.fromtimestamp(mt, dt.timezone.utc).astimezone(_TZ)
        edad = (dt.datetime.now(dt.timezone.utc)
                - dt.datetime.fromtimestamp(mt, dt.timezone.utc)).total_seconds() / 60
        txt = f" · dato {t_dato:%H:%M}"
        if edad > 20:
            fresco = False
            txt += f" (hace {int(edad)} min)"
    if abierto and fresco:
        return f"🟢 Mercado CLP abierto{txt}"
    if abierto and not fresco:
        return f"🟡 Abierto, dato algo atrasado{txt}"
    motivo = "feriado en Chile" if feriado else "cerrado"
    return f"🔴 Mercado CLP {motivo} — precio de referencia{txt}"


def _en_horario_informe():
    """True si es horario de enviar el informe grande (8-18 Chile, día hábil)."""
    ahora = dt.datetime.now(_TZ)
    feriado = (ahora.strftime("%m-%d") in C.FERIADOS_CL
               or ahora.strftime("%Y-%m-%d") in C.FERIADOS_CL)
    if C.INFORME_SOLO_DIAS_HABILES and (ahora.weekday() >= 5 or feriado):
        return False
    return C.INFORME_HORA_INI <= ahora.hour < C.INFORME_HORA_FIN


def _mercado_fresco(a):
    """True si el mercado CLP está abierto y el dato es reciente (para mostrar
    info intradía solo cuando es real, no rancia)."""
    d = a.get("usdclp") or {}
    ahora = dt.datetime.now(_TZ)
    feriado = (ahora.strftime("%m-%d") in C.FERIADOS_CL
               or ahora.strftime("%Y-%m-%d") in C.FERIADOS_CL)
    abierto = ahora.weekday() < 5 and 9 <= ahora.hour < 17 and not feriado
    mt = d.get("market_time")
    if mt:
        edad = (dt.datetime.now(dt.timezone.utc)
                - dt.datetime.fromtimestamp(mt, dt.timezone.utc)).total_seconds() / 60
        if edad > 20:
            return False
    return abierto


def _rango_dia_line(a):
    """Rango de la sesión del USD/CLP: dónde abrió, máximo, mínimo y dónde va
    ahora. Usa los campos en vivo de Yahoo y, si faltan, la vela del día."""
    d = a.get("usdclp") or {}
    velas = d.get("candles") or []
    hoy = velas[-1] if velas else {}
    op = d.get("day_open") or hoy.get("o")
    hi = d.get("day_high") or hoy.get("h")
    lo = d.get("day_low") or hoy.get("l")
    px = a["price"]
    # solo mostrar si el rango es REAL (evita velas rancias de mercado cerrado,
    # donde el máx=mín o la apertura queda fuera del rango).
    if not (op and hi and lo) or hi <= lo:
        return ""
    if not (lo <= op <= hi and lo <= px <= hi):
        return ""
    return f"📊 Sesión: abrió {op:,.1f} · máx {hi:,.1f} · mín {lo:,.1f} · ahora {px:,.1f}"


def _delta_line(a):
    """Qué se movió desde el informe anterior (dólar, cobre, DXY en el intervalo)."""
    prev = _load_state().get("last_report")
    if not prev or not prev.get("clp"):
        return ""
    mins = ""
    if prev.get("ts"):
        m = (time.time() - prev["ts"]) / 60
        mins = f" (hace {int(m)} min)" if m < 600 else ""
    partes = [f"dólar {(a['price']/prev['clp']-1)*100:+.2f}%"]
    cob = a.get("cobre") or {}
    if prev.get("cobre") and cob.get("price"):
        partes.append(f"cobre {(cob['price']/prev['cobre']-1)*100:+.2f}%")
    dxy = a.get("dxy") or {}
    if prev.get("dxy") and dxy.get("price"):
        partes.append(f"DXY {(dxy['price']/prev['dxy']-1)*100:+.2f}%")
    return f"🔄 vs informe anterior{mins}: " + " · ".join(partes)


def _set_hb(state, clave):
    """Marca la hora de esta corrida exitosa (heartbeat)."""
    state[clave] = time.time()


def _chequear_salud(state, clave_otro, max_min, etiqueta):
    """Avisa si el OTRO trabajo lleva demasiado sin correr (con freno anti-spam:
    un aviso por hora como máximo)."""
    hb = state.get(clave_otro)
    if not hb:
        return
    edad = (time.time() - hb) / 60
    if edad > max_min and time.time() - state.get("hb_warned", 0) > 3600:
        send(f"⚠️ <b>Aviso de salud del bot</b>: {etiqueta} no corre hace "
             f"{int(edad)} min. Revisa GitHub → pestaña <b>Actions</b> (¿workflow "
             f"apagado o Yahoo caído?).")
        state["hb_warned"] = time.time()


def _aviso_sin_datos(state):
    """Avisa si no hay datos de mercado (Yahoo), máximo una vez cada 3 horas."""
    if time.time() - state.get("nodata_warned", 0) > 3 * 3600:
        send("⚠️ <b>Sin datos de mercado</b> (Yahoo no responde). Lo reintento "
             "en el próximo ciclo; si sigue, puede ser un problema de la fuente.")
        state["nodata_warned"] = time.time()


def _set_snapshot(state, a):
    """Marca en `state` la foto de este informe (para el delta del próximo)."""
    state["last_report"] = {"ts": time.time(), "clp": a["price"],
                            "cobre": (a.get("cobre") or {}).get("price"),
                            "dxy": (a.get("dxy") or {}).get("price")}
    state["last_price"] = a["price"]


# --------------------------- formato del mensaje ---------------------
def _fmt_analisis(a, con_ia=True, con_noticias=True, solo_nuevas=False):
    """Arma el texto del analisis para Telegram (HTML)."""
    L = []
    L.append(f"{a['emoji']} <b>USD/CLP · {a['price']:,.2f}</b>  <i>({a['change_pct']:+.2f}% hoy)</i>")
    mkt = _estado_mercado_line(a)
    if mkt:
        L.append(mkt)
    rango = _rango_dia_line(a)
    if rango:
        L.append(rango)
    delta = _delta_line(a)
    if delta:
        L.append(delta)
    # pulso intradía (solo si el mercado está operando de verdad)
    if _mercado_fresco(a):
        try:
            import intraday as IN
            pl = IN.linea_telegram()
            if pl:
                L.append(pl)
        except Exception as e:
            print("  (aviso) intradía:", str(e)[:60])
    L.append("")
    L.append(f"Estado ahora: <b>{a['sesgo']}</b>")
    L.append(f"<i>Fuerza de la presión: {a['score']:+d}/100 (describe el momento, no predice)</i>")

    # termometro cuantitativo: RSI, volatilidad y valor justo
    stats = []
    if a.get("rsi") is not None:
        estado = "sobrecompra" if a["rsi"] >= 70 else ("sobreventa" if a["rsi"] <= 30 else "normal")
        stats.append(f"RSI {a['rsi']:.0f} ({estado})")
    if a.get("atr_pct") is not None:
        stats.append(f"volatilidad ~{a['atr_pct']:.1f}%/día")
    if stats:
        L.append("📊 " + " · ".join(stats))
    v = a.get("valor")
    if v:
        if v["z"] >= 1:
            vtxt = f"dólar CARO ({v['gap']:+.0f} sobre {v['predicho']:.0f})"
        elif v["z"] <= -1:
            vtxt = f"dólar BARATO ({v['gap']:+.0f} bajo {v['predicho']:.0f})"
        else:
            vtxt = f"en línea ({v['gap']:+.0f} vs {v['predicho']:.0f})"
        L.append(f"🎯 Valor justo (cobre+DXY+real): <b>{v['predicho']:.0f}</b> → {vtxt}")
    L.append("")

    # los motores, con su CORRELACION actual (que tan fuerte tira cada uno)
    cobre = a.get("cobre") or {}
    dxy = a.get("dxy") or {}
    brl = a.get("brl") or {}
    cr = a.get("correls") or {}

    def _corr(k):
        return f" · corr {cr[k]:+.2f}" if k in cr else ""

    if cobre.get("price") is not None:
        L.append(f"🥇 Cobre: <b>{cobre['price']:.2f}</b> USD/lb ({cobre['change_pct']:+.2f}%){_corr('cobre')}")
    if dxy.get("price") is not None:
        L.append(f"💵 DXY: <b>{dxy['price']:.1f}</b> ({dxy['change_pct']:+.2f}%){_corr('dxy')}")
    if brl.get("price") is not None:
        L.append(f"🇧🇷 Real (USD/BRL): <b>{brl['price']:.2f}</b> ({brl['change_pct']:+.2f}%){_corr('brl')}")
    L.append("")

    # por que (las senales mas fuertes)
    if a["senales"]:
        L.append("<b>Por qué:</b>")
        for txt, ap in a["senales"][:5]:
            flecha = "↑" if ap > 0 else "↓"
            L.append(f"  {flecha} {txt}")
        L.append("")

    # niveles con distancia (soportes = pisos; resistencias = techos)
    price = a["price"]
    if a["resistencias"]:
        L.append("🔴 Resistencias: " + " · ".join(
            f"{p:,.0f} <i>(+{(p/price-1)*100:.1f}%)</i>" for p in a["resistencias"]))
    if a["soportes"]:
        L.append("🟢 Soportes: " + " · ".join(
            f"{p:,.0f} <i>(-{(1-p/price)*100:.1f}%)</i>" for p in a["soportes"]))

    # fibonacci del ultimo impulso
    fib = a.get("fib")
    if fib:
        rc, pc = fib["cerca"]
        clave = [0.382, 0.5, 0.618]
        niv = " · ".join(f"{r:.3f}→{fib['levels'][r]:.0f}" for r in clave)
        L.append(f"📐 Fibonacci (impulso {fib['dir']} {fib['lo']:.0f}–{fib['hi']:.0f}): {niv}")
        L.append(f"   <i>precio cerca del {rc:.3f} ({pc:.0f})</i>")

    # riesgos a vigilar
    if a.get("riesgos"):
        L.append("")
        L.append("⚠️ <b>Riesgos</b>")
        for rg in a["riesgos"][:5]:
            L.append(f"  • {rg}")

    # reportes de HOY que ya salieron (con su resultado)
    try:
        blq_hoy = CE.bloque_resultados_telegram()
        if blq_hoy:
            L.append("")
            L.append(blq_hoy)
    except Exception as e:
        print("  (aviso) resultados de hoy fallaron:", str(e)[:60])

    # proximos reportes economicos
    try:
        blq = CE.bloque_telegram(dias=3)
        if blq:
            L.append("")
            L.append(blq)
    except Exception as e:
        print("  (aviso) reportes fallaron:", str(e)[:60])

    # noticias chilenas relevantes
    items = []
    if con_noticias:
        try:
            bloque, items = NW.bloque_telegram(top=C.NEWS_TOP, solo_nuevas=solo_nuevas)
            if bloque:
                L.append("")
                L.append(bloque)
                NW.marcar_vistas(items)
        except Exception as e:
            print("  (aviso) noticias fallaron:", str(e)[:80])

    # comentario IA (mira los datos + las noticias)
    if con_ia:
        c = ai_comment.comentar(a, noticias=items)
        if c:
            L.append("")
            L.append(f"🤖 <i>{c}</i>")

    L.append("")
    L.append("<i>📌 Tablero de CONTEXTO en tiempo real: muestra qué mueve al peso ahora "
             "(cobre inverso; DXY y real directos), sus niveles y las noticias. "
             "NO predice a dónde va el dólar — un backtest confirmó que el estado no anticipa "
             "el movimiento del día siguiente. No es consejo de inversión.</i>")
    return "\n".join(L)


# --------------------------- alertas ---------------------------------
def _revisar_alertas(a, state):
    """Devuelve lista de textos de alerta por cruces de nivel o movimientos bruscos."""
    alertas = []
    price = a["price"]
    last = state.get("last_price")

    # 1) cruce de un nivel clave
    if last:
        for nivel in C.NIVELES_CLAVE:
            cruzo_arriba = last < nivel <= price
            cruzo_abajo = last > nivel >= price
            if cruzo_arriba or cruzo_abajo:
                direccion = "SUBIÓ y cruzó" if cruzo_arriba else "BAJÓ y cruzó"
                alertas.append(
                    f"⚠️ <b>NIVEL CLAVE</b>: USD/CLP {direccion} <b>{nivel:,.0f}</b>\n"
                    f"Ahora en {price:,.2f}. Sesgo: {a['sesgo']}.")

    # 2) movimiento brusco del dia (una vez por dia). El umbral se ADAPTA a la
    #    volatilidad: solo alerta si el movimiento supera ~1.5x el rango normal
    #    (ATR), asi no molesta con ruido en dias tranquilos.
    umbral = C.MOVE_ALERT_PCT
    if a.get("atr_pct"):
        umbral = max(C.MOVE_ALERT_PCT, 1.5 * a["atr_pct"])
    if abs(a["change_pct"]) >= umbral and state.get("move_date") != _hoy():
        alertas.append(
            f"📈 <b>MOVIMIENTO FUERTE</b>: USD/CLP {a['change_pct']:+.2f}% hoy "
            f"({price:,.2f}), más de lo normal (vol ~{a.get('atr_pct', 0):.1f}%/día). "
            f"Sesgo: {a['sesgo']}.")
        state["move_date"] = _hoy()

    return alertas


# --------------------------- comandos --------------------------------
def cmd_chatid():
    res = tg("getUpdates")
    if not res.get("ok"):
        print("Error:", res)
        return
    ids = set()
    for u in res.get("result", []):
        msg = u.get("message") or u.get("channel_post") or {}
        chat = msg.get("chat", {})
        if chat.get("id"):
            ids.add((chat["id"], chat.get("first_name") or chat.get("title", "")))
    if ids:
        print("CHAT_ID(s) encontrados (pega el tuyo en secrets_local.py):")
        for cid, name in ids:
            print(f"   {cid}   ({name})")
    else:
        print("No hay mensajes. Escribele 'hola' a tu bot en Telegram y reintenta.")


def cmd_print():
    a = A.analizar()
    if not a:
        print("No pude obtener datos (Yahoo caido?). Reintenta en un momento.")
        return
    # version consola sin HTML
    print(f"\nUSD/CLP: {a['price']:.2f}  ({a['change_pct']:+.2f}%)")
    print(f"Estado ahora: {a['sesgo']}  (fuerza {a['score']:+d}/100, describe el momento, no predice)")
    cobre = a.get("cobre") or {}
    dxy = a.get("dxy") or {}
    brl = a.get("brl") or {}
    if cobre.get("price"):
        print(f"Cobre: {cobre['price']:.2f} USD/lb ({cobre['change_pct']:+.2f}%) - {a['trend_cu'][0]}")
    if dxy.get("price"):
        print(f"DXY:   {dxy['price']:.1f} ({dxy['change_pct']:+.2f}%) - {a['trend_dxy'][0]}")
    if brl.get("price"):
        print(f"Real:  {brl['price']:.2f} USD/BRL ({brl['change_pct']:+.2f}%) - {a['trend_brl'][0]}")
    print("\nPor que:")
    for txt, ap in a["senales"]:
        print(f"  {'↑' if ap>0 else '↓'} {txt}  [{ap:+.0f}]")
    print("\nResistencias:", ", ".join(f"{p:.0f}" for p in a["resistencias"]) or "n/d")
    print("Soportes:    ", ", ".join(f"{p:.0f}" for p in a["soportes"]) or "n/d")
    fib = a.get("fib")
    if fib:
        rc, pc = fib["cerca"]
        print(f"Fibonacci ({fib['dir']} {fib['lo']:.0f}-{fib['hi']:.0f}): " +
              " ".join(f"{r:.3f}={fib['levels'][r]:.0f}" for r in [0.382, 0.5, 0.618]) +
              f"  | precio cerca de {rc:.3f}")
    if a.get("riesgos"):
        print("\nRiesgos:")
        for rg in a["riesgos"]:
            print(f"  ⚠️ {rg}")
    try:
        import calendar_econ as CE
        hoy = CE.resultados_hoy()
        if hoy:
            print("\nReportes de HOY (ya salieron):")
            for e in hoy[:6]:
                res = f"{e['actual']} ({e['interp']})" if e['actual'] else "⏳ pendiente"
                print(f"  [{e['impacto']:6}] {e['hora']} {e['titulo']}: {res}")
    except Exception:
        pass
    if a.get("eventos"):
        print("\nPróximos reportes (vienen):")
        for e in a["eventos"][:6]:
            print(f"  [{e['impacto']:6}] {e['cuando']} {e['hora']} {e['titulo']}")
    if C.NEWS_ON:
        try:
            _, items = NW.bloque_telegram(top=C.NEWS_TOP)
            print("\nNoticias relevantes (Chile):")
            for it in items:
                print(f"  [{it['score']}] {it['titulo'][:70]}  ·  {it['fuente']}")
        except Exception as e:
            print("  (noticias fallaron:", str(e)[:60], ")")
    print()


def cmd_once(con_grafico=False, gate=False):
    a = A.analizar()
    if not a:
        state = _load_state()
        _aviso_sin_datos(state)
        _save_state(state)
        print("Sin datos; aviso enviado.")
        return
    state = _load_state()
    # heartbeat: el informe está VIVO aunque por horario no envíe nada
    _set_hb(state, "hb_informe")
    _chequear_salud(state, "hb_alertas", C.HEALTH_ALERTAS_MAX_MIN, "el vigilante de alertas")
    # gate de horario: de noche/finde/feriado no mandamos el informe (solo ruido)
    if gate and not _en_horario_informe():
        _save_state(state)
        print(f"[{dt.datetime.now(_TZ):%H:%M}] fuera de horario de informe (8-18 Chile); "
              f"heartbeat actualizado, no envío.")
        return
    # alertas primero (mas urgentes)
    for al in _revisar_alertas(a, state):
        send(al)
    # El grafico se manda PRIMERO con un pie corto (Telegram limita el pie a
    # 1024 chars). El analisis completo va aparte como texto (hasta 4096).
    if con_grafico:
        try:
            path = os.path.join(HERE, "usdclp.png")
            # mercado operando -> grafico de 1h (la sesion); si no, el diario
            hecho = None
            if _mercado_fresco(a):
                hecho = CH.make_chart_intraday(a, path)
            tipo = "1h" if hecho else "diario"
            if not hecho:
                CH.make_chart(a, path)
            pie = (f"{a['emoji']} USD/CLP {a['price']:,.2f} ({a['change_pct']:+.2f}%) · "
                   f"gráfico {tipo}")
            send_photo(path, caption=pie)
        except Exception as e:
            print("Fallo el grafico:", e)
    send(_fmt_analisis(a, con_noticias=C.NEWS_ON))
    _set_snapshot(state, a)
    _save_state(state)
    print(f"Enviado. USD/CLP {a['price']:.2f}, estado: {a['sesgo']}")


def _precio_contexto():
    """Linea corta con el precio actual del dolar, para pegar en una alerta."""
    try:
        d = A.ds.get(C.SYM_USDCLP)
        if d and d.get("price"):
            return f"💵 USD/CLP {d['price']:,.2f} ({d['change_pct']:+.2f}%)"
    except Exception:
        pass
    return ""


def _alertas_noticias():
    """Revisa noticias y manda AL INSTANTE las nuevas de alto impacto.
    Devuelve cuantas alerto."""
    try:
        nuevas = NW.nuevas_relevantes(min_score=C.NEWS_ALERT_SCORE)
    except Exception as e:
        print("  (aviso) alerta noticias:", str(e)[:60])
        return 0
    if not nuevas:
        return 0
    nuevas = nuevas[:C.MAX_NEWS_ALERTS]
    ctx = _precio_contexto()
    for it in nuevas:
        send(NW.alerta_telegram(it, contexto=ctx))
    NW.marcar_vistas(nuevas)   # para no repetirlas ni re-alertarlas
    return len(nuevas)


def _alertas_resultados():
    """Manda AL INSTANTE los resultados de reportes de alto impacto que acaban
    de salir (Fed, CPI, empleo...). Devuelve cuantos alerto."""
    try:
        nuevos = CE.resultados_para_alertar()
    except Exception as e:
        print("  (aviso) alerta resultados:", str(e)[:60])
        return 0
    if not nuevos:
        return 0
    ctx = _precio_contexto()
    for e in nuevos:
        send(CE.alerta_resultado_telegram(e, contexto=ctx))
    CE.marcar_resultados_vistos(nuevos)
    return len(nuevos)


def _informe_completo(primera=False):
    """Analisis completo + alertas de nivel/movimiento + informe a Telegram.
    En el primer informe muestra las noticias actuales (snapshot); despues solo
    las que no se hayan alertado ya."""
    a = A.analizar()
    if not a:
        state = _load_state()
        _aviso_sin_datos(state)
        _save_state(state)
        print(f"[{dt.datetime.now():%H:%M}] sin datos, aviso enviado")
        return
    state = _load_state()
    _chequear_salud(state, "hb_alertas", C.HEALTH_ALERTAS_MAX_MIN, "el vigilante de alertas")
    alertas = _revisar_alertas(a, state)
    for al in alertas:
        send(al)
    send(_fmt_analisis(a, con_noticias=C.NEWS_ON, solo_nuevas=not primera))
    _set_snapshot(state, a)
    _set_hb(state, "hb_informe")
    _save_state(state)
    print(f"[{dt.datetime.now():%H:%M}] INFORME · USD/CLP {a['price']:.2f} "
          f"sesgo {a['score']:+d} · {len(alertas)} alerta(s) de nivel")


def cmd_watch():
    """Dos ritmos: noticias urgentes cada NEWS_WATCH_EVERY_MIN, informe completo
    cada WATCH_EVERY_MIN."""
    fast = max(1, C.NEWS_WATCH_EVERY_MIN)
    print(f"Vigilando: noticias cada {fast} min, informe completo cada "
          f"{C.WATCH_EVERY_MIN} min. Ctrl+C para parar.")
    # arranque: informe inicial (snapshot) y SEMBRAR las noticias actuales como
    # vistas, para alertar al instante solo lo que salga DE AHORA EN ADELANTE.
    _informe_completo(primera=True)
    try:
        if C.NEWS_ON:
            NW.marcar_vistas(NW.nuevas_relevantes(min_score=C.NEWS_ALERT_SCORE))
        CE.sembrar_resultados()
        print("  (noticias y resultados actuales sembrados; alertaré solo lo nuevo)")
    except Exception:
        pass
    last_full = time.time()
    while True:
        time.sleep(fast * 60)
        try:
            now = time.time()
            # 1) informe completo cada WATCH_EVERY_MIN
            if now - last_full >= C.WATCH_EVERY_MIN * 60:
                _informe_completo()
                last_full = now
            # 2) alertas instantaneas de noticias + resultados (cada ciclo rapido)
            n = (_alertas_noticias() if C.NEWS_ON else 0) + _alertas_resultados()
            if n:
                print(f"[{dt.datetime.now():%H:%M}] {n} alerta(s) al instante")
        except Exception as e:
            print("Error en el ciclo:", e)


def cmd_alertas():
    """Comando LIVIANO para el cron de la nube (cada ~5 min): solo alertas
    (noticias urgentes + cruces de nivel), SIN informe completo.
    En la primera corrida (sin news_seen.json) siembra y no alerta, para no
    inundar."""
    state = _load_state()
    # primera vez en la nube: sembrar noticias + resultados actuales y salir
    if not os.path.exists(NW.SEEN_FILE):
        try:
            if C.NEWS_ON:
                NW.marcar_vistas(NW.nuevas_relevantes(min_score=C.NEWS_ALERT_SCORE))
            CE.sembrar_resultados()
            print("Primera corrida: noticias y resultados sembrados, sin alertar.")
        except Exception as e:
            print("  (aviso) siembra:", str(e)[:60])
        _set_hb(state, "hb_alertas")
        _save_state(state)
        return
    # 1) alertas instantaneas de noticias
    n_news = _alertas_noticias() if C.NEWS_ON else 0
    # 2) alertas instantaneas de RESULTADOS economicos (Fed, CPI, empleo...)
    n_res = _alertas_resultados()
    # 3) alertas de nivel / movimiento (necesita el analisis para precio y niveles)
    n_lvl = 0
    a = A.analizar()
    if a:
        for al in _revisar_alertas(a, state):
            send(al)
            n_lvl += 1
        state["last_price"] = a["price"]
    else:
        _aviso_sin_datos(state)
    # salud: avisar si el informe de 30 min dejó de correr
    _chequear_salud(state, "hb_informe", C.HEALTH_INFORME_MAX_MIN, "el informe de 30 min")
    _set_hb(state, "hb_alertas")
    _save_state(state)
    print(f"[{dt.datetime.now():%H:%M}] alertas: {n_news} noticia(s), "
          f"{n_res} resultado(s), {n_lvl} de nivel")


def cmd_selftest():
    """Revisa que todas las piezas funcionen (datos, análisis, noticias, gráfico)
    sin mandar nada a Telegram. Útil para verificar la salud de un vistazo."""
    print("== Auto-test del dolar-bot ==")
    estado = {"ok": True}

    def check(nombre, fn):
        try:
            r = fn()
            passed = r is not None and r is not False
            print(f"  [{'✓' if passed else '✗'}] {nombre}")
            if not passed:
                estado["ok"] = False
            return r
        except Exception as e:
            print(f"  [✗] {nombre}: ERROR {str(e)[:60]}")
            estado["ok"] = False
            return None

    import calendar_econ as CE
    check("Token de Telegram configurado", lambda: bool(C.TELEGRAM_TOKEN) and bool(C.CHAT_ID))
    check("Datos USD/CLP (Yahoo, con failover)", lambda: A.ds.get(C.SYM_USDCLP, force=True))
    check("Datos cobre", lambda: A.ds.get(C.SYM_COBRE))
    check("Datos DXY", lambda: A.ds.get(C.SYM_DXY))
    check("Datos real brasileño", lambda: A.ds.get(C.SYM_BRL))
    a = check("Análisis completo (cerebro)", lambda: A.analizar())
    check("Noticias (Google News)", lambda: NW.buscar(top=3, min_score=3) is not None)
    check("Calendario económico (ForexFactory)", lambda: CE.proximos(dias=5) is not None)
    check("Datos intradía 1h", lambda: len(__import__("intraday").candles_ohlc(C.SYM_USDCLP)) > 0)
    if a:
        check("Arma el mensaje del informe", lambda: bool(_fmt_analisis(a, con_noticias=False)))
        check("Genera el gráfico", lambda: CH.make_chart(a, os.path.join(HERE, "selftest.png")))
        try:
            os.remove(os.path.join(HERE, "selftest.png"))
        except Exception:
            pass
    print("\n" + ("✅ TODO OK — el bot está sano." if estado["ok"]
                  else "✗ HAY FALLAS — revisa las líneas con ✗ arriba."))
    return estado["ok"]


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "print"
    if cmd == "selftest":   # corre sin token, para poder diagnosticar
        cmd_selftest()
        return
    if C.TELEGRAM_TOKEN in ("", "PEGA_TU_TOKEN_AQUI"):
        print("ERROR: falta tu TELEGRAM_TOKEN en secrets_local.py o en los Secrets")
        sys.exit(1)
    if cmd == "test":
        ok = send("✅ <b>dolar-bot conectado.</b> Listo para analizar el USD/CLP.")
        print("Mensaje de prueba enviado." if ok else "Fallo el envio (revisa token/chat_id).")
    elif cmd == "chatid":
        cmd_chatid()
    elif cmd == "print":
        cmd_print()
    elif cmd == "once":
        cmd_once(con_grafico=False, gate="--gate" in sys.argv)
    elif cmd == "report":
        cmd_once(con_grafico=True, gate="--gate" in sys.argv)
    elif cmd == "alertas":
        cmd_alertas()
    elif cmd == "watch":
        cmd_watch()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
