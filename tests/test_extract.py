import unittest
from unittest import mock

from tests import _caminho  # noqa: F401
import extract
from extract import SemDadosNaFonte


class MesSemDadoTest(unittest.TestCase):
    """A API devolve 200 com [] pra mês não publicado: o que o extract faz com isso."""

    def _extrai(self, dados, **opcoes):
        with mock.patch.object(extract, "buscar_despesas", return_value=dados), \
             mock.patch.object(extract, "salvar_raw", return_value="arquivo.json") as salvar:
            try:
                extract.extrair("jacarei", 2020, 1, **opcoes)
                erro = None
            except Exception as e:  # noqa: BLE001
                erro = e
        return erro, salvar.called

    def test_pular_se_vazio_levanta_semdados_e_nao_grava(self):
        erro, gravou = self._extrai([], pular_se_vazio=True)
        self.assertIsInstance(erro, SemDadosNaFonte)
        self.assertFalse(gravou)

    def test_falhar_se_vazio_levanta_valueerror_e_nao_grava(self):
        erro, gravou = self._extrai([], falhar_se_vazio=True)
        self.assertIsInstance(erro, ValueError)
        self.assertNotIsInstance(erro, SemDadosNaFonte)
        self.assertFalse(gravou)

    def test_vazio_sem_opcao_grava_o_arquivo_vazio(self):
        erro, gravou = self._extrai([])
        self.assertIsNone(erro)
        self.assertTrue(gravou)

    def test_com_dados_grava_qualquer_que_seja_a_opcao(self):
        for opcoes in ({}, {"falhar_se_vazio": True}, {"pular_se_vazio": True}):
            erro, gravou = self._extrai([{"orgao": "X"}], **opcoes)
            self.assertIsNone(erro)
            self.assertTrue(gravou)


if __name__ == "__main__":
    unittest.main()
