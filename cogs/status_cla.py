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
        """
        Tenta encontrar os canais.
        Se interaction for passado, envia logs de debug para o admin ver o que está havendo.
        """
        if not self.client.guilds: return False, "Bot não está em nenhum servidor."
        
        guild = self.client.guilds[0]
        
        # 1. Busca Flexível (Ignora Case e Emojis)
        category = None
        categorias_visiveis = [] # Para debug

        for cat in guild.categories:
            nome_limpo = cat.name.lower() # Transforma tudo em minúsculo
            categorias_visiveis.append(cat.name) # Guarda o nome original para mostrar no erro
            
            # Se tiver "status" E "clã" no nome, achamos!
            if "status" in nome_limpo and "clã" in nome_limpo:
                category = cat
                break
            # Fallback: Tenta sem o til (clã -> cla) caso a codificação esteja estranha
            if "status" in nome_limpo and "cla" in nome_limpo:
                category = cat
                break
        
        if not category:
            lista_str = "\n".join(categorias_visiveis[:10]) # Mostra as 10 primeiras
            return False, f"Não encontrei a categoria 'Status do Clã'.\n\n🔎 **O que o bot está vendo:**\n{lista_str}\n\n⚠️ **Dica:** Verifique se o Bot tem permissão 'Ver Canal' na categoria."

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
        # Procura canais dentro da categoria encontrada
        canais_vistos = []
        for channel in category.voice_channels:
            canais_vistos.append(channel.name)
            for emoji, key in emoji_map.items():
                if emoji in channel.name:
                    found[key] = channel.id
        
        if len(found) >= 3:
            self.channel_ids = found
            self.channel_ids["guild_id"] = guild.id
            return True, f"Sucesso! Encontrei a categoria '{category.name}' e {len(found)} canais."
        
        return False, f"Achei a categoria '{category.name}', mas não os canais.\nCanais vistos: {', '.join(canais_vistos)}"

    async def perform_update_logic(self, interaction=None):
        # 1. Tenta recuperar canais (passando interaction para debug se houver)
        if not self.channel_ids:
            success, msg = await self.find_channels_automatically(interaction)
            if not success:
                return f"❌ Erro de Localização: {msg}"

        # 2. Conecta no CoC
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

    # --- TAREFA AUTOMÁTICA ---
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
            # Tenta achar categoria existente
            cat = None
            for c in guild.categories:
                if "status" in c.name.lower() and "clã" in c.name.lower():
                    cat = c
                    break
            
            if cat:
                await interaction.followup.send(f"⚠️ Já existe a categoria '{cat.name}'.", ephemeral=True)
            else:
                cat = await guild.create_category("📊 Status do Clã", overwrites=overwrites)
                # Cria canais
                c_mem = await guild.create_voice_channel("👥 Carregando...", category=cat)
                c_niv = await guild.create_voice_channel("⭐ Carregando...", category=cat)
                c_tro = await guild.create_voice_channel("🏆 Carregando...", category=cat)
                c_gue = await guild.create_voice_channel("⚔️ Carregando...", category=cat)
                c_str = await guild.create_voice_channel("🔥 Carregando...", category=cat)
                c_dat = await guild.create_voice_channel("🕒 Aguardando...", category=cat)

            # Força update para pegar os IDs
            resultado = await self.perform_update_logic(interaction)
            self.update_status_task.restart()
            
            await interaction.followup.send(f"✅ Setup finalizado!\nResultado: {resultado}", ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(f"❌ Erro: {e}", ephemeral=True)

    @app_commands.command(name="force-update", description="[Admin] Força atualização e mostra diagnóstico.")
    @commands.has_permissions(administrator=True)
    async def force_update(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        # Passa a interaction para que o log de erro saia detalhado
        resultado = await self.perform_update_logic(interaction)
        
        # Cria um Embed bonitinho com o resultado
        color = discord.Color.green() if "✅" in resultado else discord.Color.red()
        embed = discord.Embed(title="Relatório de Atualização", description=resultado, color=color)
        
        await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(client: commands.Bot):
    await client.add_cog(StatusCla(client))
