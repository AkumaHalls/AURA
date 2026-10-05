"""
Testes do core/runtime.py: a ponte entre o painel e o bot. Roda com um
cliente falso, então não precisa de Discord nem de loop de asyncio.
"""
import asyncio
import datetime
import os
import sys
import threading
import time
import unittest.mock as mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import runtime  # noqa: E402

FALHAS = 0


def checa(condicao, msg):
    global FALHAS
    if condicao:
        print("ok  ", msg)
    else:
        FALHAS += 1
        print("FALHA", msg)


class GuildFalso:
    def __init__(self, gid, nome, membros=10):
        self.id = gid
        self.name = nome
        self.member_count = membros
        self.owner_id = 999
        self.created_at = datetime.datetime(2020, 9, 13, tzinfo=datetime.timezone.utc)
        self.icon = None
        self.channels = []
        self.roles = []
        self.emojis = []
        self.me = type("Me", (), {"id": 1, "top_role": type("R", (), {"position": 9})(),
                                  "guild_permissions": type(
                                      "P", (), {"manage_channels": True,
                                                "administrator": True})()})()


class CanalFalso:
    def __init__(self, cid, guild, nome="canal", tipo=type("T", (), {"name": "text"})()):
        self.id = cid
        self.guild = guild
        self.name = nome
        self.type = tipo


class BotFalso:
    def __init__(self, guilds):
        self.guilds = guilds
        self.user = type("U", (), {"id": 1, "name": "AURA"})()
        self._is_ready = True

    def is_ready(self):
        return self._is_ready

    def is_closed(self):
        return False

    def get_guild(self, gid):
        return next((g for g in self.guilds if str(g.id) == str(gid)), None)

    def get_channel(self, cid):
        for g in self.guilds:
            for c in g.channels:
                if str(c.id) == str(cid):
                    return c
        return None

    def get_user(self, uid):
        return None


def main() -> int:
    g1 = GuildFalso(111, "Servidor Um", membros=50)
    g1.channels = [CanalFalso(900, g1, "geral"), CanalFalso(901, g1, "voz")]
    g2 = GuildFalso(222, "Servidor Dois", membros=7)
    g2.channels = [CanalFalso(800, g2, "outro")]
    bot = BotFalso([g1, g2])

    loop = asyncio.new_event_loop()
    runtime.register_client(bot, loop)

    # ---- resumos por servidor ----
    resumos = runtime.list_guild_summaries()
    checa(len(resumos) == 2, "resume os dois servidores")
    ids = {str(r["id"]) for r in resumos}
    checa(ids == {"111", "222"}, "cada resumo traz o id certo")
    checa(all("member_count" in r for r in resumos),
          "resumo usa member_count (o painel lê esse nome)")
    checa(all("members" not in r for r in resumos),
          "resumo nao usa a chave antiga 'members'")
    checa(all(isinstance(r["name"], str) for r in resumos), "resumo traz o nome")

    # ---- snapshot ----
    snap = runtime.guild_snapshot(111)
    checa(snap is not None, "snapshot do servidor existente")
    checa(str(snap["id"]) == "111", "snapshot do servidor certo")
    checa(len(snap["channels"]) == 2, "snapshot lista os canais")
    checa(runtime.guild_snapshot(999) is None, "snapshot de servidor inexistente é None")
    checa(runtime.guild_snapshot("lixo") is None, "snapshot com id inválido é None")

    # ---- o painel nunca deve achar um servidor que não existe ----
    checa(runtime.guild_summary(GuildFalso(333, "Fantasma")) is not None,
          "guild_summary funciona com qualquer objeto")

    # ---- logs ----
    runtime.log("INFO", "mensagem de teste", "teste")
    logs = runtime.get_logs(10)
    checa(any(l["message"] == "mensagem de teste" for l in logs),
          "log gravado aparece em get_logs")
    runtime.clear_logs()
    checa(runtime.get_logs(10) == [], "clear_logs limpa o buffer")

    # ---- sync de comandos: o painel sinaliza, o loop do bot consome ----
    async def espera_sync():
        primeira = await runtime.wait_sync_request(timeout=1.0)
        segunda = await runtime.wait_sync_request(timeout=0.2)
        return primeira, segunda

    loop_rodando = asyncio.new_event_loop()
    resultado_sync = {}

    # Registrar o cliente antes da thread começar: o register_client cria o
    # Evento do sync, e esperar em outro evento não veria o pedido.
    runtime.register_client(bot, loop_rodando)

    def roda_loop():
        asyncio.set_event_loop(loop_rodando)
        resultado_sync["r"] = loop_rodando.run_until_complete(espera_sync())

    th = threading.Thread(target=roda_loop, daemon=True)
    th.start()
    while not loop_rodando.is_running():
        time.sleep(0.01)
    time.sleep(0.1)

    checa(runtime.request_command_sync() is True, "painel pede sync")
    th.join(timeout=3)
    primeira, segunda = resultado_sync.get("r", (False, False))
    checa(primeira is True, "o bot enxerga o pedido")
    checa(segunda is False, "o pedido não fica repetindo para sempre")

    # ---- is_ready ----
    checa(runtime.is_ready() is True, "is_ready reflete o cliente")
    bot._is_ready = False
    checa(runtime.is_ready() is False, "is_ready falso quando desconecta")
    bot._is_ready = True

    # ---- run_coro sem loop do bot (painel salvando antes do on_ready) ----
    async def responde():
        await asyncio.sleep(0)
        return {"ok": True}

    asyncio.set_event_loop(None)
    runtime.register_client(bot, None)  # sem loop, como o painel antes do ready
    resultado = runtime.run_coro(responde())
    checa(resultado == {"ok": True}, "run_coro funciona sem loop do bot")

    # ---- erro dentro da corrotina não escapa para o painel ----
    async def explode():
        raise RuntimeError("deu ruim")

    r = runtime.run_coro(explode())
    checa(r is None, "exceção na corrotina vira None, não explode no painel")

    # ---- sem o bot, o painel ainda consegue salvar ----
    runtime.unregister_client()
    r = runtime.run_coro(responde())
    checa(r == {"ok": True},
          "sem cliente, run_coro roda num loop próprio em vez de falhar")

    # ---- devolve None quando dá timeout ----
    runtime.register_client(bot, loop)

    async def lento():
        await asyncio.sleep(5)
        return {"ok": True}

    r = runtime.run_coro(lento(), timeout=0.3)
    checa(r is None, "timeout vira None em vez de travar o painel")

    runtime.unregister_client()
    loop.close()

    print()
    print("runtime: tudo certo" if FALHAS == 0 else f"runtime: {FALHAS} falha(s)")
    return 1 if FALHAS else 0


if __name__ == "__main__":
    sys.exit(main())