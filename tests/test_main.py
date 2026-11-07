import contextlib
import io
import json
import unittest
from unittest import mock

from tests import _caminho  # noqa: F401
import main


class ImprimirCidadesTest(unittest.TestCase):
    def _roda(self, informadas, desconhecidas=(), carregadas=()):
        saida = io.StringIO()
        with mock.patch.object(main, "cidades_desconhecidas", return_value=list(desconhecidas)), \
             mock.patch.object(main, "cidades_carregadas", return_value=list(carregadas)), \
             contextlib.redirect_stdout(saida):
            main.imprimir_cidades(informadas)
        return json.loads(saida.getvalue().strip().splitlines()[-1])

    def test_cidades_informadas_e_validas_sao_devolvidas(self):
        self.assertEqual(self._roda(["jacarei", "lorena"]), ["jacarei", "lorena"])

    def test_cidade_que_a_fonte_nao_atende_e_recusada_com_o_nome_dela(self):
        with self.assertRaisesRegex(ValueError, "sao-paulo"):
            self._roda(["jacarei", "sao-paulo"], desconhecidas=["sao-paulo"])

    def test_sem_cidades_usa_as_ja_carregadas(self):
        self.assertEqual(self._roda([], carregadas=["campinas", "jacarei"]), ["campinas", "jacarei"])

    def test_sem_cidades_e_nada_carregado_e_erro(self):
        # um agendamento não pode "passar" sem processar nada
        with self.assertRaises(ValueError):
            self._roda([], carregadas=[])


class LinhaDeComandoTest(unittest.TestCase):
    def _roda(self, *args):
        with mock.patch("sys.argv", ["main.py", *args]), \
             contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as saida:
                main.main()
        return saida.exception.code

    def test_backfill_exige_ao_menos_uma_cidade(self):
        self.assertEqual(self._roda("backfill", "2020"), 2)  # 2 = erro de uso do argparse

    def test_extract_nao_aceita_dois_modos_de_mes_vazio_inexistentes(self):
        self.assertEqual(self._roda("extract", "jacarei", "2020", "1", "--nao-existe"), 2)

    def test_codigo_de_saida_de_mes_sem_dado_e_o_que_o_airflow_trata_como_pulado(self):
        self.assertEqual(main.CODIGO_SAIDA_SEM_DADOS, 99)


if __name__ == "__main__":
    unittest.main()
