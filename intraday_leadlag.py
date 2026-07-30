"""
¿El cobre (y DXY/real) se ADELANTAN al peso intradía, o se mueven al mismo tiempo?

Usa velas de 15 min. Mide, sobre retornos intradía:
  - lag 0  : correlación en la MISMA vela (co-movimiento instantáneo)
  - lag +1 : ¿el driver en esta vela predice el PESO en la SIGUIENTE? (driver lidera)
  - lag -1 : ¿el peso lidera al driver? (control)

OJO honesto: si el USD/CLP cotiza menos seguido que el cobre, puede APARECER que
el cobre lidera solo porque el dato del peso llega 'atrasado' en el feed
(precio rancio). Eso NO es tradeable. Por eso miramos también el lag -1: si hay
'liderazgo' en ambos sentidos, es artefacto de liquidez, no señal real.
"""
import numpy as np
import requests

UA = {"User-Agent": "Mozilla/5.0"}
SYMS = {"clp": "USDCLP=X", "cobre": "HG=F", "dxy": "DX-Y.NYB", "brl": "USDBRL=X"}


def _fetch(sym, interval="15m", rng="1mo"):
    r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}",
                     params={"interval": interval, "range": rng}, headers=UA, timeout=25)
    res = r.json()["chart"]["result"][0]
    ts = res["timestamp"]
    c = res["indicators"]["quote"][0]["close"]
    return {ts[i]: c[i] for i in range(len(ts)) if c[i] is not None}


def correr(interval="15m", rng="1mo"):
    m = {k: _fetch(s, interval, rng) for k, s in SYMS.items()}
    comunes = sorted(set(m["clp"]) & set(m["cobre"]) & set(m["dxy"]) & set(m["brl"]))
    print(f"{interval}: {len(comunes)} velas comunes\n")
    px = {k: np.array([m[k][t] for t in comunes], float) for k in m}
    r = {k: np.diff(np.log(px[k])) for k in px}
    clp = r["clp"]

    def corr(a, b):
        if len(a) < 20 or a.std() == 0 or b.std() == 0:
            return 0.0
        return float(np.corrcoef(a, b)[0, 1])

    print(f"{'Driver':8} {'lag0 (mismo)':>13} {'lag+1 (lidera)':>15} {'lag-1 (control)':>16}  ¿real?")
    print("-" * 66)
    for k in ("cobre", "dxy", "brl"):
        d = r[k]
        c0 = corr(d, clp)                    # misma vela
        cp = corr(d[:-1], clp[1:])           # driver t -> peso t+1
        cm = corr(clp[:-1], d[1:])           # peso t -> driver t+1 (control)
        # señal real de liderazgo del driver: predice al peso MAS que al reves
        real = "SÍ ✓" if (abs(cp) > 0.04 and abs(cp) > abs(cm) * 1.5) else "no (co-mov/rancio)"
        print(f"{k:8} {c0:+13.2f} {cp:+15.3f} {cm:+16.3f}  {real}")
    print()
    print("lag0 fuerte = se mueven juntos (bueno para NOWCAST del momento).")
    print("lag+1 fuerte y MAYOR que lag-1 = el driver se adelanta -> edge intradía real.")
    return comunes, px, r


if __name__ == "__main__":
    print("=== 15 min / 1 mes ===")
    correr("15m", "1mo")
    print("\n=== 5 min / 5 días (más fino) ===")
    correr("5m", "5d")
