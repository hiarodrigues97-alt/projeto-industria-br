#!/usr/bin/env python3
"""
Projeto 1 - Pipeline completo: EXTRAÇÃO (IBGE PIM-PF, BCB SGS, ONS, EPE) + CARGA no PostgreSQL.

Pré-requisitos:
    pip install pandas requests pyarrow openpyxl xlrd sqlalchemy psycopg2-binary
    PostgreSQL rodando (ex.: docker run --name pg-portfolio -e POSTGRES_PASSWORD=postgres \
                              -p 5432:5432 -d postgres:16)

Conexão (use variável de ambiente em vez de deixar senha no código):
    export DATABASE_URL="postgresql+psycopg2://postgres:novasenha123@localhost:5432/industria"

Uso:
    python pipeline_completo.py                       # extrai tudo e carrega no banco
    python pipeline_completo.py --modo extrair        # só gera os CSVs em ./dados
    python pipeline_completo.py --modo carregar       # só carrega CSVs já existentes
    python pipeline_completo.py --fontes bcb sidra    # só algumas fontes
    python pipeline_completo.py --inicio 2012

Camadas: CSVs (./dados) -> schema raw (cópia fiel) ; schemas staging e marts ficam
criados e vazios para o dbt. Cada execução recarrega as tabelas raw por completo.
Os códigos de variáveis/categorias do SIDRA são lidos dos metadados do IBGE (não ficam
fixos). Confira no console o título de cada tabela impresso na extração.
"""
import argparse
import io
import os
import unicodedata
import re
import sys
import time
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
import requests

OUT = Path("dados")
BRUTOS = OUT / "brutos"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 (projeto-portfolio-dados)"})


def get(url, params=None, tentativas=4, timeout=120):
    """GET com retry. Levanta erro mostrando o texto devolvido pela API."""
    ultimo = None
    for i in range(tentativas):
        try:
            r = SESSION.get(url, params=params, timeout=timeout)
            if r.status_code == 200:
                return r
            ultimo = f"HTTP {r.status_code}: {r.text[:300]}"
            if r.status_code < 500 and r.status_code != 429:
                break  # erro do cliente: repetir não adianta
        except requests.RequestException as e:
            ultimo = repr(e)
        time.sleep(2 ** i)
    raise RuntimeError(f"Falha em {url} -> {ultimo}")


# ----------------------------------------------------------------------------
# 1) IBGE PIM-PF via SIDRA
# ----------------------------------------------------------------------------
# Confirme os números no SIDRA: o IBGE troca as tabelas quando muda a base.
SIDRA_TABELAS = {
    "pimpf_brasil": {"tabela": 8888, "nivel": 1},  # Brasil, por seção/atividade
    "pimpf_uf": {"tabela": 8159, "nivel": 3},      # UFs
}
IBGE_META = "https://servicodados.ibge.gov.br/api/v3/agregados/{t}/metadados"
IBGE_PER = "https://servicodados.ibge.gov.br/api/v3/agregados/{t}/periodos"
SIDRA_API = "https://apisidra.ibge.gov.br/values"


def lista_meses(p0, p1):
    a, m = int(p0[:4]), int(p0[4:6])
    out = []
    while f"{a}{m:02d}" <= p1:
        out.append(f"{a}{m:02d}")
        m += 1
        if m > 12:
            a, m = a + 1, 1
    return out


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
    df.to_csv(OUT / f"{nome}.csv", index=False, encoding="utf-8")
    print(f"  -> {OUT / (nome + '.csv')}  ({len(df):,} linhas)")
    return df


def extrair_sidra(inicio):
    for nome, cfg in SIDRA_TABELAS.items():
        try:
            sidra_tabela(nome, cfg, inicio)
        except Exception as e:
            print(f"[SIDRA] {nome} falhou: {e}")


# ----------------------------------------------------------------------------
# 2) Banco Central - SGS
# ----------------------------------------------------------------------------
BCB_SERIES = {
    "selic_meta": 432,
    "selic_efetiva_mes": 4390,
    "ipca_mensal": 433,
    "ipca_12m": 13522,
    "cambio_venda_diario": 1,
    "ibc_br": 24363,
}


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
            s[nome].to_csv(BRUTOS / f"bcb_{nome}.csv", header=["valor"])
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
    mensal.to_csv(OUT / "bcb_mensal.csv")
    print(f"  -> {OUT / 'bcb_mensal.csv'}")


