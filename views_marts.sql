-- =============================================================
-- Camada marts: views consumidas pelo Power BI
-- Pré-requisito: tabelas do schema raw carregadas por pipeline_completo.py
-- Execute no DBeaver/pgAdmin conectado ao banco "industria".
-- =============================================================

-- Calendário mensal (termina no último mês disponível da PIM-PF)
CREATE OR REPLACE VIEW marts.dim_calendario AS
SELECT d::date                  AS data,
       EXTRACT(YEAR FROM d)::int  AS ano,
       EXTRACT(MONTH FROM d)::int AS mes,
       TO_CHAR(d, 'YYYY-MM')      AS ano_mes
FROM generate_series('2002-01-01'::date,
                     (SELECT MAX(data)::date FROM raw.pimpf_brasil),
                     interval '1 month') AS d;

-- Macroeconomia (Banco Central, SGS)
CREATE OR REPLACE VIEW marts.fato_macro AS
SELECT data::date AS data,
       selic_meta,
       selic_efetiva_mes,
       ipca_mensal,
       ipca_12m,
       cambio_venda_media,
       ibc_br
FROM raw.bcb_mensal;

-- Carga de energia por subsistema (ONS), média mensal em MWmed
CREATE OR REPLACE VIEW marts.fato_carga AS
SELECT mes::date AS data,
       id_subsistema,
       carga_mwmed
FROM raw.ons_carga_mensal;

-- Produção industrial: Brasil (IBGE, PIM-PF, tabela 8888)
CREATE OR REPLACE VIEW marts.fato_pimpf_brasil AS
SELECT data::date AS data,
       variavel_codigo::text AS variavel_codigo,
       variavel,
       secoes_e_atividades_industriais_cnae_2_0_codigo::text AS atividade_codigo,
       secoes_e_atividades_industriais_cnae_2_0 AS atividade,
       unidade_de_medida AS unidade,
       valor_2::numeric AS valor
FROM raw.pimpf_brasil
WHERE valor_2 IS NOT NULL;

-- Produção industrial: UFs (IBGE, PIM-PF, tabela 8159)
CREATE OR REPLACE VIEW marts.fato_pimpf_uf AS
SELECT data::date AS data,
       unidade_da_federacao_codigo::text AS uf_codigo,
       unidade_da_federacao AS uf,
       variavel_codigo::text AS variavel_codigo,
       variavel,
       secoes_e_atividades_industriais_cnae_2_0_codigo::text AS atividade_codigo,
       secoes_e_atividades_industriais_cnae_2_0 AS atividade,
       unidade_de_medida AS unidade,
       valor_2::numeric AS valor
FROM raw.pimpf_uf
WHERE valor_2 IS NOT NULL;

-- Dimensão de atividades industriais, com nome limpo e nível
CREATE OR REPLACE VIEW marts.dim_atividade AS
SELECT DISTINCT
       atividade_codigo,
       atividade AS atividade_original,
       regexp_replace(atividade, '^[0-9.]+\s+', '') AS atividade_nome,
       split_part(atividade, ' ', 1) AS cnae,
       CASE WHEN atividade_codigo = '129314' THEN 'Indústria geral'
            WHEN atividade_codigo IN ('129315', '129316') THEN 'Seção'
            ELSE 'Divisão da transformação' END AS nivel
FROM marts.fato_pimpf_brasil;
