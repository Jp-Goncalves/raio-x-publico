from municipios import cidades_desconhecidas
from pipeline import rodar_pipeline

MESES = range(1, 13)


def rodar_backfill(cidades: list[str], ano: int) -> None:
    desconhecidas = cidades_desconhecidas(cidades)
    if desconhecidas:
        raise ValueError(
            f"cidades que o TCE-SP não atende (ou fora da dimensão): {', '.join(desconhecidas)}"
        )

    sucesso = 0
    falhas = []

    for cidade in cidades:
        for mes in MESES:
            print(f"\n----- {cidade} {ano}/{mes:02d} -----")
            try:
                rodar_pipeline(cidade, ano, mes)
                sucesso += 1
            except Exception as e:
                print(f"[erro] {cidade}/{ano}/{mes:02d}: {e}")
                falhas.append((cidade, mes, str(e)))

    print(f"\n=== backfill concluído: {sucesso} ok, {len(falhas)} falha(s) ===")
    if falhas:
        print("Falhas:")
        for cidade, mes, msg in falhas:
            print(f"  {cidade}/{ano}/{mes:02d}: {msg}")
