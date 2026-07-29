"""
Noticias financieras chilenas relevantes para el USD/CLP.

Fuente: Google News RSS en español-Chile (hl=es-419, gl=CL). Google News
AGREGA automaticamente todos los medios chilenos (Diario Financiero, El
Mercurio/Emol, La Tercera-Pulso, BioBio, Cooperativa, etc.), asi que con unas
pocas busquedas por tema barremos toda la prensa financiera del pais.

Cada nota se PUNTUA por palabras clave (dolar, cobre, Banco Central, Fed...)
para mostrar solo lo mas relevante. Se recuerda lo ya mostrado (seen.json)
para no repetir las mismas noticias en cada ciclo del vigilante.

HONESTO: detecta que SALIO la noticia, no predice si el dolar sube o baja.
"""
import os
import re
import json
import time
import html
import requests
import feedparser

HERE = os.path.dirname(os.path.abspath(__file__))
SEEN_FILE = os.path.join(HERE, "news_seen.json")
UA = {"User-Agent": "Mozilla/5.0"}

# Busquedas por tema (Google News RSS, ultimas 48-72h, en español de Chile).
def _url(q):
    q = requests.utils.quote(q)
    return (f"https://news.google.com/rss/search?q={q}"
            "&hl=es-419&gl=CL&ceid=CL:es-419")

TEMAS = {
    "Dólar/CLP":     _url("dólar peso chileno tipo de cambio when:2d"),
    "Cobre":         _url("precio del cobre Chile when:2d"),
    "Banco Central": _url('"Banco Central" Chile tasa OR TPM OR intervención when:3d'),
    "Economía CL":   _url("economía Chile IPC OR inflación OR IMACEC when:2d"),
    "Real/EM":       _url("real brasileño OR monedas emergentes América Latina when:2d"),
    # Fed / EE.UU.: el motor #1 del dólar global. Captura la DECISION de tasas,
    # inflacion (CPI/PCE) y empleo (payrolls) de Estados Unidos.
    "Fed/EE.UU.":    _url("Reserva Federal Fed tasa de interés OR decisión OR Powell OR Warsh when:1d"),
    "Macro EE.UU.":  _url("Estados Unidos inflación CPI OR empleo OR nóminas OR PCE when:1d"),
}

# Palabras que suman relevancia (a mas puntaje, mas arriba aparece).
KW = {
    # alto impacto directo en el peso
    "dólar": 3, "peso": 2, "tipo de cambio": 3, "cobre": 3, "banco central": 3,
    "tpm": 3, "tasa": 2, "intervención": 4, "reservas": 2,
    # macro que mueve
    "inflación": 2, "ipc": 2, "imacec": 2, "fed": 3, "powell": 2, "china": 2,
    "recesión": 2, "cobre": 3, "litio": 1, "riesgo": 1, "emergentes": 2,
    "real": 1, "brasil": 1, "trump": 1, "arancel": 2, "aranceles": 2,
    "reserva federal": 3, "warsh": 2, "tasas": 2, "recorte": 2, "hawkish": 2,
    "empleo": 1, "nóminas": 2, "payrolls": 2, "pce": 2,
}


def _norm(t):
    return re.sub(r"\s+", " ", t.lower()).strip()


def _load_seen():
    try:
        return set(json.load(open(SEEN_FILE)))
    except Exception:
        return set()


def _save_seen(seen):
    try:
        # guarda solo las ultimas ~400 para no crecer sin fin
        json.dump(list(seen)[-400:], open(SEEN_FILE, "w"))
    except Exception:
        pass


def _score(titulo):
    t = _norm(titulo)
    return sum(p for kw, p in KW.items() if kw in t)


# Notas de OTROS paises (sobre todo el peso mexicano) que se cuelan por la
# palabra "peso". Se descartan salvo que hablen tambien de Chile o el cobre.
_OTRO_PAIS = ("méxico", "mexicano", "mexicana", "banxico", "argentin",
              "colombia", "colombiano")

