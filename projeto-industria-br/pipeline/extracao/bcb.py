"""Banco Central: séries do SGS (Selic, IPCA, câmbio e IBC-Br)."""
from datetime import date

import pandas as pd

from pipeline.config import BCB_SERIES, BRUTOS, OUT
from pipeline.utils import get, salvar_csv


def sgs(cod, ini, fim, passo=5):
    """Busca em blocos de `passo` anos (séries diárias têm limite de janela)."""
    partes = []
    for a in range(ini, fim + 1, passo):
        b = min(a + passo - 1, fim)
        url = (f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{cod}/dados"
               f"?formato=json&dataInicial=01/01/{a}&dataFinal=31/12/{b}")
        js = get(url, timeout=60).json()
        if isinstance(js, list) and js:
            partes.append(pd.DataFrame(js))
    d = pd.concat(partes)
    d["data"] = pd.to_datetime(d["data"], dayfirst=True)
    d["valor"] = d["valor"].astype(float)
    return d.drop_duplicates("data").set_index("data")["valor"]


def extrair_bcb(inicio):
    fim = date.today().year
    s = {}
    for nome, cod in BCB_SERIES.items():
        try:
            s[nome] = sgs(cod, inicio, fim)
            salvar_csv(s[nome], BRUTOS / f"bcb_{nome}.csv", header=["valor"])
            print(f"[BCB] {nome} ({cod}): {len(s[nome]):,} obs")
        except Exception as e:
            print(f"[BCB] {nome} ({cod}) falhou: {e}")
    if not s:
        return
    mensal = pd.DataFrame({
        # Selic meta é diária em degraus: usa o último valor do mês
        "selic_meta": s["selic_meta"].resample("MS").last() if "selic_meta" in s else None,
        "selic_efetiva_mes": s.get("selic_efetiva_mes"),
        "ipca_mensal": s.get("ipca_mensal"),
        "ipca_12m": s.get("ipca_12m"),
        "cambio_venda_media": s["cambio_venda_diario"].resample("MS").mean()
        if "cambio_venda_diario" in s else None,
        "ibc_br": s.get("ibc_br"),
    })
    mensal.index.name = "data"
    salvar_csv(mensal, OUT / "bcb_mensal.csv")
    print(f"  -> {OUT / 'bcb_mensal.csv'}")
