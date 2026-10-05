"""Testa a migração do .env antigo para a config multiserver, sem Mongo real."""
import os
import sys
import unittest.mock as mk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ENV = {
    "TEST_GUILD_ID": "100000000000000001",
    "id_canal_suporte": "100000000000000002",
    "id_cargo_atendente": "100000000000000003",
    "ID_CANAL_TRANSCRICOES": "100000000000000004",
    "id_canal_logs_tri": "100000000000000004",
    "CANAL_REGISTRO_ID": "100000000000000005",
    "REGISTRATION_CHANNEL_ID": "100000000000000005",
    "LOG_CHANNEL_ID": "100000000000000006",
    "APPROVAL_LOG_CHANNEL_ID": "100000000000000007",
    "CARGO_MEMBRO_ID": "100000000000000008",
    "CARGO_BANIDO_ID": "100000000000000009",
    "COC_MEMBER_ROLE_ID": "100000000000000008",
    "COC_ELDER_ROLE_ID": "100000000000000010",
    "COC_COLEADER_ROLE_ID": "100000000000000011",
    "CLAN_TAG": "#EXEMPLO",
    "KICK_MESSAGE": "Você foi removido do servidor por não fazer mais parte do clã.",
    "OWNER_ID": "100000000000000012",
    "MONGO_URI": "mongodb://localhost:27017/aura_teste",
}

import mongo_db
from core import runtime as rt
from core import settings as st

falhas = 0


def eq(nome, obtido, esperado):
    global falhas
    ok = obtido == esperado
    print(f"{'ok  ' if ok else 'FALHA'} {nome}")
    if not ok:
        print(f"      esperado={esperado!r}\n      obtido  ={obtido!r}")
        falhas += 1
    return ok


def roda_migracao(forcar=False):
    """Roda a migração capturando a config que iria para o banco."""
    os.environ.update(ENV)
    rt.list_guild_summaries = lambda: []
    capturado = {}

    def fake_upsert(gid, doc, updated_by=None):
        capturado["gid"] = gid
        capturado["doc"] = st.normalize(doc, gid, doc.get("guild_name"))
        return True

    mongo_db.db = mk.MagicMock()
    with mk.patch.object(mongo_db, "upsert_guild_config", side_effect=fake_upsert), \
         mk.patch.object(mongo_db, "get_guild_config_raw", return_value=None):
        avisos = mongo_db.migrar_config_antiga(forcar=forcar)
    return capturado, avisos


def main():
    cap, avisos = roda_migracao()
    d = cap.get("doc")

    print("== destino ==")
    for a in avisos:
        print("   ", a)

    print("\n== identificacao ==")
    eq("servidor veio do TEST_GUILD_ID", cap.get("gid"), ENV["TEST_GUILD_ID"])
    eq("dono em owner_ids", d.get("owner_ids"), [ENV["OWNER_ID"]])
    eq("perfil detectado", d.get("profile"), "coc")

    print("\n== modulos ligados ==")
    ligados = sorted(k for k, v in d["modules"].items() if v)
    for m in ligados:
        print("   ", m)
    eq("tickets ligado", d["modules"]["tickets"], True)
    eq("autorole ligado", d["modules"]["autorole"], True)
    eq("games ligado", d["modules"]["games"], True)
    eq("logs ligado", d["modules"]["logs"], True)

    print("\n== ids de canais/cargos ==")
    eq("canal de suporte", d["tickets"]["support_channel_id"], int(ENV["id_canal_suporte"]))
    eq("cargo de atendimento", d["tickets"]["staff_role_id"], int(ENV["id_cargo_atendente"]))
    eq("canal de transcricoes", d["tickets"]["transcript_channel_id"], int(ENV["ID_CANAL_TRANSCRICOES"]))
    eq("canal do autorole", d["autorole"]["channel_id"], int(ENV["REGISTRATION_CHANNEL_ID"]))
    eq("cargo de membro", d["autorole"]["give_role_id"], int(ENV["CARGO_MEMBRO_ID"]))
    eq("cargo de banido", d["autorole"]["deny_role_id"], int(ENV["CARGO_BANIDO_ID"]))
    eq("canal de log da moderacao",
       d["moderation"]["log_channel_id"], int(ENV["CANAL_REGISTRO_ID"]))

    print("\n== clash of clans ==")
    eq("clan tag normalizada com #", d["games"]["coc"]["clan_tag"], "#EXEMPLO")
    eq("cargo member do clã", d["games"]["coc"]["roles"]["member"], int(ENV["COC_MEMBER_ROLE_ID"]))
    eq("cargo elder do clã", d["games"]["coc"]["roles"]["elder"], int(ENV["COC_ELDER_ROLE_ID"]))
    eq("cargo coleader do clã", d["games"]["coc"]["roles"]["coleader"], int(ENV["COC_COLEADER_ROLE_ID"]))
    eq("canal de aprovacao", d["games"]["coc"]["approval_channel_id"], int(ENV["APPROVAL_LOG_CHANNEL_ID"]))
    eq("mensagem de remocao", d["games"]["coc"]["kick_message"], ENV["KICK_MESSAGE"])

    print("\n== moderacao herdou as exclusoes ==")
    print("    canais ignorados:", d["moderation"]["ignored_channels"])
    print("    cargos ignorados:", d["moderation"]["ignored_roles"])
    eq("canal de suporte ignorado",
       int(ENV["id_canal_suporte"]) in d["moderation"]["ignored_channels"], True)
    eq("atendente fica isento",
       int(ENV["id_cargo_atendente"]) in d["moderation"]["escalation"]["exempt_roles"], True)

    print("\n== tickets genericos ==")
    labels = [c["label"] for c in d["tickets"]["categories"]]
    print("    categorias:", labels)
    eq("ha mais de uma categoria", len(labels) > 1, True)
    eq("todas tem chave unica", len({c["key"] for c in d["tickets"]["categories"]}), len(labels))

    print("\n== nao sobrescreve config existente ==")
    os.environ.update(ENV)
    rt.list_guild_summaries = lambda: []
    mongo_db.db = mk.MagicMock()
    with mk.patch.object(mongo_db, "get_guild_config_raw", return_value={"guild_id": "x"}), \
         mk.patch.object(mongo_db, "upsert_guild_config") as up:
        avisos = mongo_db.migrar_config_antiga()
        eq("nao chamou upsert", up.called, False)
        eq("avisou que ja existe",
           "já tem configuração" in avisos[0], True)

    print("\n== secrets NAO vao para o banco ==")
    doc = cap["doc"]
    texto = str(doc)
    for nome in ("DISCORD_TOKEN", "COC_PASSWORD", "WEB_PANEL_PASSWORD", "MONGO_URI"):
        eq(f"{nome} ausente", nome in texto, False)
    eq("senha nao vazou", "protecao" in texto.lower(), False)
    eq("token nao vazou", "GK2RAB" in texto, False)

    print()
    print("FALHAS:", falhas)
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())