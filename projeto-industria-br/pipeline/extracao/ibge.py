"""IBGE: PIM-PF via SIDRA (tabelas 8888 e 8159)."""
import time

import pandas as pd

from pipeline.config import IBGE_META, IBGE_PER, OUT, SIDRA_API, SIDRA_TABELAS
from pipeline.utils import get, lista_meses, salvar_csv


def sidra_tabela(nome, cfg, inicio):
    t, nivel = cfg["tabela"], cfg["nivel"]
    meta = get(IBGE_META.format(t=t)).json()
    print(f"[SIDRA] tabela {t}: {meta.get('nome')}")
    niveis = meta.get("nivelTerritorial", {}).get("Administrativo", [])
    if f"N{nivel}" not in niveis:
        print(f"  ! nível N{nivel} não consta nos metadados (disponíveis: {niveis}). "
              f"Verifique se o número da tabela está correto.")
    variaveis = meta["variaveis"]
    classes = meta.get("classificacoes", [])
    print(f"  variáveis: {[(v['id'], v['nome']) for v in variaveis]}")
    print(f"  classificações: {[(c['id'], c['nome'], len(c['categorias'])) for c in classes]}")

    periodos = [p["id"] for p in get(IBGE_PER.format(t=t)).json()]
    p0, p1 = periodos[0], periodos[-1]
    if inicio:
        p0 = max(p0, f"{inicio}01")
    meses = lista_meses(p0, p1)
    blocos = [meses[i:i + 36] for i in range(0, len(meses), 36)]  # evita o limite de 100 mil valores

    filtro_cls = "".join(f"/c{c['id']}/all" for c in classes)
    partes = []
    for v in variaveis:
        for b in blocos:
            url = f"{SIDRA_API}/t/{t}/n{nivel}/all/v/{v['id']}/p/{b[0]}-{b[-1]}{filtro_cls}"
            dados = get(url).json()
            if len(dados) <= 1:
                continue
            df = pd.DataFrame(dados[1:]).rename(columns=dados[0])
            partes.append(df)
            time.sleep(0.3)
    if not partes:
        print("  ! nenhum dado retornado")
        return None
    df = pd.concat(partes, ignore_index=True)
    col_mes = next(c for c in df.columns if c.startswith("Mês") and "Código" in c)
    df["data"] = pd.to_datetime(df[col_mes], format="%Y%m")
    df["valor"] = pd.to_numeric(df["Valor"], errors="coerce")  # "...", "-", "X" viram NaN
    salvar_csv(df, OUT / f"{nome}.csv", index=False, encoding="utf-8")
    print(f"  -> {OUT / (nome + '.csv')}  ({len(df):,} linhas)")
    return df


def extrair_sidra(inicio):
    for nome, cfg in SIDRA_TABELAS.items():
        try:
            sidra_tabela(nome, cfg, inicio)
        except Exception as e:
            print(f"[SIDRA] {nome} falhou: {e}")
