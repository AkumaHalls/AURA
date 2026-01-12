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

# Carrega variáveis do arquivo .env
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# Tenta pegar as credenciais do CoC. 
COC_EMAIL = os.getenv("COC_EMAIL")
COC_PASSWORD = os.getenv("COC_PASSWORD")
CLAN_TAG = os.getenv("CLAN_TAG")

# Arquivo onde o bot salva os IDs dos canais criados para não perder a referência
CONFIG_FILE = "status_channels.json"

class StatusCla(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client
        self.coc_client = None
        self.channel_ids = self.load_config()
        # Inicia a tarefa de atualização automática
        self.update_status_task.start()

    def load_config(self):
        """Carrega a configuração salva dos canais."""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def save_config(self):
        """Salva a configuração dos canais."""
        with open(CONFIG_FILE, "w") as f:
            json.dump(self.channel_ids, f, indent=4)

    async def connect_coc(self):
        """Gerencia a conexão com a API do Clash of Clans."""
        if self.coc_client:
            return

        try:
            # Login simples com email e senha
            self.coc_client = coc.Client(key_count=1, key_names="StatusBotKey", throttle_limit=20)
            await self.coc_client.login(COC_EMAIL, COC_PASSWORD)
            print("StatusCla: Conectado à API do Clash of Clans.")
        except Exception as e:
            print(f"StatusCla: Erro ao conectar no CoC: {e}")
            self.coc_client = None 

    def cog_unload(self):
        """Limpeza ao desligar o bot."""
        self.update_status_task.cancel()
        if self.coc_client:
            asyncio.create_task(self.coc_client.close())

    # --- TAREFA AUTOMÁTICA (Loop a cada 10 minutos) ---
    @tasks.loop(minutes=10)
    async def update_status_task(self):
        # Só roda se houver canais configurados
        if not self.channel_ids:
            return

        await self.connect_coc()
        if not self.coc_client:
            print("StatusCla: Cliente CoC não conectado. Pulando atualização.")
            return

        try:
            # Busca os dados do clã
            clan = await self.coc_client.get_clan(CLAN_TAG)
            
            guild_id = self.channel_ids.get("guild_id")
            guild = self.client.get_guild(guild_id)

            if not guild:
                print(f"StatusCla: Servidor ID {guild_id} não encontrado.")
                return

            # Pega o horário atual em SP
            tz = pytz.timezone('America/Sao_Paulo')
            horario_atual = datetime.now(tz).strftime("%d/%m às %H:%M")

            # Lista dos dados para atualizar
            stats = {
                "membros_id": f"👥 Membros: {clan.member_count}/50",
                "nivel_id": f"⭐ Nível: {clan.level}",
                "trofeus_id": f"🏆 Troféus: {clan.points}",
                "guerras_id": f"⚔️ Guerras Ganhas: {clan.war_wins}",
                "streak_id": f"🔥 Win Streak: {clan.war_win_streak}",
                "data_id": f"🕒 Atualizado: {horario_atual}" # NOVO CANAL
            }

            # Atualiza cada canal
            for key, new_name in stats.items():
                channel_id = self.channel_ids.get(key)
                if channel_id:
                    channel = guild.get_channel(channel_id)
                    if channel:
                        # Verifica se o nome mudou para evitar spam na API do Discord
                        if channel.name != new_name:
                            await channel.edit(name=new_name)
                            # Pequeno delay para evitar Rate Limit do Discord
                            await asyncio.sleep(1) 
                    else:
                        print(f"StatusCla: Canal {key} (ID: {channel_id}) não encontrado no servidor.")

        except Exception as e:
            print(f"StatusCla: Erro ao atualizar status: {e}")
            traceback.print_exc() # Imprime o erro completo no log

    # Adicionado para garantir que o bot esteja pronto antes de começar
    @update_status_task.before_loop
    async def before_update_status(self):
        await self.client.wait_until_ready()

    # Adicionado para mostrar erros críticos caso o loop quebre
    @update_status_task.error
    async def update_status_error(self, error):
        print(f"StatusCla: O loop de atualização parou devido a um erro:")
        traceback.print_exception(type(error), error, error.__traceback__)

    # --- COMANDO SLASH: SETUP ---
    @app_commands.command(name="setup-status", description="[Admin] Cria o painel de status do clã automaticamente.")
    @commands.has_permissions(administrator=True)
    async def setup_status(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)

        if not COC_EMAIL or not CLAN_TAG:
            await interaction.followup.send("❌ Erro: Configure `COC_EMAIL`, `COC_PASSWORD` e `CLAN_TAG` no seu `.env` primeiro.", ephemeral=True)
            return

        guild = interaction.guild
        
        # Configura permissão para ninguém entrar nos canais de voz
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(connect=False)
        }
        
        try:
            # Cria a categoria
            categoria = await guild.create_category("📊 Status do Clã", overwrites=overwrites)
            
            # Cria os canais iniciais
            c_membros = await guild.create_voice_channel("👥 Carregando...", category=categoria)
            c_nivel = await guild.create_voice_channel("⭐ Carregando...", category=categoria)
            c_trofeus = await guild.create_voice_channel("🏆 Carregando...", category=categoria)
            c_guerras = await guild.create_voice_channel("⚔️ Carregando...", category=categoria)
            c_streak = await guild.create_voice_channel("🔥 Carregando...", category=categoria)
            # Cria o canal de data/hora
            c_data = await guild.create_voice_channel("🕒 Aguardando atualização...", category=categoria)

            # Salva os IDs no arquivo json
            self.channel_ids = {
                "guild_id": guild.id,
                "category_id": categoria.id,
                "membros_id": c_membros.id,
                "nivel_id": c_nivel.id,
                "trofeus_id": c_trofeus.id,
                "guerras_id": c_guerras.id,
                "streak_id": c_streak.id,
                "data_id": c_data.id # Salva o ID do novo canal
            }
            self.save_config()
            
            # Força a atualização imediata
            if self.update_status_task.is_running():
                self.update_status_task.restart()
            else:
                self.update_status_task.start()

            await interaction.followup.send("✅ Painel de Status criado! Aguarde alguns instantes para os nomes atualizarem.", ephemeral=True)

        except Exception as e:
            await interaction.followup.send(f"❌ Erro ao criar canais: {e}", ephemeral=True)

    # --- COMANDO SLASH: DELETAR ---
    @app_commands.command(name="delete-status", description="[Admin] Remove o painel de status da memória do bot.")
    @commands.has_permissions(administrator=True)
    async def delete_status(self, interaction: discord.Interaction):
        self.channel_ids = {}
        self.save_config()
        await interaction.response.send_message("✅ O bot parou de atualizar o painel. Você pode deletar os canais manualmente agora.", ephemeral=True)

async def setup(client: commands.Bot):
    await client.add_cog(StatusCla(client))
