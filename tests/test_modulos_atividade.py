"""
Testes offline dos módulos de atividade (boas-vindas, registros, contador) e dos
fixes desta rodada. Sem Discord real e sem Mongo.
"""
import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017/aura_teste")

from core import settings as st
from core import placeholders as ph
from cogs import status_cla as SC


def eq(nome, obtido, esperado):
    ok = obtido == esperado
    print(f"{'ok  ' if ok else 'FALHA'} {nome}")
    if not ok:
        print(f"      esperado={esperado!r}\n      obtido  ={obtido!r}")
    return 0 if ok else 1


def verdade(nome, condicao):
    print(f"{'ok  ' if condicao else 'FALHA'} {nome}")
    return 0 if condicao else 1


class FakeClan:
    member_count = 42
    level = 7
    points = 12345
    war_wins = 88
    war_win_streak = 6


class FakeVoice:
    def __init__(self, nome, cid):
        self.name = nome
        self.id = cid


class FakeCat:
    def __init__(self, nome, canais):
        self.name = nome
        self.voice_channels = canais


class FakeGuild:
    def __init__(self, cats):
        self.categories = cats
        self.voice_channels = [c for cat in cats for c in cat.voice_channels]


def main():
    falhas = 0

    # ---------------------------------------------------------------- settings
    d = st.DEFAULT_BOAS_VINDAS["leave_message"]
    falhas += verdade("default leave_message sem caracteres estranhos",
                      not re.search(r"[\u4e00-\u9fff]", d))
    falhas += verdade("default leave_message usa {member_count}", "{member_count}" in d)

    # normalize conserta o texto corrompido salvo no Mongo e troca {members}
    corrompido = st.normalize_boas_vindas(
        {"leave_message": "{user} saiu. Já我们是 {members} membros."})
    falhas += verdade("normalize conserta 'Já我们是'",
                      "Já somos" in corrompido["leave_message"])
    falhas += verdade("normalize troca {members} por {member_count}",
                      "{member_count}" in corrompido["leave_message"]
                      and "{members}" not in corrompido["leave_message"])

    # ------------------------------------------------------------- placeholders
    class G:
        name = "Servidor"
        id = 1
        member_count = 7
        emojis = []

    falhas += eq("placeholder {members} resolvido", ph.render("{members}", guild=G()), "7")
    falhas += eq("placeholder {member_count} resolvido",
                 ph.render("{member_count}", guild=G()), "7")
    falhas += eq("placeholder {count} via extra", ph.render("{count}", guild=G(),
                                                            extra={"count": 99}), "99")

    # --------------------------------------------------------------- status_cla
    falhas += eq("formato membros B.A.D", SC._numeros(FakeClan())["membros"],
                 "👥 Membros: 42/50")
    falhas += eq("formato nível B.A.D", SC._numeros(FakeClan())["nivel"],
                 "⭐ Nível: 7")
    falhas += eq("formato troféus B.A.D", SC._numeros(FakeClan())["trofeus"],
                 "🏆 Troféus: 12345")
    falhas += eq("formato guerras B.A.D", SC._numeros(FakeClan())["guerras"],
                 "⚔️ Guerras Ganhas: 88")
    falhas += eq("formato streak B.A.D", SC._numeros(FakeClan())["streak"],
                 "🔥 Win Streak: 6")
    falhas += verdade("formato data B.A.D",
                      SC._numeros(FakeClan())["data"].startswith("🕒 Atualizado: "))

    falhas += eq("alias estrelas->nivel", SC._ALIAS["estrelas"], "nivel")
    falhas += eq("alias vitorias_guerra->guerras", SC._ALIAS["vitorias_guerra"], "guerras")
    falhas += eq("alias tempo->data", SC._ALIAS["tempo"], "data")

    falhas += verdade("_saudavel: 'nada mudou' é sucesso",
                      SC._saudavel("nada mudou (os canais já estavam certos)"))
    falhas += verdade("_saudavel: 'sem tag' é problema",
                      not SC._saudavel("sem tag de clã configurada"))
    falhas += verdade("_saudavel: 'N canais atualizado' é sucesso",
                      SC._saudavel("6 canais atualizados"))
    falhas += verdade("_saudavel: None é problema", not SC._saudavel(None))

    # auto-detecção de canais por emoji numa categoria "status do clã"
    cat = FakeCat("🔰 Status do Clã", [
        FakeVoice("👥 Membros: 0/50", 11),
        FakeVoice("⭐ Nível: 0", 12),
        FakeVoice("🏆 Troféus: 0", 13),
        FakeVoice("⚔️ Guerras: 0", 14),
        FakeVoice("🔥 Streak: 0", 15),
        FakeVoice("🕒 Atualizado: —", 16),
    ])
    guild = FakeGuild([cat])
    achados = SC.StatusCla._achar_canais(guild, None)
    falhas += eq("autodetect acha 6 canais", len(achados), 6)
    falhas += eq("autodetect mapeia membros", achados["membros"].id, 11)
    falhas += eq("autodetect mapeia nivel", achados["nivel"].id, 12)

    # ------------------------------------------------- módulos de atividade carregam
    from cogs import boas_vindas as BV
    from cogs import registros as RG
    from cogs import contador as CT

    falhas += verdade("cog BoasVindas tem on_member_join",
                      hasattr(BV.BoasVindas, "on_member_join"))
    falhas += verdade("cog BoasVindas tem on_member_remove",
                      hasattr(BV.BoasVindas, "on_member_remove"))
    falhas += verdade("cog Registros tem on_raw_message_delete",
                      hasattr(RG.Registros, "on_raw_message_delete"))
    falhas += verdade("cog Registros tem on_member_update",
                      hasattr(RG.Registros, "on_member_update"))
    falhas += verdade("cog Contador tem atualizar (loop)",
                      hasattr(CT.Contador, "atualizar"))

    # boas-vindas só fica ativo com módulo + config ligados
    cfg_bv = st.default_config(1, "S")
    cfg_bv["modules"]["boas_vindas"] = True
    cfg_bv["boas_vindas"]["enabled"] = True
    falhas += verdade("BV ativo com módulo ligado", BV._ativo(cfg_bv))
    cfg_bv["boas_vindas"]["enabled"] = False
    falhas += verdade("BV inativo com módulo desligado", not BV._ativo(cfg_bv))

    # ------------------------------------------------------- fixes de regressão
    cogs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cogs")
    fontes = {}
    for arq in os.listdir(cogs_dir):
        if arq.endswith(".py"):
            with open(os.path.join(cogs_dir, arq), encoding="utf-8") as fh:
                fontes[arq] = fh.read()

    falhas += verdade("nenhum cog usa trigger_typing (removido no discord.py 2.x)",
                      not any("trigger_typing" in t for t in fontes.values()))
    falhas += verdade("nenhum app_command usa @commands.guild_only",
                      not any("@commands.guild_only" in t for t in fontes.values()))
    falhas += verdade("nenhum app_command usa @commands.has_permissions",
                      not any("@commands.has_permissions" in t for t in fontes.values()))
    falhas += verdade("status_cla lê member_count/level/points (API correta)",
                      all(k in fontes["status_cla.py"]
                          for k in ("member_count", "level", "points", "war_win_streak")))
    falhas += verdade("grupos de comando marcados guild_only=True",
                      all("guild_only=True" in t for t in (
                          fontes["admin.py"], fontes["atendimento.py"],
                          fontes["autorole.py"], fontes["moderacao.py"],
                          fontes["status_cla.py"])))
    falhas += verdade("boas-vindas ignoram bots",
                      "member.bot" in fontes["boas_vindas.py"])
    falhas += verdade("registros ignoram bots em join/remove",
                      fontes["registros.py"].count("member.bot") + 
                      fontes["registros.py"].count("author.bot") >= 2)
    falhas += verdade("registros usam evento raw para delete",
                      "on_raw_message_delete" in fontes["registros.py"])

    # defer antes do trabalho lento (janela de 3s da interação)
    sc = fontes["status_cla.py"]
    falhas += verdade("status-cla auto-detectar defer antes do upsert",
                      "response.defer" in sc and "followup.send" in sc)
    falhas += verdade("status-cla forcar defere antes de get_config",
                      "response.defer(ephemeral=True)\n        cfg = await" in sc)

    # main.py: handler de erro do tree registrado
    raiz = os.path.dirname(cogs_dir)
    with open(os.path.join(raiz, "main.py"), encoding="utf-8") as fh:
        main_src = fh.read()
    falhas += verdade("main.py registra tree.on_error",
                      "tree.on_error" in main_src and "on_tree_error" in main_src)
    falhas += verdade("main.py trata MissingPermissions",
                      "MissingPermissions" in main_src)

    # autorole: reação que falha não derruba o fluxo
    from cogs import autorole as AR
    import discord

    class _Resp:
        status = 403
        reason = "Forbidden"

    class MsgReacaoRuim:
        async def add_reaction(self, _):
            raise discord.Forbidden(_Resp(), "sem permissão")

    try:
        asyncio.new_event_loop().run_until_complete(
            AR._reagir(MsgReacaoRuim(), "✅"))
        falhas += verdade("_reagir engole erro de permissão", True)
    except Exception:
        falhas += verdade("_reagir engole erro de permissão", False)

    print()
    print("FALHAS:", falhas)
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
