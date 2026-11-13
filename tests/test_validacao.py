import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests import _caminho  # noqa: F401
import extract
import load
import municipios
from validacao import validar_cidade, validar_periodo, validar_uf

# o que um atacante (ou um erro de digitação) poderia mandar no lugar do nome da cidade
CIDADES_MALICIOSAS = [
    "../../etc/passwd",
    "..\\..\\windows\\win.ini",
    "jacarei/../../x",
    "jacarei?x=1",
    "jacarei#frag",
    "jacarei\n",
    "jacarei ",
    "Jacarei",  # maiúscula: a API espera minúsculas
    "jacareí",  # acento
    "",
    "-jacarei",  # começa com hífen (poderia ser lido como opção)
    "a" * 81,
    "jacarei%2f..",
]


class ValidarCidadeTest(unittest.TestCase):
    def test_aceita_nomes_como_a_api_escreve(self):
        for cidade in ("jacarei", "sao-jose-dos-campos", "santa-barbara-d-oeste", "a1"):
            self.assertEqual(validar_cidade(cidade), cidade)

    def test_recusa_entradas_perigosas_ou_fora_do_padrao(self):
        for cidade in CIDADES_MALICIOSAS:
            with self.subTest(cidade=cidade), self.assertRaises(ValueError):
                validar_cidade(cidade)

    def test_recusa_o_que_nao_e_texto(self):
        for cidade in (None, 123, ["jacarei"]):
            with self.subTest(cidade=cidade), self.assertRaises(ValueError):
                validar_cidade(cidade)


class ValidarPeriodoEUfTest(unittest.TestCase):
    def test_periodo_valido(self):
        self.assertEqual(validar_periodo(2026, 12), (2026, 12))

    def test_periodo_invalido(self):
        for ano, mes in ((2026, 0), (2026, 13), (2026, -1), (1899, 1), (2101, 1)):
            with self.subTest(ano=ano, mes=mes), self.assertRaises(ValueError):
                validar_periodo(ano, mes)

    def test_uf(self):
        self.assertEqual(validar_uf("SP"), "SP")
        self.assertEqual(validar_uf("sp"), "sp")  # o IBGE aceita; quem trata a caixa é o payload
        for uf in ("", "S", "SPP", "35", "S/", "../", None):
            with self.subTest(uf=uf), self.assertRaises(ValueError):
                validar_uf(uf)


class EntradasNaoChegamAoDestinoTest(unittest.TestCase):
    """Com uma entrada maliciosa, nada é pedido à API, gravado ou lido: o erro vem antes."""

    def test_extract_nao_chama_a_api_nem_grava(self):
        with tempfile.TemporaryDirectory() as pasta, \
             mock.patch.object(extract, "RAW_DIR", Path(pasta) / "raw"), \
             mock.patch.object(extract, "get_json") as http:
            for cidade in CIDADES_MALICIOSAS:
                with self.subTest(cidade=cidade), self.assertRaises(ValueError):
                    extract.extrair(cidade, 2026, 1)
            http.assert_not_called()
            self.assertEqual(list(Path(pasta).rglob("*")), [])  # nem a pasta foi criada

    def test_extract_recusa_periodo_invalido(self):
        with mock.patch.object(extract, "get_json") as http:
            for ano, mes in ((2026, 13), (2026, 0), (9999, 1)):
                with self.subTest(ano=ano, mes=mes), self.assertRaises(ValueError):
                    extract.extrair("jacarei", ano, mes)
            http.assert_not_called()

    def test_salvar_raw_nao_escreve_fora_da_pasta(self):
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            destino = raiz / "data" / "raw"
            with mock.patch.object(extract, "RAW_DIR", destino):
                with self.assertRaises(ValueError):
                    extract.salvar_raw([], "../../fora", 2026, 1)
            self.assertEqual(list(raiz.rglob("*")), [])

    def test_ler_raw_nao_le_fora_da_pasta(self):
        with tempfile.TemporaryDirectory() as pasta:
            segredo = Path(pasta) / "segredo_01.json"  # o que "../segredo" tentaria alcançar
            segredo.write_text('["conteudo que nao pode ser lido"]', encoding="utf-8")
            with mock.patch.object(load, "RAW_DIR", Path(pasta) / "data" / "raw"):
                with self.assertRaises(ValueError):
                    load.ler_raw("../../segredo", 2026, 1)

    def test_municipios_nao_chama_o_ibge_com_uf_invalida(self):
        with mock.patch.object(municipios, "get_json") as http:
            for uf in ("../x", "SP/../..", "35", ""):
                with self.subTest(uf=uf), self.assertRaises(ValueError):
                    municipios.carregar_municipios(uf)
            http.assert_not_called()


if __name__ == "__main__":
    unittest.main()
