# =====================================================================
#  CONFIGURACION del bot del DOLAR/CLP  ->  esto es lo que puedes editar.
# =====================================================================
#
#  El agente analiza el USD/CLP (dolar/peso chileno) para trading, mirando
#  sus 3 motores principales:
#     1) El propio USD/CLP (tendencia y momentum)
#     2) El COBRE   -> relacion INVERSA (cobre sube -> peso fuerte -> USD/CLP baja)
#     3) El DXY     -> relacion DIRECTA (dolar global sube -> USD/CLP sube)
#
import os

# ---------------------------------------------------------------------
#  Secretos (token de Telegram, chat_id, API de IA). Orden de busqueda:
#    1) Variables de entorno (cuando corre en la nube).
#    2) Archivo secrets_local.py (cuando corre en tu Mac).
#  Asi tu token real nunca queda en un archivo que se suba a internet.
# ---------------------------------------------------------------------
try:
    import secrets_local as _sl
    _LOCAL_TOKEN = getattr(_sl, "TELEGRAM_TOKEN", "")
    _LOCAL_CHAT = getattr(_sl, "CHAT_ID", 0)
    _LOCAL_AI = getattr(_sl, "ANTHROPIC_API_KEY", "")
except ImportError:
    _LOCAL_TOKEN, _LOCAL_CHAT, _LOCAL_AI = "", 0, ""

def _pick(env_name, local):
    v = os.environ.get(env_name)
    return v if v else local

TELEGRAM_TOKEN = _pick("TELEGRAM_TOKEN", _LOCAL_TOKEN)
CHAT_ID = int(_pick("CHAT_ID", _LOCAL_CHAT or 0))
ANTHROPIC_API_KEY = _pick("ANTHROPIC_API_KEY", _LOCAL_AI)

# Modelo de IA para el comentario en lenguaje natural (Haiku = barato y rapido).
# Si dejas la API key vacia, el bot igual funciona: usa solo el analisis por reglas.
AI_MODEL = "claude-haiku-4-5-20251001"
# False = nunca llama a la IA (solo reglas, gratis). Ahora en False porque tu
# API key no tiene saldo. Ponlo en True cuando cargues créditos para tener el
# comentario en lenguaje natural.
USE_AI = False

# Noticias financieras chilenas (Google News RSS, gratis, sin key).
NEWS_ON = True   # False = no busca noticias
NEWS_TOP = 5     # cuantos titulares mostrar como maximo en el informe

# --- Alertas INSTANTANEAS de noticias ---
# El vigilante revisa noticias en este ritmo rapido y, si aparece un titular
# NUEVO que supera el umbral de relevancia, lo manda AL INSTANTE (sin esperar
# el informe de 30 min). Asi lo urgente llega en ~pocos minutos.
NEWS_WATCH_EVERY_MIN = 4     # cada cuantos min revisa noticias para alertar
NEWS_ALERT_SCORE = 6         # puntaje minimo de relevancia para disparar alerta
MAX_NEWS_ALERTS = 4          # tope de alertas por revision (anti-inundacion)

# ---------------------------------------------------------------------
#  Simbolos en Yahoo Finance (gratis, sin API key).
# ---------------------------------------------------------------------
SYM_USDCLP = "USDCLP=X"    # dolar / peso chileno
SYM_COBRE = "HG=F"         # cobre (futuro COMEX, USD por libra)
SYM_DXY = "DX-Y.NYB"       # indice dolar (dolar contra canasta de monedas)
SYM_BRL = "USDBRL=X"       # dolar / real brasileño (el CLP sigue mucho al real)
SYM_BONO = "^TNX"          # bono del Tesoro USA 10 años (tasas -> apetito por riesgo EM)
SYM_IRX = "^IRX"           # T-bill EE.UU. 13 semanas (proxy tasa Fed, para el carry)

# TPM de Chile de respaldo (%), por si mindicador.cl no responde. Actualízala
# cuando el Banco Central mueva la tasa (sale en las noticias del bot).
TPM_FALLBACK = 4.5

# ---------------------------------------------------------------------
#  Cada cuantos minutos revisa el vigilante (--watch).
# ---------------------------------------------------------------------
WATCH_EVERY_MIN = 30

TIMEZONE = "America/Santiago"   # hora de Chile

# ---------------------------------------------------------------------
#  Horario del INFORME grande (hora de Chile). De noche/finde/feriado el
#  mercado está cerrado y el informe solo repetiría "precio de referencia",
#  así que NO se envía. Las alertas urgentes de noticias/datos siguen 24/7.
#  (Enviar `report --gate` respeta este horario; sin --gate siempre envía.)
# ---------------------------------------------------------------------
INFORME_HORA_INI = 8    # desde las 08:00
INFORME_HORA_FIN = 18   # hasta las 18:00 (el último informe sale antes de las 18)
INFORME_SOLO_DIAS_HABILES = True   # False = también fines de semana

# ---------------------------------------------------------------------
#  Salud del bot (heartbeat). Cada trabajo (alertas/informe) deja su
#  "última corrida" en state.json; el otro avisa si lleva demasiado sin correr.
#  Así, si Yahoo se cae o GitHub apaga un workflow, te ENTERAS (no quedas ciego).
# ---------------------------------------------------------------------
HEALTH_ALERTAS_MAX_MIN = 25   # el informe avisa si el vigilante (5 min) no corre hace esto
HEALTH_INFORME_MAX_MIN = 80   # las alertas avisan si el informe (30 min) no corre hace esto

# ---------------------------------------------------------------------
#  Feriados de Chile (mercado cerrado). Fijos por fecha como "MM-DD"; los
#  movibles (Viernes Santo, algunos lunes) van como fecha completa "AAAA-MM-DD".
#  Actualizar una vez al año con el calendario nuevo.
# ---------------------------------------------------------------------
FERIADOS_CL = {
    "01-01", "05-01", "05-21", "06-20", "06-29", "07-16", "08-15",
    "09-18", "09-19", "10-31", "11-01", "12-08", "12-25",
    # movibles 2026
    "2026-04-03", "2026-04-04", "2026-10-12", "2026-11-16",
    # movibles 2027
    "2027-03-26", "2027-03-27", "2027-10-11",
}

# ---------------------------------------------------------------------
#  NIVELES CLAVE del USD/CLP (aprendidos de 2022-2026).
#     ~1000-1060 = techo estructural (solo se supera en panico)
#     ~880-840   = piso estructural
#  Si el precio CRUZA uno de estos niveles, el bot manda una ALERTA.
# ---------------------------------------------------------------------
NIVELES_CLAVE = [1010, 1000, 970, 950, 930, 910, 900, 880]

# Alerta por movimiento brusco: si el USD/CLP se mueve mas que este % en el dia.
MOVE_ALERT_PCT = 1.2

# ---------------------------------------------------------------------
#  Umbrales del analisis tecnico (no tocar salvo que sepas lo que haces).
# ---------------------------------------------------------------------
SMA_CORTA = 20     # media movil corta (dias)  -> tendencia reciente
SMA_LARGA = 50     # media movil larga (dias)  -> tendencia de fondo
