"""
Testa a gravação de config contra as mesmas regras do Mongo, sem subir um
MongoDB.

O bug real: `upsert_guild_config` mandava `created_at` no `$set` (via `doc`) e
também no `$setOnInsert`. O Mongo 4.4 responde "Updating the path 'created_at'
would create a conflict" e a gravação é recusada — o que impedia até a
migração do `.env` de salvar. Aqui um dublê de collection reproduz a regra.
"""
import os
import sys
import unittest.mock as mk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mongo_db  # noqa: E402
from core import settings as st  # noqa: E402

FALHAS = 0


def checa(condicao, msg):
    global FALHAS
    if condicao:
        print("ok  ", msg)
    else:
        FALHAS += 1
        print("FALHA", msg)


class WriteError(Exception):
    pass


class CollectionDuble:
    """
    Repete a regra do Mongo: um caminho não pode estar em `$set` e em
    `$setOnInsert` no mesmo update, mesmo com valores iguais (confirmado contra
    o Mongo 4.4 da VPS). O `$setOnInsert` só entra quando o documento é criado.
    """

    def __init__(self):
        self.docs = {}

    def update_one(self, filtro, update, upsert=False):
        set_ = set(update.get("$set", {}))
        on_ins = set(update.get("$setOnInsert", {}))
        conflito = set_ & on_ins
        if conflito:
            raise WriteError(
                f"Updating the path '{sorted(conflito)[0]}' would create a conflict")

        chave = filtro.get("guild_id")
        doc = self.docs.get(chave)
        if doc is None:
            doc = dict(update.get("$setOnInsert", {}))
            self.docs[chave] = doc
        doc.update(update.get("$set", {}))
        return None


def main() -> int:
    col = CollectionDuble()
    db = mk.MagicMock()
    db.guild_configs = col

    vistas = []

    class Espiador:
        """Guarda o update enviado, para checar a invariante do Mongo."""

        def update_one(self, filtro, update, upsert=False):
            vistas.append((set(update.get("$set", {})), set(update.get("$setOnInsert", {}))))
            return col.update_one(filtro, update, upsert=upsert)

    db.guild_configs = Espiador()

    with mk.patch.object(mongo_db, "db", db), \
         mk.patch.object(mongo_db, "_garantir_conexao", lambda: True):

        cfg = st.default_config("123", "Servidor Teste")
        checa("created_at" in cfg, "default_config traz created_at")

        # Invariante: nenhum caminho nos dois operadores.
        mongo_db.upsert_guild_config("123", cfg, updated_by="teste")
        set_, on_ins = vistas[-1]
        checa(not (set_ & on_ins),
              "created_at nao esta em $set e $setOnInsert "
              f"(em comum: {sorted(set_ & on_ins)})")

        ok = mongo_db.upsert_guild_config("123", cfg, updated_by="teste")
        checa(ok is True, "primeira gravacao da config funciona")
        checa("123" in col.docs, "o documento foi criado")
        salvo = col.docs.get("123", {})
        checa("guild_id" in salvo, "o documento tem guild_id")
        checa(salvo.get("updated_by") == "teste", "gravou quem alterou")
        checa(isinstance(salvo.get("created_at"), float),
              "created_at ficou gravado como numero")

        # Segunda gravação: é update, tem de preservar o created_at original.
        antes = col.docs["123"]["created_at"]
        cfg2 = dict(cfg)
        cfg2["prefix"] = "-ak"
        ok2 = mongo_db.upsert_guild_config("123", cfg2, updated_by="outro")
        checa(ok2 is True, "segunda gravacao funciona")
        checa(col.docs["123"]["prefix"] == "-ak", "mudou o prefixo")
        checa(col.docs["123"]["created_at"] == antes,
              "created_at original nao foi sobrescrito")
        checa(col.docs["123"]["updated_by"] == "outro", "atualizou updated_by")

        # Update numa config que já existe no banco, vinda do painel.
        ok3 = mongo_db.upsert_guild_config("123", {"prefix": "-x", "profile": "coc"},
                                           updated_by="painel")
        checa(ok3 is True, "update parcial (painel) funciona")
        checa(col.docs["123"]["prefix"] == "-x", "prefixo do painel foi salvo")
        checa(col.docs["123"].get("profile") == "coc", "perfil foi salvo")

        # Um doc sem created_at (config vinda de outra versao) tambem tem de gravar.
        ok4 = mongo_db.upsert_guild_config("999", {"prefix": "-z"}, updated_by="velho")
        checa(ok4 is True, "config antiga sem created_at tambem grava")
        checa(isinstance(col.docs["999"].get("created_at"), float),
              "created_at foi preenchido no insert")

    print()
    print("gravacao de config: tudo certo" if FALHAS == 0
          else f"gravacao de config: {FALHAS} falha(s)")
    return 1 if FALHAS else 0


if __name__ == "__main__":
    sys.exit(main())