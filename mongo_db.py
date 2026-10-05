"""
AURA · Camada de dados (MongoDB)
-------------------------------
Um único ponto de acesso ao banco. Todas as coleções e índices são criados
aqui, e a reconexão é automática (o Mongo na VPS reinicia de vez em quando e
o bot não pode cair por causa disso).

Coleções:
    guild_configs    configuração por servidor (ver core/settings.py)
    tickets          tickets de atendimento com transcrição
    ticket_feedback  avaliações de atendimento (1 a 5)
    provas           resultados das provas/seleções
    pending_approvals  seleções aguardando aprovação
    infractions      histórico de punições automáticas e manuais
    modlog           registro de tudo que o AURA puniu
    audit            alterações feitas no painel web
"""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import PyMongoError

from core import runtime

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "aura_bot")

client: Optional[MongoClient] = None
db = None

_lock = threading.RLock()
_indexes_ready = False


# --------------------------------------------------------------------------
# Conexão
# --------------------------------------------------------------------------

def _uri_masked(uri: Optional[str]) -> str:
    if not uri:
        return "None"
    at = uri.find("@")
    if at > 0:
        return "mongodb://***@" + uri[at + 1:]
    return uri[:40] + "..." if len(uri) > 40 else uri


def conectar(verbose: bool = True) -> bool:
    """Conecta (ou reconecta) ao MongoDB. Retorna True em caso de sucesso."""
    global client, db, _indexes_ready

    if not MONGO_URI:
        if verbose:
            print("[MONGO] MONGO_URI não configurado. Painel e módulos de dados desligados.")
        return False

    with _lock:
        if client is not None:
            try:
                client.admin.command("ping")
                return True
            except PyMongoError:
                pass

        try:
            if verbose:
                print(f"[MONGO] Conectando em {_uri_masked(MONGO_URI)} (db={MONGO_DB_NAME})")
            client = MongoClient(
                MONGO_URI,
                serverSelectionTimeoutMS=8000,
                connectTimeoutMS=8000,
                socketTimeoutMS=20000,
                tz_aware=True,
            )
            client.admin.command("ping")
            db = client.get_database(MONGO_DB_NAME)
            _indexes_ready = False
            _criar_indices()
            if verbose:
                print("[MONGO] Conectado com sucesso.")
            runtime.log("INFO", "MongoDB conectado.", "db")
            return True
        except Exception as exc:
            print(f"[MONGO] Falha ao conectar: {exc}")
            runtime.log("ERRO", f"Falha ao conectar no MongoDB: {exc}", "db")
            client = None
            db = None
            return False


def _garantir_conexao() -> bool:
    if db is not None:
        try:
            db.command("ping")
            return True
        except Exception:
            pass
    return conectar(verbose=False)


def get_db():
    return db


def status() -> Dict[str, Any]:
    ok = False
    detalhe = "não configurado"
    if MONGO_URI:
        if db is not None:
            try:
                db.command("ping")
                ok = True
                detalhe = f"conectado · {MONGO_DB_NAME}"
            except Exception as exc:
                detalhe = f"sem resposta ({exc})"
        else:
            detalhe = "aguardando conexão"
    return {
        "ok": ok,
        "uri": _uri_masked(MONGO_URI),
        "db": MONGO_DB_NAME,
        "detalhe": detalhe,
    }


def _criar_indices() -> None:
    global _indexes_ready
    if _indexes_ready or db is None:
        return
    specs = [
        ("guild_configs", [("guild_id", ASCENDING)], {"unique": True}),
        ("tickets", [("guild_id", ASCENDING), ("data", DESCENDING)], {}),
        ("tickets", [("guild_id", ASCENDING), ("user_id", ASCENDING), ("status", ASCENDING)], {}),
        ("tickets", [("ticket_id", ASCENDING)], {}),
        ("ticket_feedback", [("ticket_id", ASCENDING)], {}),
        ("provas", [("guild_id", ASCENDING), ("date", DESCENDING)], {}),
        ("pending_approvals", [("user_id", ASCENDING)], {}),
        ("infractions", [("guild_id", ASCENDING), ("user_id", ASCENDING), ("ts", DESCENDING)], {}),
        ("infractions", [("guild_id", ASCENDING), ("ts", DESCENDING)], {}),
        ("modlog", [("guild_id", ASCENDING), ("ts", DESCENDING)], {}),
        ("audit", [("ts", DESCENDING)], {}),
    ]
    for coll, keys, opts in specs:
        try:
            db[coll].create_index(keys, **opts)
        except Exception as exc:
            runtime.log("AVISO", f"Índice {coll} não criado: {exc}", "db")
    _indexes_ready = True


# --------------------------------------------------------------------------
# guild_configs
# --------------------------------------------------------------------------

def get_guild_config_raw(guild_id) -> Optional[Dict[str, Any]]:
    if not _garantir_conexao() or db is None:
        return None
    try:
        return db.guild_configs.find_one({"guild_id": str(guild_id)}, {"_id": 0})
    except Exception as exc:
        runtime.log("ERRO", f"Falha ao ler config do servidor: {exc}", "db")
        return None


