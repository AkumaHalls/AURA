import discord
import json
import os
import io
import random
from datetime import datetime, timedelta
from discord.ext import commands
from discord import app_commands, ui

# --- CONFIGURAÇÃO ---
ID_CANAL_BACKUP = 123456789012345678 # ID do canal de logs

# --- CLASSES DE INTERFACE ---
class IntroView(ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.confirmado = False

    @ui.button(label="Começar Avaliação", style=discord.ButtonStyle.green, emoji="✅")
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmado = True
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()

    @ui.button(label="Cancelar", style=discord.ButtonStyle.red, emoji="✖️")
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmado = False
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="❌ Avaliação cancelada.", view=self, embed=None)
        self.stop()

class ProvaView(ui.View):
    def __init__(self, questao, total, atual):
        TEMPO_POR_QUESTAO = 120
        super().__init__(timeout=TEMPO_POR_QUESTAO) 
        self.value = None
        self.questao = questao
        timestamp_fim = int(datetime.now().timestamp() + TEMPO_POR_QUESTAO)
        
        alternativas_com_indice = list(enumerate(questao['alternativas']))
        random.shuffle(alternativas_com_indice)
        
        options = []
        for i, (indice_original, texto) in enumerate(alternativas_com_indice):
            letra = chr(65 + i) 
            options.append(discord.SelectOption(label=f"{letra}) {texto[:95]}", value=str(indice_original)))

        self.select = discord.ui.Select(placeholder="Selecione a resposta correta...", options=options)
        self.select.callback = self.callback
        self.add_item(self.select)

        self.embed = discord.Embed(
            title=f"📝 Questão {atual}/{total}",
            description=f"**{questao['pergunta']}**\n\n⏳ **Tempo restante:** <t:{timestamp_fim}:R>",
            color=discord.Color.blue()
        )
        self.embed.set_footer(text=f"Selecione a melhor opção abaixo.")

    async def callback(self, interaction: discord.Interaction):
        self.value = int(self.select.values[0])
        self.select.disabled = True
        await interaction.response.defer()
        self.stop()

