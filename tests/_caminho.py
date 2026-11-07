"""Põe src/ no caminho de importação, como o main.py enxerga os módulos. Importado pelos testes."""
import sys
from pathlib import Path

SRC = str(Path(__file__).resolve().parent.parent / "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)
