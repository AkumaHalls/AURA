"""Mostra a data e a origem dos tickets para saber quais sao antigos."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mongo_db  # noqa: E402

mongo_db.conectar()
for d in mongo_db.db.tickets.find({}).sort("ts", -1).limit(10):
    ts = d.get("ts") or 0
    print(f"{d.get('_id')} | {time.strftime('%Y-%m-%d %H:%M', time.localtime(ts))} | "
          f"thread={d.get('ticket_id')} | guild_id={d.get('guild_id')} | "
          f"status={d.get('status')} | {d.get('user_name')}")
print("total de tickets:", mongo_db.db.tickets.count_documents({}))