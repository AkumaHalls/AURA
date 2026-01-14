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

# Nome da categoria que o bot vai procurar caso se perca
CATEGORY_NAME = "📊 Status do Clã"

class StatusCla(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client
        self.coc_client = None
        self.channel_ids = {} 
        self.update_status_task.start()

    async def connect_coc(self):
        """Gerencia conexão CoC e reconexão se cair."""
        try:
            if self.coc_client and self.coc_client.http.session:
                 return # Já conectado

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

    async def find_channels_automatically(self):
        """Tenta encontrar os canais automaticamente pelo ÍCONE e CATEGORIA."""
        if not self.client.guilds: return False
        
        guild = self.client.guilds[0] # Pega o primeiro servidor
        category = discord.utils.get(guild.categories, name=CATEGORY_NAME)
        
        if not category:
            return False

        # Mapeamento: Emoji -> Chave Interna
        emoji_map = {
            "👥": "membros_id",
            "⭐": "nivel_id",
            "🏆": "trofeus_id",
            "⚔️": "guerras_id",
            "🔥": "streak_id",
            "🕒": "data_id"
        }

        found = {}
        for channel in category.voice_channels:
            # Pega o primeiro caractere do nome (o emoji)
            first_char = channel.name.split(" ")[0]
            if first_char in emoji_map:
                found[emoji_map[first_char]] = channel.id
        
        # Só atualiza se achou a maioria dos canais
        if len(found) >= 3:
            self.channel_ids = found
            self.channel_ids["guild_id"] = guild.id
            print(f"StatusCla: Recuperação automática bem sucedida! Canais encontrados: {len(found)}")
            return True
        
        return False

    # --- TAREFA PRINCIPAL ---
    @tasks.loop(minutes=10)
    async def update_status_task(self):
        try:
            # 1. Tenta recuperar os canais se a lista estiver vazia (Pós-Restart)
            if not self.channel_ids:
                if not await self.find_channels_automatically():
                    print("StatusCla: Não foi possível encontrar os canais. Verifique se a categoria '📊 Status do Clã' existe.")
                    return

            # 2. Conecta no CoC
            await self.connect_coc()
            if not self.coc_client: return

            # 3. Pega dados do Clã
            clan = await self.coc_client.get_clan(CLAN_TAG)
            
            guild_id = self.channel_ids.get("guild_id")
            guild = self.client.get_guild(guild_id)
            if not guild: return

            tz = pytz.timezone('America/Sao_Paulo')
            horario = datetime.now(tz).strftime("%d/%m %H:%M")

            # 4. Define os novos nomes
            stats = {
                "membros_id": f"👥 Membros: {clan.member_count}/50",
                "nivel_id": f"⭐ Nível: {clan.level}",
                "trofeus_id": f"🏆 Troféus: {clan.points}",
                "guerras_id": f"⚔️ Guerras Ganhas: {clan.war_wins}",
                "streak_id": f"🔥 Win Streak: {clan.war_win_streak}",
                "data_id": f"🕒 Atualizado: {horario}"
            }

            # 5. Aplica a atualização
            for key, new_name in stats.items():
                cid = self.channel_ids.get(key)
                if cid:
                    channel = guild.get_channel(cid)
                    # Verifica se precisa editar para evitar rate limit do Discord
                    if channel and channel.name != new_name:
                        await channel.edit(name=new_name)
                        await asyncio.sleep(1.5) # Pausa pequena entre edições

        except Exception as e:
            print(f"StatusCla Erro: {e}")
            traceback.print_exc()

    @update_status_task.before_loop
    async def before_update(self):
        await self.client.wait_until_ready()

    # --- COMANDOS ---
    @app_commands.command(name="setup-status", description="[Admin] Cria o painel de status (Recria se deletado).")
    @commands.has_permissions(administrator=True)
    async def setup_status(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        
        # Permissões: Ninguém conecta, todos veem
        overwrites = {guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=True)}

        try:
            # Verifica se já existe a categoria para não duplicar
            existing_cat = discord.utils.get(guild.categories, name=CATEGORY_NAME)
            if existing_cat:
                cat = existing_cat
                await interaction.followup.send("⚠️ A categoria já existe. Vou tentar recriar apenas os canais que faltam...", ephemeral=True)
            else:
                cat = await guild.create_category(CATEGORY_NAME, overwrites=overwrites)

            # Criação dos canais
            c_mem = await guild.create_voice_channel("👥 Carregando...", category=cat)
            c_niv = await guild.create_voice_channel("⭐ Carregando...", category=cat)
            c_tro = await guild.create_voice_channel("🏆 Carregando...", category=cat)
            c_gue = await guild.create_voice_channel("⚔️ Carregando...", category=cat)
            c_str = await guild.create_voice_channel("🔥 Carregando...", category=cat)
            c_dat = await guild.create_voice_channel("🕒 Aguardando...", category=cat)

            # Salva na memória
            self.channel_ids = {
                "guild_id": guild.id, 
                "membros_id": c_mem.id, "nivel_id": c_niv.id,
                "trofeus_id": c_tro.id, "guerras_id": c_gue.id,
                "streak_id": c_str.id, "data_id": c_dat.id
            }
            
            # Força uma atualização imediata
            self.update_status_task.restart()
            
            await interaction.followup.send("✅ Painel criado com sucesso! Ele deve atualizar em instantes.", ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(f"❌ Erro ao criar canais: {e}", ephemeral=True)

    @app_commands.command(name="force-update", description="[Admin] Força uma atualização imediata dos status.")
    @commands.has_permissions(administrator=True)
    async def force_update(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        self.update_status_task.restart()
        await interaction.followup.send("🔄 Atualização forçada iniciada.", ephemeral=True)

async def setup(client: commands.Bot):
    await client.add_cog(StatusCla(client))
