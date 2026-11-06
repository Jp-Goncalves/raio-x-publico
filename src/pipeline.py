from extract import extrair
from load import carregar
from transform import transformar_e_gravar


def rodar_pipeline(cidade: str, ano: int, mes: int) -> None:
    print(f"=== EXTRACT: {cidade}/{ano}/{mes:02d} ===")
    extrair(cidade, ano, mes)

    print(f"\n=== LOAD: {cidade}/{ano}/{mes:02d} ===")
    carregar(cidade, ano, mes)

    print(f"\n=== TRANSFORM: {cidade}/{ano}/{mes:02d} ===")
    transformar_e_gravar(cidade, ano, mes)

    print(f"\npipeline concluído para {cidade}/{ano}/{mes:02d}")
