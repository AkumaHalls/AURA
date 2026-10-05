"""
Testa a retomada de aprovações de prova depois de um restart, sem Discord
nem MongoDB: os dois lados são substituídos por dublês.
"""
import asyncio
import os
import sys
import unittest.mock as mk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mongo_db  # noqa: E402
from cogs import sistema_prova as sp  # noqa: E402

FALHAS = 0


def checa(condicao, msg):
    global FALHAS
    if condicao:
        print("ok  ", msg)
    else:
        FALHAS += 1
        print("FALHA", msg)


QUESTOES = [{"id": 1, "pergunta": "p", "alternativas": ["a", "b"], "correta": 0}]
BLOCO = {"approval_role_id": 42, "notify_channel_id": None, "title": "Exame"}


class GuildFalso:
    def __init__(self, gid):
        self.id = gid
        self.name = "Guild"
        self.owner = None
        self._membros = {}

    def get_member(self, uid):
        return self._membros.get(int(uid))

    def get_channel(self, cid):
        return None

    def get_role(self, rid):
        return None


class MembroFalso:
    def __init__(self, uid):
        self.id = uid
        self.mention = f"<@{uid}>"
        self.name = f"user{uid}"
        self.joined_at = None
        self.created_at = None
        self.dm_aberta = True

    def __str__(self):
        return self.name

    async def create_dm(self):
        return object()


class CogFalso(sp.SistemaProva):
    def __init__(self, client, guild):
        super().__init__(client)
        self.guild = guild
        self.avisados = []

    async def _avisar_aprovadores(self, guild, bloco, membro, questoes, uid):
        self.avisados.append((str(guild.id), bloco.get("approval_role_id"),
                               str(membro.id), list(questoes)))
        return len(self.avisados) <= self.falhar_ate  # tipo: ignore[attr-defined]


class ClientFalso:
    def __init__(self, guild):
        self._guild = guild
        self.guilds = [guild]

    def get_guild(self, gid):
        return self._guild if str(self._guild.id) == str(gid) else None


async def roda(fn, *args):
    return await fn(*args)