def upsert_guild_config(guild_id, doc: Dict[str, Any], updated_by: str = None) -> bool:
    if not _garantir_conexao() or db is None:
        return False
    doc = dict(doc)
    doc["guild_id"] = str(guild_id)
    doc["updated_at"] = time.time()
    doc["updated_by"] = updated_by
    try:
        db.guild_configs.update_one(
            {"guild_id": str(guild_id)},
            {"$set": doc, "$setOnInsert": {"created_at": time.time()}},
            upsert=True,
        )
        return True
    except Exception as exc:
        runtime.log("ERRO", f"Falha ao salvar config do servidor: {exc}", "db")
        return False


def delete_guild_config(guild_id) -> bool:
    if not _garantir_conexao() or db is None:
        return False
    try:
        db.guild_configs.delete_one({"guild_id": str(guild_id)})
        return True
    except Exception:
        return False


def rename_guild_config(guild_id, name: str, icon: str = None) -> None:
    if not _garantir_conexao() or db is None:
        return
    upd: Dict[str, Any] = {"guild_name": name}
    if icon:
        upd["guild_icon"] = icon
    try:
        db.guild_configs.update_one({"guild_id": str(guild_id)}, {"$set": upd})
    except Exception:
        pass


def list_all_guild_configs() -> List[Dict[str, Any]]:
    if not _garantir_conexao() or db is None:
        return []
    try:
        return list(db.guild_configs.find({}, {"_id": 0}).sort("guild_name", ASCENDING))
    except Exception:
        return []


# --------------------------------------------------------------------------
# Tickets
# --------------------------------------------------------------------------

def salvar_ticket(
    user_id,
    user_name: str,
    tipo: str,
    status: str = "aberto",
    atendente: str = None,
    *,
    guild_id=None,
    guild_name: str = None,
    ticket_id: str = None,
    channel_name: str = None,
    categoria_key: str = None,
    avatar: str = None,
) -> Optional[str]:
    if not _garantir_conexao() or db is None:
        return None
    doc = {
        "user_id": str(user_id),
        "user_name": user_name,
        "tipo": tipo,
        "status": status,
        "atendente": atendente,
        "guild_id": str(guild_id) if guild_id else None,
        "guild_name": guild_name,
        "ticket_id": str(ticket_id) if ticket_id else None,
        "channel_name": channel_name,
        "categoria_key": categoria_key,
        "avatar": avatar,
        "data": datetime.now().isoformat(),
        "ts": time.time(),
    }
    try:
        res = db.tickets.insert_one(doc)
        return str(res.inserted_id)
    except Exception as exc:
        runtime.log("ERRO", f"Falha ao salvar ticket: {exc}", "db")
        return None


def atualizar_ticket_status(ticket_id, status: str, atendente: str = None,
                            motivo: str = None) -> bool:
    """Atualiza por ticket_id (id interno do Mongo) — não depende de user_id/data."""
    if not _garantir_conexao() or db is None:
        return False
    upd: Dict[str, Any] = {"status": status}
    if atendente:
        upd["atendente"] = atendente
    if motivo:
        upd["motivo_encerramento"] = motivo
    if status == "fechado":
        upd["fechado_em"] = time.time()
    try:
        r = db.tickets.update_one({"_id": _oid(ticket_id)}, {"$set": upd})
        return r.matched_count > 0
    except Exception as exc:
        runtime.log("ERRO", f"Falha ao atualizar ticket: {exc}", "db")
        return False


def _oid(value):
    from bson import ObjectId
    if isinstance(value, ObjectId):
        return value
    try:
        return ObjectId(str(value))
    except Exception:
        return None


def _texto(valor, padrao: str = "") -> str:
    """
    Converte qualquer coisa em string guardavel no Mongo. Sem isso, passar um
    objeto do discord.py (Member, Guild) para um campo quebra o insert.
    """
    if valor is None:
        return padrao
    if isinstance(valor, str):
        return valor[:500]
    return str(valor)[:500]


def get_ticket(ticket_id) -> Optional[Dict[str, Any]]:
    if not _garantir_conexao() or db is None:
        return None
    try:
        doc = db.tickets.find_one({"_id": _oid(ticket_id)})
        if doc:
            doc["_id"] = str(doc["_id"])
        return doc
    except Exception:
        return None


def salvar_transcricao(ticket_id, transcript: str, atendente: str = None,
                       mensagem_count: int = 0) -> bool:
    if not _garantir_conexao() or db is None:
        return False
    upd: Dict[str, Any] = {
        "transcript": transcript[:200_000],
        "mensagem_count": mensagem_count,
        "status": "fechado",
        "fechado_em": time.time(),
    }
    if atendente:
        upd["atendente"] = atendente
    try:
        r = db.tickets.update_one({"_id": _oid(ticket_id)}, {"$set": upd})
        return r.matched_count > 0
    except Exception as exc:
        runtime.log("ERRO", f"Falha ao salvar transcrição: {exc}", "db")
        return False


