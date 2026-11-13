import unittest

from pipeline.utils import erro_legivel, lista_meses, norm_colunas, norm_nome


class TestUtils(unittest.TestCase):
    def test_norm_nome_remove_acento_e_simbolos(self):
        self.assertEqual(norm_nome("Mês (Código)"), "mes_codigo")

    def test_norm_nome_prefixa_quando_comeca_com_numero(self):
        self.assertEqual(norm_nome("2022"), "c_2022")

    def test_norm_nome_respeita_limite(self):
        self.assertEqual(len(norm_nome("a" * 100, 63)), 63)

    def test_norm_colunas_evita_duplicadas(self):
        # o SIDRA devolve "Valor" (texto) e o script cria "valor" (numérico)
        self.assertEqual(norm_colunas(["Valor", "valor", "Mês"]), ["valor", "valor_2", "mes"])

    def test_lista_meses_cruza_o_ano(self):
        self.assertEqual(lista_meses("202511", "202602"),
                         ["202511", "202512", "202601", "202602"])

    def test_erro_legivel_recupera_texto_cp1252(self):
        try:
            "conexão falhou".encode("cp1252").decode("utf-8")
        except UnicodeDecodeError as e:
            self.assertEqual(erro_legivel(e), "conexão falhou")


if __name__ == "__main__":
    unittest.main()
