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

# --- COLOQUE O ID DA CATEGORIA AQUI EM BAIXO ---
# Exemplo: ID_CATEGORIA_FIXA = 1328134880193941575
ID_CATEGORIA_FIXA = 1460298995279855658  # <--- COLE O ID AQUI (SUBSTITUA O 0)

class StatusCla(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client
        self.coc_client = None
        self.channel_ids = {} 
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

    async def find_channels_automatically(self, interaction=None):
        if not self.client.guilds: return False, "Bot não está em nenhum servidor."
        
        guild = self.client.guilds[0]
        category = None

        # 1. TENTA PELO ID FIXO (PRIORIDADE MÁXIMA)
        if ID_CATEGORIA_FIXA != 0:
            category = guild.get_channel(ID_CATEGORIA_FIXA)
            if not category:
                return False, f"Configurei o ID {ID_CATEGORIA_FIXA}, mas não achei essa categoria no servidor."
        
        # 2. TENTA PELO NOME (FALLBACK)
        if not category:
            for cat in guild.categories:
                # Procura 'status' E 'clã' (ou 'cla') ignorando maiúsculas
                if "status" in cat.name.lower() and ("clã" in cat.name.lower() or "cla" in cat.name.lower()):
                    category = cat
                    break
        
        if not category:
            # Lista TODAS as categorias para debug (sem limite de 10)
            lista_str = "\n".join([f"{c.name} (ID: {c.id})" for c in guild.categories])
            return False, f"Não encontrei a categoria.\n\n🔎 **Categorias que eu vejo:**\n{lista_str}"

        # Mapeamento
        emoji_map = {
            "👥": "membros_id",
            "⭐": "nivel_id",
            "🏆": "trofeus_id",
            "⚔️": "guerras_id",
            "🔥": "streak_id",
            "🕒": "data_id"
        }

        found = {}
        canais_vistos = []
        
        # Procura canais dentro da categoria
        for channel in category.voice_channels:
            canais_vistos.append(channel.name)
            for emoji, key in emoji_map.items():
                if emoji in channel.name:
                    found[key] = channel.id
        
        # Se achou pelo menos 3 canais, considera sucesso
        if len(found) >= 3:
            self.channel_ids = found
            self.channel_ids["guild_id"] = guild.id
            return True, f"Sucesso! Usando categoria '{category.name}' (ID: {category.id})."
        
        return False, f"Achei a categoria '{category.name}', mas os canais não batem.\nCanais lá dentro: {', '.join(canais_vistos)}"

    async def perform_update_logic(self, interaction=None):
        # 1. Tenta localizar canais
        if not self.channel_ids:
            success, msg = await self.find_channels_automatically(interaction)
            if not success:
                return f"❌ {msg}"

        # 2. Conecta CoC
        await self.connect_coc()
        if not self.coc_client: 
            return "❌ Erro: Falha na conexão com a API do Clash."

        try:
            # 3. Pega dados
            clan = await self.coc_client.get_clan(CLAN_TAG)
            
            guild_id = self.channel_ids.get("guild_id")
            guild = self.client.get_guild(guild_id)
            if not guild: return "❌ Erro: Servidor Discord sumiu."

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

            updated_count = 0
            for key, new_name in stats.items():
                cid = self.channel_ids.get(key)
                if cid:
                    channel = guild.get_channel(cid)
                    if channel and channel.name != new_name:
                        await channel.edit(name=new_name)
                        updated_count += 1
                        await asyncio.sleep(1.5) 
            
            return f"✅ Atualização concluída! {updated_count} canais modificados. (Hora: {horario})"

        except Exception as e:
            traceback.print_exc()
            return f"❌ Erro durante atualização: {e}"

    # --- TAREFAS E COMANDOS ---
    @tasks.loop(minutes=10)
    async def update_status_task(self):
        await self.perform_update_logic()

    @update_status_task.before_loop
    async def before_update(self):
        await self.client.wait_until_ready()

    @app_commands.command(name="setup-status", description="[Admin] Recria o painel se necessário.")
    @commands.has_permissions(administrator=True)
    async def setup_status(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        # ... (lógica de criação mantida simples, foco no update)
        await interaction.followup.send("⚠️ Use `/force-update` para conectar aos canais existentes.", ephemeral=True)

    @app_commands.command(name="force-update", description="[Admin] Força atualização e mostra diagnóstico.")
    @commands.has_permissions(administrator=True)
    async def force_update(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        resultado = await self.perform_update_logic(interaction)
        
        # Embed grande para caber todo o log se precisar
        embed = discord.Embed(title="Relatório de Atualização", description=resultado[:4000], color=discord.Color.blurple())
        await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(client: commands.Bot):
    await client.add_cog(StatusCla(client))