def listar_tickets(
    guild_id=None,
    status: str = None,
    tipo: str = None,
    busca: str = None,
    limite: int = 200,
    offset: int = 0,
    sort_desc: bool = True,
) -> List[Dict[str, Any]]:
    if not _garantir_conexao() or db is None:
        return []
    q: Dict[str, Any] = {}
    if guild_id:
        q["guild_id"] = str(guild_id)
    if status and status != "todos":
        q["status"] = status
    if tipo and tipo != "todos":
        q["tipo"] = tipo
    if busca:
        rx = {"$regex": str(busca).strip()[:60], "$options": "i"}
        q["$or"] = [{"user_name": rx}, {"user_id": rx}, {"tipo": rx}, {"atendente": rx}]
    try:
        cur = db.tickets.find(q, {"_id": 1, "transcript": 0}).sort(
            "ts", DESCENDING if sort_desc else ASCENDING
        ).skip(max(0, offset)).limit(max(1, min(1000, limite)))
        out = []
        for doc in cur:
            doc["_id"] = str(doc["_id"])
            out.append(doc)
        return out
    except Exception as exc:
        runtime.log("ERRO", f"Falha ao listar tickets: {exc}", "db")
        return []


def contar_tickets(guild_id=None, status: str = None) -> Dict[str, int]:
    out = {"aberto": 0, "atendendo": 0, "fechado": 0, "total": 0}
    if not _garantir_conexao() or db is None:
        return out
    base: Dict[str, Any] = {"guild_id": str(guild_id)} if guild_id else {}
    try:
        for st in ("aberto", "atendendo", "fechado"):
            out[st] = db.tickets.count_documents({**base, "status": st})
        out["total"] = db.tickets.count_documents(base)
    except Exception:
        pass
    return out


def deletar_ticket(ticket_id) -> bool:
    if not _garantir_conexao() or db is None:
        return False
    try:
        r = db.tickets.delete_one({"_id": _oid(ticket_id)})
        db.ticket_feedback.delete_many({"ticket_id": str(ticket_id)})
        return r.deleted_count > 0
    except Exception:
        return False


def ticket_aberto_do_usuario(guild_id, user_id) -> Optional[Dict[str, Any]]:
    if not _garantir_conexao() or db is None:
        return None
    try:
        doc = db.tickets.find_one(
            {"guild_id": str(guild_id), "user_id": str(user_id), "status": {"$in": ["aberto", "atendendo"]}},
            {"_id": 1, "transcript": 0},
        )
        if doc:
            doc["_id"] = str(doc["_id"])
        return doc
    except Exception:
        return None


def tickets_abertos_por_usuario(guild_id, user_id) -> int:
    if not _garantir_conexao() or db is None:
        return 0
    try:
        return db.tickets.count_documents({
            "guild_id": str(guild_id),
            "user_id": str(user_id),
            "status": {"$in": ["aberto", "atendendo"]},
        })
    except Exception:
        return 0


def salvar_feedback(ticket_id, user_id, nota: int, comentario: str = None) -> bool:
    if not _garantir_conexao() or db is None:
        return False
    try:
        db.ticket_feedback.update_one(
            {"ticket_id": str(ticket_id)},
            {"$set": {
                "ticket_id": str(ticket_id),
                "user_id": str(user_id),
                "nota": max(1, min(5, int(nota))),
                "comentario": (comentario or "")[:1000],
                "ts": time.time(),
            }},
            upsert=True,
        )
        return True
    except Exception:
        return False


def media_feedback(guild_id=None) -> Dict[str, Any]:
    out = {"media": 0.0, "total": 0, "distribuicao": {}}
    if not _garantir_conexao() or db is None:
        return out
    q: Dict[str, Any] = {}
    if guild_id:
        try:
            q = {"ticket_id": {"$in": db.tickets.find(
                {"guild_id": str(guild_id)}, {"_id": 1, "ticket_id": 1}).distinct("ticket_id")}}
        except Exception:
            q = {}
    try:
        cur = db.ticket_feedback.find(q, {"nota": 1})
        notas = [d.get("nota", 0) for d in cur if d.get("nota")]
        if notas:
            out["media"] = round(sum(notas) / len(notas), 2)
            out["total"] = len(notas)
            for n in range(1, 6):
                out["distribuicao"][n] = notas.count(n)
    except Exception:
        pass
    return out


# --------------------------------------------------------------------------
# Provas
# --------------------------------------------------------------------------

def salvar_prova(user_id, user_name, score, total, passed, respostas,
                 *, guild_id=None, guild_name=None, cooldowns=None) -> bool:
    if not _garantir_conexao() or db is None:
        return False
    try:
        db.provas.insert_one({
            "user_id": str(user_id),
            "user_name": user_name,
            "score": score,
            "total": total,
            "passed": bool(passed),
            "respostas": respostas,
            "guild_id": str(guild_id) if guild_id else None,
            "guild_name": guild_name,
            "date": datetime.now().isoformat(),
            "ts": time.time(),
        })
        return True
    except Exception as exc:
        runtime.log("ERRO", f"Falha ao salvar prova: {exc}", "db")
        return False


