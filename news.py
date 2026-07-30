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
import unicodedata
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


# ---------------------------------------------------------------------
#  DEDUPLICACION POR HISTORIA (no por titulo exacto).
#  La MISMA noticia la publican 20 medios con titulos distintos. Para no
#  repetirla, reducimos cada titular a su "firma": el conjunto de palabras
#  con contenido (sin articulos ni preposiciones, sin tildes). Dos titulares
#  son la MISMA historia si comparten suficientes palabras.
# ---------------------------------------------------------------------
_STOP = set((
    "de la el en y a los las un una por con para que se su del al lo es mas "
    "ante sobre hoy tras entre como o u ni le ya son fue ser este esta esto "
    "estos estas segun hasta desde muy no si tras cual sus e mientras pese "
    "aun aunque hay ha han sin dia dias tan solo esa ese uno dos"
).split())


def _sin_tildes(s):
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def _stem(w):
    """Stem minimo en español: unifica plural/singular (tasas->tasa, cambios->
    cambio) para que el mismo hecho matchee aunque cambie el numero."""
    if len(w) > 4 and w.endswith("s"):
        w = w[:-1]
    return w


# Temas canonicos: cualquier SINONIMO del disparador agrega el mismo token,
# asi "Fed", "Reserva Federal", "Powell" y "FOMC" caen todos en "@fed" y el bot
# los reconoce como la misma historia aunque el titular use palabras distintas.
# Solo temas de EVENTO (poco frecuentes: suele haber uno por dia); el dolar y el
# cobre NO van aca (son demasiado frecuentes) y se agrupan por parecido normal.
_CANON = {
    "@fed":    ("fed", "reserva federal", "federal reserve", "fomc", "powell", "warsh"),
    "@bcch":   ("banco central", "tpm"),
    "@ipc":    ("ipc", "imacec", "pce", "precios al consumidor"),
    "@empleo": ("empleo", "desempleo", "nomina", "payroll", "cesantia"),
}
_CANON_TOKENS = frozenset(_CANON)


def _firma(titulo):
    """Conjunto de palabras con contenido del titular + su tema canonico
    (la 'huella' de la historia)."""
    t = _sin_tildes(_norm(titulo))
    palabras = re.findall(r"[a-z0-9%]+", t)
    base = set(_stem(w) for w in palabras if len(w) >= 3 and w not in _STOP)
    for tok, disparadores in _CANON.items():
        if any(g in t for g in disparadores):
            base.add(tok)
    return frozenset(base)


_UMBRAL_DUP = 0.5      # 50% de las palabras del titular mas corto coinciden
_MIN_COMPARTIDAS = 3   # y al menos 3 palabras en comun -> misma historia


def _es_misma_historia(firma, firmas_previas):
    """True si `firma` es la misma historia que alguna ya vista/mostrada."""
    canon = firma & _CANON_TOKENS
    for p in firmas_previas:
        comun = len(firma & p)
        # mismo tema de evento (@fed, @bcch...) + al menos una palabra mas
        if (canon & p) and comun >= 2:
            return True
        # o titulares muy parecidos en general
        if comun >= _MIN_COMPARTIDAS and comun / min(len(firma), len(p)) >= _UMBRAL_DUP:
            return True
    return False


def _load_seen():
    """Devuelve lista de firmas (frozensets) ya vistas. Convierte el formato
    viejo (titulos en texto) al vuelo."""
    try:
        data = json.load(open(SEEN_FILE))
    except Exception:
        return []
    out = []
    for e in data:
        if isinstance(e, list):
            out.append(frozenset(e))
        elif isinstance(e, str):
            out.append(_firma(e))
    return out


def _save_seen(firmas):
    try:
        # guarda solo las ultimas ~500 historias para no crecer sin fin
        json.dump([sorted(f) for f in firmas[-500:]], open(SEEN_FILE, "w"))
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
    """Devuelve lista de dicts {titulo, fuente, link, score, firma, nuevo}
    ordenada por relevancia, con UNA sola nota por historia (agrupa los mismos
    hechos publicados por distintos medios). `nuevo`=True si la historia no se
    habia mostrado antes."""
    seen = _load_seen()

    # 1) juntar candidatos de todos los temas
    candidatos = []
    for tema, url in TEMAS.items():
        try:
            d = feedparser.parse(requests.get(url, headers=UA, timeout=15).content)
        except Exception:
            continue
        for e in d.entries[:20]:
            titulo_full = html.unescape(e.get("title", ""))
            fuente = _fuente(e, titulo_full)
            titulo = titulo_full.rsplit(" - ", 1)[0] if " - " in titulo_full else titulo_full
            if not titulo or not _es_de_chile(titulo_full):
                continue
            sc = _score(titulo_full)
            if sc < min_score:
                continue
            firma = _firma(titulo)
            if len(firma) < 2:
                continue
            candidatos.append({
                "titulo": titulo.strip(), "fuente": fuente.strip(),
                "link": e.get("link", ""), "score": sc, "tema": tema, "firma": firma,
            })

    # 2) del mas relevante al menos, quedarse con UNA nota por historia
    candidatos.sort(key=lambda x: -x["score"])
    firmas_batch = []
    unicos = []
    for c in candidatos:
        if _es_misma_historia(c["firma"], firmas_batch):
            continue   # ya tenemos esta historia (otro medio) -> se descarta
        firmas_batch.append(c["firma"])
        c["nuevo"] = not _es_misma_historia(c["firma"], seen)
        unicos.append(c)

    return unicos[:top]


def marcar_vistas(items):
    """Guarda como vistas las HISTORIAS ya mostradas (por su firma), para no
    repetirlas aunque las publique otro medio con otro titulo."""
    seen = _load_seen()
    for it in items:
        seen.append(it.get("firma") or _firma(it["titulo"]))
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
