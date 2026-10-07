"""
AURA · ponto de entrada
-----------------------
Sobe o bot e, assim que o Discord responde, o painel web.

Ordem das coisas:
    1. carrega o .env
    2. conecta no MongoDB
    3. carrega os cogs de cogs/
    4. registra o cliente em core.runtime (é o que dá acesso ao Discord pelo painel)
    5. no on_ready: sincroniza comandos, importa config legada do .env, cria as
       configs que faltam e sobe o Flask na porta WEB_PANEL_PORT
"""

import asyncio
import os
import threading
import time
import traceback
from os import listdir

import discord
from discord import app_commands
from discord.errors import LoginFailure
from discord.ext import commands, tasks
from dotenv import load_dotenv

load_dotenv()

from core import runtime  # noqa: E402
from core import settings as st  # noqa: E402
from mongo_db import conectar, migrar_config_antiga  # noqa: E402
from web_panel import run_web_panel  # noqa: E402

TOKEN_BOT = os.getenv("DISCORD_TOKEN")
PREFIXO_PADRAO = "-br"

if not TOKEN_BOT:
    print("Erro: DISCORD_TOKEN não encontrado.")
    print("      Copie .env.example para .env e preencha antes de subir.")
    raise SystemExit(1)

#: Servidores de teste: os comandos aparecem na hora neles.
GUILD_IDS_TESTE = [
    int(v) for v in {
        os.getenv("TEST_GUILD_ID", ""),
        os.getenv("id_servidor_tribunal", ""),
    } if str(v).strip().isdigit()
]


