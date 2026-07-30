"""
VERIFICACION: ¿el liderazgo del cobre sobre el peso es REAL o precio rancio?

Prueba decisiva:
  - Si el cobre lidera al peso SOLO cuando Chile está cerrado (madrugada) -> es
    precio rancio (el peso 'salta' al abrir para ponerse al día). NO tradeable.
  - Si el liderazgo PERSISTE en horario líquido (Chile operando) -> es real.

Además: estrategia intradía solo en horario líquido, con selectividad (operar
solo cuando el cobre se mueve fuerte) y COSTOS, para ver si deja plata neta.
"""
import datetime as dt
import numpy as np
import requests

UA = {"User-Agent": "Mozilla/5.0"}
SYMS = {"clp": "USDCLP=X", "cobre": "HG=F"}


def _fetch(sym, interval="15m", rng="1mo"):
    r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}",
                     params={"interval": interval, "range": rng}, headers=UA, timeout=25)
    res = r.json()["chart"]["result"][0]
    ts = res["timestamp"]
    c = res["indicators"]["quote"][0]["close"]
    return {ts[i]: c[i] for i in range(len(ts)) if c[i] is not None}


def correr(interval="15m", rng="1mo"):
    m = {k: _fetch(s, interval, rng) for k, s in SYMS.items()}
    comunes = sorted(set(m["clp"]) & set(m["cobre"]))
    px = {k: np.array([m[k][t] for t in comunes], float) for k in m}
    r = {k: np.diff(np.log(px[k])) for k in px}
    horas = np.array([dt.datetime.utcfromtimestamp(t).hour for t in comunes[1:]])
    clp, cu = r["clp"], r["cobre"]
    print(f"{interval}/{rng}: {len(comunes)} velas comunes\n")

    def corr(a, b):
        if len(a) < 20 or a.std() == 0 or b.std() == 0:
            return 0.0, len(a)
        return float(np.corrcoef(a, b)[0, 1]), len(a)

    # Horario LÍQUIDO: Chile operando (UTC 13-18 ≈ 9:00-14:00 hora Chile),
    # que además pisa la sesión activa del cobre en EE.UU.
    liq = (horas >= 13) & (horas < 18)

    print("== El cobre se adelanta 15m al peso: ¿dónde? (lag+1) ==")
    c_all, n_all = corr(cu[:-1], clp[1:])
    print(f"  Todas las horas:     corr {c_all:+.3f}  ({n_all} pares)")
    cl, nl = corr(cu[:-1][liq[:-1]], clp[1:][liq[:-1]])
    ci, ni = corr(cu[:-1][~liq[:-1]], clp[1:][~liq[:-1]])
    print(f"  Horario LÍQUIDO:     corr {cl:+.3f}  ({nl} pares)   <- si sigue fuerte = REAL")
    print(f"  Horario ilíquido:    corr {ci:+.3f}  ({ni} pares)   <- si solo aquí = precio rancio")
    # control: peso lidera cobre en liquido
    cc, _ = corr(clp[:-1][liq[:-1]], cu[1:][liq[:-1]])
    print(f"  Control (peso→cobre, líquido): corr {cc:+.3f}   (debe ser ~0)\n")

    # --- estrategia intradía en horario líquido, con selectividad y costos ---
    print("== Estrategia intradía (solo horario líquido) ==")
    umbral = np.quantile(np.abs(cu), 0.75)   # operar solo si el cobre se movió fuerte
    señal = -np.sign(cu[:-1])                 # cobre baja -> compro dólar (sube)
    fuerte = np.abs(cu[:-1]) >= umbral
    activo = liq[:-1] & fuerte
    fwd = clp[1:]
    pos = np.where(activo, señal, 0.0)
    hit = (np.sign(pos[activo]) == np.sign(fwd[activo])).mean() * 100 if activo.sum() else 0
    print(f"  Operaciones (cobre fuerte + líquido): {int(activo.sum())} de {len(pos)} velas")
    print(f"  Acierto direccional: {hit:.1f}%")
    mueve = np.abs(fwd[activo]).mean() * 10000
    print(f"  Movimiento medio del peso tras la señal: {mueve:.1f} pb  (esto hay que ganarle a los costos)")
    gross = pos * fwd
    for costo in (0, 3, 6, 10):
        # cada entrada+salida paga ~2x el costo; aquí cobramos por operar
        neto = gross.copy()
        neto[activo] -= costo / 10000
        tot = neto.sum() * 100
        print(f"    Costo {costo:2d} pb/lado → neto {tot:+5.2f}%  ({int(activo.sum())} trades)")
    print("  (Nota: 1 mes de datos, muestra chica. Es indicativo, no definitivo.)")


if __name__ == "__main__":
    correr("15m", "1mo")
