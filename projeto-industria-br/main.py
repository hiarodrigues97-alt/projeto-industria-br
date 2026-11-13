#!/usr/bin/env python3
"""
Projeto 1 - Pipeline de dados da indústria brasileira: extração + carga no PostgreSQL.

Pré-requisitos:
    pip install -r requirements.txt
    PostgreSQL rodando (ex.: docker run --name pg-portfolio -e POSTGRES_PASSWORD=SUA_SENHA \\
                              -p 5432:5432 -d postgres:16)

Conexão (use variável de ambiente em vez de deixar senha no código):
    export DATABASE_URL="postgresql+psycopg2://postgres:SUA_SENHA@localhost:5432/industria"

Uso:
    python main.py                       # extrai tudo e carrega no banco
    python main.py --modo extrair        # só gera os CSVs em ./dados
    python main.py --modo carregar       # só carrega CSVs já existentes
    python main.py --fontes bcb sidra    # só algumas fontes
    python main.py --inicio 2012
"""
import argparse
import os
import sys

from pipeline.carga.postgres import carregar_tudo
from pipeline.config import BRUTOS, DB_PADRAO, OUT
from pipeline.extracao.bcb import extrair_bcb
from pipeline.extracao.epe import extrair_epe
from pipeline.extracao.ibge import extrair_sidra
from pipeline.extracao.ons import extrair_ons
from pipeline.utils import erro_legivel

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
