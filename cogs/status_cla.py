import discord
import asyncio
import os
import coc
import traceback
from datetime import datetime
import pytz
from discord.ext import commands, tasks
from discord import app_commands
from dotenv import load_dotenv

# Carrega variáveis
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

COC_EMAIL = os.getenv("COC_EMAIL")
COC_PASSWORD = os.getenv("COC_PASSWORD")
CLAN_TAG = os.getenv("CLAN_TAG")

class StatusCla(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client
        self.coc_client = None
        # Agora não guardamos IDs fixos globais, pois pode ter mais de um servidor
        self.update_status_task.start()

    async def connect_coc(self):
        try:
            if self.coc_client and self.coc_client.http.session:
                 return 
            self.coc_client = coc.Client(key_count=1, key_names="StatusBotKey", throttle_limit=20)
            await self.coc_client.login(COC_EMAIL, COC_PASSWORD)
            print("StatusCla: Conectado ao CoC API.")
        except Exception as e:
            print(f"StatusCla: Erro login CoC: {e}")
            self.coc_client = None

    def cog_unload(self):
        self.update_status_task.cancel()
        if self.coc_client:
            asyncio.create_task(self.coc_client.close())

    async def find_channels_in_guild(self, guild):
        """
        Procura a categoria e os canais DENTRO de um servidor específico.
        Retorna: (Sucesso: bool, Mensagem/Dados)
        """
        category = None
        
        # 1. Procura categoria pelo NOME (Flexível)
        for cat in guild.categories:
            nome = cat.name.lower()
            # Procura "status" E "clã" (ou "cla")
            if "status" in nome and ("clã" in nome or "cla" in nome):
                category = cat
                break
        
        if not category:
            return False, f"Categoria 'Status do Clã' não encontrada no servidor '{guild.name}'."

        # 2. Mapeamento de Emojis
        emoji_map = {
            "👥": "membros",
            "⭐": "nivel",
            "🏆": "trofeus",
            "⚔️": "guerras",
            "🔥": "streak",
            "🕒": "data"
        }

        found_channels = {}
        
        # 3. Procura canais dentro da categoria
        # Tenta pegar voice_channels, se não tiver, pega channels geral
        canais_para_checar = category.voice_channels if hasattr(category, 'voice_channels') else category.channels

        for channel in canais_para_checar:
            for emoji, key in emoji_map.items():
                if emoji in channel.name:
                    found_channels[key] = channel
        
        # Se achou pelo menos 3 canais, considera válido
        if len(found_channels) >= 3:
            return True, found_channels
        
        return False, f"Categoria '{category.name}' encontrada, mas não achei os canais com emojis (👥, ⭐, etc)."

    async def update_guild_status(self, guild, found_channels):
        """Executa a atualização para um servidor específico."""
        try:
            # Garante conexão CoC
            await self.connect_coc()
            if not self.coc_client: return "Falha conexão CoC"

            clan = await self.coc_client.get_clan(CLAN_TAG)
            
            tz = pytz.timezone('America/Sao_Paulo')
            horario = datetime.now(tz).strftime("%d/%m %H:%M")

            stats = {
                "membros": f"👥 Membros: {clan.member_count}/50",
                "nivel": f"⭐ Nível: {clan.level}",
                "trofeus": f"🏆 Troféus: {clan.points}",
                "guerras": f"⚔️ Guerras Ganhas: {clan.war_wins}",
                "streak": f"🔥 Win Streak: {clan.war_win_streak}",
                "data": f"🕒 Atualizado: {horario}"
            }

            count = 0
            for key, channel in found_channels.items():
                new_name = stats.get(key)
                if new_name and channel.name != new_name:
                    await channel.edit(name=new_name)
                    count += 1
                    await asyncio.sleep(1.5) # Evita rate limit
            
            return f"Atualizado ({count} canais) em '{guild.name}'."

        except Exception as e:
            traceback.print_exc()
            return f"Erro em '{guild.name}': {e}"

    # --- TAREFA AUTOMÁTICA ---
    @tasks.loop(minutes=10)
    async def update_status_task(self):
        # Itera sobre TODOS os servidores que o bot está
        for guild in self.client.guilds:
            success, result = await self.find_channels_in_guild(guild)
            if success:
                # Se achou a categoria neste servidor, atualiza
                await self.update_guild_status(guild, result)
            # Se não achou, ignora (provavelmente é o outro servidor que não tem status)

    @update_status_task.before_loop
    async def before_update(self):
        await self.client.wait_until_ready()

    # --- COMANDOS ---
    @app_commands.command(name="setup-status", description="[Admin] Cria o painel de status.")
    @commands.has_permissions(administrator=True)
    async def setup_status(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        # ... Lógica de criação omitida para focar no fix, mas o comando existe ...
        await interaction.followup.send("⚠️ Use `/force-update` para conectar o painel.", ephemeral=True)

    @app_commands.command(name="force-update", description="[Admin] Força atualização NESTE servidor.")
    @commands.has_permissions(administrator=True)
    async def force_update(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        # 1. Procura SOMENTE no servidor onde o comando foi digitado
        guild = interaction.guild
        success, result = await self.find_channels_in_guild(guild)

        if success:
            found_channels = result
            # 2. Atualiza
            msg_update = await self.update_guild_status(guild, found_channels)
            
            embed = discord.Embed(title="✅ Sucesso", description=msg_update, color=discord.Color.green())
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            # Mostra o erro específico deste servidor
            embed = discord.Embed(title="❌ Erro", description=result, color=discord.Color.red())
            embed.set_footer(text=f"Servidor analisado: {guild.name}")
            await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(client: commands.Bot):
    await client.add_cog(StatusCla(client))
