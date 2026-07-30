"""
BUSQUEDA DE EDGE — probar varias señales a ver si ALGUNA predice el USD/CLP.

Prueba (sin lookahead) señales de TENDENCIA, MEAN-REVERSION y LEAD-LAG contra
el retorno futuro (1, 5 y 10 días). Para cada una mide:
  - correlación con el retorno futuro
  - acierto direccional
  - Sharpe de una estrategia long/short simple
  - ESTABILIDAD: corr en la 1ª mitad vs 2ª mitad del período (anti-suerte)

Filtro honesto: una señal solo cuenta si funciona en AMBAS mitades con el mismo
signo. Si solo brilla en una, es casualidad / sobreajuste.
"""
import math
import numpy as np
import backtest as B


def correr():
    fechas, arr, hi, lo = B.cargar()
    n = len(fechas)
    rets = {k: np.concatenate([[0.0], np.diff(np.log(arr[k]))]) for k in arr}

    # --- precomputar indicadores ---
    print(f"{n} días. Precomputando indicadores...")
    sma20 = [B._sma(arr["clp"], 20, i) for i in range(n)]
    sma50 = [B._sma(arr["clp"], 50, i) for i in range(n)]
    rsi = [B._rsi(arr["clp"], i) for i in range(n)]
    valz = [B._valor_z(arr, i) if i >= 60 else 0.0 for i in range(n)]

    def ret(k, i, w):   # retorno de los ultimos w dias del instrumento k
        if i - w < 0:
            return 0.0
        return math.log(arr[k][i] / arr[k][i - w])

    # --- definicion de señales (valor>0 = predigo que el DÓLAR SUBE) ---
    senales = {
        "Compuesto (actual)":      lambda i: B.puntuar(arr, rets, hi, lo, i),
        "Tendencia (20/50)":       lambda i: (1 if (sma20[i] and sma50[i] and arr['clp'][i] > sma20[i] > sma50[i])
                                              else -1 if (sma20[i] and sma50[i] and arr['clp'][i] < sma20[i] < sma50[i]) else 0),
        "Momentum 10d":            lambda i: ret("clp", i, 10),
        "Valor justo FADE":        lambda i: -valz[i],          # dólar caro -> predigo baja
        "RSI FADE":                lambda i: -(rsi[i] - 50) if rsi[i] is not None else 0.0,
        "Reversión 1d":            lambda i: -rets["clp"][i],   # ayer subió -> predigo baja
        "Cobre lead 5d":           lambda i: -ret("cobre", i, 5),  # cobre subió -> peso fuerte -> dólar baja
        "DXY lead 5d":             lambda i: ret("dxy", i, 5),
        "Real lead 5d":            lambda i: ret("brl", i, 5),
        "Cobre lead 1d":           lambda i: -rets["cobre"][i],
    }

    I = list(range(65, n - 11))
    mitad = I[len(I) // 2]

    def evaluar(fn, horizon, sub=None):
        idx = [i for i in I if (sub is None or (i < mitad if sub == 1 else i >= mitad))]
        s = np.array([fn(i) for i in idx], float)
        f = np.array([math.log(arr["clp"][i + horizon] / arr["clp"][i]) for i in idx], float)
        if s.std() == 0:
            return None
        corr = float(np.corrcoef(s, f)[0, 1])
        act = s != 0
        hit = float((np.sign(s[act]) == np.sign(f[act])).mean() * 100) if act.sum() else float("nan")
        pnl = np.sign(s) * f
        sharpe = float(pnl.mean() / (pnl.std() + 1e-9) * math.sqrt(252 / horizon))
        return {"corr": corr, "hit": hit, "sharpe": sharpe, "n": int(act.sum())}

    # base: cuantos dias subio el dolar (para comparar el acierto)
    fwd1 = np.array([math.log(arr["clp"][i + 1] / arr["clp"][i]) for i in I])
    base_up = (fwd1 > 0).mean() * 100
    print(f"Base: el dólar subió el {base_up:.1f}% de los días (referencia del acierto)\n")

    print("HORIZONTE 1 DÍA")
    print(f"{'Señal':22} {'corr':>7} {'acierto':>8} {'Sharpe':>7} {'corr 1ªmit':>10} {'corr 2ªmit':>10}  estable?")
    print("-" * 82)
    resultados = []
    for nom, fn in senales.items():
        r = evaluar(fn, 1)
        r1 = evaluar(fn, 1, sub=1)
        r2 = evaluar(fn, 1, sub=2)
        if not r:
            continue
        estable = "SÍ ✓" if (r1 and r2 and np.sign(r1["corr"]) == np.sign(r2["corr"]) and
                             abs(r1["corr"]) > 0.02 and abs(r2["corr"]) > 0.02) else "no"
        print(f"{nom:22} {r['corr']:+7.3f} {r['hit']:7.1f}% {r['sharpe']:+7.2f} "
              f"{r1['corr']:+10.3f} {r2['corr']:+10.3f}  {estable}")
        resultados.append((nom, fn, r, estable))

    # horizonte 5 dias para las mismas señales (a veces el edge es mas lento)
    print("\nHORIZONTE 5 DÍAS (corr)")
    for nom, fn in senales.items():
        r = evaluar(fn, 5)
        if r:
            print(f"  {nom:22} corr {r['corr']:+.3f}   acierto {r['hit']:.1f}%   Sharpe {r['sharpe']:+.2f}")

    return resultados


if __name__ == "__main__":
    correr()
