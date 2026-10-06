"""Lista os canais de painel e suporte configurados, para conferir de fora."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mongo_db  # noqa: E402

mongo_db.conectar()
for d in mongo_db.list_all_guild_configs():
    tk = d.get("tickets") or {}
    print(d.get("guild_name"), "|", d["guild_id"])
    print("   support_channel_id:", tk.get("support_channel_id"))
    print("   panel_channel_id  :", tk.get("panel_channel_id"))