"""ONS: carga de energia por subsistema, agregada para média mensal."""
import io

import pandas as pd

from pipeline.config import ONS_CKAN, ONS_DATASET, ONS_FORMATO, OUT
from pipeline.utils import get, salvar_csv


def ons_recursos():
    try:
        pkg = get(f"{ONS_CKAN}/package_show", params={"id": ONS_DATASET}).json()["result"]
    except Exception:
        achados = get(f"{ONS_CKAN}/package_search", params={"q": "carga energia", "rows": 30}).json()
        print("[ONS] dataset não encontrado pelo slug. Candidatos (ajuste ONS_DATASET):")
        for p in achados["result"]["results"]:
            print(f"   {p['name']}  -  {p.get('title')}")
        return []
    return [r for r in pkg["resources"]
            if (r.get("format") or "").lower() == ONS_FORMATO and r.get("url")]


def _col(df, *chaves):
    for c in df.columns:
        if all(k in c.lower() for k in chaves):
            return c
    return None


def ons_ler(conteudo, url):
    if url.lower().endswith(".parquet") or ONS_FORMATO == "parquet":
        return pd.read_parquet(io.BytesIO(conteudo))
    df = pd.read_csv(io.BytesIO(conteudo), sep=";", low_memory=False)
    if df.shape[1] == 1:
        df = pd.read_csv(io.BytesIO(conteudo), sep=",", low_memory=False)
    return df


def extrair_ons(inicio):
    recursos = ons_recursos()
    if not recursos:
        return
    acc = []
    for r in recursos:
        url = r["url"]
        try:
            df = ons_ler(get(url, timeout=600).content, url)
        except Exception as e:
            print(f"[ONS] {url} falhou: {e}")
            continue
        tempo = _col(df, "instante") or _col(df, "data")
        sub = _col(df, "id_subsistema")
        carga = _col(df, "carga", "mwmed") or _col(df, "val_carga")
        if not (tempo and sub and carga):
            print(f"[ONS] colunas não reconhecidas em {url}: {list(df.columns)}")
            continue
        df["mes"] = pd.to_datetime(df[tempo], errors="coerce").dt.to_period("M").dt.to_timestamp()
        g = df.groupby([sub, "mes"])[carga].agg(["sum", "count"]).reset_index()
        g.columns = ["id_subsistema", "mes", "soma", "n"]
        acc.append(g)
        print(f"[ONS] ok: {url.rsplit('/', 1)[-1]} ({len(df):,} linhas)")
    if not acc:
        return
    tot = pd.concat(acc).groupby(["id_subsistema", "mes"], as_index=False)[["soma", "n"]].sum()
    tot["carga_mwmed"] = tot["soma"] / tot["n"]
    tot = tot[tot["mes"].dt.year >= inicio].drop(columns=["soma", "n"])
    salvar_csv(tot, OUT / "ons_carga_mensal.csv", index=False)
    print(f"  -> {OUT / 'ons_carga_mensal.csv'}  ({len(tot):,} linhas)")
