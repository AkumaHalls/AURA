"""
Roda a suíte inteira e devolve erro se qualquer teste falhar.
Uso: python -X utf8 tests\run_all.py
"""
import os
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
PYTHON = sys.executable

TESTES = [
    ("settings", "test_settings.py"),
    ("templates", "test_templates.py"),
    ("runtime", "test_runtime.py"),
    ("provas", "test_provas_retomada.py"),
    ("views persistentes", "test_views_persistentes.py"),
    ("variaveis de ambiente", "test_env_vars.py"),
    ("gravacao de config", "test_db_write.py"),
    ("painel nao perde config", "test_painel_config.py"),
    ("filtro por servidor", "test_filtro_guild.py"),
    ("fluxo de tickets", "test_ticket_fluxo.py"),
    ("pre-configuracao", "test_preconfig.py"),
    ("moderacao", "test_moderacao.py"),
    ("painel", "test_painel.py"),
    ("painel post", "test_painel_post.py"),
    ("chamadas mongo_db", "test_chamadas_db.py"),
    ("persistencia do ticket", "test_ticket_persistencia.py"),
    ("migracao do .env", "test_migracao_env.py"),
]


def main() -> int:
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    falhas = []

    for nome, arquivo in TESTES:
        caminho = os.path.join(AQUI, arquivo)
        print(f"\n{'=' * 62}\n  {nome}  ({arquivo})\n{'=' * 62}")
        proc = subprocess.run([PYTHON, "-X", "utf8", caminho], cwd=RAIZ, env=env)
        if proc.returncode != 0:
            falhas.append(nome)

    print(f"\n{'=' * 62}")
    if falhas:
        print(f"FALHARAM: {len(falhas)} de {len(TESTES)}")
        for n in falhas:
            print(f"  - {n}")
        return 1
    print(f"todos os {len(TESTES)} testes passaram")
    return 0


if __name__ == "__main__":
    sys.exit(main())