"""EPE: download das planilhas de consumo e inspeção (o layout muda com frequência)."""
import re
from urllib.parse import unquote, urljoin

import pandas as pd

from pipeline.config import BRUTOS, EPE_PAGINAS
from pipeline.utils import get


def extrair_epe(inicio):
    pasta = BRUTOS / "epe"
    pasta.mkdir(parents=True, exist_ok=True)
    baixados = []
    for pag in EPE_PAGINAS:
        try:
            html = get(pag).text
        except Exception as e:
            print(f"[EPE] página indisponível: {pag} ({e})")
            continue
        links = re.findall(r'href=["\']([^"\']+\.(?:xlsx?|csv))["\']', html, re.I)
        for l in sorted(set(links)):
            url = urljoin(pag, l)
            destino = pasta / unquote(url.rsplit("/", 1)[-1].split("?")[0])
            try:
                destino.write_bytes(get(url, timeout=300).content)
                baixados.append(destino)
                print(f"[EPE] baixado: {destino.name}")
            except Exception as e:
                print(f"[EPE] falhou {url}: {e}")
    if not baixados:
        print("[EPE] nenhum arquivo encontrado automaticamente. Abra a página, baixe a planilha "
              f"manualmente e coloque em {pasta}/")
        baixados = list(pasta.glob("*.xls*")) + list(pasta.glob("*.csv"))
    # Inspeção: valide colunas/abas antes de escrever o parser definitivo
    for f in baixados:
        print(f"\n[EPE] inspeção de {f.name}")
        try:
            if f.suffix.lower() == ".csv":
                print(pd.read_csv(f, sep=None, engine="python", nrows=5).to_string())
            else:
                for aba, d in pd.read_excel(f, sheet_name=None, header=None, nrows=8).items():
                    print(f"  aba '{aba}':")
                    print(d.to_string(max_cols=12))
        except Exception as e:
            print(f"  não foi possível ler: {e}")
