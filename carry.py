"""
CARRY: diferencial de tasas Chile − EE.UU. (contexto ESTRATÉGICO, no señal diaria).

  carry = TPM Chile − tasa corta EE.UU. (proxy Fed, ^IRX)

  carry > 0: te PAGAN por tener pesos (viento de cola estructural para el CLP).
  carry < 0: cuesta tener pesos (viento en contra).

HONESTO: el carry funciona en horizontes LARGOS y con colas de riesgo (en un día
de pánico se pierde meses de acumulación). NO predice el movimiento diario. Es
marco estratégico, no una señal para operar hoy.

Fuentes: TPM de mindicador.cl (Banco Central de Chile) con caché + respaldo en
config; tasa EE.UU. de Yahoo (^IRX). Ambas gratis, sin API key.
"""
import os
import json
import time
import requests
import config as C
import datasource as ds

HERE = os.path.dirname(os.path.abspath(__file__))
TPM_CACHE = os.path.join(HERE, "tpm_cache.json")
UA = {"User-Agent": "Mozilla/5.0"}
TTL = 12 * 3600   # la TPM cambia cada ~6 semanas: refrescar 2 veces al día basta


def get_tpm():
    """Tasa de Política Monetaria de Chile (%). mindicador.cl -> caché -> config."""
    # caché fresca en disco
    try:
        c = json.load(open(TPM_CACHE))
        if time.time() - c.get("ts", 0) < TTL:
            return c["valor"]
    except Exception:
        c = None
    # intentar mindicador
    try:
        r = requests.get("https://mindicador.cl/api/tpm", headers=UA, timeout=15)
        v = float(r.json()["serie"][0]["valor"])
        json.dump({"valor": v, "ts": time.time()}, open(TPM_CACHE, "w"))
        return v
    except Exception:
        if c:
            return c["valor"]                 # última copia buena
        return getattr(C, "TPM_FALLBACK", None)   # respaldo de config


def get_us_short():
    """Tasa corta de EE.UU. (%) — ^IRX (T-bill 13 semanas, proxy de la Fed)."""
    d = ds.get(C.SYM_IRX)
    return d["price"] if d and d.get("price") is not None else None


def carry():
    """Devuelve dict {tpm, us, diff} o None si falta algún dato."""
    tpm = get_tpm()
    us = get_us_short()
    if tpm is None or us is None:
        return None
    return {"tpm": tpm, "us": us, "diff": tpm - us}


def carry_line():
    """Línea para el informe (HTML). '' si no hay datos."""
    c = carry()
    if not c:
        return ""
    d = c["diff"]
    if d >= 0.25:
        efecto = "te pagan por tener pesos (apoyo estructural)"
    elif d <= -0.25:
        efecto = "cuesta tener pesos (viento en contra)"
    else:
        efecto = "carry casi neutro"
    return (f"💰 <b>Carry</b> (tasas Chile−EE.UU.): TPM {c['tpm']:.2f}% − Fed {c['us']:.2f}% "
            f"= <b>{d:+.2f}%</b> → {efecto}\n"
            f"   <i>factor estratégico de largo plazo, no señal diaria</i>")
