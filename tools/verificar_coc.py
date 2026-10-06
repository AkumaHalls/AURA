"""Mostra o bloco games.coc do B.A.D como esta no Mongo.

Uso (dentro do container): python tools/verificar_coc.py [guild_id]
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mongo_db  # noqa: E402

GID = sys.argv[1] if len(sys.argv) > 1 else "1362076878458065037"

mongo_db.conectar()
for d in mongo_db.list_all_guild_configs():
    if str(d.get("guild_id")) != GID:
        continue
    coc = (d.get("games") or {}).get("coc") or {}
    print(f"{d.get('guild_name')} ({GID})")
    print(json.dumps(coc, ensure_ascii=False, indent=2, default=str))