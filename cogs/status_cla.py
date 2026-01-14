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

# Texto base para procurar a categoria (ignora emojis)
CATEGORY_PARTIAL_NAME = "Status do Clã"

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
        """Tenta encontrar os canais automaticamente procurando por 'Status do Clã'."""
        if not self.client.guilds: 
            print("StatusCla: Nenhum servidor encontrado.")
            return False
        
        guild = self.client.guilds[0] # Pega o primeiro servidor
        
        # 1. Procura a Categoria pelo nome parcial (contém "Status do Clã")
        category = None
        for cat in guild.categories:
            if CATEGORY_PARTIAL_NAME in cat.name:
                category = cat
                break
        
        if not category:
            print(f"StatusCla: Categoria contendo '{CATEGORY_PARTIAL_NAME}' não encontrada.")
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
        # Procura canais dentro da categoria
        for channel in category.voice_channels:
            # Verifica se o emoji está no nome do canal
            for emoji, key in emoji_map.items():
                if emoji in channel.name:
                    found[key] = channel.id
        
        # Só atualiza se achou a maioria dos canais
        if len(found) >= 3:
            self.channel_ids = found
            self.channel_ids["guild_id"] = guild.id
            print(f"StatusCla: Recuperação automática bem sucedida! Canais encontrados: {len(found)}")
            return True
        
        print(f"StatusCla: Canais insuficientes encontrados na categoria '{category.name}'. Encontrados: {len(found)}")
        return False

    async def perform_update_logic(self):
        """Lógica separada de atualização para usar no loop e no force-update"""
        # 1. Tenta recuperar os canais se a lista estiver vazia
        if not self.channel_ids:
            if not await self.find_channels_automatically():
                return "❌ Erro: Não encontrei a categoria 'Status do Clã' ou os canais."

        # 2. Conecta no CoC
        await self.connect_coc()
        if not self.coc_client: 
            return "❌ Erro: Falha na conexão com a API do Clash."

        try:
            # 3. Pega dados do Clã
            clan = await self.coc_client.get_clan(CLAN_TAG)
            
            guild_id = self.channel_ids.get("guild_id")
            guild = self.client.get_guild(guild_id)
            if not guild: return "❌ Erro: Servidor Discord não encontrado."

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

            updated_count = 0
            # 5. Aplica a atualização
            for key, new_name in stats.items():
                cid = self.channel_ids.get(key)
                if cid:
                    channel = guild.get_channel(cid)
                    if channel and channel.name != new_name:
                        await channel.edit(name=new_name)
                        updated_count += 1
                        await asyncio.sleep(1.5) 
            
            if updated_count > 0:
                return f"✅ Sucesso! {updated_count} canais atualizados para {horario}."
            else:
                return f"✅ Dados verificados. Nenhuma alteração necessária (tudo atualizado)."

        except Exception as e:
            traceback.print_exc()
            return f"❌ Erro durante atualização: {e}"

    # --- TAREFA PRINCIPAL ---
    @tasks.loop(minutes=10)
    async def update_status_task(self):
        await self.perform_update_logic()

    @update_status_task.before_loop
    async def before_update(self):
        await self.client.wait_until_ready()

    # --- COMANDOS ---
    @app_commands.command(name="setup-status", description="[Admin] Cria o painel de status.")
    @commands.has_permissions(administrator=True)
    async def setup_status(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        overwrites = {guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=True)}

        try:
            # Procura categoria existente parcial
            cat = None
            for c in guild.categories:
                if CATEGORY_PARTIAL_NAME in c.name:
                    cat = c
                    break
            
            if cat:
                await interaction.followup.send(f"⚠️ Encontrei a categoria '{cat.name}'. Tentando usar ela...", ephemeral=True)
            else:
                cat = await guild.create_category("📊 Status do Clã", overwrites=overwrites)

            # Cria canais
            c_mem = await guild.create_voice_channel("👥 Carregando...", category=cat)
            c_niv = await guild.create_voice_channel("⭐ Carregando...", category=cat)
            c_tro = await guild.create_voice_channel("🏆 Carregando...", category=cat)
            c_gue = await guild.create_voice_channel("⚔️ Carregando...", category=cat)
            c_str = await guild.create_voice_channel("🔥 Carregando...", category=cat)
            c_dat = await guild.create_voice_channel("🕒 Aguardando...", category=cat)

            self.channel_ids = {
                "guild_id": guild.id, 
                "membros_id": c_mem.id, "nivel_id": c_niv.id,
                "trofeus_id": c_tro.id, "guerras_id": c_gue.id,
                "streak_id": c_str.id, "data_id": c_dat.id
            }
            
            self.update_status_task.restart()
            await interaction.followup.send("✅ Painel configurado! A primeira atualização ocorre em instantes.", ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(f"❌ Erro ao criar: {e}", ephemeral=True)

    @app_commands.command(name="force-update", description="[Admin] Força atualização e mostra diagnóstico.")
    @commands.has_permissions(administrator=True)
    async def force_update(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        # Executa a lógica e pega a mensagem de resultado
        resultado = await self.perform_update_logic()
        await interaction.followup.send(f"📢 **Relatório de Atualização:**\n{resultado}", ephemeral=True)

async def setup(client: commands.Bot):
    await client.add_cog(StatusCla(client))
