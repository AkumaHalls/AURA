# AS IMPORTAÇÕES NECESSÁRIAS
import discord
import os
from os import listdir
from discord.ext import commands
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

    async def on_ready(self):
        # Executa ações quando o bot estiver pronto
        await self.wait_until_ready()
        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="Bem vindo"))  # Define o status do bot
        if not self.synced:
            test_guild_id = os.getenv("TEST_GUILD_ID")
            if test_guild_id:
                try:
                    guild = discord.Object(id=int(test_guild_id))
                    await self.tree.sync(guild=guild)
                    print(f"Comandos sincronizados para guild {test_guild_id} (TEST_GUILD_ID)")
                except:
                    await self.tree.sync()
            else:
                await self.tree.sync()  # Global sync (lento, até 1h)
            self.synced = True
            print(f"Comandos sincronizados: {self.synced}")
        print(f"\nO bot {self.user} já está online e disponível.")
        print(f"\nID do dono é {donoid}")

# Inicializa o cliente
client = Client()

# Liga o bot e o mantém online
try:
    client.run(token_bot)
except LoginFailure:
    print("Erro ao fazer login: O token fornecido é inválido ou incorreto.")
except Exception as e:
    print(f"Erro desconhecido: {e}")
