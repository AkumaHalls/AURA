"""
Lista as threads de ticket do canal de suporte e mostra quais estao vazias.

Depois do bug do topico, varias threads ficaram criadas sem nenhuma mensagem.
Este script mostra o estado para dar para fechar as orfas.
"""
import os
import sys

import requests

API = "https://discord.com/api/v10"


def main() -> int:
    canal_id = sys.argv[1]
    token = os.getenv("DISCORD_TOKEN")
    h = {"Authorization": f"Bot {token}"}

    ativos = requests.get(f"{API}/channels/{canal_id}/threads/active",
                          headers=h, params={"limit": 100}, timeout=30).json()
    arq = requests.get(f"{API}/channels/{canal_id}/threads/archived/public",
                       headers=h, params={"limit": 100}, timeout=30).json()

    for rotulo, lista in (("ativas", ativos), ("arquivadas", arq)):
        ths = lista.get("threads", []) if isinstance(lista, dict) else lista
        print(f"--- {rotulo}: {len(ths)} ---")
        for t in ths:
            msgs = requests.get(f"{API}/channels/{t['id']}/messages",
                                headers=h, params={"limit": 50}, timeout=30).json()
            print(f"  {t['id']} | {t['name'][:40]:40} | msgs={len(msgs):3} | "
                  f"arquivada={t.get('thread_metadata', {}).get('archived')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())