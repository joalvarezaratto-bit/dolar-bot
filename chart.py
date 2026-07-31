"""
Grafico del USD/CLP (velas diarias) limpio y moderno para Telegram:
velas claras, medias moviles, soportes/resistencias como etiquetas a la derecha,
zona dorada de Fibonacci (0.5-0.618) y el precio actual destacado.
"""
import datetime as dt
import config as C

try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo(C.TIMEZONE)
except Exception:
    _TZ = dt.timezone(dt.timedelta(hours=-4))   # respaldo: Chile continental


def _local(ts):
    """Convierte epoch UTC a hora de Chile (para las etiquetas del eje)."""
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).astimezone(_TZ)

# --- paleta ---
BG = "#0d1117"
UP = "#3fb950"       # vela alcista (verde github)
DOWN = "#f85149"     # vela bajista (rojo github)
SMA1 = "#58a6ff"     # media corta (azul)
SMA2 = "#d29922"     # media larga (ambar)
TXT = "#e6edf3"
MUTE = "#8b949e"
GRID = "#21262d"
GOLD = "#f0b90b"


def _sma_series(candles, n):
    cierres = [c["c"] for c in candles]
    out = [None] * len(cierres)
    for i in range(n - 1, len(cierres)):
        out[i] = sum(cierres[i - n + 1:i + 1]) / n
    return out


