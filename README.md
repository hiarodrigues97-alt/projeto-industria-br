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
├── pipeline_completo.py   extração das fontes e carga no schema raw
├── sql/views_marts.sql    views do schema marts consumidas pelo Power BI
├── docs/medidas_dax.md    medidas DAX do dashboard
├── requirements.txt
└── README.md
```

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
   python pipeline_completo.py
   ```
   Opções úteis: `--modo extrair`, `--modo carregar`, `--fontes bcb sidra` e `--inicio 2012`.
5. Execute `sql/views_marts.sql` no banco para criar as views do schema marts.
6. No Power BI Desktop, use **Obter dados → Banco de dados PostgreSQL**, informe o servidor e o banco `industria` e selecione as views do schema `marts`.

## Decisões técnicas

- **Metadados em vez de códigos fixos.** A extração do SIDRA lê variáveis e categorias dos metadados do IBGE, então o script não quebra quando o IBGE reorganiza as tabelas.
- **Consultas em blocos.** O SIDRA limita cada consulta a 100 mil valores e as séries diárias do SGS têm limite de janela. A extração divide os períodos em blocos.
- **Camada raw preservada.** As tabelas raw são cópias fiéis das fontes e são recarregadas por completo a cada execução, o que torna a carga repetível.
- **Agregação da carga do ONS.** A carga é agregada para média mensal por subsistema antes de ir para o banco.
- **Registro de carga.** A tabela `raw._carga_log` guarda quantas linhas entraram em cada tabela e quando.

## Dashboard

Quatro páginas: visão geral, setores, energia × produção e macro.

| Visão geral | Setores |
|---|---|
| ![Visão geral](<img width="1437" height="810" alt="pagina1_visao_geral" src="https://github.com/user-attachments/assets/addd2492-3fdf-490d-9be3-cb67039f24c2" />
) | ![Setores](<img width="1440" height="807" alt="pagina2_setores" src="https://github.com/user-attachments/assets/df21de57-02df-485e-b7bc-cf1a85e4a8c0" />
) |

| Energia × produção | Macro |
|---|---|
| ![Energia e produção](<img width="1437" height="807" alt="pagina3_energia_producao" src="https://github.com/user-attachments/assets/8a54b2c1-4a4f-472a-a063-d6d93d81b678" />
) | ![Macro](<img width="1441" height="810" alt="pagina4_macro" src="https://github.com/user-attachments/assets/fc90d333-267b-4c13-b597-cc62218e37cd" />
) |


## Status e próximos passos

- [x] Extração do IBGE (PIM-PF) e do Banco Central (SGS)
- [x] Carga no PostgreSQL (schema raw) e views no schema marts
- [x] Dashboard no Power BI
- [ ] Tratamento dos dados da EPE (os arquivos são baixados e carregados como texto no raw; falta o parser por classe de consumo)
- [ ] Camada de transformação com dbt (staging e marts)
- [ ] Orquestração da atualização com Airflow
- [ ] Migração do banco para o Azure

## Autor

[Hiã Henrique Rodrigues] · [LinkedIn](www.linkedin.com/in/hiã-henrique-rodrigues-941552207)

Dados: IBGE, Banco Central do Brasil, ONS e EPE.
