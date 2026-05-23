import discord
import os
import psutil
import platform
import time
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

# CARREGA E LE O ARQUIVO .env na raiz do projeto
# O '..' sobe um nível de diretório para encontrar o .env
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

try:
    # Acessa e define o id do dono a partir do .env
    donoid = int(os.getenv("DONO_ID"))
except (ValueError, TypeError):
    print("AVISO: A variável de ambiente 'DONO_ID' não está definida ou não é um número. Comandos de dono não funcionarão.")
    donoid = None # Define como None para que as verificações falhem de forma segura

# Pega o processo atual para informações de sistema
PROC = psutil.Process(os.getpid())

def getdonoid():
    """Função para retornar o ID do dono."""
    return donoid

def getmensagemerro():
    """Função para retornar a mensagem de erro padrão."""
    return mensagemerro

# Mensagem de erro que será exibida sempre que um comando falhar.
mensagemerro = "<:ew:969703224825225266> Ue? Isso não funcionou como deveria... \nAcho que você tentou usar isso em um canal errado ou não tem permissão para tal função <:derp:969703169670131812>"

# Início da classe da Cog
class onwer(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self):
        """Evento que é acionado quando a Cog está pronta."""
        print("Cog onwer carregado.")

    # GRUPO DE COMANDOS 'dono'
    dono = app_commands.Group(name="owner", description="Comandos de dono do bot.")

    @dono.command(name="say", description="🦊⠂Diga alguma coisa como AURA")
    @app_commands.describe(mensagem="Qual é a mensagem?")
    async def say(self, interaction: discord.Interaction, mensagem: str):
        print(f"Comando say - User: {interaction.user.name} - mensagem:{mensagem}")
        if interaction.user.id == donoid:
            await interaction.response.send_message("<:BN:416595378956271626>┃ enviando sua mensagem...", ephemeral=True)
            await interaction.channel.send(f"{mensagem}")
        else:
            await interaction.response.send_message(mensagemerro, ephemeral=True)

    @dono.command(name="listar", description="🦊⠂lista os servidores que o AURA está.")
    async def listservers(self, interaction: discord.Interaction):
        print(f"Usuario: {interaction.user.name} usou lista servidores")
        if interaction.user.id == donoid:
            await interaction.response.defer(ephemeral=True)
            servers = self.client.guilds
            lista = "Lista de Servidores 🦊\n"
            for server in servers:
                lista += f"Nome:`{server.name}` - id:`{server.id}`\n"
            await interaction.followup.send(content=lista)
        else:
            await interaction.response.send_message(mensagemerro, ephemeral=True)

    @dono.command(name="sair", description="🦊⠂Faz o AURA sair de um servidor.")
    @app_commands.describe(id_servidor="Qual é a ID do servidor?")
    async def leave(self, interaction: discord.Interaction, id_servidor: str):
        print(f"Usuario: {interaction.user.name} usou sair servidores")
        if interaction.user.id == donoid:
            try:
                guild = self.client.get_guild(int(id_servidor))
                if guild:
                    await guild.leave()
                    await interaction.response.send_message(f"Saí do servidor: {guild.name}")
                else:
                    await interaction.response.send_message("Não encontrei um servidor com essa ID.", ephemeral=True)
            except ValueError:
                await interaction.response.send_message("A ID do servidor deve ser um número.", ephemeral=True)
        else:
            await interaction.response.send_message(mensagemerro, ephemeral=True)

    @dono.command(name="bot-name", description="🦊⠂Define um novo nome ao bot")
    @app_commands.describe(nome="Qual é o novo nome?")
    async def set_bot_name(self, interaction: discord.Interaction, nome: str):
        print(f"Comando bot-name - User: {interaction.user.name} - novo nome:{nome}")
        if interaction.user.id == donoid:
            await self.client.user.edit(username=nome)
            await interaction.response.send_message(f"<:BN:416595378956271626>┃ O Nome do bot foi definido para {nome}", ephemeral=True)
        else:
            await interaction.response.send_message(mensagemerro, ephemeral=True)

    @dono.command(name="sync", description="🦊⠂Força a sincronização dos comandos slash (limpa cache e re-sincroniza)")
    async def sync_commands(self, interaction: discord.Interaction):
        if interaction.user.id != donoid:
            return await interaction.response.send_message(mensagemerro, ephemeral=True)
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            await self.client.full_sync()
            await interaction.followup.send("✅ Comandos re-sincronizados globalmente. Pode levar até 1h para propagar.")
        except Exception as e:
            await interaction.followup.send(f"❌ Erro ao sincronizar: {e}")

    @dono.command(name="sync-guild", description="🦊⠂Sincroniza comandos em um servidor específico (teste imediato)")
    @app_commands.describe(guild_id="ID do servidor")
    async def sync_guild(self, interaction: discord.Interaction, guild_id: str):
        if interaction.user.id != donoid:
            return await interaction.response.send_message(mensagemerro, ephemeral=True)
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            guild = discord.Object(id=int(guild_id))
            self.client.tree.clear_commands(guild=guild)
            await self.client.tree.sync(guild=guild)
            await interaction.followup.send(f"✅ Comandos sincronizados para guild {guild_id}.")
        except Exception as e:
            await interaction.followup.send(f"❌ Erro: {e}")

    @dono.command(name="bot-avatar", description="🦊⠂Define um novo avatar ao bot")
    @app_commands.describe(avatar="Qual é o novo avatar?")
    async def set_bot_avatar(self, interaction: discord.Interaction, avatar: discord.Attachment):
        print(f"Comando bot-avatar - User: {interaction.user.name}")
        if interaction.user.id == donoid:
            avatar_bytes = await avatar.read()
            await self.client.user.edit(avatar=avatar_bytes)
            await interaction.response.send_message(f"<:BN:416595378956271626>┃ O Avatar do bot foi redefinido", ephemeral=True)
        else:
            await interaction.response.send_message(mensagemerro, ephemeral=True)

    # GRUPO DE COMANDOS 'bot'
    bot = app_commands.Group(name="bot", description="Comandos de controle do bot.")

    @bot.command(name="ping", description='🤖⠂Exibe o ping do bot')
    async def ping(self, interaction: discord.Interaction):
        print(f"Usuario: {interaction.user.name} usou ping")
        resposta = discord.Embed(
            colour=discord.Color.yellow(),
            title="🏓┃Pong",
            description=f"Latencia: `{round(self.client.latency * 1000)}`ms."
        )
        await interaction.response.send_message(embed=resposta)

    @bot.command(name="info", description='🤖⠂Exibe informações sobre o bot')
    async def botinfo(self, interaction: discord.Interaction):
        print(f"Usuario: {interaction.user.name} usou botinfo")
        try:
            # Informações de memória
            mem = psutil.virtual_memory()
            mem_total_mb = mem.total / (1024 * 1024)
            mem_used_mb = mem.used / (1024 * 1024)
            
            # Uptime do processo (tempo que o bot está online)
            start_time_timestamp = int(PROC.create_time())

            resposta = discord.Embed(
                colour=discord.Color.yellow(),
                title=f"🦊┃Informações do {self.client.user.name}",
                description="Aqui estão algumas informações sobre mim e a máquina que me hospeda."
            )
            if self.client.user.avatar:
                resposta.set_thumbnail(url=self.client.user.avatar.url)
            
            # Informações da Hospedagem (Render)
            resposta.add_field(name="🖥️ Hospedagem", value="```Render```", inline=True)
            resposta.add_field(name="👨‍💻 Linguagem", value=f"```Python {platform.python_version()}```", inline=True)
            resposta.add_field(name="📦 Biblioteca", value=f"```discord.py {discord.__version__}```", inline=True)

            # Informações de Recursos
            resposta.add_field(name="📊 Uso de RAM", value=f"```{mem_used_mb:.2f} / {mem_total_mb:.2f} MB```", inline=True)
            resposta.add_field(name="🌡️ Uso de CPU", value=f"```{psutil.cpu_percent()}%```", inline=True)
            resposta.add_field(name="🕐 Online desde", value=f"<t:{start_time_timestamp}:R>", inline=True)

            # Informações do Bot
            resposta.add_field(name="🦊 Dono", value=f"<@{donoid}>", inline=True)
            resposta.add_field(name="🏓 Ping", value=f"```{round(self.client.latency * 1000)}ms```", inline=True)
            resposta.add_field(name="🔮 Menção", value=f"<@{self.client.user.id}>", inline=True)

            await interaction.response.send_message(embed=resposta)
        except Exception as e:
            print(f"Erro no comando botinfo: {e}")
            await interaction.response.send_message("Ocorreu um erro ao buscar as informações do bot.", ephemeral=True)

    @bot.command(name="help", description='🤖⠂Ajuda sobre o bot.')
    async def help(self, interaction: discord.Interaction):
        resposta = discord.Embed(
            colour=discord.Color.yellow(),
            title="🦊┃Ajuda sobre o bot",
            description="Eaeee AURA aqui, ainda estou em desenvolvimento"
        )
        await interaction.response.send_message(embed=resposta)

async def setup(client: commands.Bot) -> None:
    """Função para carregar a Cog no bot."""
    await client.add_cog(onwer(client))
