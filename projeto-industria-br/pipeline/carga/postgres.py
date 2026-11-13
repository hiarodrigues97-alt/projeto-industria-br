"""Carga no PostgreSQL: schema raw (cópia fiel) e views do schema marts."""
from urllib.parse import unquote

import pandas as pd

from pipeline.config import BRUTOS, OUT, SCHEMAS, SQL_DIR
from pipeline.utils import erro_legivel, norm_colunas, norm_nome


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


def recriar_marts(engine):
    """As views do marts dependem das tabelas raw. Como cada carga recria as tabelas raw,
    as views são removidas antes e recriadas depois (sql/views_marts.sql)."""
    from sqlalchemy import text
    with engine.begin() as c:
        c.execute(text("DROP SCHEMA IF EXISTS marts CASCADE"))
        c.execute(text("CREATE SCHEMA marts"))


def criar_views(engine):
    arq = SQL_DIR / "views_marts.sql"
    if not arq.exists():
        print(f"[DB] {arq} não encontrado: crie as views manualmente no banco.")
        return
    try:
        with engine.begin() as c:
            c.exec_driver_sql(arq.read_text(encoding="utf-8"))
        print("[DB] views do schema marts recriadas (sql/views_marts.sql)")
    except Exception as e:
        print(f"[DB] não foi possível criar as views: {erro_legivel(e)}")


def carregar_tudo(db_url):
    engine = conectar(db_url)
    recriar_marts(engine)
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
            carregar_tabela(engine, d, f"epe_{norm_nome(unquote(f.stem), 28)}_{norm_nome(aba, 28)}")
    criar_views(engine)
    # resumo
    from sqlalchemy import text
    with engine.connect() as c:
        print("\n[DB] resumo da carga (raw._carga_log, última execução de cada tabela):")
        for t, n in c.execute(text(
                "SELECT DISTINCT ON (tabela) tabela, linhas FROM raw._carga_log "
                "ORDER BY tabela, carregado_em DESC")):
            print(f"   {t:<45}{n:>12,}")
    engine.dispose()
