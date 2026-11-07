import unittest
from unittest import mock

import requests

from tests import _caminho  # noqa: F401
import api_client


def resposta(status=200, json_valor=None, json_invalido=False):
    r = mock.Mock()
    r.status_code = status
    if status >= 400:
        r.raise_for_status.side_effect = requests.exceptions.HTTPError(str(status))
    if json_invalido:
        r.json.side_effect = requests.exceptions.JSONDecodeError("Expecting value", "", 0)
    else:
        r.json.return_value = json_valor
    return r


class RetryTest(unittest.TestCase):
    def _chama(self, respostas):
        with mock.patch.object(api_client.requests, "get", side_effect=respostas) as get, \
             mock.patch.object(api_client.time, "sleep") as sleep:
            try:
                resultado = api_client.get_json("http://x", "teste")
                erro = None
            except Exception as e:  # noqa: BLE001 - o teste inspeciona qualquer erro
                resultado, erro = None, e
        return resultado, erro, get.call_count, [c.args[0] for c in sleep.call_args_list]

    def test_5xx_tenta_de_novo_com_espera_crescente(self):
        resultado, erro, chamadas, esperas = self._chama([resposta(500), resposta(500), resposta(200, [1])])
        self.assertEqual((resultado, erro, chamadas, esperas), ([1], None, 3, [2, 4]))

    def test_corpo_que_nao_e_json_tambem_tenta_de_novo(self):
        resultado, _, chamadas, _ = self._chama(
            [resposta(200, json_invalido=True), resposta(200, json_invalido=True), resposta(200, [2])]
        )
        self.assertEqual((resultado, chamadas), ([2], 3))

    def test_4xx_falha_na_hora_sem_tentar_de_novo(self):
        _, erro, chamadas, esperas = self._chama([resposta(404)])
        self.assertIsInstance(erro, requests.exceptions.HTTPError)
        self.assertEqual((chamadas, esperas), (1, []))

    def test_erro_de_conexao_tenta_de_novo(self):
        resultado, _, chamadas, esperas = self._chama([requests.exceptions.ConnectionError("sem rede"), resposta(200, [3])])
        self.assertEqual((resultado, chamadas, esperas), ([3], 2, [2]))

    def test_esgotadas_as_tentativas_levanta_runtimeerror(self):
        _, erro, chamadas, esperas = self._chama([resposta(500)] * api_client.MAX_TENTATIVAS)
        self.assertIsInstance(erro, RuntimeError)
        self.assertIn("teste", str(erro))
        self.assertEqual((chamadas, esperas), (4, [2, 4, 8]))


if __name__ == "__main__":
    unittest.main()
