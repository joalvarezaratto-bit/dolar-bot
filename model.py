"""
El MOTOR CUANTITATIVO del agente.

Aqui vive la matematica que convierte al bot de "termometro" en "analista":

  1) CORRELACION DINAMICA: mide que tan fuerte esta siguiendo el USD/CLP a
     cada motor (cobre, DXY, real) EN LAS ULTIMAS SEMANAS. Asi los pesos no
     son fijos: si el cobre esta explicando mucho al peso, pesa mas; si el
     peso lo esta ignorando, pesa menos.

  2) VALOR JUSTO (valor relativo): una regresion estima donde "deberia" estar
     el USD/CLP dado el nivel actual del cobre, el DXY y el real. Si el precio
     real se aparta mucho -> el peso esta caro/barato vs sus motores (posible
     correccion, o senal de que manda algo local: politica, flujos).

  3) RSI y ATR: fuerza del momentum (sobrecompra/sobreventa) y volatilidad
     (para saber si un movimiento es grande o normal).

Usa numpy (ya viene instalado con matplotlib).
HONESTO: son modelos estadisticos sobre datos pasados, no una bola de cristal.
"""
import datetime as dt
import numpy as np


def _fecha(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%d")


def alinear(series_por_symbol):
    """Recibe {nombre: candles} y devuelve (fechas, {nombre: array_de_cierres})
    solo con las fechas comunes a TODOS. Asi comparamos manzanas con manzanas."""
    mapas = {}
    for nombre, candles in series_por_symbol.items():
        if not candles:
            return None, None
        mapas[nombre] = {_fecha(c["t"]): c["c"] for c in candles}
    comunes = None
    for m in mapas.values():
        comunes = set(m) if comunes is None else (comunes & set(m))
    comunes = sorted(comunes)
    if len(comunes) < 30:
        return None, None
    arrays = {nombre: np.array([mapas[nombre][d] for d in comunes], dtype=float)
              for nombre in mapas}
    return comunes, arrays


def retornos(precios):
    """Retornos logaritmicos diarios (cambios % encadenables)."""
    precios = np.asarray(precios, dtype=float)
    return np.diff(np.log(precios))


def correlacion(r_clp, r_driver, ventana=40):
    """Correlacion de retornos en la ventana reciente. Rango -1..+1.
    -1 = se mueven al reves; +1 = al mismo lado; 0 = sin relacion."""
    a, b = r_clp[-ventana:], r_driver[-ventana:]
    if len(a) < 10 or np.std(a) == 0 or np.std(b) == 0:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def rsi(precios, n=14):
    """RSI de Wilder (0-100). >70 sobrecompra, <30 sobreventa."""
    p = np.asarray(precios, dtype=float)
    if len(p) < n + 1:
        return None
    d = np.diff(p)
    subidas = np.where(d > 0, d, 0.0)
    bajadas = np.where(d < 0, -d, 0.0)
    ag = subidas[:n].mean()
    ap = bajadas[:n].mean()
    for i in range(n, len(d)):
        ag = (ag * (n - 1) + subidas[i]) / n
        ap = (ap * (n - 1) + bajadas[i]) / n
    if ap == 0:
        return 100.0
    rs = ag / ap
    return float(100 - 100 / (1 + rs))


def atr_pct(candles, n=14):
    """ATR (rango medio real) como % del precio. Mide volatilidad tipica."""
    if len(candles) < n + 1:
        return None
    trs = []
    for i in range(1, len(candles)):
        h, l = candles[i]["h"], candles[i]["l"]
        cprev = candles[i - 1]["c"]
        trs.append(max(h - l, abs(h - cprev), abs(l - cprev)))
    atr = np.mean(trs[-n:])
    return float(atr / candles[-1]["c"] * 100)


FIB_RATIOS = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]


def fibonacci(candles, lookback=70):
    """Retrocesos de Fibonacci sobre el swing (impulso) mas reciente e importante.
    Devuelve {dir, hi, lo, levels:{ratio:precio}, cerca:(ratio,precio)} o None.
    'cerca' = el nivel fib mas proximo al precio actual (posible zona de reaccion)."""
    ventana = candles[-lookback:] if len(candles) > lookback else candles
    if len(ventana) < 10:
        return None
    hi_i = max(range(len(ventana)), key=lambda i: ventana[i]["h"])
    lo_i = min(range(len(ventana)), key=lambda i: ventana[i]["l"])
    hi = ventana[hi_i]["h"]
    lo = ventana[lo_i]["l"]
    if hi == lo:
        return None
    subiendo = hi_i > lo_i   # el maximo llego despues -> impulso al alza
    levels = {}
    for r in FIB_RATIOS:
        levels[r] = (hi - (hi - lo) * r) if subiendo else (lo + (hi - lo) * r)
    price = candles[-1]["c"]
    cerca = min(levels.items(), key=lambda kv: abs(kv[1] - price))
    return {"dir": "alza" if subiendo else "baja", "hi": hi, "lo": lo,
            "levels": levels, "cerca": cerca}


def valor_justo(arrays, ventana=60):
    """Regresion: estima el USD/CLP 'justo' segun cobre + DXY + real.
    Devuelve dict {predicho, real, gap, z, betas} o None.

    gap = real - predicho (pesos). z = gap en desviaciones estandar.
      z > +1  -> dolar CARO vs sus motores (peso subvalorado; ojo correccion)
      z < -1  -> dolar BARATO vs sus motores (peso sobrevalorado)
    """
    if not all(k in arrays for k in ("clp", "cobre", "dxy", "brl")):
        return None
    n = min(ventana, len(arrays["clp"]))
    if n < 30:
        return None
    y = arrays["clp"][-n:]
    X = np.column_stack([
        arrays["cobre"][-n:],
        arrays["dxy"][-n:],
        arrays["brl"][-n:],
        np.ones(n),
    ])
    try:
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    except Exception:
        return None
    pred = X @ beta
    resid = y - pred
    sd = np.std(resid)
    if sd == 0:
        return None
    gap = float(y[-1] - pred[-1])
    return {
        "predicho": float(pred[-1]),
        "real": float(y[-1]),
        "gap": gap,
        "z": float(gap / sd),
        "betas": {"cobre": float(beta[0]), "dxy": float(beta[1]), "real": float(beta[2])},
    }