def make_chart(a, path="usdclp.png", velas=65):
    """a = dict de analysis.analizar(). Dibuja las ultimas `velas` diarias."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle, FancyBboxPatch

    full = a["usdclp"]["candles"]
    candles = full[-velas:]
    sma_c = _sma_series(full, C.SMA_CORTA)[-velas:]
    sma_l = _sma_series(full, C.SMA_LARGA)[-velas:]
    n = len(candles)
    price = a["price"]

    fig, ax = plt.subplots(figsize=(13, 7), dpi=130)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)

    # rango Y con un pequeño margen
    lows = [c["l"] for c in candles]
    highs = [c["h"] for c in candles]
    y0, y1 = min(lows), max(highs)
    margen = (y1 - y0) * 0.08
    ax.set_ylim(y0 - margen, y1 + margen)

    # --- zona dorada de Fibonacci (0.5-0.618), sutil, en vez de 5 lineas ---
    fib = a.get("fib")
    if fib:
        p50, p618 = fib["levels"][0.5], fib["levels"][0.618]
        lo_z, hi_z = min(p50, p618), max(p50, p618)
        ax.axhspan(lo_z, hi_z, color=GOLD, alpha=0.07, zorder=0)
        ax.text(0.6, hi_z, "  zona Fibonacci 0.5–0.618", color=GOLD, alpha=0.7,
                fontsize=8, va="bottom", ha="left", style="italic")

    # --- medias moviles (debajo de las velas) ---
    xs = list(range(n))
    if any(sma_c):
        ax.plot(xs, sma_c, color=SMA1, linewidth=1.6, alpha=0.95,
                label=f"SMA {C.SMA_CORTA}", zorder=2, solid_capstyle="round")
    if any(sma_l):
        ax.plot(xs, sma_l, color=SMA2, linewidth=1.6, alpha=0.95,
                label=f"SMA {C.SMA_LARGA}", zorder=2, solid_capstyle="round")

    # --- velas ---
    w = 0.62
    for i, c in enumerate(candles):
        subio = c["c"] >= c["o"]
        color = UP if subio else DOWN
        # mecha
        ax.plot([i, i], [c["l"], c["h"]], color=color, linewidth=1.0,
                alpha=0.9, zorder=3, solid_capstyle="round")
        # cuerpo
        lo_body = min(c["o"], c["c"])
        alto = abs(c["c"] - c["o"]) or (c["c"] * 0.0004)
        ax.add_patch(Rectangle((i - w / 2, lo_body), w, alto, facecolor=color,
                               edgecolor=color, linewidth=0.5, zorder=4))

    # --- soportes / resistencias como etiquetas a la derecha (max 2 c/u) ---
    def _tag(y, texto, color):
        ax.axhline(y, color=color, linestyle=(0, (6, 4)), linewidth=1.0,
                   alpha=0.55, zorder=1)
        ax.annotate(texto, xy=(n - 1, y), xytext=(6, 0), textcoords="offset points",
                    va="center", ha="left", fontsize=8.5, color=BG, fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.3", fc=color, ec="none"), zorder=6)

    for p in a["resistencias"][:2]:
        _tag(p, f"R {p:,.0f}", DOWN)
    for p in a["soportes"][:2]:
        _tag(p, f"S {p:,.0f}", UP)

    # --- precio actual: linea + etiqueta destacada ---
    pc = UP if a["change_pct"] >= 0 else DOWN
    ax.axhline(price, color=TXT, linewidth=1.0, alpha=0.5,
               linestyle=(0, (2, 2)), zorder=5)
    ax.annotate(f"{price:,.1f}", xy=(n - 1, price), xytext=(6, 0),
                textcoords="offset points", va="center", ha="left", fontsize=9.5,
                color=BG, fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.35", fc=pc, ec="none"), zorder=7)

    # --- eje X con FECHAS ---
    idxs = list(range(0, n, max(1, n // 7)))
    etiquetas = [_local(candles[i]["t"]).strftime("%d %b") for i in idxs]
    ax.set_xticks(idxs)
    ax.set_xticklabels(etiquetas, color=MUTE, fontsize=9)

    # --- titulo / subtitulo ---
    signo = "▲" if a["change_pct"] >= 0 else "▼"
    ax.set_title("USD/CLP · velas diarias", color=TXT, fontsize=15,
                 fontweight="bold", loc="left", pad=26)
    ax.annotate(f"{price:,.2f}   {signo} {a['change_pct']:+.2f}%",
                xy=(0, 1), xycoords="axes fraction", xytext=(0, 8),
                textcoords="offset points", fontsize=12, fontweight="bold",
                color=pc, ha="left", va="bottom")

    # --- estilo general ---
    ax.tick_params(colors=MUTE, length=0)
    ax.yaxis.tick_right()
    ax.yaxis.set_tick_params(labelsize=9)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.grid(True, axis="y", color=GRID, linewidth=0.7, alpha=0.7)
    ax.set_axisbelow(True)
    ax.set_xlim(-1, n + 9)

    leg = ax.legend(loc="upper left", facecolor=BG, edgecolor=GRID,
                    labelcolor=TXT, fontsize=9, framealpha=0.6)
    leg.get_frame().set_linewidth(0.6)

    fig.subplots_adjust(left=0.02, right=0.93, top=0.88, bottom=0.08)
    fig.savefig(path, facecolor=fig.get_facecolor())
    plt.close(fig)
    return path


def make_chart_intraday(a, path="usdclp.png", barras=90):
    """Grafico de velas de 1 HORA (la sesion en detalle), mismo estilo limpio.
    Devuelve None si no hay datos intradia (para caer al grafico diario)."""
    import intraday as IN
    candles = IN.candles_ohlc(C.SYM_USDCLP, "60m", "7d")
    if len(candles) < 20:
        return None

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    candles = candles[-barras:]
    sma = _sma_series(candles, 24)   # ~1 dia de trading
    n = len(candles)
    price = a["price"]

    fig, ax = plt.subplots(figsize=(13, 7), dpi=130)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)

    y0, y1 = min(c["l"] for c in candles), max(c["h"] for c in candles)
    m = (y1 - y0) * 0.10 or price * 0.001
    ax.set_ylim(y0 - m, y1 + m)

    # sombrear cada segundo dia para ubicarse en el tiempo
    prev_day, start = None, 0
    shade = False
    for i, c in enumerate(candles):
        day = _local(c["t"]).date()
        if day != prev_day:
            if shade and prev_day is not None:
                ax.axvspan(start - 0.5, i - 0.5, color="#ffffff", alpha=0.02, zorder=0)
            shade = not shade
            start = i
            prev_day = day
    if shade:
        ax.axvspan(start - 0.5, n - 0.5, color="#ffffff", alpha=0.02, zorder=0)

    if any(sma):
        ax.plot(range(n), sma, color=SMA1, linewidth=1.6, alpha=0.95,
                label="SMA 24h", zorder=2, solid_capstyle="round")

    w = 0.6
    for i, c in enumerate(candles):
        color = UP if c["c"] >= c["o"] else DOWN
        ax.plot([i, i], [c["l"], c["h"]], color=color, linewidth=1.0, alpha=0.9,
                zorder=3, solid_capstyle="round")
        lo_body = min(c["o"], c["c"])
        alto = abs(c["c"] - c["o"]) or (c["c"] * 0.0003)
        ax.add_patch(Rectangle((i - w / 2, lo_body), w, alto, facecolor=color,
                               edgecolor=color, linewidth=0.4, zorder=4))

    def _tag(y, texto, color):
        ax.axhline(y, color=color, linestyle=(0, (6, 4)), linewidth=1.0, alpha=0.5, zorder=1)
        ax.annotate(texto, xy=(n - 1, y), xytext=(6, 0), textcoords="offset points",
                    va="center", ha="left", fontsize=8.5, color=BG, fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.3", fc=color, ec="none"), zorder=6)

    for p in a["resistencias"][:2]:
        if y0 - m <= p <= y1 + m:
            _tag(p, f"R {p:,.0f}", DOWN)
    for p in a["soportes"][:2]:
        if y0 - m <= p <= y1 + m:
            _tag(p, f"S {p:,.0f}", UP)

    pc = UP if a["change_pct"] >= 0 else DOWN
    ax.axhline(price, color=TXT, linewidth=1.0, alpha=0.5, linestyle=(0, (2, 2)), zorder=5)
    ax.annotate(f"{price:,.1f}", xy=(n - 1, price), xytext=(6, 0),
                textcoords="offset points", va="center", ha="left", fontsize=9.5,
                color=BG, fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.35", fc=pc, ec="none"), zorder=7)

    idxs = list(range(0, n, max(1, n // 7)))
    ax.set_xticks(idxs)
    ax.set_xticklabels([_local(candles[i]["t"]).strftime("%d %Hh") for i in idxs],
                       color=MUTE, fontsize=9)

    signo = "▲" if a["change_pct"] >= 0 else "▼"
    ax.set_title("USD/CLP · velas 1h (sesión reciente)", color=TXT, fontsize=15,
                 fontweight="bold", loc="left", pad=26)
    ax.annotate(f"{price:,.2f}   {signo} {a['change_pct']:+.2f}%",
                xy=(0, 1), xycoords="axes fraction", xytext=(0, 8),
                textcoords="offset points", fontsize=12, fontweight="bold",
                color=pc, ha="left", va="bottom")

    ax.tick_params(colors=MUTE, length=0)
    ax.yaxis.tick_right()
    for s in ax.spines.values():
        s.set_visible(False)
    ax.grid(True, axis="y", color=GRID, linewidth=0.7, alpha=0.7)
    ax.set_axisbelow(True)
    ax.set_xlim(-1, n + 9)
    leg = ax.legend(loc="upper left", facecolor=BG, edgecolor=GRID,
                    labelcolor=TXT, fontsize=9, framealpha=0.6)
    leg.get_frame().set_linewidth(0.6)

    fig.subplots_adjust(left=0.02, right=0.93, top=0.88, bottom=0.08)
    fig.savefig(path, facecolor=fig.get_facecolor())
    plt.close(fig)
    return path