def main() -> int:
    guild = GuildFalso(555)
    guild._membros[777] = MembroFalso(777)
    client = ClientFalso(guild)

    apagados = []

    def fake_listar(incluir_questoes=False, guild_id=None):
        return REGISTROS

    def fake_apagar(uid, gid=None):
        apagados.append((str(uid), str(gid)))
        return True

    # ---------- 1. pending aguardando_aprovador é reenviado ----------
    REGISTROS = [{"user_id": "777", "guild_id": "555", "status": "aguardando_aprovador",
                  "questoes": QUESTOES, "config": BLOCO}]
    cog = CogFalso(client, guild)
    cog.falhar_ate = 99
    with mk.patch.object(mongo_db, "listar_aprovacoes_pendentes", fake_listar), \
         mk.patch.object(mongo_db, "deletar_aprovacao_pendente", fake_apagar):
        n = asyncio.run(cog._retomar_aprovacoes())
    checa(n == 1, "aprovação pendente é reenviada aos aprovadores")
    checa(len(cog.avisados) == 1, "o aviso foi realmente disparado")
    checa(cog.avisados[0][1] == 42, "o cargo de aprovador veio do bloco salvo")
    checa(cog.avisados[0][3] == QUESTOES, "as questões voltaram do banco")
    checa(apagados == [], "não apaga o registro que foi reenviado com sucesso")

    # ---------- 2. aguardando_usuario é limpo ----------
    REGISTROS = [{"user_id": "777", "guild_id": "555", "status": "aguardando_usuario",
                  "questoes": QUESTOES, "config": BLOCO}]
    apagados = []
    cog = CogFalso(client, guild)
    cog.falhar_ate = 99
    with mk.patch.object(mongo_db, "listar_aprovacoes_pendentes", fake_listar), \
         mk.patch.object(mongo_db, "deletar_aprovacao_pendente", fake_apagar):
        n = asyncio.run(cog._retomar_aprovacoes())
    checa(n == 0, "esperando o examineando não conta como retomada")
    checa(apagados == [("777", "555")],
          "DM já aberta e botão morto: registro é apagado para reinscrever")

    # ---------- 3. membro saiu do servidor ----------
    REGISTROS = [{"user_id": "999", "guild_id": "555", "status": "aguardando_aprovador",
                  "questoes": QUESTOES, "config": BLOCO}]
    apagados = []
    cog = CogFalso(client, guild)
    cog.falhar_ate = 99
    with mk.patch.object(mongo_db, "listar_aprovacoes_pendentes", fake_listar), \
         mk.patch.object(mongo_db, "deletar_aprovacao_pendente", fake_apagar):
        n = asyncio.run(cog._retomar_aprovacoes())
    checa(n == 0, "membro que saiu do servidor não é retomado")
    checa(apagados == [("999", "555")], "registro de quem não está mais lá é limpo")

    # ---------- 4. servidor fora do bot ----------
    REGISTROS = [{"user_id": "777", "guild_id": "999", "status": "aguardando_aprovador",
                  "questoes": QUESTOES, "config": BLOCO}]
    apagados = []
    cog = CogFalso(client, guild)
    cog.falhar_ate = 99
    with mk.patch.object(mongo_db, "listar_aprovacoes_pendentes", fake_listar), \
         mk.patch.object(mongo_db, "deletar_aprovacao_pendente", fake_apagar):
        n = asyncio.run(cog._retomar_aprovacoes())
    checa(n == 0, "servidor fora do bot não é retomado")
    checa(apagados == [("777", "999")], "registro de servidor ausente é limpo")

    # ---------- 5. ninguém recebeu o aviso ----------
    REGISTROS = [{"user_id": "777", "guild_id": "555", "status": "aguardando_aprovador",
                  "questoes": QUESTOES, "config": BLOCO}]
    apagados = []
    cog = CogFalso(client, guild)
    cog.falhar_ate = 0  # _avisar_aprovadores devolve False
    with mk.patch.object(mongo_db, "listar_aprovacoes_pendentes", fake_listar), \
         mk.patch.object(mongo_db, "deletar_aprovacao_pendente", fake_apagar):
        n = asyncio.run(cog._retomar_aprovacoes())
    checa(n == 0, "sem aprovador alcançável, nada é contado como retomado")
    checa(apagados == [("777", "555")],
          "registro sem ninguém para aprovar é limpo")

    # ---------- 6. registro incompleto não trava ----------
    REGISTROS = [{"user_id": "777", "guild_id": "555", "status": "aguardando_aprovador",
                  "questoes": [], "config": BLOCO}]
    apagados = []
    cog = CogFalso(client, guild)
    cog.falhar_ate = 99
    with mk.patch.object(mongo_db, "listar_aprovacoes_pendentes", fake_listar), \
         mk.patch.object(mongo_db, "deletar_aprovacao_pendente", fake_apagar):
        n = asyncio.run(cog._retomar_aprovacoes())
    checa(n == 0, "registro sem questões é ignorado")
    checa(apagados == [("777", "555")], "registro incompleto é limpo")

    # ---------- 7. on_ready só retoma uma vez ----------
    REGISTROS = []
    cog = CogFalso(client, guild)
    cog.falhar_ate = 99
    with mk.patch.object(mongo_db, "listar_aprovacoes_pendentes", fake_listar):
        asyncio.run(cog.on_ready())
        asyncio.run(cog.on_ready())
    checa(cog._ja_retomou is True, "a retomada marca que já rodou")

    print()
    print("provas: tudo certo" if FALHAS == 0 else f"provas: {FALHAS} falha(s)")
    return 1 if FALHAS else 0


if __name__ == "__main__":
    sys.exit(main())