def listar_provas(guild_id=None, resultado: str = None, busca: str = None,
                  limite: int = 200, offset: int = 0) -> List[Dict[str, Any]]:
    if not _garantir_conexao() or db is None:
        return []
    q: Dict[str, Any] = {}
    if guild_id:
        q["guild_id"] = str(guild_id)
    if resultado == "aprovado":
        q["passed"] = True
    elif resultado == "reprovado":
        q["passed"] = False
    if busca:
        rx = {"$regex": str(busca).strip()[:60], "$options": "i"}
        q["$or"] = [{"user_name": rx}, {"user_id": rx}]
    try:
        return list(db.provas.find(q, {"_id": 1, "respostas": 0})
                    .sort("ts", DESCENDING).skip(max(0, offset)).limit(max(1, min(1000, limite))))
    except Exception:
        return []


def get_prova(prova_id) -> Optional[Dict[str, Any]]:
    if not _garantir_conexao() or db is None:
        return None
    try:
        doc = db.provas.find_one({"_id": _oid(prova_id)})
        if doc:
            doc["_id"] = str(doc["_id"])
        return doc
    except Exception:
        return None


def deletar_prova(prova_id) -> bool:
    if not _garantir_conexao() or db is None:
        return False
    try:
        return db.provas.delete_one({"_id": _oid(prova_id)}).deleted_count > 0
    except Exception:
        return False


def stats_provas(guild_id=None) -> Dict[str, Any]:
    out = {"total": 0, "aprovados": 0, "reprovados": 0, "taxa": 0.0, "media": 0.0}
    if not _garantir_conexao() or db is None:
        return out
    base: Dict[str, Any] = {"guild_id": str(guild_id)} if guild_id else {}
    try:
        out["total"] = db.provas.count_documents(base)
        out["aprovados"] = db.provas.count_documents({**base, "passed": True})
        out["reprovados"] = db.provas.count_documents({**base, "passed": False})
        if out["total"]:
            out["taxa"] = round(out["aprovados"] / out["total"] * 100, 1)
        docs = list(db.provas.find(base, {"score": 1, "total": 1}))
        notas = [(d.get("score") or 0) / d["total"] * 100 for d in docs if d.get("total")]
        if notas:
            out["media"] = round(sum(notas) / len(notas), 1)
    except Exception:
        pass
    return out


# --------------------------------------------------------------------------
# Cooldowns / aprovações pendentes
# --------------------------------------------------------------------------

def salvar_aprovacao_pendente(user_id, user_name, questoes, config, status="aguardando_dono",
                              *, guild_id=None) -> bool:
    if not _garantir_conexao() or db is None:
        return False
    try:
        db.pending_approvals.update_one(
            {"user_id": str(user_id), "guild_id": str(guild_id) if guild_id else None},
            {"$set": {
                "user_id": str(user_id),
                "user_name": user_name,
                "questoes": questoes,
                "config": config,
                "status": status,
                "guild_id": str(guild_id) if guild_id else None,
                "data_solicitacao": datetime.now().isoformat(),
            }},
            upsert=True,
        )
        return True
    except Exception as exc:
        runtime.log("ERRO", f"Falha ao salvar aprovação pendente: {exc}", "db")
        return False


def get_aprovacao_pendente(user_id, guild_id=None):
    if not _garantir_conexao() or db is None:
        return None
    try:
        return db.pending_approvals.find_one(
            {"user_id": str(user_id), "guild_id": str(guild_id) if guild_id else None},
            {"_id": 0},
        )
    except Exception:
        return None


def deletar_aprovacao_pendente(user_id, guild_id=None) -> bool:
    if not _garantir_conexao() or db is None:
        return False
    try:
        db.pending_approvals.delete_one(
            {"user_id": str(user_id), "guild_id": str(guild_id) if guild_id else None}
        )
        return True
    except Exception:
        return False


def atualizar_status_aprovacao(user_id, status: str, guild_id=None) -> bool:
    if not _garantir_conexao() or db is None:
        return False
    try:
        db.pending_approvals.update_one(
            {"user_id": str(user_id), "guild_id": str(guild_id) if guild_id else None},
            {"$set": {"status": status}},
        )
        return True
    except Exception:
        return False


def listar_aprovacoes_pendentes(guild_id=None, incluir_questoes=False):
    """
    Lista as solicitações que ficaram esperando.

    Por padrão não traz as questões (o painel só quer contar e listar). Com
    `incluir_questoes=True` volta o documento inteiro, que é o que a retomada
    após restart precisa para reabrir a prova.
    """
    if not _garantir_conexao() or db is None:
        return []
    q = {"guild_id": str(guild_id)} if guild_id else {}
    proj = {"_id": 0} if incluir_questoes else {"_id": 0, "questoes": 0}
    try:
        return list(db.pending_approvals.find(q, proj))
    except Exception:
        return []


def set_cooldown(user_id: str, guild_id: str, dias: int) -> None:
    if not _garantir_conexao() or db is None:
        return
    try:
        db.cooldowns.update_one(
            {"user_id": str(user_id), "guild_id": str(guild_id)},
            {"$set": {"ate": datetime.now() + timedelta(days=max(0, dias)), "ts": time.time()}},
            upsert=True,
        )
    except Exception:
        pass