# ----------------------------------------------------------------------------
# 3) ONS - carga de energia (agregada para mensal)
# ----------------------------------------------------------------------------
ONS_CKAN = "https://dados.ons.org.br/api/3/action"
ONS_DATASET = "carga-energia"   # slug do dataset; se falhar, o script lista candidatos
ONS_FORMATO = "csv"             # use um só formato (csv OU parquet) para não duplicar dados


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
    tot.to_csv(OUT / "ons_carga_mensal.csv", index=False)
    print(f"  -> {OUT / 'ons_carga_mensal.csv'}  ({len(tot):,} linhas)")


# ----------------------------------------------------------------------------
# 4) EPE - consumo de energia (download + inspeção; o layout muda com frequência)
# ----------------------------------------------------------------------------
EPE_PAGINAS = [
    "https://www.epe.gov.br/pt/publicacoes-dados-abertos/publicacoes/consumo-de-energia-eletrica",
    "https://www.epe.gov.br/pt/publicacoes-dados-abertos/publicacoes/"
    "Consumo-mensal-de-energia-eletrica-por-classe-regioes-e-subsistemas",
]


def extrair_epe(inicio):
    pasta = BRUTOS / "epe"
    pasta.mkdir(parents=True, exist_ok=True)
    baixados = []
    for pag in EPE_PAGINAS:
        try:
            html = get(pag).text
        except Exception as e:
            print(f"[EPE] página indisponível: {pag} ({e})")
            continue
        links = re.findall(r'href=["\']([^"\']+\.(?:xlsx?|csv))["\']', html, re.I)
        for l in sorted(set(links)):
            url = urljoin(pag, l)
            destino = pasta / url.rsplit("/", 1)[-1].split("?")[0]
            try:
                destino.write_bytes(get(url, timeout=300).content)
                baixados.append(destino)
                print(f"[EPE] baixado: {destino.name}")
            except Exception as e:
                print(f"[EPE] falhou {url}: {e}")
    if not baixados:
        print("[EPE] nenhum arquivo encontrado automaticamente. Abra a página, baixe a planilha "
              f"manualmente e coloque em {pasta}/")
        baixados = list(pasta.glob("*.xls*")) + list(pasta.glob("*.csv"))
    # Inspeção: valide colunas/abas antes de escrever o parser definitivo
    for f in baixados:
        print(f"\n[EPE] inspeção de {f.name}")
        try:
            if f.suffix.lower() == ".csv":
                print(pd.read_csv(f, sep=None, engine="python", nrows=5).to_string())
            else:
                for aba, d in pd.read_excel(f, sheet_name=None, header=None, nrows=8).items():
                    print(f"  aba '{aba}':")
                    print(d.to_string(max_cols=12))
        except Exception as e:
            print(f"  não foi possível ler: {e}")


# ----------------------------------------------------------------------------
# 5) CARGA NO POSTGRESQL (schema raw)
# ----------------------------------------------------------------------------
DB_PADRAO = "postgresql+psycopg2://postgres:novasenha123@localhost:5432/industria"
SCHEMAS = ["raw", "staging", "marts"]


def norm_nome(n, limite=60):
    """'Mês (Código)' -> 'mes_codigo' (minúsculas, sem acento, só [a-z0-9_])."""
    n = unicodedata.normalize("NFKD", str(n)).encode("ascii", "ignore").decode()
    n = re.sub(r"[^a-zA-Z0-9]+", "_", n).strip("_").lower()
    if not n or n[0].isdigit():
        n = "c_" + n
    return n[:limite]


def norm_colunas(cols):
    vistos, out = {}, []
    for c in cols:
        base = norm_nome(c)
        vistos[base] = vistos.get(base, 0) + 1
        out.append(base if vistos[base] == 1 else f"{base}_{vistos[base]}")
    return out


def erro_legivel(e):
    """No Windows em PT-BR, as mensagens do libpq/PostgreSQL vêm em cp1252 e quebram o
    decode UTF-8 do psycopg2. Aqui recuperamos o texto real do erro."""
    if isinstance(e, UnicodeDecodeError):
        try:
            return e.object.decode("cp1252", errors="replace")
        except Exception:
            pass
    return str(e)


