import os
import json
from datetime import datetime
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

MONGO_URI = os.getenv("MONGO_URI")
client = None
db = None

def conectar():
    global client, db
    if not MONGO_URI:
        print("MONGO_URI não configurado. MongoDB não disponível.")
        return False
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
        db = client.get_database("aura_bot")
        print("Conectado ao MongoDB com sucesso.")
        return True
    except Exception as e:
        print(f"Erro ao conectar MongoDB: {e}")
        client = None
        db = None
        return False

def get_db():
    return db

def _garantir_conexao():
    if db is None:
        print("MongoDB: db era None, tentando reconectar...")
        conectar()

def salvar_prova(user_id, user_name, score, total, passed, respostas):
    _garantir_conexao()
    if not db:
        print("MongoDB: Não foi possível salvar prova (sem conexão)")
        return
    try:
        db.provas.insert_one({
            "user_id": str(user_id),
            "user_name": user_name,
            "score": score,
            "total": total,
            "passed": passed,
            "respostas": respostas,
            "date": datetime.now().isoformat()
        })
        print(f"MongoDB: Prova de {user_name} salva ({score}/{total})")
    except Exception as e:
        print(f"Erro ao salvar prova no MongoDB: {e}")

def salvar_ticket(user_id, user_name, tipo, status, atendente=None):
    _garantir_conexao()
    if not db:
        print("MongoDB: Não foi possível salvar ticket (sem conexão)")
        return
    try:
        db.tickets.insert_one({
            "user_id": str(user_id),
            "user_name": user_name,
            "tipo": tipo,
            "status": status,
            "atendente": atendente,
            "data": datetime.now().isoformat()
        })
        print(f"MongoDB: Ticket de {user_name} salvo ({tipo})")
    except Exception as e:
        print(f"Erro ao salvar ticket no MongoDB: {e}")

def atualizar_ticket(user_id, status, atendente=None):
    _garantir_conexao()
    if not db:
        print("MongoDB: Não foi possível atualizar ticket (sem conexão)")
        return
    try:
        update = {"status": status}
        if atendente:
            update["atendente"] = atendente
        db.tickets.update_one(
            {"user_id": str(user_id), "status": "aberto"},
            {"$set": update}
        )
    except Exception as e:
        print(f"Erro ao atualizar ticket no MongoDB: {e}")

def listar_provas(limite=50):
    if not db: return []
    try:
        return list(db.provas.find({}, {"_id": 0}).sort("date", -1).limit(limite))
    except Exception as e:
        print(f"Erro ao listar provas: {e}")
        return []

def listar_tickets(limite=50):
    if not db: return []
    try:
        return list(db.tickets.find({}, {"_id": 0}).sort("data", -1).limit(limite))
    except Exception as e:
        print(f"Erro ao listar tickets: {e}")
        return []

def deletar_prova(user_id, date):
    if not db: return False
    try:
        r = db.provas.delete_one({"user_id": str(user_id), "date": date})
        return r.deleted_count > 0
    except Exception as e:
        print(f"Erro ao deletar prova: {e}")
        return False

def deletar_ticket(user_id, data):
    if not db: return False
    try:
        r = db.tickets.delete_one({"user_id": str(user_id), "data": data})
        return r.deleted_count > 0
    except Exception as e:
        print(f"Erro ao deletar ticket: {e}")
        return False

def stats_dashboard():
    if not db: return {"total_provas": 0, "aprovados": 0, "reprovados": 0, "total_tickets": 0}
    try:
        total = db.provas.count_documents({})
        aprovados = db.provas.count_documents({"passed": True})
        reprovados = db.provas.count_documents({"passed": False})
        tickets = db.tickets.count_documents({})
        return {"total_provas": total, "aprovados": aprovados, "reprovados": reprovados, "total_tickets": tickets}
    except Exception as e:
        print(f"Erro ao buscar stats: {e}")
        return {"total_provas": 0, "aprovados": 0, "reprovados": 0, "total_tickets": 0}