"""
Confere que a busca de ticket por thread funciona no Mongo de verdade.

O bug do topico deixou o _id do Mongo sem forma de ser recuperado a partir da
thread. Aqui pegamos os tickets reais e tentamos resolver cada um pela thread,
que e o caminho que o botao de atender usa.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mongo_db  # noqa: E402

mongo_db.conectar()
docs = list(mongo_db.db.tickets.find({}).sort("ts", -1).limit(8))

if not docs:
    print("nenhum ticket no banco ainda")
    raise SystemExit(0)

print(f"{len(docs)} ticket(s) recente(s):\n")
ok = falha = sem_thread = 0
for d in docs:
    tid = d.get("_id")
    thread_id = d.get("ticket_id")
    achado = mongo_db.ticket_por_thread(thread_id, d.get("guild_id")) if thread_id else None
    if achado and str(achado["_id"]) == str(tid):
        ok += 1
        marca = "ok "
    elif thread_id and achado:
        falha += 1
        marca = "XX "
    else:
        sem_thread += 1
        marca = "-- "
    print(f"{marca}{tid} | thread={thread_id} | {d.get('status')} | "
          f"{d.get('user_name')} | tipo={d.get('tipo')}")

print(f"\nresolvidos pela thread: {ok}")
print(f"resolvidos para outro ticket: {falha}")
print(f"sem thread gravada (ticket antigo): {sem_thread}")