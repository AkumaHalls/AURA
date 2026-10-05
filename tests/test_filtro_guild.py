"""
Filtro por servidor que enxerga o registro gravado antes do multiserver.

Bug real em produção: `listar_provas`, `listar_tickets`, `listar_infracoes`,
`listar_modlog`, `stats_provas`, `contar_tickets` e `top_infratores`
filravam por `guild_id: <id>` e descartavam o documento sem `guild_id` — o que
existe para tudo que foi gravado antes da config por servidor. O painel
mostrava "nenhuma tentativa registrada" com a prova salva no banco.
"""
import os
import sys
import unittest.mock as mk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FALHAS = 0


def checa(condicao, msg):
    global FALHAS
    if condicao:
        print("ok  ", msg)
    else:
        FALHAS += 1
        print("FALHA", msg)


GID = "1362076878458065037"
OUTRO = "810674050581659668"


class Cursor(list):
    """Encadeia sort/skip/limit como o cursor do pymongo."""

    def sort(self, campo, ordem=1):
        # Campo ausente ordena como null; usa string para não comparar None.
        return Cursor(sorted(
            self,
            key=lambda d: (d.get(campo) is None,
                           "" if d.get(campo) is None else str(d.get(campo))),
            reverse=(ordem < 0)))

    def skip(self, n):
        return Cursor(self[n:])

    def limit(self, n):
        return Cursor(self[:max(0, n)])


class Col:
    """Faz match do Mongo o suficiente para estes filtros."""

    def __init__(self, docs, nome):
        self.docs = docs
        self.nome = nome

    def _match(self, doc, q):
        for chave, cond in (q or {}).items():
            if chave == "$and":
                if not all(self._match(doc, c) for c in cond):
                    return False
            elif chave == "$or":
                if not any(self._match(doc, c) for c in cond):
                    return False
            elif isinstance(cond, dict) and "$exists" in cond:
                if (chave in doc) != bool(cond["$exists"]):
                    return False
            elif isinstance(cond, dict) and "$gte" in cond:
                if (doc.get(chave) is None) or doc.get(chave) < cond["$gte"]:
                    return False
            elif isinstance(cond, dict) and "$regex" in cond:
                alvo = doc.get(chave)
                if not isinstance(alvo, str):
                    return False
                if cond.get("$options") == "i":
                    if cond["$regex"].lower() not in alvo.lower():
                        return False
                elif cond["$regex"] not in alvo:
                    return False
            else:
                if doc.get(chave) != cond:
                    return False
        return True

    def find(self, q=None, proj=None):
        return Cursor([d for d in self.docs if self._match(d, q)])

    def count_documents(self, q=None):
        return len(self.find(q))

    def find_one(self, q=None, proj=None):
        achados = self.find(q)
        return achados[0] if achados else None

    def aggregate(self, pipeline):
        """Só o suficiente para o group/sort/limit do top_infratores."""
        docs = self.find(pipeline[0].get("$match"))
        grupos = {}
        for d in docs:
            chave = (d.get("guild_id"), d.get("user_id"), d.get("user_name"))
            g = grupos.setdefault(chave, {"_id": {"guild_id": chave[0],
                                                  "user_id": chave[1],
                                                  "user_name": chave[2]},
                                          "total": 0, "ultima": None})
            g["total"] += 1
            g["ultima"] = max(g["ultima"] or 0, d.get("ts") or 0)
        saida = sorted(grupos.values(), key=lambda g: -g["total"])
        return saida[: max(1, min(50, pipeline[-1].get("$limit", 50)))]


class BancoFalso:
    def __init__(self):
        self._dados = {
            "provas": [
                {"_id": "p1", "user_id": "1020485181028716688", "user_name": "oziel701",
                 "score": 15, "total": 15, "passed": True, "guild_id": None},   # legado
                {"_id": "p2", "user_id": "200", "user_name": "moderno", "score": 5,
                 "total": 15, "passed": False, "guild_id": GID},               # do B.A.D
                {"_id": "p3", "user_id": "300", "user_name": "outro_servidor",
                 "score": 9, "total": 15, "passed": True, "guild_id": OUTRO},  # de outro
                {"_id": "p4", "user_id": "400", "user_name": "sem_campo_guild",
                 "score": 3, "total": 15, "passed": False},                    # sem o campo
            ],
            "infractions": [
                {"_id": "i1", "user_id": "1", "motivo": "spam", "ts": 10,
                 "guild_id": None},
                {"_id": "i2", "user_id": "2", "motivo": "x", "ts": 20,
                 "guild_id": OUTRO},
            ],
            "modlog": [{"_id": "m1", "acao": "ban", "alvo": "x", "ts": 5,
                        "guild_id": None}],
            "tickets": [
                {"_id": "t1", "user_id": "1", "status": "aberto", "ts": 5,
                 "guild_id": None},
                {"_id": "t2", "user_id": "2", "status": "aberto", "ts": 6,
                 "guild_id": OUTRO},
            ],
        }
        for nome, docs in self._dados.items():
            setattr(self, nome, Col(docs, nome))


