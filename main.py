# AS IMPORTAÇÕES NECESSÁRIAS
import discord
import os
import asyncio
import time
from os import listdir
from discord.ext import commands, tasks
from discord.errors import LoginFailure
from dotenv import load_dotenv

load_dotenv()

# Conecta ao MongoDB (antes de tudo para estar disponível nos cogs e no web panel)
from mongo_db import conectar
conectar()

# Inicia o painel web em uma thread separada
import threading
from web_panel import run_web_panel
threading.Thread(target=run_web_panel, daemon=True).start()

# Verifica se o arquivo .env existe (opcional para desenvolvimento local)
if not os.path.exists('.env'):
    print("O arquivo .env não foi encontrado. Por favor, edite o Exemplo.env para .env com as informações do seu bot.")
else:
    load_dotenv()  # Carrega as variáveis de ambiente do arquivo .env (local)

# Carrega o token do bot e o ID do dono a partir das variáveis de ambiente
token_bot = os.getenv("DISCORD_TOKEN")  # Token do bot
donoid = os.getenv("OWNER_ID")          # ID do dono do bot
prefixo = '-br'                         # Define o prefixo do bot

# Verifica se o token foi carregado corretamente
if not token_bot:
    print("Erro: O token do bot não foi encontrado. Certifique-se de que a variável DISCORD_TOKEN foi configurada corretamente.")
    exit()

SIGNAL_FILE = 'sync_signal.txt'

# Classe básica de inicialização do bot
class Client(commands.Bot):
    def __init__(self) -> None:
        # Configura o prefixo do bot e os intents
        super().__init__(command_prefix=prefixo, intents=discord.Intents().all())
        self.synced = False  # Evita sincronizar comandos mais de uma vez
        self.cogslist = []

        # Lê a lista de cogs (arquivos separados com comandos) e registra
        for cog in listdir("cogs"):
            if cog.endswith(".py"):
                cog = os.path.splitext(cog)[0]
                self.cogslist.append('cogs.' + cog)

    async def setup_hook(self):
        # Carrega as extensões (cogs) registradas
        for ext in self.cogslist:
            await self.load_extension(ext)
        # Inicia background tasks
        self.loop.create_task(self._sync_signal_listener())

    async def _sync_signal_listener(self):
        await self.wait_until_ready()
        while not self.is_closed():
            if os.path.exists(SIGNAL_FILE):
                try:
                    os.remove(SIGNAL_FILE)
                    print("Sinal de sync detectado! Limpando cache de guilds...")
                    for guild in self.guilds:
                        try:
                            self.tree.clear_commands(guild=guild)
                            await self.tree.sync(guild=guild)
                        except:
                            pass
                    await self.tree.sync()
                    print("Sync completo via sinal do web panel.")
                except Exception as e:
                    print(f"Erro no sync via sinal: {e}")
            await asyncio.sleep(5)

    async def full_sync(self):
        """Limpa comandos de guild e sincroniza globalmente."""
        print("Limpando cache de guilds...")
        for guild in self.guilds:
            try:
                self.tree.clear_commands(guild=guild)
                await self.tree.sync(guild=guild)
            except:
                pass
        await self.tree.sync()
        print("Sync global concluído.")

    async def on_ready(self):
        await self.wait_until_ready()
        self.start_time = time.time()
        self.status_index = 0

        # Primeira atualizacao de status imediatamente
        await self._update_status()
        self.status_rotation.start()

        if not self.synced:
            cmds = [c.name for c in self.tree.get_commands()]
            print(f"Comandos registrados no tree: {cmds}")
            await self.tree.sync()
            print("Comandos sincronizados globalmente.")
            self.synced = True
            print(f"Comandos sincronizados: {self.synced}")
        print(f"\nO bot {self.user} já está online e disponível.")
        print(f"\nID do dono é {donoid}")

    async def _update_status(self):
        total_users = sum(g.member_count or 0 for g in self.guilds)
        total_cogs = len(self.cogs)
        total_cmds = len(self.tree.get_commands())
        ping = round(self.latency * 1000)
        uptime_seconds = int(time.time() - self.start_time)
        uptime_str = f"{uptime_seconds // 3600}h {(uptime_seconds % 3600) // 60}m"

        activities = [
            discord.Activity(type=discord.ActivityType.watching, name=f"Operational Cluster • {len(self.guilds)} servidores"),
            discord.Activity(type=discord.ActivityType.watching, name=f"Latência: {ping}ms • {total_cogs} módulos"),
            discord.Activity(type=discord.ActivityType.playing, name=f"B.A.D • {total_users} membros"),
            discord.Activity(type=discord.ActivityType.listening, name=f"{total_cmds} comandos • Uptime: {uptime_str}"),
            discord.Activity(type=discord.ActivityType.watching, name=f"Sistema Online • v2.0"),
            discord.Activity(type=discord.ActivityType.competing, name=f"Gerenciando {len(self.guilds)} clãs"),
        ]

        activity = activities[self.status_index % len(activities)]
        self.status_index += 1
        await self.change_presence(activity=activity)

    @tasks.loop(minutes=1)
    async def status_rotation(self):
        await self._update_status()

# Inicializa o cliente
client = Client()

# Liga o bot e o mantém online
try:
    client.run(token_bot)
except LoginFailure:
    print("Erro ao fazer login: O token fornecido é inválido ou incorreto.")
except Exception as e:
    print(f"Erro desconhecido: {e}")
