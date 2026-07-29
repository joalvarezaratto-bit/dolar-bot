"""
Grafico del USD/CLP (velas diarias) con soportes, resistencias, medias moviles
y niveles clave. Guarda un PNG para mandar por Telegram.

Mismo estilo visual oscuro que tu grafico de BTC.
"""
import config as C
import analysis as A


def _sma_series(candles, n):
    cierres = [c["c"] for c in candles]
    out = [None] * len(cierres)
    for i in range(n - 1, len(cierres)):
        out[i] = sum(cierres[i - n + 1:i + 1]) / n
    return out


def make_chart(a, path="usdclp.png", velas=90):
    """a = dict de analysis.analizar(). Dibuja las ultimas `velas` diarias."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    full = a["usdclp"]["candles"]
    candles = full[-velas:]
    sma_c = _sma_series(full, C.SMA_CORTA)[-velas:]
    sma_l = _sma_series(full, C.SMA_LARGA)[-velas:]

    fig, ax = plt.subplots(figsize=(12, 7))
    fig.patch.set_facecolor("#0e1117")
    ax.set_facecolor("#0e1117")

    for i, c in enumerate(candles):
        subio = c["c"] >= c["o"]
        color = "#26a69a" if subio else "#ef5350"
        ax.plot([i, i], [c["l"], c["h"]], color=color, linewidth=0.8, zorder=2)
        lo_body = min(c["o"], c["c"])
        alto = abs(c["c"] - c["o"]) or (c["h"] * 0.0005)
        ax.add_patch(Rectangle((i - 0.3, lo_body), 0.6, alto,
                               facecolor=color, edgecolor=color, zorder=3))

    n = len(candles)
    xs = range(n)
    # medias moviles
    if any(sma_c):
        ax.plot(xs, sma_c, color="#42a5f5", linewidth=1.2, alpha=0.9,
                label=f"SMA{C.SMA_CORTA}", zorder=4)
    if any(sma_l):
        ax.plot(xs, sma_l, color="#ab47bc", linewidth=1.2, alpha=0.9,
                label=f"SMA{C.SMA_LARGA}", zorder=4)

    # resistencias (rojo) y soportes (verde)
    for p in a["resistencias"]:
        ax.axhline(p, color="#ef5350", linestyle="--", linewidth=1.1, alpha=0.9)
        ax.text(n - 0.5, p, f" R {p:,.0f}", color="#ef5350", va="center",
                fontsize=9, fontweight="bold")
    for p in a["soportes"]:
        ax.axhline(p, color="#26a69a", linestyle="--", linewidth=1.1, alpha=0.9)
        ax.text(n - 0.5, p, f" S {p:,.0f}", color="#26a69a", va="center",
                fontsize=9, fontweight="bold")

    # fibonacci (naranja punteado) del ultimo impulso
    fib = a.get("fib")
    if fib:
        for r in [0.236, 0.382, 0.5, 0.618, 0.786]:
            p = fib["levels"][r]
            ax.axhline(p, color="#f0b90b", linestyle=":", linewidth=0.9, alpha=0.65)
            ax.text(0, p, f"fib {r:.3f} ", color="#f0b90b", va="center", ha="right", fontsize=8)

    # precio actual
    ax.axhline(a["price"], color="white", linewidth=0.9, alpha=0.5)

    ax.set_title(f"USD/CLP · diario · {a['price']:,.2f}  ({a['change_pct']:+.2f}%)",
                 color="white", fontsize=14, fontweight="bold")
    ax.tick_params(colors="#888")
    for s in ax.spines.values():
        s.set_color("#333")
    ax.grid(True, color="#222", linewidth=0.5)
    ax.set_xlim(-2, n + 6)
    ax.margins(y=0.05)
    leg = ax.legend(loc="upper left", facecolor="#0e1117", edgecolor="#333",
                    labelcolor="#ccc", fontsize=9)
    plt.tight_layout()
    fig.savefig(path, dpi=110, facecolor=fig.get_facecolor())
    plt.close(fig)
    return path
