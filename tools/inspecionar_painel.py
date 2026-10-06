"""
Confere o estado do painel publicado: embed, campos e se o DropDown responde.

Nao da para clicar no Discord por script, entao o que dá para medir e:
- o embed tem os campos certos (e nao tem 'Categorias')
- as opcoes do DropDown batem com a config
"""
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

API = "https://discord.com/api/v10"


def main() -> int:
    guild_id, canal_id, msg_id = sys.argv[1], sys.argv[2], sys.argv[3]
    token = os.getenv("DISCORD_TOKEN")
    h = {"Authorization": f"Bot {token}"}
    r = requests.get(f"{API}/channels/{canal_id}/messages/{msg_id}", headers=h, timeout=30)
    if r.status_code != 200:
        print("ERRO:", r.status_code, r.text[:300])
        return 1
    msg = r.json()
    emb = (msg.get("embeds") or [{}])[0]

    print("titulo  :", emb.get("title"))
    print("cor     :", emb.get("color"))
    print("imagem  :", "sim" if emb.get("image") else "NAO")
    print("rodape  :", (emb.get("footer") or {}).get("text"))
    print("campos  :", [f.get("name") for f in emb.get("fields") or []] or "nenhum (limpo)")
    print("desc    :", (emb.get("description") or "")[:120])

    comps = msg.get("components") or []
    selects = [c for row in comps for c in (row.get("components") or [])]
    print("componentes:", len(comps), "linha(s),", len(selects), "item(ns)")
    for s in selects:
        print("  custom_id:", s.get("custom_id"))
        for o in s.get("options") or []:
            print(f"    {o.get('emoji', {}).get('name') if o.get('emoji') else '-'} "
                  f"{o.get('label')} -> {o.get('value')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())