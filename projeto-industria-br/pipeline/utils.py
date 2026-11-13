"""Funções compartilhadas: HTTP com retry, gravação de CSV, normalização de nomes e datas."""
import re
import time
import unicodedata

import requests

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 (projeto-portfolio-dados)"})


def salvar_csv(obj, caminho, **kw):
    """Grava CSV; se o arquivo estiver aberto em outro programa (ex.: Excel), explica o motivo."""
    try:
        obj.to_csv(caminho, **kw)
    except PermissionError:
        raise RuntimeError(f"Não foi possível gravar {caminho}: o arquivo está aberto em outro "
                           f"programa (Excel, por exemplo). Feche-o e rode de novo.")


def get(url, params=None, tentativas=4, timeout=120):
    """GET com retry. Levanta erro mostrando o texto devolvido pela API."""
    ultimo = None
    for i in range(tentativas):
        try:
            r = SESSION.get(url, params=params, timeout=timeout)
            if r.status_code == 200:
                return r
            ultimo = f"HTTP {r.status_code}: {r.text[:300]}"
            if r.status_code < 500 and r.status_code != 429:
                break  # erro do cliente: repetir não adianta
        except requests.RequestException as e:
            ultimo = repr(e)
        time.sleep(2 ** i)
    raise RuntimeError(f"Falha em {url} -> {ultimo}")


def lista_meses(p0, p1):
    a, m = int(p0[:4]), int(p0[4:6])
    out = []
    while f"{a}{m:02d}" <= p1:
        out.append(f"{a}{m:02d}")
        m += 1
        if m > 12:
            a, m = a + 1, 1
    return out


def norm_nome(n, limite=60):
    """'Mês (Código)' -> 'mes_codigo' (minúsculas, sem acento, só [a-z0-9_])."""
    n = unicodedata.normalize("NFKD", str(n)).encode("ascii", "ignore").decode()
    n = re.sub(r"[^a-zA-Z0-9]+", "_", n).strip("_").lower()
    if not n or n[0].isdigit():
        n = "c_" + n
    return n[:limite]


def norm_colunas(cols):
    vistos, out = {}, []
    for c in cols:
        base = norm_nome(c)
        vistos[base] = vistos.get(base, 0) + 1
        out.append(base if vistos[base] == 1 else f"{base}_{vistos[base]}")
    return out


def erro_legivel(e):
    """No Windows em PT-BR, as mensagens do libpq/PostgreSQL vêm em cp1252 e quebram o
    decode UTF-8 do psycopg2. Aqui recuperamos o texto real do erro."""
    if isinstance(e, UnicodeDecodeError):
        try:
            return e.object.decode("cp1252", errors="replace")
        except Exception:
            pass
    return str(e)
