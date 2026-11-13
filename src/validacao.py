"""Validação das entradas que viram parte de uma URL ou de um caminho de arquivo.

O nome da cidade (slug), o ano, o mês e a UF chegam de fora: da linha de comando, dos parâmetros
do DAG ou do dashboard. Antes de montarem uma URL ou o nome de um arquivo em data/raw, passam
por aqui. Sem isso, um slug como "../../x" escreveria um arquivo fora de data/raw, e um slug
com "/" ou "?" mudaria o endereço que a API recebe.

É uma lista de permitidos (só o que a gente sabe que é válido passa), e não uma lista de
proibidos: não tem como esquecer um caractere perigoso.
"""
import re

# como a API do TCE-SP escreve o nome: minúsculas, sem acento, hífen no lugar do espaço
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")
_UF = re.compile(r"^[A-Za-z]{2}$")


def validar_cidade(cidade: str) -> str:
    if not isinstance(cidade, str) or not _SLUG.fullmatch(cidade):
        raise ValueError(
            f"nome de cidade inválido: {cidade!r}. Use o nome que a API espera: "
            "minúsculas, sem acento, hífen no lugar do espaço (ex.: 'sao-jose-dos-campos')."
        )
    return cidade


def validar_periodo(ano: int, mes: int) -> tuple[int, int]:
    if not (1900 <= ano <= 2100):
        raise ValueError(f"ano fora do intervalo aceito (1900 a 2100): {ano}")
    if not (1 <= mes <= 12):
        raise ValueError(f"mês inválido: {mes}. Use de 1 a 12.")
    return ano, mes


def validar_uf(uf: str) -> str:
    if not isinstance(uf, str) or not _UF.fullmatch(uf):
        raise ValueError(f"UF inválida: {uf!r}. Use a sigla de duas letras, ex.: SP.")
    return uf
