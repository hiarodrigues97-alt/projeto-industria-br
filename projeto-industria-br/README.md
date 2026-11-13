# Indústria brasileira: do dado público ao dashboard

Pipeline de dados que reúne indicadores públicos da produção industrial, da energia elétrica
e do cenário macroeconômico do Brasil, organiza tudo em um banco PostgreSQL e alimenta um
dashboard no Power BI.

> Projeto de portfólio em andamento. As etapas pendentes estão listadas no fim.

## Pergunta que o projeto responde

Como a produção industrial brasileira se comporta por setor e como ela se relaciona com a
carga de energia e com o cenário macroeconômico (Selic, inflação, câmbio e atividade)?

## Fontes de dados

| Fonte | O que traz | Acesso |
|---|---|---|
| IBGE, PIM-PF | Índice de produção física por seção e atividade industrial (Brasil e UFs) | API do SIDRA (tabelas 8888 e 8159) |
| Banco Central, SGS | Selic, IPCA, câmbio e IBC-Br | API SGS |
| ONS | Carga de energia por subsistema | Portal de dados abertos |
| EPE | Consumo de energia elétrica por classe | Portal de dados abertos |

## Arquitetura

```
Fontes públicas (IBGE, BCB, ONS, EPE)
        |  Python (requests, pandas)
        v
CSVs em dados/
        |  pandas + SQLAlchemy
        v
PostgreSQL: schema raw        (cópia fiel da fonte)
        |
        v
PostgreSQL: schema marts      (views para análise)
        |
        v
Power BI (modelo + DAX)       (dashboard de 4 páginas)
```

O schema `staging` está criado e reservado para a etapa de transformação com dbt.

## Estrutura do repositório

```
.
├── main.py                    ponto de entrada (CLI): orquestra extração e carga
├── pipeline/
│   ├── config.py              caminhos, tabelas do SIDRA, séries do BCB, ONS, EPE e banco
│   ├── utils.py               HTTP com retry, gravação de CSV, normalização de nomes e datas
│   ├── extracao/
│   │   ├── ibge.py            PIM-PF via SIDRA (metadados, blocos de períodos)
│   │   ├── bcb.py             séries do SGS em blocos de anos
│   │   ├── ons.py             carga de energia agregada para média mensal
│   │   └── epe.py             download e inspeção das planilhas de consumo
│   └── carga/
│       └── postgres.py        schema raw, recriação das views do marts e log de carga
├── sql/views_marts.sql        views do schema marts consumidas pelo Power BI
├── tests/                     testes unitários (sem internet nem banco)
├── docs/medidas_dax.md        medidas DAX do dashboard
├── requirements.txt
└── README.md
```

Cada módulo tem uma responsabilidade: para incluir uma nova fonte, basta criar um arquivo em
`pipeline/extracao/` e registrá-lo no dicionário `FONTES` do `main.py`.

## Como rodar

1. Instale as dependências:
   ```
   pip install -r requirements.txt
   ```
2. Suba um PostgreSQL local, por exemplo com Docker:
   ```
   docker run --name pg-portfolio -e POSTGRES_PASSWORD=SUA_SENHA -p 5432:5432 -d postgres:16
   ```
3. Defina a conexão:
   ```
   # Linux/macOS
   export DATABASE_URL="postgresql+psycopg2://postgres:SUA_SENHA@localhost:5432/industria"
   # Windows PowerShell
   $env:DATABASE_URL="postgresql+psycopg2://postgres:SUA_SENHA@localhost:5432/industria"
   ```
4. Execute o pipeline (extrai as fontes e carrega o schema raw; o banco e os schemas são criados se não existirem):
   ```
   python main.py
   ```
   Opções úteis: `--modo extrair`, `--modo carregar`, `--fontes bcb sidra` e `--inicio 2012`.
5. Execute `sql/views_marts.sql` no banco para criar as views do schema marts.
6. No Power BI Desktop, use **Obter dados → Banco de dados PostgreSQL**, informe o servidor e o banco `industria` e selecione as views do schema `marts`.

## Testes

Testes unitários com respostas simuladas, então rodam sem internet e sem banco:

```
python -m unittest discover -s tests -t . -v
```

## Decisões técnicas

- **Metadados em vez de códigos fixos.** A extração do SIDRA lê variáveis e categorias dos metadados do IBGE, então o script não quebra quando o IBGE reorganiza as tabelas.
- **Consultas em blocos.** O SIDRA limita cada consulta a 100 mil valores e as séries diárias do SGS têm limite de janela. A extração divide os períodos em blocos.
- **Camada raw preservada.** As tabelas raw são cópias fiéis das fontes e são recarregadas por completo a cada execução, o que torna a carga repetível.
- **Agregação da carga do ONS.** A carga é agregada para média mensal por subsistema antes de ir para o banco.
- **Código modular.** Configuração, utilidades, extração por fonte e carga ficam em módulos separados, o que facilita testar e incluir novas fontes.
- **Registro de carga.** A tabela `raw._carga_log` guarda quantas linhas entraram em cada tabela e quando.

## Dashboard

Quatro páginas: visão geral, setores, energia × produção e macro.

| Visão geral | Setores |
|---|---|
| ![Visão geral](docs/pagina1_visao_geral.png) | ![Setores](docs/pagina2_setores.png) |

| Energia × produção | Macro |
|---|---|
| ![Energia e produção](docs/pagina3_energia_producao.png) | ![Macro](docs/pagina4_macro.png) |

## Principais achados

<!-- Escreva aqui 2 ou 3 achados reais do seu dashboard, cada um em uma frase, com número. -->

## Status e próximos passos

- [x] Extração do IBGE (PIM-PF) e do Banco Central (SGS)
- [x] Carga no PostgreSQL (schema raw) e views no schema marts
- [x] Dashboard no Power BI
- [ ] Tratamento dos dados da EPE (os arquivos são baixados e carregados como texto no raw; falta o parser por classe de consumo)
- [ ] Camada de transformação com dbt (staging e marts)
- [ ] Orquestração da atualização com Airflow
- [ ] Migração do banco para o Azure

## Autor

[Seu nome] · [LinkedIn](https://www.linkedin.com/in/SEU_PERFIL)

Dados: IBGE, Banco Central do Brasil, ONS e EPE.
