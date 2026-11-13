"""Configurações centrais: caminhos, tabelas do SIDRA, séries do BCB, ONS, EPE e banco."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
OUT = BASE_DIR / "dados"
BRUTOS = OUT / "brutos"
SQL_DIR = BASE_DIR / "sql"

# ---- IBGE (SIDRA) ----
# Confirme os números no SIDRA: o IBGE troca as tabelas quando muda a base.
SIDRA_TABELAS = {
    "pimpf_brasil": {"tabela": 8888, "nivel": 1},  # Brasil, por seção/atividade
    "pimpf_uf": {"tabela": 8159, "nivel": 3},      # UFs
}


IBGE_META = "https://servicodados.ibge.gov.br/api/v3/agregados/{t}/metadados"


IBGE_PER = "https://servicodados.ibge.gov.br/api/v3/agregados/{t}/periodos"


SIDRA_API = "https://apisidra.ibge.gov.br/values"

# ---- Banco Central (SGS) ----
BCB_SERIES = {
    "selic_meta": 432,
    "selic_efetiva_mes": 4390,
    "ipca_mensal": 433,
    "ipca_12m": 13522,
    "cambio_venda_diario": 1,
    "ibc_br": 24364,  # IBC-Br dessazonalizado (24363 = sem ajuste sazonal)
}

# ---- ONS ----
ONS_CKAN = "https://dados.ons.org.br/api/3/action"


ONS_DATASET = "carga-energia"


ONS_FORMATO = "csv"

# ---- EPE ----
EPE_PAGINAS = [
    "https://www.epe.gov.br/pt/publicacoes-dados-abertos/publicacoes/consumo-de-energia-eletrica",
    "https://www.epe.gov.br/pt/publicacoes-dados-abertos/publicacoes/"
    "Consumo-mensal-de-energia-eletrica-por-classe-regioes-e-subsistemas",
]

# ---- Banco de dados ----
# Prefira a variável de ambiente DATABASE_URL (ou o argumento --db) a escrever a senha aqui.
DB_PADRAO = "postgresql+psycopg2://postgres:SUA_SENHA@localhost:5432/industria"


SCHEMAS = ["raw", "staging", "marts"]
