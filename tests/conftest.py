import sys
from pathlib import Path

# Garante que o pacote `pipeline` (na raiz do repo) seja importável nos testes.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATA_DIR = Path(__file__).resolve().parent / "data"