def main() -> int:
    import mongo_db
    from core import settings as st

    banco = BancoFalso()
    with mk.patch.multiple(mongo_db, db=banco, _garantir_conexao=lambda: True):

        # --- provas: o caso que o usuario viu ---
        itens = mongo_db.listar_provas(guild_id=GID)
        nomes = sorted(i["user_name"] for i in itens)
        checa("oziel701" in nomes, "a prova antiga (guild_id None) aparece no painel")
        checa("moderno" in nomes, "a prova do proprio servidor aparece")
        checa("outro_servidor" not in nomes, "prova de OUTRO servidor nao aparece")
        checa("sem_campo_guild" in nomes, "prova sem o campo guild_id tambem aparece")

        stats = mongo_db.stats_provas(guild_id=GID)
        checa(stats["total"] == 3, f"stats conta 3 provas do servidor (veio {stats['total']})")
        checa(stats["aprovados"] == 1, f"stats conta 1 aprovada (veio {stats['aprovados']})")
        checa(stats["reprovados"] == 2, f"stats conta 2 reprovadas (veio {stats['reprovados']})")

        # --- busca por texto junto do filtro de servidor ---
        achados = mongo_db.listar_provas(guild_id=GID, busca="oziel")
        checa(len(achados) == 1 and achados[0]["user_name"] == "oziel701",
              "busca por nome acha a prova antiga")
        checa(mongo_db.listar_provas(guild_id=GID, busca="outro") == [],
              "busca nao traz registro de outro servidor")

        # --- filtro de resultado ---
        so_aprov = mongo_db.listar_provas(guild_id=GID, resultado="aprovado")
        checa([i["user_name"] for i in so_aprov] == ["oziel701"],
              "filtro de aprovado pega so a prova legacy aprovada")
        so_reprov = mongo_db.listar_provas(guild_id=GID, resultado="reprovado")
        checa(sorted(i["user_name"] for i in so_reprov) == ["moderno", "sem_campo_guild"],
              "filtro de reprovado pega as duas do servidor")

        # --- sem guild_id: nao pode filtrar nada ---
        checa(len(mongo_db.listar_provas()) == 4, "sem guild_id, lista todas as provas")

        # --- tickets / infrações / modlog / contadores ---
        tks = mongo_db.listar_tickets(guild_id=GID)
        checa(len(tks) == 1 and tks[0]["user_id"] == "1",
              "ticket legado aparece; o de outro servidor nao")
        infs = mongo_db.listar_infracoes(guild_id=GID)
        checa(len(infs) == 1 and infs[0]["user_id"] == "1",
              "infracao legada aparece; a de outro servidor nao")
        mlog = mongo_db.listar_modlog(guild_id=GID)
        checa(len(mlog) == 1, "modlog legado aparece")
        cont = mongo_db.contar_tickets(guild_id=GID)
        checa(cont["aberto"] == 1, f"contar_tickets ve 1 aberto (veio {cont['aberto']})")
        top = mongo_db.top_infratores(guild_id=GID, dias=36500)
        checa(len(top) == 1, "top_infratores ve so a infracao do servidor")

        # --- infracoes com busca (o $or nao pode ser sobrescrito) ---
        ib = mongo_db.listar_infracoes(guild_id=GID, busca="spam")
        checa(len(ib) == 1, "busca em infracoes nao perde o filtro de servidor")

    print()
    print("filtro por servidor: tudo certo" if FALHAS == 0
          else f"filtro por servidor: {FALHAS} falha(s)")
    return 1 if FALHAS else 0


if __name__ == "__main__":
    sys.exit(main())