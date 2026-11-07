import unittest
from unittest import mock

from tests import _caminho  # noqa: F401
import municipios


def municipio(uf):
    return {"id": 1, "nome": "X", "microrregiao": {"mesorregiao": {"UF": {"sigla": uf}}}}


class UfDoPayloadTest(unittest.TestCase):
    def test_devolve_a_sigla_de_dentro_do_payload(self):
        self.assertEqual(municipios._uf_do_payload([municipio("SP"), municipio("SP")]), "SP")

    def test_recusa_payload_com_mais_de_uma_uf(self):
        with self.assertRaises(ValueError):
            municipios._uf_do_payload([municipio("SP"), municipio("RJ")])


class CargaRecusaDadoRuimTest(unittest.TestCase):
    """Nenhum desses casos pode chegar ao banco: um [] não pode trocar um raw bom."""

    def test_uf_inexistente_a_api_devolve_lista_vazia(self):
        with mock.patch.object(municipios, "get_json", return_value=[]), \
             mock.patch.object(municipios, "conectar") as conectar:
            with self.assertRaises(ValueError):
                municipios.carregar_municipios("XX")
        conectar.assert_not_called()

    def test_lista_do_tce_vazia(self):
        with mock.patch.object(municipios, "get_json", return_value=[]), \
             mock.patch.object(municipios, "conectar") as conectar:
            with self.assertRaises(ValueError):
                municipios.carregar_municipios_tce_sp()
        conectar.assert_not_called()

    def test_lista_do_tce_sem_o_campo_municipio(self):
        with mock.patch.object(municipios, "get_json", return_value=[{"outro": "campo"}]), \
             mock.patch.object(municipios, "conectar") as conectar:
            with self.assertRaises(ValueError):
                municipios.carregar_municipios_tce_sp()
        conectar.assert_not_called()


if __name__ == "__main__":
    unittest.main()