def get_cooldown(user_id: str, guild_id: str) -> Optional[datetime]:
    if not _garantir_conexao() or db is None:
        return None
    try:
        doc = db.cooldowns.find_one({"user_id": str(user_id), "guild_id": str(guild_id)})
        return doc.get("ate") if doc else None
    except Exception:
        return None


def limpar_cooldowns_expirados() -> int:
    if not _garantir_conexao() or db is None:
        return 0
    try:
        return db.cooldowns.delete_many({"ate": {"$lt": datetime.now()}}).deleted_count
    except Exception:
        return 0


# --------------------------------------------------------------------------
# Infrações (moderação)
# --------------------------------------------------------------------------

def registrar_infracao(guild_id, user_id, user_name, guild_name, motivo: str,
                       filtro: str, severidade: str, punicao: str,
                       mod_id: str = None, mod_name: str = None,
                       evidencia: str = None, extras: Dict[str, Any] = None) -> Optional[str]:
    if not _garantir_conexao() or db is None:
        return None
    doc = {
        "guild_id": str(guild_id),
        "guild_name": guild_name,
        "user_id": str(user_id),
        "user_name": _texto(user_name),
        "motivo": (motivo or "")[:500],
        "filtro": filtro,
        "severidade": severidade,
        "punicao": punicao,
        "mod_id": str(mod_id) if mod_id else None,
        "mod_name": _texto(mod_name),
        "evidencia": (evidencia or "")[:1000],
        "ts": time.time(),
        "date": datetime.now().isoformat(),
    }
    if extras:
        doc.update(extras)
    try:
        res = db.infractions.insert_one(doc)
        return str(res.inserted_id)
    except Exception as exc:
        runtime.log("ERRO", f"Falha ao registrar infração: {exc}", "db")
        return None


def contar_infracoes(guild_id, user_id, desde_dias: int = None) -> int:
    if not _garantir_conexao() or db is None:
        return 0
    q: Dict[str, Any] = {"guild_id": str(guild_id), "user_id": str(user_id)}
    if desde_dias:
        q["ts"] = {"$gte": time.time() - desde_dias * 86400}
    try:
        return db.infractions.count_documents(q)
    except Exception:
        return 0


def historico_infracoes(guild_id, user_id: str = None, limite: int = 50) -> List[Dict[str, Any]]:
    if not _garantir_conexao() or db is None:
        return []
    q: Dict[str, Any] = {"guild_id": str(guild_id)}
    if user_id:
        q["user_id"] = str(user_id)
    try:
        cur = db.infractions.find(q).sort("ts", DESCENDING).limit(max(1, min(500, limite)))
        out = []
        for d in cur:
            d["_id"] = str(d["_id"])
            out.append(d)
        return out
    except Exception:
        return []


def listar_infracoes(guild_id=None, user_id: str = None, busca: str = None,
                     limite: int = 200, offset: int = 0) -> List[Dict[str, Any]]:
    if not _garantir_conexao() or db is None:
        return []
    q: Dict[str, Any] = {}
    if guild_id:
        q["guild_id"] = str(guild_id)
    if user_id:
        q["user_id"] = str(user_id)
    if busca:
        rx = {"$regex": str(busca).strip()[:60], "$options": "i"}
        q["$or"] = [{"user_name": rx}, {"user_id": rx}, {"motivo": rx}]
    try:
        cur = db.infractions.find(q).sort("ts", DESCENDING).skip(max(0, offset)).limit(
            max(1, min(1000, limite)))
        out = []
        for d in cur:
            d["_id"] = str(d["_id"])
            out.append(d)
        return out
    except Exception:
        return []


def apagar_infracoes(guild_id, user_id: str) -> int:
    if not _garantir_conexao() or db is None:
        return 0
    try:
        return db.infractions.delete_many({"guild_id": str(guild_id), "user_id": str(user_id)}).deleted_count
    except Exception:
        return 0


def top_infratores(guild_id=None, limite: int = 10, dias: int = 30) -> List[Dict[str, Any]]:
    if not _garantir_conexao() or db is None:
        return []
    match: Dict[str, Any] = {"ts": {"$gte": time.time() - dias * 86400}}
    if guild_id:
        match["guild_id"] = str(guild_id)
    try:
        return list(
            db.infractions.aggregate([
                {"$match": match},
                {"$group": {
                    "_id": {"guild_id": "$guild_id", "user_id": "$user_id", "user_name": "$user_name"},
                    "total": {"$sum": 1},
                    "ultima": {"$max": "$ts"},
                }},
                {"$sort": {"total": -1}},
                {"$limit": max(1, min(50, limite))},
            ])
        )
    except Exception:
        return []


def stats_moderacao(guild_id=None, dias: int = 30) -> Dict[str, Any]:
    out = {"total": 0, "por_filtro": {}, "por_punicao": {}, "periodo_dias": dias}
    if not _garantir_conexao() or db is None:
        return out
    match: Dict[str, Any] = {"ts": {"$gte": time.time() - dias * 86400}}
    if guild_id:
        match["guild_id"] = str(guild_id)
    try:
        out["total"] = db.infractions.count_documents(match)
        for campo, chave in (("filtro", "por_filtro"), ("punicao", "por_punicao")):
            pipeline = [
                {"$match": match},
                {"$group": {"_id": f"${campo}", "n": {"$sum": 1}}},
                {"$sort": {"n": -1}},
            ]
            for r in db.infractions.aggregate(pipeline):
                out[chave][r["_id"] or "—"] = r["n"]
    except Exception:
        pass
    return out


