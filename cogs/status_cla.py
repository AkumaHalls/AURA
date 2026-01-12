import discord
import asyncio
import json
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

CONFIG_FILE = "status_channels.json"
CATEGORY_NAME = "📊 Status do Clã"

class StatusCla(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client
        self.coc_client = None
        self.channel_ids = {} # Começa vazio, carrega depois
        self.update_status_task.start()

    def load_config(self):
        """Tenta carregar do arquivo. Se falhar, retorna vazio."""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def save_config(self):
        """Salva a configuração no disco (útil enquanto a VPS não reinicia)."""
        with open(CONFIG_FILE, "w") as f:
            json.dump(self.channel_ids, f, indent=4)

    async def try_recover_config(self):
        """Tenta encontrar os canais no Discord se o arquivo de config sumiu."""
        print("StatusCla: Tentando recuperar configuração dos canais existentes no Discord...")
        
        # Procura no primeiro servidor disponível (ou configure um ID fixo se preferir)
        guild = self.client.guilds[0] if self.client.guilds else None
        if not guild:
            return False

        # Procura a categoria pelo nome
        category = discord.utils.get(guild.categories, name=CATEGORY_NAME)
        if not category:
            print("StatusCla: Categoria não encontrada. Necessário rodar /setup-status.")
            return False

        new_config = {"guild_id": guild.id, "category_id": category.id}
        
        # Mapeia emojis para chaves de config
        emoji_map = {
            "👥": "membros_id",
            "⭐": "nivel_id",
            "🏆": "trofeus_id",
            "⚔️": "guerras_id",
            "🔥": "streak_id",
            "🕒": "data_id"
        }

        found_count = 0
        for channel in category.voice_channels:
            # Verifica o primeiro caractere (emoji) do nome do canal
            first_char = channel.name.split(" ")[0] # Pega o que está antes do primeiro espaço
            
            if first_char in emoji_map:
                key = emoji_map[first_char]
                new_config[key] = channel.id
                found_count += 1

        if found_count >= 3: # Se achou pelo menos 3 canais, considera recuperado
            self.channel_ids = new_config
            self.save_config()
            print(f"StatusCla: Recuperação bem-sucedida! {found_count} canais reconectados.")
            return True
        
        return False

    async def connect_coc(self):
        """Gerencia conexão CoC."""
        if self.coc_client: return
        try:
            self.coc_client = coc.Client(key_count=1, key_names="StatusBotKey", throttle_limit=20)
            await self.coc_client.login(COC_EMAIL, COC_PASSWORD)
            print("StatusCla: Conectado ao CoC.")
        except Exception as e:
            print(f"StatusCla: Erro login CoC: {e}")
            self.coc_client = None

    def cog_unload(self):
        self.update_status_task.cancel()
        if self.coc_client:
            asyncio.create_task(self.coc_client.close())

    # --- TAREFA ---
    @tasks.loop(minutes=10)
    async def update_status_task(self):
        # 1. Se não tem configuração, tenta carregar do arquivo
        if not self.channel_ids:
            self.channel_ids = self.load_config()
        
        # 2. Se ainda não tem configuração (arquivo sumiu no restart), tenta recuperar do Discord
        if not self.channel_ids:
            if not await self.try_recover_config():
                # Se falhar a recuperação, para por aqui até alguém rodar setup
                return

        await self.connect_coc()
        if not self.coc_client: return

        try:
            clan = await self.coc_client.get_clan(CLAN_TAG)
            guild_id = self.channel_ids.get("guild_id")
            guild = self.client.get_guild(guild_id)

            if not guild: return

            tz = pytz.timezone('America/Sao_Paulo')
            horario = datetime.now(tz).strftime("%d/%m %H:%M")

            stats = {
                "membros_id": f"👥 Membros: {clan.member_count}/50",
                "nivel_id": f"⭐ Nível: {clan.level}",
                "trofeus_id": f"🏆 Troféus: {clan.points}",
                "guerras_id": f"⚔️ Guerras Ganhas: {clan.war_wins}",
                "streak_id": f"🔥 Win Streak: {clan.war_win_streak}",
                "data_id": f"🕒 Atualizado: {horario}"
            }

            for key, name in stats.items():
                cid = self.channel_ids.get(key)
                if cid:
                    channel = guild.get_channel(cid)
                    if channel and channel.name != name:
                        await channel.edit(name=name)
                        await asyncio.sleep(1)

        except Exception as e:
            print(f"Erro update: {e}")
            traceback.print_exc()

    @update_status_task.before_loop
    async def before_update(self):
        await self.client.wait_until_ready()

    # --- COMANDOS ---
    @app_commands.command(name="setup-status", description="[Admin] Cria o painel de status.")
    @commands.has_permissions(administrator=True)
    async def setup_status(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        overwrites = {guild.default_role: discord.PermissionOverwrite(connect=False)}

        try:
            cat = await guild.create_category(CATEGORY_NAME, overwrites=overwrites)
            c_mem = await guild.create_voice_channel("👥 Carregando...", category=cat)
            c_niv = await guild.create_voice_channel("⭐ Carregando...", category=cat)
            c_tro = await guild.create_voice_channel("🏆 Carregando...", category=cat)
            c_gue = await guild.create_voice_channel("⚔️ Carregando...", category=cat)
            c_str = await guild.create_voice_channel("🔥 Carregando...", category=cat)
            c_dat = await guild.create_voice_channel("🕒 Aguardando...", category=cat)

            self.channel_ids = {
                "guild_id": guild.id, "category_id": cat.id,
                "membros_id": c_mem.id, "nivel_id": c_niv.id,
                "trofeus_id": c_tro.id, "guerras_id": c_gue.id,
                "streak_id": c_str.id, "data_id": c_dat.id
            }
            self.save_config()
            self.update_status_task.restart()
            await interaction.followup.send("✅ Painel criado!", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Erro: {e}", ephemeral=True)

    @app_commands.command(name="delete-status", description="[Admin] Deleta painel.")
    @commands.has_permissions(administrator=True)
    async def delete_status(self, interaction: discord.Interaction):
        self.channel_ids = {}
        self.save_config()
        await interaction.response.send_message("✅ Parado. Delete os canais manualmente.", ephemeral=True)

async def setup(client: commands.Bot):
    await client.add_cog(StatusCla(client))
