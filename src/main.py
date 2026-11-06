import argparse
import sys

from backfill import rodar_backfill
from extract import extrair
from load import carregar
from pipeline import rodar_pipeline
from transform import transformar_e_gravar


def _add_cidade_ano_mes(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("cidade")
    subparser.add_argument("ano", type=int)
    subparser.add_argument("mes", type=int)


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline raio-x-publico")
    subparsers = parser.add_subparsers(dest="comando", required=True)

    _add_cidade_ano_mes(subparsers.add_parser("extract", help="só extrai da API e salva o raw"))
    _add_cidade_ano_mes(subparsers.add_parser("load", help="só carrega o raw salvo no Postgres"))
    _add_cidade_ano_mes(subparsers.add_parser("transform", help="só transforma e grava em stg_pagamentos"))
    _add_cidade_ano_mes(subparsers.add_parser("pipeline", help="roda extract -> load -> transform"))
    subparsers.add_parser("backfill", help="roda o pipeline pra vários períodos passados")

    args = parser.parse_args()

    try:
        if args.comando == "extract":
            extrair(args.cidade, args.ano, args.mes)
        elif args.comando == "load":
            carregar(args.cidade, args.ano, args.mes)
        elif args.comando == "transform":
            transformar_e_gravar(args.cidade, args.ano, args.mes)
        elif args.comando == "pipeline":
            rodar_pipeline(args.cidade, args.ano, args.mes)
        elif args.comando == "backfill":
            rodar_backfill()
    except Exception as e:
        print(f"\n[erro] comando '{args.comando}' falhou: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