# --------------------------------------------------------------------------
# modlog
# --------------------------------------------------------------------------

def registrar_modlog(guild_id, guild_name, acao: str, alvo: str = None,
                     alvo_id: str = None, mod_id: str = None, mod_name: str = None,
                     motivo: str = None, extras: Dict[str, Any] = None) -> Optional[str]:
    if not _garantir_conexao() or db is None:
        return None
    doc = {
        "guild_id": str(guild_id),
        "guild_name": guild_name,
        "acao": acao,
        "alvo": alvo,
        "alvo_id": str(alvo_id) if alvo_id else None,
        "mod_id": str(mod_id) if mod_id else None,
        "mod_name": mod_name,
        "motivo": (motivo or "")[:500],
        "ts": time.time(),
        "date": datetime.now().isoformat(),
    }
    if extras:
        doc.update(extras)
    try:
        return str(db.modlog.insert_one(doc).inserted_id)
    except Exception:
        return None


def listar_modlog(guild_id=None, acao: str = None, busca: str = None,
                  limite: int = 200, offset: int = 0) -> List[Dict[str, Any]]:
    if not _garantir_conexao() or db is None:
        return []
    q: Dict[str, Any] = {}
    if guild_id:
        q["guild_id"] = str(guild_id)
    if acao and acao != "todos":
        q["acao"] = acao
    if busca:
        rx = {"$regex": str(busca).strip()[:60], "$options": "i"}
        q["$or"] = [{"alvo": rx}, {"alvo_id": rx}, {"motivo": rx}, {"mod_name": rx}]
    try:
        cur = db.modlog.find(q).sort("ts", DESCENDING).skip(max(0, offset)).limit(
            max(1, min(1000, limite)))
        out = []
        for d in cur:
            d["_id"] = str(d["_id"])
            out.append(d)
        return out
    except Exception:
        return []


# --------------------------------------------------------------------------
# Auditoria do painel
# --------------------------------------------------------------------------

def registrar_auditoria(guild_id, guild_name, acao: str, modulo: str,
                        autor: str = "painel", antes=None, depois=None) -> Optional[str]:
    if not _garantir_conexao() or db is None:
        return None
    doc = {
        "guild_id": str(guild_id) if guild_id else None,
        "guild_name": guild_name,
        "acao": acao,
        "modulo": modulo,
        "autor": _texto(autor),
        "antes": antes,
        "depois": depois,
        "ts": time.time(),
        "date": datetime.now().isoformat(),
    }
    try:
        return str(db.audit.insert_one(doc).inserted_id)
    except Exception:
        return None


def listar_auditoria(guild_id=None, limite: int = 100) -> List[Dict[str, Any]]:
    if not _garantir_conexao() or db is None:
        return []
    q: Dict[str, Any] = {"guild_id": str(guild_id)} if guild_id else {}
    try:
        cur = db.audit.find(q, {"antes": 0, "depois": 0}).sort("ts", DESCENDING).limit(
            max(1, min(500, limite)))
        out = []
        for d in cur:
            d["_id"] = str(d["_id"])
            out.append(d)
        return out
    except Exception:
        return []


# --------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------

def stats_dashboard(guild_id=None) -> Dict[str, Any]:
    """Números do topo do painel. Mantido compatível com o painel antigo."""
    base = {
        "total_provas": 0, "aprovados": 0, "reprovados": 0, "total_tickets": 0,
        "tickets_abertos": 0, "tickets_atendendo": 0, "tickets_fechados": 0,
        "total_infracoes": 0, "servidores": 0, "media_feedback": 0.0,
    }
    if not _garantir_conexao() or db is None:
        return base

    prov = stats_provas(guild_id)
    tks = contar_tickets(guild_id)
    mod = stats_moderacao(guild_id)
    fb = media_feedback(guild_id)

    base.update({
        "total_provas": prov["total"],
        "aprovados": prov["aprovados"],
        "reprovados": prov["reprovados"],
        "total_tickets": tks["total"],
        "tickets_abertos": tks["aberto"],
        "tickets_atendendo": tks["atendendo"],
        "tickets_fechados": tks["fechado"],
        "total_infracoes": mod["total"],
        "media_feedback": fb["media"],
    })
    try:
        base["servidores"] = (
            db.guild_configs.count_documents({"guild_id": str(guild_id)})
            if guild_id else db.guild_configs.count_documents({})
        )
    except Exception:
        pass
    return base


