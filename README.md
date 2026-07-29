# dolar-bot 🇨🇱💵

Agente que analiza el **USD/CLP (dólar/peso chileno)** para trading y te manda
el análisis a **Telegram**. Mira el dólar y sus 2 motores principales:

- 🥇 **Cobre** → relación **inversa** (cobre sube → peso fuerte → USD/CLP baja).
- 💵 **DXY** (dólar global) → relación **directa** (DXY sube → USD/CLP sube).

Calcula un **sesgo** (alcista/bajista/neutral) con un puntaje de −100 a +100 y
te explica el **por qué**. Datos gratis de Yahoo Finance (sin API key).

> Es un mapa de probabilidades por reglas y correlaciones, **no una predicción**
> ni consejo de inversión.

---

## Cómo usarlo

Abre la Terminal y entra a la carpeta:

```bash
cd ~/dolar-bot
```

Comandos (todos empiezan con `python3 dolarbot.py`):

| Comando | Qué hace |
|---|---|
| `python3 dolarbot.py test`   | Manda un mensaje de prueba a tu Telegram. Úsalo primero. |
| `python3 dolarbot.py print`  | Muestra el análisis en la pantalla (no manda nada a Telegram). |
| `python3 dolarbot.py once`   | Hace 1 análisis y lo manda a Telegram. |
| `python3 dolarbot.py report` | Igual que `once` pero **con gráfico**. |
| `python3 dolarbot.py watch`  | Vigila en **dos ritmos**: noticias urgentes cada ~4 min + informe completo cada 30 min. Déjalo corriendo. |

### Para que corra solo (dos ritmos)

Deja esta ventana de Terminal abierta:

```bash
cd ~/dolar-bot && python3 dolarbot.py watch
```

Mientras esté abierta:

- **Informe completo cada 30 min**: análisis + riesgos + reportes + niveles +
  Fibonacci + noticias.
- **Alerta instantánea cada ~4 min**: si sale una noticia NUEVA de alto impacto
  (dólar, cobre, Banco Central, Fed…), te llega en pocos minutos, sin esperar
  el informe.
- **Alerta de nivel**: si el dólar cruza un nivel clave (900, 950, 1000…) o se
  mueve más de lo normal (según su volatilidad).

Al arrancar, siembra las noticias actuales como "ya vistas" para NO inundarte:
solo alerta lo que salga de ahí en adelante.

Qué tan rápido llega una noticia: `indexado por Google News (~2-15 min)` +
`espera al próximo ciclo de 4 min` → normalmente **~5-10 min** desde que se
publica. Ajusta el ritmo en `config.py` (`NEWS_WATCH_EVERY_MIN`) y la
sensibilidad con `NEWS_ALERT_SCORE`.

*(Si quieres que corra aunque cierres el Mac, se puede montar en la nube igual
que tu news-bot — avísame y lo armamos.)*

---

## Configuración (archivo `config.py`)

- `WATCH_EVERY_MIN = 30` → cada cuántos minutos revisa.
- `NIVELES_CLAVE` → niveles que disparan alerta al cruzarse.
- `MOVE_ALERT_PCT = 1.2` → % de movimiento diario que dispara alerta.
- `USE_AI = True` → comentario en lenguaje natural con Claude (necesita saldo en
  tu API key; si no hay saldo, el bot funciona igual solo con reglas).

Tus tokens van en `secrets_local.py` (no se sube a GitHub). Por ahora usa el
**mismo bot de Telegram** que tu news-bot. Si quieres un bot dedicado solo para
el dólar, crea uno con @BotFather y pega el token nuevo ahí.

---

## Cómo lee el sesgo

| Puntaje | Sesgo |
|---|---|
| ≥ +40  | 🔴 Alcista (dólar sube / peso débil) |
| +15 a +39 | 🟠 Levemente alcista |
| −14 a +14 | ⚪ Neutral |
| −15 a −39 | 🟢 Levemente bajista |
| ≤ −40  | 🟢 Bajista (dólar baja / peso fuerte) |
