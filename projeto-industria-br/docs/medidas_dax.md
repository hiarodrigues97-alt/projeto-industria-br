# Medidas DAX

Cada medida é criada separadamente na tabela `Medidas` do Power BI. Os códigos de variável
vêm da tabela 8888 do SIDRA (PIM-PF, base 2022 = 100).

| Código | Variável |
|---|---|
| 12606 | Número-índice (2022=100) |
| 12607 | Número-índice com ajuste sazonal (2022=100) |
| 11601 | Variação mês/mês imediatamente anterior, com ajuste sazonal |
| 11602 | Variação mês/mesmo mês do ano anterior |
| 11603 | Variação acumulada no ano |
| 11604 | Variação acumulada em 12 meses |

Atividade 129314 = Indústria geral.

```dax
Atividade Ativa = SELECTEDVALUE(dim_atividade[atividade_codigo], "129314")
```
```dax
Indice SA = VAR atividade = [Atividade Ativa] RETURN CALCULATE(AVERAGE(fato_pimpf_brasil[valor]), fato_pimpf_brasil[variavel_codigo] = "12607", fato_pimpf_brasil[atividade_codigo] = atividade)
```
```dax
Var Acum 12m % = VAR atividade = [Atividade Ativa] RETURN CALCULATE(AVERAGE(fato_pimpf_brasil[valor]), fato_pimpf_brasil[variavel_codigo] = "11604", fato_pimpf_brasil[atividade_codigo] = atividade) / 100
```
```dax
Var vs Mesmo Mes % = VAR atividade = [Atividade Ativa] RETURN CALCULATE(AVERAGE(fato_pimpf_brasil[valor]), fato_pimpf_brasil[variavel_codigo] = "11602", fato_pimpf_brasil[atividade_codigo] = atividade) / 100
```
```dax
Media Movel 3m = AVERAGEX(DATESINPERIOD(dim_calendario[data], MAX(dim_calendario[data]), -3, MONTH), [Indice SA])
```
```dax
Ultimo Mes = MAX(fato_pimpf_brasil[data])
```
```dax
Carga Total MWmed = SUM(fato_carga[carga_mwmed])
```

As demais medidas (base fixa, variação mensal, acumulado no ano, variantes por setor e
macro) seguem o mesmo padrão.

Observação: dentro do `CALCULATE`, o valor da medida `Atividade Ativa` é guardado em uma
variável (`VAR`) antes de ser usado no filtro, pois o DAX não aceita uma medida diretamente
em um filtro simples.
