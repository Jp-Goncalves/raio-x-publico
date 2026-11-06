from pipeline import rodar_pipeline

CIDADES = ["jacarei", "campinas"]
ANO = 2020
MESES = range(1, 13)


def rodar_backfill() -> None:
    sucesso = 0
    falhas = []

    for cidade in CIDADES:
        for mes in MESES:
            print(f"\n----- {cidade} {ANO}/{mes:02d} -----")
            try:
                rodar_pipeline(cidade, ANO, mes)
                sucesso += 1
            except Exception as e:
                print(f"[erro] {cidade}/{ANO}/{mes:02d}: {e}")
                falhas.append((cidade, mes, str(e)))

    print(f"\n=== backfill concluído: {sucesso} ok, {len(falhas)} falha(s) ===")
    if falhas:
        print("Falhas:")
        for cidade, mes, msg in falhas:
            print(f"  {cidade}/{ANO}/{mes:02d}: {msg}")
