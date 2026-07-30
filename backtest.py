"""
BACKTEST del sesgo del agente — ¿de verdad predice, o solo suena bien?

Para CADA dia historico t, recalcula el puntaje del agente usando SOLO datos
hasta t (sin mirar el futuro), y mide si ese puntaje anticipo el movimiento del
USD/CLP del dia siguiente (y de la semana siguiente).

Replica la MISMA logica de analysis.py:
  - Tendencia propia (medias 20/50)
  - RSI (momentum + extremos)
  - Motores por correlacion medida (cobre inverso, DXY y real directos)
  - Valor justo (regresion cobre+DXY+real -> mean reversion)

HONESTO: es una prueba estadistica sobre el pasado. Que haya funcionado antes
no garantiza el futuro, pero si NO funciono antes, no hay por que confiar en el.
"""
import math
import datetime as dt
import numpy as np
import requests
import config as C

UA = {"User-Agent": "Mozilla/5.0"}


def _fetch(symbol, rng="5y"):
    r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
                     params={"interval": "1d", "range": rng}, headers=UA, timeout=30)
    res = r.json()["chart"]["result"][0]
    ts = res["timestamp"]
    q = res["indicators"]["quote"][0]
    out = {}
    for i in range(len(ts)):
        c = q["close"][i]
        h, l = q["high"][i], q["low"][i]
        if c is None:
            continue
        d = dt.datetime.utcfromtimestamp(ts[i]).strftime("%Y-%m-%d")
        out[d] = {"c": c, "h": h if h is not None else c, "l": l if l is not None else c}
    return out


def cargar():
    """Descarga y alinea los 4 instrumentos por fechas comunes."""
    m = {"clp": _fetch(C.SYM_USDCLP), "cobre": _fetch(C.SYM_COBRE),
         "dxy": _fetch(C.SYM_DXY), "brl": _fetch(C.SYM_BRL)}
    comunes = sorted(set(m["clp"]) & set(m["cobre"]) & set(m["dxy"]) & set(m["brl"]))
    arr = {k: np.array([m[k][d]["c"] for d in comunes], dtype=float) for k in m}
    hi = np.array([m["clp"][d]["h"] for d in comunes], dtype=float)
    lo = np.array([m["clp"][d]["l"] for d in comunes], dtype=float)
    return comunes, arr, hi, lo


def _sma(x, n, i):
    if i + 1 < n:
        return None
    return x[i - n + 1:i + 1].mean()


def _rsi(x, i, n=14):
    if i < n:
        return None
    d = np.diff(x[:i + 1])
    up = np.where(d > 0, d, 0.0)
    dn = np.where(d < 0, -d, 0.0)
    ag, ap = up[:n].mean(), dn[:n].mean()
    for k in range(n, len(d)):
        ag = (ag * (n - 1) + up[k]) / n
        ap = (ap * (n - 1) + dn[k]) / n
    if ap == 0:
        return 100.0
    return 100 - 100 / (1 + ag / ap)


def _corr(r_clp, r_k, i, win=40):
    a, b = r_clp[i - win:i], r_k[i - win:i]
    if len(a) < 10 or a.std() == 0 or b.std() == 0:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def _zmov(r_k, i, win=40):
    base = r_k[i - win:i]
    sd = base.std()
    if sd == 0:
        return 0.0
    return float(r_k[i - 5:i].sum() / (sd * math.sqrt(5)))


def _valor_z(arr, i, win=60):
    y = arr["clp"][i - win + 1:i + 1]
    X = np.column_stack([arr["cobre"][i - win + 1:i + 1],
                         arr["dxy"][i - win + 1:i + 1],
                         arr["brl"][i - win + 1:i + 1],
                         np.ones(win)])
    try:
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    except Exception:
        return 0.0
    resid = y - X @ beta
    sd = resid.std()
    return 0.0 if sd == 0 else float(resid[-1] / sd)


def puntuar(arr, rets, hi, lo, i):
    """Reproduce el puntaje del agente en el dia i, con datos SOLO hasta i."""
    price = arr["clp"][i]
    score = 0.0

    # 1) Tendencia propia (medias 20/50)
    s20, s50 = _sma(arr["clp"], 20, i), _sma(arr["clp"], 50, i)
    if s20 and s50:
        if price > s20 > s50:
            score += 30
        elif price < s20 < s50:
            score -= 30

    # 2) RSI
    rsi = _rsi(arr["clp"], i)
    if rsi is not None:
        score += (rsi - 50) / 50 * 12
        if rsi >= 70:
            score -= 5
        elif rsi <= 30:
            score += 5

    # 3) Motores por correlacion (cobre/dxy/brl); corr ya trae el signo
    for k in ("cobre", "dxy", "brl"):
        corr = _corr(rets["clp"], rets[k], i)
        z = _zmov(rets[k], i)
        score += max(-16, min(16, corr * z * 12))

    # 4) Valor justo (mean reversion)
    z = max(-2, min(2, _valor_z(arr, i)))
    score += -z * 6.5

    return int(max(-100, min(100, round(score))))


