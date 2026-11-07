import unittest
from datetime import date
from decimal import Decimal, InvalidOperation

from tests import _caminho  # noqa: F401
from transform import converter_data, converter_valor, separar_fornecedor, transformar


class ConversoesTest(unittest.TestCase):
    def test_valor_em_formato_brasileiro(self):
        self.assertEqual(converter_valor("1266,00"), Decimal("1266.00"))
        self.assertEqual(converter_valor("1.234.567,89"), Decimal("1234567.89"))  # ponto é milhar
        self.assertEqual(converter_valor("-5.200,50"), Decimal("-5200.50"))

    def test_valor_nao_vira_float(self):
        # dinheiro em Decimal: float perderia centavos
        self.assertIsInstance(converter_valor("0,10"), Decimal)

    def test_valor_invalido_levanta(self):
        with self.assertRaises(InvalidOperation):
            converter_valor("abc")

    def test_data_dia_mes_ano(self):
        self.assertEqual(converter_data("30/01/2020"), date(2020, 1, 30))

    def test_data_invalida_levanta(self):
        with self.assertRaises(ValueError):
            converter_data("2020-01-30")  # formato errado
        with self.assertRaises(ValueError):
            converter_data("31/02/2020")  # dia que não existe

    def test_fornecedor_com_tres_partes(self):
        self.assertEqual(
            separar_fornecedor("CNPJ - PESSOA JURÍDICA - 65069593000198"), ("CNPJ", "65069593000198")
        )

    def test_fornecedor_com_duas_partes(self):
        self.assertEqual(separar_fornecedor("PESSOA FÍSICA - 921998"), ("PESSOA FÍSICA", "921998"))
        self.assertEqual(
            separar_fornecedor("INSCRIÇÃO GENÉRICA-OUTROS - 5130001"), ("INSCRIÇÃO GENÉRICA-OUTROS", "5130001")
        )


class TransformarTest(unittest.TestCase):
    def _registro(self, **mudancas):
        base = {
            "orgao": "PREFEITURA",
            "evento": "Empenhado",
            "nr_empenho": "1-2020",
            "id_fornecedor": "CNPJ - PESSOA JURÍDICA - 123",
            "nm_fornecedor": "ACME",
            "dt_emissao_despesa": "02/03/2020",
            "vl_despesa": "10,50",
        }
        return {**base, **mudancas}

    def test_converte_os_tipos(self):
        ok, erros = transformar([self._registro()])
        self.assertEqual(erros, [])
        self.assertEqual(ok[0]["vl_despesa"], Decimal("10.50"))
        self.assertEqual(ok[0]["dt_emissao_despesa"], date(2020, 3, 2))
        self.assertEqual(ok[0]["tipo_identificacao_fornecedor"], "CNPJ")

    def test_registro_ruim_vai_para_erros_sem_derrubar_os_bons(self):
        ok, erros = transformar([self._registro(), self._registro(vl_despesa="xx"), self._registro()])
        self.assertEqual(len(ok), 2)
        self.assertEqual([i for i, _, _ in erros], [1])


if __name__ == "__main__":
    unittest.main()
