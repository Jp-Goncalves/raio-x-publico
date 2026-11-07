import unittest
from unittest import mock

from tests import _caminho  # noqa: F401
import airflow_client as ac


def resposta(status, json_valor=None):
    r = mock.Mock()
    r.status_code = status
    r.json.return_value = json_valor or {}
    r.text = ""
    return r


class IdDaCargaTest(unittest.TestCase):
    def test_mesmo_pedido_mesmo_id_independente_da_ordem_das_cidades(self):
        self.assertEqual(
            ac.id_da_carga(["lorena", "jacarei"], "2026-08", 1),
            ac.id_da_carga(["jacarei", "lorena"], "2026-08", 1),
        )

    def test_pedido_diferente_id_diferente(self):
        base = ac.id_da_carga(["lorena"], "2026-08", 1)
        self.assertNotEqual(base, ac.id_da_carga(["lorena"], "2026-09", 1))
        self.assertNotEqual(base, ac.id_da_carga(["lorena"], "2026-08", 2))
        self.assertNotEqual(base, ac.id_da_carga(["lorena", "jacarei"], "2026-08", 1))

    def test_id_so_tem_caracteres_aceitos_pelo_airflow(self):
        self.assertRegex(ac.id_da_carga(["lorena"], "2026-08", 1), r"^[A-Za-z0-9_.:+-]+$")


class DispararCargaTest(unittest.TestCase):
    def _dispara(self, respostas):
        posts = []

        def falso(metodo, caminho, **kwargs):
            if metodo == "POST":
                posts.append(kwargs["json"]["dag_run_id"])
            return respostas.pop(0)

        with mock.patch.object(ac, "_chamar", side_effect=falso):
            run_id = ac.disparar_carga(["lorena"], "2026-08", 1)
        return run_id, posts

    def test_pedido_novo(self):
        run_id, posts = self._dispara([resposta(201)])
        self.assertEqual(len(posts), 1)
        self.assertEqual(run_id, posts[0])

    def test_id_repetido_com_execucao_em_andamento_acompanha_a_mesma(self):
        run_id, posts = self._dispara([resposta(409), resposta(200, {"state": "running"})])
        self.assertEqual(len(posts), 1)  # nenhum segundo POST
        self.assertEqual(run_id, posts[0])

    def test_id_repetido_com_execucao_concluida_acompanha_a_mesma(self):
        run_id, posts = self._dispara([resposta(409), resposta(200, {"state": "success"})])
        self.assertEqual((len(posts), run_id), (1, posts[0]))

    def test_id_repetido_com_execucao_que_falhou_cria_um_pedido_novo(self):
        run_id, posts = self._dispara([resposta(409), resposta(200, {"state": "failed"}), resposta(201)])
        self.assertEqual(len(posts), 2)
        self.assertNotEqual(posts[0], posts[1])
        self.assertEqual(run_id, posts[1])

    def test_recusa_do_airflow_vira_erro_tratavel(self):
        with mock.patch.object(ac, "_chamar", return_value=resposta(400)):
            with self.assertRaises(ac.AirflowIndisponivel):
                ac.disparar_carga(["lorena"], "2026-08", 1)


if __name__ == "__main__":
    unittest.main()