def _es_de_chile(titulo):
    t = _norm(titulo)
    if any(x in t for x in _OTRO_PAIS):
        return any(x in t for x in ("chile", "chileno", "cobre", "banco central de chile"))
    return True


def _fuente(entry, titulo):
    """Google News pone la fuente en entry.source o al final del titulo tras ' - '."""
    src = ""
    try:
        src = entry.source.get("title", "")
    except Exception:
        pass
    if not src and " - " in titulo:
        src = titulo.rsplit(" - ", 1)[-1]
    return src


def buscar(top=6, min_score=3):
    """Devuelve lista de dicts {titulo, fuente, link, score, nuevo} ordenada por
    relevancia. `nuevo`=True si no se habia mostrado antes."""
    seen = _load_seen()
    vistos_ahora = {}
    for tema, url in TEMAS.items():
        try:
            d = feedparser.parse(requests.get(url, headers=UA, timeout=15).content)
        except Exception:
            continue
        for e in d.entries[:20]:
            titulo_full = html.unescape(e.get("title", ""))
            fuente = _fuente(e, titulo_full)
            # limpia el " - Fuente" del final para mostrar el titular limpio
            titulo = titulo_full.rsplit(" - ", 1)[0] if " - " in titulo_full else titulo_full
            key = _norm(titulo)[:90]
            if not titulo or key in vistos_ahora:
                continue
            if not _es_de_chile(titulo_full):
                continue   # descarta peso mexicano/argentino/etc sin contexto chileno
            sc = _score(titulo_full)
            if sc < min_score:
                continue
            vistos_ahora[key] = {
                "titulo": titulo.strip(),
                "fuente": fuente.strip(),
                "link": e.get("link", ""),
                "score": sc,
                "tema": tema,
                "nuevo": key not in seen,
            }
    items = sorted(vistos_ahora.values(), key=lambda x: -x["score"])[:top]
    return items


def marcar_vistas(items):
    """Guarda como vistas las noticias ya mostradas (para no repetirlas)."""
    seen = _load_seen()
    for it in items:
        seen.add(_norm(it["titulo"])[:90])
    _save_seen(seen)


def nuevas_relevantes(min_score=6, top=12):
    """Titulares NUEVOS (no vistos antes) que superan `min_score`, para ALERTA
    instantanea. No los marca como vistos: eso lo hace quien los envie."""
    items = buscar(top=top, min_score=min_score)
    return [i for i in items if i["nuevo"]]


def alerta_telegram(it, contexto=""):
    """Formatea UNA noticia como alerta instantanea (HTML). contexto = linea
    opcional con el precio actual del dolar."""
    fuente = f" · <i>{html.escape(it['fuente'])}</i>" if it.get("fuente") else ""
    titulo = html.escape(it["titulo"])
    tema = html.escape(it.get("tema", ""))
    L = [f"🚨 <b>NOTICIA relevante</b> · {tema}",
         f"<a href=\"{it['link']}\">{titulo}</a>{fuente}"]
    if contexto:
        L.append(contexto)
    return "\n".join(L)


def bloque_telegram(top=5, solo_nuevas=False, min_score=3):
    """Arma el bloque de noticias para el mensaje (HTML). Devuelve (texto, items).
    Si solo_nuevas=True, muestra unicamente titulares no vistos antes."""
    items = buscar(top=max(top, 8), min_score=min_score)
    if solo_nuevas:
        items = [i for i in items if i["nuevo"]]
    items = items[:top]
    if not items:
        return ("", [])
    L = ["📰 <b>Noticias relevantes (Chile)</b>"]
    for it in items:
        fuente = f" · <i>{html.escape(it['fuente'])}</i>" if it["fuente"] else ""
        titulo = html.escape(it["titulo"])
        L.append(f"  • <a href=\"{it['link']}\">{titulo}</a>{fuente}")
    return ("\n".join(L), items)