class Client(commands.Bot):
    def __init__(self) -> None:
        super().__init__(command_prefix=self._prefixo, intents=discord.Intents().all())
        self.synced = False
        self.cogslist = []
        self.start_time = time.time()
        self.status_index = 0
        self._painel_subiu = False
        self._migrou_legado = False

        for arq in sorted(listdir("cogs")):
            if arq.endswith(".py") and not arq.startswith("_"):
                self.cogslist.append("cogs." + os.path.splitext(arq)[0])

    async def _prefixo(self, bot, message):
        """Cada servidor pode ter seu próprio prefixo; o padrão é -br."""
        if message and message.guild:
            try:
                cfg = await st.get_config_cached(message.guild.id,
                                                 guild_name=message.guild.name)
                p = (cfg.get("prefix") or PREFIXO_PADRAO).strip()
                if p:
                    return p
            except Exception:
                pass
        return PREFIXO_PADRAO

    # ------------------------------------------------------------------
    # boot
    # ------------------------------------------------------------------

    async def setup_hook(self):
        if not conectar():
            print("Aviso: sem MongoDB. O painel salva config, mas nada persiste.")
        else:
            print("MongoDB conectado.")

        for ext in self.cogslist:
            try:
                await self.load_extension(ext)
            except Exception as exc:
                print(f"Falha ao carregar {ext}: {exc}")
        print(f"{len(self.cogslist)} cog(s) no disco.")

        # O painel recebe o cliente: é ele que fala com o Discord pela API.
        runtime.register_client(self, self.loop)
        self.tree.on_error = self.on_tree_error
        self.loop.create_task(self._ouvir_pedido_de_sync())

    async def on_tree_error(self, interaction: discord.Interaction,
                            error: app_commands.AppCommandError):
        """
        Responde ao usuário quando um slash command falha.

        Sem isto, um check de permissão negado (ou qualquer exceção) falhava em
        silêncio: o Discord só mostrava "o aplicativo não respondeu".
        """
        if isinstance(error, app_commands.MissingPermissions):
            faltando = ", ".join(error.missing_permissions)
            texto = f"🚫 Você não tem permissão para isso (`{faltando}`)."
        elif isinstance(error, app_commands.CheckFailure):
            texto = "🚫 Você não pode usar este comando aqui."
        else:
            texto = "❌ Algo deu errado ao executar o comando."
            origem = error.__cause__ or error
            detalhe = "".join(traceback.format_exception(
                type(origem), origem, origem.__traceback__))
            runtime.log("ERRO", f"slash command {interaction.command}: "
                                 f"{type(error).__name__}: {error}\n{detalhe}", "bot")
        try:
            if interaction.response.is_done():
                await interaction.followup.send(texto, ephemeral=True)
            else:
                await interaction.response.send_message(texto, ephemeral=True)
        except discord.HTTPException:
            pass

    async def _ouvir_pedido_de_sync(self):
        """O painel pede re-sync dos comandos; aqui o bot atende."""
        while not self.is_closed():
            try:
                if await runtime.wait_sync_request(timeout=5.0):
                    print("O painel pediu sincronização de comandos.")
                    await self.full_sync()
            except asyncio.CancelledError:
                return
            except Exception as exc:
                print(f"Falha no sync pedido pelo painel: {exc}")

    async def on_ready(self):
        runtime.log("INFO", f"AURA online: {len(self.guilds)} servidor(es)", "bot")
        self.start_time = time.time()

        if not self.synced:
            await self.full_sync()
            self.synced = True

        guilds = "\n".join(
            f"  • {g.name} ({g.id}) · {g.member_count or 0} membros"
            for g in self.guilds
        ) or "  (nenhum)"
        print(f"\n✅ {self.user} online em {len(self.guilds)} servidor(es):\n{guilds}")

        await self._preparar_configs()

        if not self.status_rotation.is_running():
            self.status_rotation.start()
        self._subir_painel()

    async def _preparar_configs(self):
        """
        Importa a configuração antiga do .env uma vez e só depois carrega as
        configs dos servidores.

        A ordem importa: `get_config_cached` guarda no cache a config padrão de
        quem ainda não tem nada no Mongo. Se a carga viesse antes da migração,
        o cache ficaria com o padrão e o painel ignoraria o que foi importado
        até o cache expirar.
        """
        if not self._migrou_legado:
            self._migrou_legado = True
            try:
                for aviso in migrar_config_antiga():
                    print(f"♻️ {aviso}")
            except Exception as exc:
                print(f"Aviso ao importar a config antiga: {exc}")

        for guild in self.guilds:
            try:
                await st.get_config_cached(guild.id, guild_name=guild.name)
            except Exception as exc:
                print(f"Aviso: config de {guild.name} ficou pendente: {exc}")

    def _subir_painel(self):
        """Sobe o painel depois do on_ready: assim o runtime já tem o cliente."""
        if self._painel_subiu:
            return
        self._painel_subiu = True
        threading.Thread(target=run_web_panel, daemon=True).start()

    # ------------------------------------------------------------------
    # comandos
    # ------------------------------------------------------------------

    async def full_sync(self):
        """
        Publica os comandos. Nos servidores de teste vai por servidor (aparece na
        hora); nos outros, global (pode demorar até uma hora na Discord).
        """
        print("Sincronizando comandos…")
        cmds = sorted(c.name for c in self.tree.get_commands())
        print(f"  {len(cmds)} comando(s): {', '.join(cmds)}")

        for guild_id in GUILD_IDS_TESTE:
            guild = self.get_guild(guild_id)
            if guild is None:
                print(f"  · {guild_id} não está no bot, pulando sync de teste")
                continue
            try:
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
                print(f"  ✓ {guild.name}: sync instantâneo")
            except Exception as exc:
                print(f"  ✗ {guild.name}: {exc}")

        try:
            await self.tree.sync()
            print("  ✓ sync global")
        except Exception as exc:
            print(f"  ✗ sync global falhou: {exc}")

    # ------------------------------------------------------------------
    # presença
    # ------------------------------------------------------------------

    async def _update_status(self):
        total_users = sum(g.member_count or 0 for g in self.guilds)
        total_cogs = len(self.cogs)
        total_cmds = len(self.tree.get_commands())
        ping = round(self.latency * 1000)
        segundos = int(time.time() - self.start_time)
        uptime = f"{segundos // 3600}h {(segundos % 3600) // 60}m"

        atividades = [
            discord.Activity(type=discord.ActivityType.watching,
                             name=f"{len(self.guilds)} servidores • {total_users} membros"),
            discord.Activity(type=discord.ActivityType.watching,
                             name=f"Latência {ping}ms • {total_cogs} módulos"),
            discord.Activity(type=discord.ActivityType.listening,
                             name=f"{total_cmds} comandos • {uptime}"),
            discord.Activity(type=discord.ActivityType.watching,
                             name="AURA • painel por servidor"),
        ]

        await self.change_presence(
            activity=atividades[self.status_index % len(atividades)])
        self.status_index += 1

    @tasks.loop(minutes=1)
    async def status_rotation(self):
        try:
            await self._update_status()
        except Exception:
            pass

    @status_rotation.before_loop
    async def _espera_pronto(self):
        await self.wait_until_ready()

    # ------------------------------------------------------------------
    # eventos
    # ------------------------------------------------------------------

    async def on_guild_join(self, guild: discord.Guild):
        """Servidor novo entra com a configuração padrão, pronta para editar."""
        try:
            await st.get_config_cached(guild.id, guild_name=guild.name)
            print(f"➕ {guild.name}: configuração inicial criada.")
        except Exception as exc:
            print(f"Aviso ao entrar em {guild.name}: {exc}")


def main() -> int:
    client = Client()
    try:
        client.run(TOKEN_BOT)
    except LoginFailure:
        print("Erro ao fazer login: token inválido ou o bot saiu do servidor.")
        return 1
    except Exception as exc:
        print(f"Erro ao iniciar o AURA: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())