# --- CLASSE PRINCIPAL ---
class SistemaProva(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client
        self.cooldowns = {} 
        self.questoes_data = {} 

    async def carregar_provas(self):
        """Carrega o JSON assumindo que ele está corretamente em UTF-8"""
        try:
            # Lógica inteligente para achar o arquivo na raiz
            caminhos_tentativa = [
                "provas.json",
                os.path.join(os.getcwd(), "provas.json"),
                os.path.join(os.path.dirname(__file__), '..', 'provas.json')
            ]

            arquivo_encontrado = None
            for caminho in caminhos_tentativa:
                if os.path.exists(caminho):
                    arquivo_encontrado = caminho
                    break
            
            if not arquivo_encontrado:
                print(f"SistemaProva: ERRO CRÍTICO - Arquivo 'provas.json' não encontrado na raiz.")
                return

            # Aqui lemos direto em UTF-8 (O padrão correto)
            with open(arquivo_encontrado, 'r', encoding='utf-8') as f:
                self.questoes_data = json.load(f)
            
            print(f"SistemaProva: Banco de questões carregado de: {arquivo_encontrado}")

        except Exception as e:
            print(f"SistemaProva: Erro ao ler arquivo: {e}")

    async def carregar_backup_cooldowns(self):
        await self.client.wait_until_ready()
        try:
            canal_backup = self.client.get_channel(ID_CANAL_BACKUP)
            if not canal_backup: return
            async for message in canal_backup.history(limit=1):
                if message.attachments:
                    arquivo = await message.attachments[0].read()
                    self.cooldowns = json.loads(arquivo.decode('utf-8'))
                    return
        except Exception:
            self.cooldowns = {}

    async def salvar_backup_cooldowns(self):
        try:
            canal_backup = self.client.get_channel(ID_CANAL_BACKUP)
            if not canal_backup: return
            arquivo_memoria = io.StringIO(json.dumps(self.cooldowns, indent=4))
            arquivo_discord = discord.File(arquivo_memoria, filename="cooldowns_backup.json")
            await canal_backup.send(content=f"Backup automático - {datetime.now()}", file=arquivo_discord)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_ready(self):
        await self.carregar_provas()
        await self.carregar_backup_cooldowns()

    @app_commands.command(name="iniciar-prova", description="Inicia o teste para Co-Líder.")
    async def iniciar_prova(self, interaction: discord.Interaction):
        # Se o banco estiver vazio, tenta carregar de novo
        if not self.questoes_data:
            await self.carregar_provas()
            if not self.questoes_data:
                await interaction.response.send_message("⚠️ **Erro:** O sistema de provas está offline (arquivo não carregado). Avise um Admin.", ephemeral=True)
                return

        user_id = str(interaction.user.id)
        if user_id in self.cooldowns:
            data_liberacao = datetime.fromisoformat(self.cooldowns[user_id])
            if datetime.now() < data_liberacao:
                ts = int(data_liberacao.timestamp())
                await interaction.response.send_message(f"❌ Você reprovou recentemente. Tente novamente <t:{ts}:R>.", ephemeral=True)
                return
            
        config = self.questoes_data['config']
        todas_questoes = self.questoes_data['questoes']
        
        qtd_questoes = config.get('total_questoes_aplicadas', 10)
        if len(todas_questoes) < qtd_questoes:
            questoes_selecionadas = todas_questoes
        else:
            questoes_selecionadas = random.sample(todas_questoes, qtd_questoes)

        try:
            dm_channel = await interaction.user.create_dm()
            
            embed_intro = discord.Embed(
                title="🛡️ Exame de Qualificação: Co-Líder B.A.D",
                description=f"Olá, {interaction.user.mention}.",
                color=discord.Color.gold()
            )
            embed_intro.add_field(name="🔢 Questões", value=f"**{len(questoes_selecionadas)} questões**.", inline=True)
            embed_intro.add_field(name="⏱️ Tempo", value="**2 minutos** por questão.", inline=True)
            embed_intro.add_field(name="🎯 Aprovação", value=f"Mínimo de **{config['acertos_para_aprovar']}** acertos.", inline=False)
            
            view_intro = IntroView()
            await dm_channel.send(embed=embed_intro, view=view_intro)
            await interaction.response.send_message("📩 Enviei as instruções da prova no seu privado (DM).", ephemeral=True)

            if await view_intro.wait() or not view_intro.confirmado: return

        except discord.Forbidden:
            await interaction.response.send_message("❌ Habilite mensagens diretas (DM).", ephemeral=True)
            return

        acertos = 0
        erros_detalhados = []
        
        msg_prova = await dm_channel.send("🚀 **Iniciando...**")
        await discord.utils.sleep_until(datetime.now() + timedelta(seconds=3))

        for i, questao in enumerate(questoes_selecionadas):
            view = ProvaView(questao, len(questoes_selecionadas), i+1)
            msg_pergunta = await dm_channel.send(embed=view.embed, view=view)
            await view.wait()
            
            if view.value is None:
                await dm_channel.send("❌ **Tempo Esgotado!** Prova encerrada.")
                self.cooldowns[user_id] = (datetime.now() + timedelta(hours=1)).isoformat()
                await self.salvar_backup_cooldowns()
                return

            if view.value == questao['correta']: acertos += 1
            else:
                erros_detalhados.append({
                    "pergunta": questao['pergunta'],
                    "escolhida": questao['alternativas'][view.value],
                    "correta": questao['alternativas'][questao['correta']]
                })
            
            view.embed.description = f"**{questao['pergunta']}**" 
            view.embed.set_footer(text="Respondida.")
            await msg_pergunta.edit(view=None, embed=view.embed)
            
        passou = acertos >= config['acertos_para_aprovar']
        cor = discord.Color.green() if passou else discord.Color.red()
        
        embed_user = discord.Embed(title="📊 Resultado Final", description=f"Acertou **{acertos}/{len(questoes_selecionadas)}**.", color=cor)
        if passou: embed_user.add_field(name="Status", value="✅ **APROVADO!**")
        else:
            dias = config.get('tempo_cooldown_dias', 3)
            embed_user.add_field(name="Status", value=f"❌ **REPROVADO**.\nTente em **{dias} dias**.")
            self.cooldowns[user_id] = (datetime.now() + timedelta(days=dias)).isoformat()
            await self.salvar_backup_cooldowns()
            
        await dm_channel.send(embed=embed_user)

        try:
            log_channel = self.client.get_channel(810674051277651980) 
            if log_channel:
                embed_admin = discord.Embed(title=f"📑 Relatório: {interaction.user.name}", color=cor)
                embed_admin.add_field(name="Nota", value=f"{acertos}/{len(questoes_selecionadas)}")
                embed_admin.add_field(name="Resultado", value="APROVADO" if passou else "REPROVADO")
                if erros_detalhados:
                    texto = "\n".join([f"Q: {e['pergunta']}\n❌ {e['escolhida']}\n✅ {e['correta']}\n" for e in erros_detalhados[:5]])
                    embed_admin.add_field(name="Erros (Top 5)", value=texto[:1024], inline=False)
                await log_channel.send(embed=embed_admin)
        except: pass

async def setup(client: commands.Bot):
    await client.add_cog(SistemaProva(client))