def correr():
    print("Descargando 5 años de datos...")
    fechas, arr, hi, lo = cargar()
    n = len(fechas)
    print(f"{n} días alineados: {fechas[0]} → {fechas[-1]}\n")

    rets = {k: np.concatenate([[0.0], np.diff(np.log(arr[k]))]) for k in arr}

    scores, fwd1, fwd5 = [], [], []
    ini = 65   # necesita historia para medias/corr/regresion
    for i in range(ini, n - 6):
        s = puntuar(arr, rets, hi, lo, i)
        r1 = math.log(arr["clp"][i + 1] / arr["clp"][i])
        r5 = math.log(arr["clp"][i + 5] / arr["clp"][i])
        scores.append(s); fwd1.append(r1); fwd5.append(r5)

    scores = np.array(scores); fwd1 = np.array(fwd1); fwd5 = np.array(fwd5)
    print(f"Días evaluados: {len(scores)}\n")

    # --- 1) Correlacion puntaje vs retorno futuro ---
    c1 = np.corrcoef(scores, fwd1)[0, 1]
    c5 = np.corrcoef(scores, fwd5)[0, 1]
    print("== ¿El puntaje se relaciona con el movimiento futuro? ==")
    print(f"  Correlación puntaje ↔ retorno día siguiente:   {c1:+.3f}")
    print(f"  Correlación puntaje ↔ retorno semana siguiente: {c5:+.3f}")
    print("  (>0 = a mayor puntaje, mayor tendencia a subir el dólar. |0.05|+ ya es señal útil)\n")

    # --- 2) Acierto direccional cuando hay señal ---
    print("== Acierto direccional (¿acertó el signo del día siguiente?) ==")
    for umb in (0, 15, 40):
        mask = np.abs(scores) >= umb
        if mask.sum() == 0:
            continue
        aciertos = np.sign(scores[mask]) == np.sign(fwd1[mask])
        hit = aciertos.mean() * 100
        print(f"  |puntaje|≥{umb:2d}:  {hit:5.1f}% de acierto   ({mask.sum()} días)")
    print("  (50% = azar. Arriba de 52-53% ya es explotable con gestión de riesgo)\n")

    # --- 3) Retorno promedio por tramo de puntaje ---
    print("== Retorno promedio del día siguiente, por tramo de puntaje ==")
    tramos = [(-100, -40, "Bajista fuerte"), (-40, -15, "Bajista leve"),
              (-15, 15, "Neutral"), (15, 40, "Alcista leve"), (40, 100, "Alcista fuerte")]
    for lo_s, hi_s, etq in tramos:
        m = (scores >= lo_s) & (scores < hi_s)
        if m.sum() == 0:
            continue
        print(f"  {etq:16} ({lo_s:+4d}..{hi_s:+4d}): {fwd1[m].mean()*10000:+6.1f} pb   ({m.sum()} días)")
    print("  (debería ser CRECIENTE: más bajista → más negativo; más alcista → más positivo)\n")

    # --- 4) Estrategia simple vs comprar y mantener ---
    print("== Estrategia: seguir el sesgo (long si ≥+15, short si ≤−15) ==")
    pos = np.where(scores >= 15, 1, np.where(scores <= -15, -1, 0))
    pnl = pos * fwd1
    activos = pos != 0
    if activos.sum():
        sharpe = pnl[activos].mean() / (pnl[activos].std() + 1e-9) * math.sqrt(252)
        total = pnl.sum() * 100
        bh = fwd1.sum() * 100
        print(f"  Días en posición: {activos.sum()} de {len(scores)}")
        print(f"  Retorno acumulado estrategia: {total:+.1f}%   (Sharpe ~{sharpe:+.2f})")
        print(f"  Comprar y mantener el dólar:  {bh:+.1f}%")
    print()

    return {"scores": scores, "fwd1": fwd1, "pos": pos, "fechas": fechas[ini:ini + len(scores)]}


if __name__ == "__main__":
    correr()
