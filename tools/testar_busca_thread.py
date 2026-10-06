"""
Prova que a busca de ticket por thread funciona no Mongo real.

Insere um ticket sintetico com um id de thread ficticio, resolve por
`ticket_por_thread` (o caminho que o botao de atender usa) e apaga no final.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mongo_db  # noqa: E402

THREAD_FICTICIA = "1234567890123456789"
GUILD = "1362076878458065037"

mongo_db.conectar()

doc = {
    "user_id": "0", "user_name": "teste_busca", "tipo": "Teste",
    "status": "aberto", "atendente": None, "guild_id": GUILD,
    "guild_name": "teste", "ticket_id": THREAD_FICTICIA,
    "channel_name": "teste-busca", "categoria_key": "outros",
    "avatar": None, "data": "", "ts": 0,
}
res = mongo_db.db.tickets.insert_one(doc)
tid = str(res.inserted_id)
print(f"inserido _id={tid} com thread={THREAD_FICTICIA}")

try:
    achado = mongo_db.ticket_por_thread(THREAD_FICTICIA, GUILD)
    print("achado      :", str(achado["_id"]) if achado else None)
    print("bate com _id:", bool(achado) and str(achado["_id"]) == tid)
    print("user_name   :", achado.get("user_name") if achado else None)

    # guild diferente nao deve achar o ticket de outro servidor
    outro = mongo_db.ticket_por_thread(THREAD_FICTICIA, "999999999999999999")
    print("outro guild :", outro)

    # e a busca por _id continua funcionando (usada no /atendimento e avaliacao)
    por_id = mongo_db.get_ticket(tid)
    print("get_ticket  :", bool(por_id))
finally:
    mongo_db.db.tickets.delete_one({"_id": res.inserted_id})
    print("limpo:", mongo_db.db.tickets.count_documents({"_id": res.inserted_id}) == 0)