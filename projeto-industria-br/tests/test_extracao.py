"""Testes da extração com respostas simuladas (sem acesso à internet)."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from pipeline.extracao import bcb, ibge


class Resp:
    def __init__(self, dados):
        self._dados = dados

    def json(self):
        return self._dados


class TestBCB(unittest.TestCase):
    def test_sgs_junta_blocos_e_remove_duplicadas(self):
        def fake_get(url, **kw):
            if "dataInicial=01/01/2020" in url:
                return Resp([{"data": "01/01/2020", "valor": "1.5"}, {"data": "01/02/2020", "valor": "1.6"}])
            return Resp([{"data": "01/02/2020", "valor": "1.6"}, {"data": "01/01/2025", "valor": "2.0"}])

        with patch.object(bcb, "get", fake_get):
            serie = bcb.sgs(432, 2020, 2026)  # 2 blocos de até 5 anos
        self.assertEqual(len(serie), 3)
        self.assertEqual(serie.iloc[0], 1.5)
        self.assertEqual(serie.index[-1], pd.Timestamp("2025-01-01"))


class TestSIDRA(unittest.TestCase):
    def test_sidra_tabela_grava_csv_com_data_e_valor(self):
        meta = {"nome": "Tabela de teste",
                "nivelTerritorial": {"Administrativo": ["N1"]},
                "variaveis": [{"id": 12607, "nome": "Índice SA"}],
                "classificacoes": [{"id": 544, "nome": "Atividades", "categorias": [{"id": 1}]}]}
        periodos = [{"id": "202601"}, {"id": "202602"}]
        cab = {"D3C": "Mês (Código)", "V": "Valor"}
        valores = [cab, {"D3C": "202601", "V": "100.5"}, {"D3C": "202602", "V": "..."}]

        def fake_get(url, **kw):
            if "metadados" in url:
                return Resp(meta)
            if "periodos" in url:
                return Resp(periodos)
            return Resp(valores)

        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(ibge, "get", fake_get), patch.object(ibge, "OUT", Path(tmp)), \
                patch.object(ibge.time, "sleep", lambda s: None):
            df = ibge.sidra_tabela("teste", {"tabela": 8888, "nivel": 1}, None)
            self.assertTrue((Path(tmp) / "teste.csv").exists())
        self.assertEqual(df["data"].iloc[0], pd.Timestamp("2026-01-01"))
        self.assertEqual(df["valor"].iloc[0], 100.5)
        self.assertTrue(pd.isna(df["valor"].iloc[1]))  # "..." vira NaN


if __name__ == "__main__":
    unittest.main()