def garantir_banco(url):
    """Cria o banco de destino se ele ainda não existir."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url
    u = make_url(url)
    alvo = u.database
    try:
        adm = create_engine(u.set(database="postgres"), isolation_level="AUTOCOMMIT")
        with adm.connect() as c:
            if not c.execute(text("SELECT 1 FROM pg_database WHERE datname=:n"), {"n": alvo}).scalar():
                c.execute(text(f'CREATE DATABASE "{alvo}"'))
                print(f"[DB] banco '{alvo}' criado")
        adm.dispose()
    except Exception as e:
        print(f"[DB] não foi possível verificar/criar o banco '{alvo}': {erro_legivel(e)}")


def conectar(url):
    from sqlalchemy import create_engine, text
    garantir_banco(url)
    engine = create_engine(url, pool_pre_ping=True)
    with engine.begin() as c:
        for sc in SCHEMAS:
            c.execute(text(f"CREATE SCHEMA IF NOT EXISTS {sc}"))
        c.execute(text("CREATE TABLE IF NOT EXISTS raw._carga_log ("
                       "tabela text, linhas integer, carregado_em timestamptz DEFAULT now())"))
    return engine


def carregar_tabela(engine, df, nome):
    from sqlalchemy import text
    df = df.copy()
    df.columns = norm_colunas(df.columns)
    nome = norm_nome(nome, 63)
    df.to_sql(nome, engine, schema="raw", if_exists="replace", index=False,
              chunksize=max(100, 30000 // max(1, df.shape[1])), method="multi")
    with engine.begin() as c:
        c.execute(text("INSERT INTO raw._carga_log (tabela, linhas) VALUES (:t, :n)"),
                  {"t": f"raw.{nome}", "n": int(len(df))})
    print(f"[DB] raw.{nome}: {len(df):,} linhas")


def ler_csv(path):
    cab = pd.read_csv(path, nrows=0).columns
    return pd.read_csv(path, parse_dates=["data"] if "data" in cab else False)


def carregar_tudo(db_url):
    engine = conectar(db_url)
    # 1) tabelas principais geradas na extração
    for nome in ["pimpf_brasil", "pimpf_uf", "bcb_mensal", "ons_carga_mensal"]:
        f = OUT / f"{nome}.csv"
        if not f.exists():
            print(f"[DB] {f} não existe, pulando")
            continue
        carregar_tabela(engine, ler_csv(f), nome)
    # 2) séries brutas do BCB (uma tabela por série)
    for f in sorted(BRUTOS.glob("bcb_*.csv")):
        carregar_tabela(engine, ler_csv(f), f.stem)
    # 3) EPE: layout não padronizado -> cada aba vai como texto, para você inspecionar no SQL
    for f in sorted((BRUTOS / "epe").glob("*")):
        try:
            if f.suffix.lower() == ".csv":
                abas = {"csv": pd.read_csv(f, sep=None, engine="python", dtype=str, header=None)}
            elif f.suffix.lower() in (".xls", ".xlsx"):
                abas = pd.read_excel(f, sheet_name=None, dtype=str, header=None)
            else:
                continue
        except Exception as e:
            print(f"[DB] EPE {f.name} não lido: {e}")
            continue
        for aba, d in abas.items():
            d.columns = [f"col_{i}" for i in range(d.shape[1])]
            carregar_tabela(engine, d, f"epe_{f.stem}_{aba}")
    # resumo
    from sqlalchemy import text
    with engine.connect() as c:
        print("\n[DB] resumo da carga (raw._carga_log, última execução de cada tabela):")
        for t, n in c.execute(text(
                "SELECT DISTINCT ON (tabela) tabela, linhas FROM raw._carga_log "
                "ORDER BY tabela, carregado_em DESC")):
            print(f"   {t:<45}{n:>12,}")
    engine.dispose()


# ----------------------------------------------------------------------------
FONTES = {"sidra": extrair_sidra, "bcb": extrair_bcb, "ons": extrair_ons, "epe": extrair_epe}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modo", choices=["tudo", "extrair", "carregar"], default="tudo")
    ap.add_argument("--fontes", nargs="+", choices=FONTES, default=list(FONTES))
    ap.add_argument("--inicio", type=int, default=2002, help="ano inicial (padrão 2002)")
    ap.add_argument("--db", default=os.getenv("DATABASE_URL", DB_PADRAO),
                    help="URL SQLAlchemy do PostgreSQL (ou variável DATABASE_URL)")
    a = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    BRUTOS.mkdir(parents=True, exist_ok=True)

    if a.modo in ("tudo", "extrair"):
        for f in a.fontes:
            print(f"\n===== EXTRAÇÃO: {f.upper()} =====")
            try:
                FONTES[f](a.inicio)
            except Exception as e:
                print(f"[{f}] erro inesperado: {e}", file=sys.stderr)

    if a.modo in ("tudo", "carregar"):
        print("\n===== CARGA NO POSTGRESQL =====")
        try:
            carregar_tudo(a.db)
        except Exception as e:
            print(f"[DB] falha na carga: {erro_legivel(e)}\nVerifique se o PostgreSQL está rodando e se a "
                  f"URL/senha estão corretas (--db ou DATABASE_URL).", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