def series_dias(guild_id=None, dias: int = 14) -> Dict[str, List[int]]:
    """Série diária de tickets e infrações para os gráficos do painel."""
    out = {"datas": [], "tickets": [], "infracoes": [], "provas": []}
    if not _garantir_conexao() or db is None:
        return out

    agora = datetime.now()
    for i in range(dias - 1, -1, -1):
        out["datas"].append((agora - timedelta(days=i)).strftime("%d/%m"))

    def serie(coll: str) -> List[int]:
        match: Dict[str, Any] = {
            "ts": {"$gte": (agora - timedelta(days=dias)).timestamp()}
        }
        if guild_id:
            match["guild_id"] = str(guild_id)
        try:
            pipeline = [
                {"$match": match},
                {"$group": {
                    "_id": {"$dateToString": {"format": "%d/%m", "date": {"$toDate": "$ts"}}},
                    "n": {"$sum": 1},
                }},
            ]
            mapa = {r["_id"]: r["n"] for r in db[coll].aggregate(pipeline)}
            return [mapa.get(d, 0) for d in out["datas"]]
        except Exception:
            return [0] * dias

    out["tickets"] = serie("tickets")
    out["infracoes"] = serie("infractions")
    out["provas"] = serie("provas")
    return out


# --------------------------------------------------------------------------
# Migração do modelo antigo (uma única config no .env)
# --------------------------------------------------------------------------

def _ids_do_env() -> List[str]:
    """IDs de servidor candidatos vindos do .env antigo (ordem de prioridade)."""
    achados: List[str] = []
    for nome in ("DISCORD_GUILD_ID_LEGADO", "TEST_GUILD_ID",
                 "id_servidor_tribunal", "GUILD_ID"):
        v = os.getenv(nome)
        if v and v.strip().isdigit() and v.strip() not in achados:
            achados.append(v.strip())
    return achados


def _nome_do_env() -> Dict[str, str]:
    """Nome legível dos servidores configurados no .env antigo."""
    nomes: Dict[str, str] = {}
    gid = next((i for i in _ids_do_env()), None)
    if gid:
        nomes[gid] = os.getenv("DISCORD_GUILD_NAME") or f"Servidor {gid}"
    return nomes


