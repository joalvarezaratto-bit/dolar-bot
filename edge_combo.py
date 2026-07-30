"""
Señal COMBINADA de las 3 que pasaron el filtro anti-suerte:
  valor justo FADE (mean-reversion) + cobre lead + DXY lead.

Se estandariza cada una (sin lookahead) y se suman. Luego se prueba como
estrategia long/short: acierto, Sharpe, retorno vs comprar-y-mantener,
consistencia por mitades, y con COSTOS de transacción (el USD/CLP es exótico,
spread ancho -> los costos importan).
"""
import math
import numpy as np
import backtest as B


def construir():
    fechas, arr, hi, lo = B.cargar()
    n = len(fechas)
    rets = {k: np.concatenate([[0.0], np.diff(np.log(arr[k]))]) for k in arr}
    valz = [B._valor_z(arr, i) if i >= 60 else 0.0 for i in range(n)]

    def rstd(x, i, w=60):
        s = x[i - w:i].std()
        return s if s > 0 else 1e-9

    def señal(i):
        v = -valz[i]                                   # valor justo fade (ya ~z)
        cu = -rets["cobre"][i] / rstd(rets["cobre"], i)  # cobre lead 1d
        dx5 = math.log(arr["dxy"][i] / arr["dxy"][i - 5]) if i >= 5 else 0.0
        dx = dx5 / (rstd(rets["dxy"], i) * math.sqrt(5))  # DXY lead 5d
        return v + cu + dx

    return fechas, arr, señal, n


def evaluar():
    fechas, arr, señal, n = construir()
    I = list(range(65, n - 2))
    s = np.array([señal(i) for i in I])
    f = np.array([math.log(arr["clp"][i + 1] / arr["clp"][i]) for i in I])
    mitad = len(I) // 2

    def stats(sl, fl):
        corr = float(np.corrcoef(sl, fl)[0, 1])
        hit = float((np.sign(sl) == np.sign(fl)).mean() * 100)
        pnl = np.sign(sl) * fl
        sh = float(pnl.mean() / (pnl.std() + 1e-9) * math.sqrt(252))
        return corr, hit, sh

    c, h, sh = stats(s, f)
    c1, h1, s1 = stats(s[:mitad], f[:mitad])
    c2, h2, s2 = stats(s[mitad:], f[mitad:])
    print("== SEÑAL COMBINADA (valor-fade + cobre lead + DXY lead) ==")
    print(f"  Correlación con día siguiente: {c:+.3f}")
    print(f"  Acierto direccional:           {h:.1f}%")
    print(f"  Sharpe (long/short, bruto):    {sh:+.2f}")
    print(f"  Consistencia  1ª mitad: corr {c1:+.3f} acierto {h1:.1f}% Sharpe {s1:+.2f}")
    print(f"                2ª mitad: corr {c2:+.3f} acierto {h2:.1f}% Sharpe {s2:+.2f}")
    print()

    # --- estrategia con costos ---
    pos = np.sign(s)
    turnover = np.abs(np.diff(np.concatenate([[0], pos])))   # cambios de posicion
    gross = pos * f
    bh = f
    print("== Estrategia long/short vs comprar-y-mantener ==")
    print(f"  Días long: {(pos>0).mean()*100:.0f}%  ·  días short: {(pos<0).mean()*100:.0f}%  (balanceado = no vive de la tendencia)")
    print(f"  Rotación media: {turnover.mean()*100:.0f}% (cuántos días cambia de lado)")
    for costo_bps in (0, 3, 7):
        neto = gross - turnover * costo_bps / 10000
        tot = neto.sum() * 100
        shn = neto.mean() / (neto.std() + 1e-9) * math.sqrt(252)
        print(f"  Costo {costo_bps} pb/trade → retorno {tot:+6.1f}%   Sharpe {shn:+.2f}")
    print(f"  Comprar y mantener el dólar:      {bh.sum()*100:+6.1f}%   Sharpe {bh.mean()/bh.std()*math.sqrt(252):+.2f}")
    print()

    # curva para graficar (costo 3 pb)
    neto = gross - turnover * 3 / 10000
    return {"eq_estrategia": np.cumsum(neto) * 100, "eq_bh": np.cumsum(bh) * 100,
            "fechas": [fechas[i] for i in I]}


if __name__ == "__main__":
    evaluar()
