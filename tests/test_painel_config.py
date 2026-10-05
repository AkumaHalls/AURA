"""
Testa que o painel NÃO perde a config do servidor.

Bug real, visto em produção: `_salvar_cfg` invalida o cache a cada gravação, e
`_servidores()` lia a config só do cache. Então, logo depois de salvar, a
página seguinte não achava nada e caía em `default_config` — que, ao ser
salvo de novo, gravava o default por cima da config real, zerando perfil,
owner_ids, módulos e as seções de cada módulo.

Aqui o painel roda com o Flask test client e um MongoDB falso em memória.
"""
import asyncio
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


class Col:
    """Collection em memória, com o upsert por $set que o mongo_db usa."""

    def __init__(self, docs):
        self.docs = docs

    def update_one(self, filtro, update, upsert=False):
        chave = filtro.get("guild_id")
        doc = self.docs.setdefault(chave, {})
        doc.update(update.get("$setOnInsert", {}))
        doc.update(update.get("$set", {}))

    def find_one(self, filtro, proj=None):
        d = self.docs.get(filtro.get("guild_id"))
        return dict(d) if d is not None else None

    def count_documents(self, filtro=None):
        return len(self.docs)


class MongoFalso:
    def __init__(self):
        self.docs = {}
        self.guild_configs = Col(self.docs)
        self.audit = mk.MagicMock()
        self.migracoes = mk.MagicMock()


def main() -> int:
    mongo = MongoFalso()
    mongo_doc = mk.MagicMock()
    mongo_doc.db = mongo
    mongo_doc.guild_configs = mongo.guild_configs
    mongo_doc.registrar_auditoria = lambda *a, **k: None
    mongo_doc.listar_auditoria = lambda *a, **k: []

    import mongo_db
    import web_panel as wp
    from core import settings as st

    resumo = [{"id": GID, "name": "BAD - Bravos ANJOS DEFENSORES", "icon": None,
               "members": 42}]

    def ambiente():
        return mk.patch.multiple(
            mongo_db, db=mongo_doc, _garantir_conexao=lambda: True,
        ), mk.patch.multiple(
            wp.runtime, list_guild_summaries=lambda: resumo, get_client=lambda: None,
            run_coro=lambda coro, **k: _executa(coro),
        )

    # `get_config_cached` e `save_config` reais rodam aqui: só o MongoDB é
    # falso. Assim o teste exercita o caminho de verdade, inclusive o
    # `invalidate` do cache que causava o problema.
    def _executa(coro):
        # O painel chama `runtime.run_coro`; aqui rodamos a corrotina de verdade
        # para o `save_config` realmente gravar (e o cache ser invalidado).
        if asyncio.iscoroutine(coro):
            return asyncio.run(coro)
        return coro

    # ---- o painel com o Mongo ligado ----
    app = wp.app
    app.config.update(TESTING=True, SECRET_KEY="x")
    cli = app.test_client()

    p1, p2 = ambiente()
    with p1, p2:
        with cli.session_transaction() as s:
            s["painel_ok"] = True

        # Config "real" do servidor, como a migração do .env deixou.
        st.invalidate()
        mongo.docs[GID] = st.normalize({
            "profile": "coc",
            "owner_ids": ["260912891782365196"],
            "modules": {"tickets": True, "logs": True, "games": True},
            "tickets": {"enabled": True, "panel_channel_id": 1362973481834381483,
                        "categories": [{"key": "guerras_cwl", "label": "Guerras",
                                        "emoji": "x", "description": "d",
                                        "prompt": "p"}]},
        }, GID, "BAD - Bravos ANJOS DEFENSORES")

        # 1) Salva os tickets (o caminho que o usuário usou).
        r = cli.post("/config/tickets", data={"enabled": "1",
                                              "panel_channel_id": "1362973481834381483"},
                     follow_redirects=False)
        checa(r.status_code in (302, 303), f"salvar tickets redireciona ({r.status_code})")
        salvo = mongo.docs[GID]
        checa(salvo.get("profile") == "coc", "perfil sobreviveu ao save de tickets")
        checa(salvo.get("owner_ids") == ["260912891782365196"],
              "owner_ids sobreviveu ao save de tickets")
        checa(salvo.get("modules", {}).get("tickets") is True,
              "módulo tickets continua ligado")

        # 2) O ponto que estragava tudo: cache frio logo após o save.
        st.invalidate()
        servidores = wp._servidores()
        cfg_lida = servidores[0]["cfg"] if servidores else None
        checa(cfg_lida is not None, "com cache frio, o painel ainda acha a config")
        if cfg_lida is not None:
            checa(cfg_lida.get("profile") == "coc",
                  "com cache frio, o perfil ainda e 'coc' (antes: default)")
            checa(cfg_lida.get("owner_ids") == ["260912891782365196"],
                  "com cache frio, os donos ainda aparecem")

        # 3) Salvando de novo com o cache frio, nada pode ser zerado.
        r = cli.post("/config/tickets", data={"enabled": "1",
                                              "panel_channel_id": "1362973481834381483"})
        checa(r.status_code in (302, 303), f"segundo save redireciona ({r.status_code})")
        salvo = mongo.docs[GID]
        checa(salvo.get("profile") == "coc", "perfil sobreviveu ao 2o save")
        checa(salvo.get("owner_ids") == ["260912891782365196"],
              "owner_ids sobreviveu ao 2o save")

    print()
    print("painel nao perde config: tudo certo" if FALHAS == 0
          else f"painel nao perde config: {FALHAS} falha(s)")
    return 1 if FALHAS else 0


if __name__ == "__main__":
    sys.exit(main())