def migrar_config_antiga(forcar: bool = False) -> List[str]:
    """
    Importa os IDs do .env antigo (modelo de servidor único) para a config
    multiserver, para o AURA não começar do zero.

    Serveres candidatos, em ordem:
        1. DISCORD_GUILD_ID_LEGADO / TEST_GUILD_ID / id_servidor_tribunal
        2. o primeiro servidor onde o bot está

    Não sobrescreve uma config já existente a menos que forcar=True.
    """
    from core import runtime as rt
    from core import settings as st

    avisos: List[str] = []
    candidatos = _ids_do_env()
    guilds_vinculados = rt.list_guild_summaries()
    por_id = {str(g["id"]): g for g in guilds_vinculados}

    if candidatos:
        alvo_id = candidatos[0]
        alvo = por_id.get(alvo_id) or {
            "id": alvo_id,
            "name": _nome_do_env().get(alvo_id, f"Servidor {alvo_id}"),
            "icon": None,
        }
        if guilds_vinculados and alvo_id not in por_id:
            avisos.append(
                f"Atenção: o ID {alvo_id} do .env não está entre os servidores do bot. "
                f"O AURA está em: {', '.join(g['name'] for g in guilds_vinculados)}."
            )
    elif guilds_vinculados:
        alvo = guilds_vinculados[0]
        avisos.append(f"Nenhum ID de servidor no .env; usando '{alvo['name']}'.")
    else:
        return [
            "Não encontrei onde importar: o bot ainda não conectou e o .env não tem "
            "TEST_GUILD_ID / id_servidor_tribunal."
        ]

    if get_guild_config_raw(alvo["id"]) and not forcar:
        return [f"'{alvo['name']}' já tem configuração — nada foi sobrescrito."]

    def env_int(nome, atual=None):
        v = os.getenv(nome)
        try:
            return int(v) if v and str(v).strip() else atual
        except ValueError:
            return atual

    def env_str(nome, padrao=None):
        return os.getenv(nome) or padrao

    cfg = st.default_config(alvo["id"], alvo["name"], alvo.get("icon"))

    # ---- Tickets ----
    tk = cfg["tickets"]
    tk["support_channel_id"] = env_int("id_canal_suporte")
    tk["staff_role_id"] = env_int("id_cargo_atendente")
    tk["log_channel_id"] = env_int("id_canal_logs_bh") or env_int("CANAL_REGISTRO_ID")
    tk["transcript_channel_id"] = env_int("ID_CANAL_TRANSCRICOES") or env_int("id_canal_logs_tri")
    tk["categories"] = st.normalize_categories(st.PRESET_TICKET_CATEGORIES["coc"])
    if tk["support_channel_id"] or tk["staff_role_id"]:
        tk["enabled"] = True
        cfg["modules"]["tickets"] = True

    # ---- Autorole / registro ----
    ar = cfg["autorole"]
    ar["channel_id"] = env_int("REGISTRATION_CHANNEL_ID") or env_int("CANAL_REGISTRO_ID")
    ar["give_role_id"] = env_int("CARGO_MEMBRO_ID")
    ar["deny_role_id"] = env_int("CARGO_BANIDO_ID")
    ar["log_channel_id"] = env_int("CANAL_REGISTRO_ID") or env_int("LOG_CHANNEL_ID")
    ar["keyword"] = ar.get("keyword") or ""
    if ar["channel_id"] and ar["give_role_id"]:
        ar["enabled"] = True
        cfg["modules"]["autorole"] = True

    # ---- Moderação: herda os canais de registro que já existiam ----
    md = cfg["moderation"]
    md["log_channel_id"] = env_int("CANAL_REGISTRO_ID") or env_int("LOG_CHANNEL_ID")
    md["punish_channel_id"] = env_int("CANAL_REGISTRO_ID") or env_int("LOG_CHANNEL_ID")
    md["ignored_channels"] = [i for i in [
        env_int("id_canal_suporte"), env_int("ID_CANAL_TRANSCRICOES"),
        env_int("id_canal_logs_tri"),
    ] if i]
    md["ignored_roles"] = [i for i in [
        env_int("id_cargo_atendente"), env_int("OWNER_ID"), env_int("DONO_ID"),
    ] if i]
    md["escalation"]["exempt_roles"] = [i for i in [
        env_int("id_cargo_atendente"), env_int("OWNER_ID"), env_int("DONO_ID"),
    ] if i]

    # ---- Logs ----
    canal_logs = env_int("CANAL_REGISTRO_ID") or env_int("LOG_CHANNEL_ID")
    cfg["logs"]["mod_channel_id"] = canal_logs
    cfg["logs"]["join_channel_id"] = env_int("REGISTRATION_CHANNEL_ID") or canal_logs
    cfg["logs"]["leave_channel_id"] = env_int("REGISTRATION_CHANNEL_ID") or canal_logs
    cfg["logs"]["enabled"] = bool(canal_logs)
    cfg["modules"]["logs"] = cfg["logs"]["enabled"]

    # ---- Perfil de jogo (Clash of Clans) ----
    coc = cfg["games"]["coc"]
    coc["clan_tag"] = (env_str("CLAN_TAG") or "").lstrip("#")
    coc["registration_channel_id"] = env_int("REGISTRATION_CHANNEL_ID") or env_int("CANAL_REGISTRO_ID")
    coc["log_channel_id"] = env_int("LOG_CHANNEL_ID")
    coc["approval_channel_id"] = env_int("APPROVAL_LOG_CHANNEL_ID")
    coc["roles"] = {
        "member": env_int("COC_MEMBER_ROLE_ID"),
        "elder": env_int("COC_ELDER_ROLE_ID"),
        "coleader": env_int("COC_COLEADER_ROLE_ID"),
    }
    coc["kick_message"] = env_str(
        "KICK_MESSAGE",
        "Você foi removido do servidor por não fazer mais parte do clã.",
    )
    if coc["clan_tag"]:
        coc["enabled"] = True
        cfg["modules"]["games"] = True

    dono = env_int("OWNER_ID") or env_int("DONO_ID")
    if dono:
        cfg["owner_ids"] = [dono]

    cfg["profile"] = "coc" if coc["enabled"] else "generico"
    cfg["migrated_from_env"] = True
    cfg["updated_by"] = "migracao-do-env"

    if upsert_guild_config(alvo["id"], cfg, updated_by="migracao"):
        # O painel ou um comando podem ter pedido a config antes desta
        # migração, deixando o padrão no cache. Descarta para a próxima leitura
        # ir no banco e ver o que acabou de ser importado.
        st.invalidate(str(alvo["id"]))
        avisos.append(f"Configuração do .env importada para '{alvo['name']}' ({alvo['id']}).")
    else:
        avisos.append("Não foi possível salvar a configuração migrada.")

    # As secrets do .env não fazem mais falta: não as copia para o banco.
    # Só fica o registro de quais variáveis antigas foram usadas.
    try:
        db.migracoes.insert_one({
            "guild_id": str(alvo["id"]),
            "guild_name": alvo["name"],
            "origem": "env",
            "variaveis_usadas": sorted([
                n for n in (
                    "TEST_GUILD_ID", "id_servidor_tribunal", "id_canal_suporte",
                    "id_cargo_atendente", "ID_CANAL_TRANSCRICOES", "id_canal_logs_tri",
                    "CANAL_REGISTRO_ID", "REGISTRATION_CHANNEL_ID", "LOG_CHANNEL_ID",
                    "APPROVAL_LOG_CHANNEL_ID", "CARGO_MEMBRO_ID", "CARGO_BANIDO_ID",
                    "COC_MEMBER_ROLE_ID", "COC_ELDER_ROLE_ID", "COC_COLEADER_ROLE_ID",
                    "CLAN_TAG", "KICK_MESSAGE", "OWNER_ID", "DONO_ID",
                ) if os.getenv(n)
            ]),
            "ts": time.time(),
        })
    except Exception:
        pass

    # Associa registros antigos (gravados sem guild_id) a este servidor.
    try:
        r = db.tickets.update_many(
            {"guild_id": None},
            {"$set": {"guild_id": str(alvo["id"]), "guild_name": alvo["name"]}},
        )
        if r.modified_count:
            avisos.append(f"{r.modified_count} ticket(s) antigo(s) associado(s) a este servidor.")
    except Exception:
        pass

    return avisos
