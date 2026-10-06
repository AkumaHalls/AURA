"""
Ajusta o texto do painel de tickets para o modelo antigo, limpo.

O preset de pre-configuracao tinha gravado uma `panel_description` que nao era
a do modelo antigo. Este script troca pelo texto de antes e garante que a cor
seja a dourada.

Uso (dentro do container): python tools/ajustar_painel.py [guild_id]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mongo_db  # noqa: E402

TEXTO_ANTIGO = ("Bem-vindo à central de ajuda! Use o menu abaixo para selecionar "
                "o motivo do seu contato e abrir um ticket. "
                "Um líder ou co-líder irá te ajudar.")

mongo_db.conectar()

for d in mongo_db.list_all_guild_configs():
    tk = d.get("tickets") or {}
    antes = (tk.get("panel_description"), tk.get("panel_title"), tk.get("panel_color"))
    tk["panel_description"] = TEXTO_ANTIGO
    tk["panel_title"] = None
    tk["panel_color"] = "#f1c40f"
    mongo_db.upsert_guild_config(d["guild_id"], d, updated_by="ajustar_painel")
    print(f"{d.get('guild_name')} ({d['guild_id']})")
    print(f"  panel_title       : {antes[1]!r} -> None")
    print(f"  panel_description : {antes[0][:60]!r}... -> texto antigo")
    print(f"  panel_color       : {antes[2]!r} -> '#f1c40f'")