import discord
import json
import os
import io
import random
from datetime import datetime, timedelta
from discord.ext import commands
from discord import app_commands, ui

# --- CONFIGURAÇÃO ---
# ID do canal onde o bot vai salvar o arquivo de cooldowns
ID_CANAL_BACKUP = 123456789012345678 

# --- CLASSES DE INTERFACE (VIEWS) ---

class IntroView(ui.View):
    def __init__(self):
        super().__init__(timeout=300) # 5 minutos para ler as regras
        self.confirmado = False

    @ui.button(label="Começar Avaliação", style=discord.ButtonStyle.green, emoji="✅")
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmado = True
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()

    @ui.button(label="Cancelar/Não estou pronto", style=discord.ButtonStyle.red, emoji="✖️")
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmado = False
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="❌ Avaliação cancelada. Estude e volte quando estiver pronto!", view=self, embed=None)
        self.stop()

class ProvaView(ui.View):
    def __init__(self, questao, total, atual):
        # 120 segundos = 2 minutos por questão
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

# --- CLASSE PRINCIPAL (COG) ---

class SistemaProva(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client
        self.cooldowns = {} 
        self.questoes_data = {} 

    async def carregar_provas(self):
        """Lê o arquivo estático do GitHub/Pasta usando caminho absoluto"""
        try:
            # CORREÇÃO AQUI: Garante que pega o arquivo na raiz, subindo um nível (..)
            caminho_provas = os.path.join(os.path.dirname(__file__), '..', 'provas.json')
            caminho_provas = os.path.abspath(caminho_provas)

            if os.path.exists(caminho_provas):
                with open(caminho_provas, 'r', encoding='utf-8') as f:
                    self.questoes_data = json.load(f)
                print(f"SistemaProva: Questões carregadas com sucesso de: {caminho_provas}")
            else:
                print(f"SistemaProva: AVISO - Arquivo não encontrado no caminho: {caminho_provas}")
        except Exception as e:
            print(f"SistemaProva: Erro ao ler provas.json: {e}")

    async def carregar_backup_cooldowns(self):
        """Baixa o último backup do canal do Discord"""
        await self.client.wait_until_ready()
        try:
            canal_backup = self.client.get_channel(ID_CANAL_BACKUP)
            if not canal_backup:
                print("SistemaProva: ERRO - Canal de backup não encontrado! Verifique o ID.")
                return

            async for message in canal_backup.history(limit=1):
                if message.attachments:
                    arquivo = await message.attachments[0].read()
                    self.cooldowns = json.loads(arquivo.decode('utf-8'))
                    print(f"SistemaProva: Cooldowns restaurados ({len(self.cooldowns)} registros).")
                    return
        except Exception as e:
            print(f"SistemaProva: Nenhum backup encontrado ou erro ao ler: {e}")
            self.cooldowns = {}

    async def salvar_backup_cooldowns(self):
        try:
            canal_backup = self.client.get_channel(ID_CANAL_BACKUP)
            if not canal_backup: return

            arquivo_memoria = io.StringIO(json.dumps(self.cooldowns, indent=4))
            arquivo_discord = discord.File(arquivo_memoria, filename="cooldowns_backup.json")
            
            await canal_backup.send(content=f"Backup automático - {datetime.now()}", file=arquivo_discord)
        except Exception as e:
            print(f"SistemaProva: Erro ao salvar backup: {e}")

    @commands.Cog.listener()
    async def on_ready(self):
        await self.carregar_provas()
        await self.carregar_backup_cooldowns()

    @app_commands.command(name="iniciar-prova", description="Inicia o teste para Co-Líder.")
    async def iniciar_prova(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)

        # 1. Verifica Cooldown
        if user_id in self.cooldowns:
            data_liberacao = datetime.fromisoformat(self.cooldowns[user_id])
            if datetime.now() < data_liberacao:
                ts = int(data_liberacao.timestamp())
                await interaction.response.send_message(f"❌ Você reprovou recentemente.\nVocê poderá tentar novamente <t:{ts}:R>.", ephemeral=True)
                return

        # 2. Carrega Configurações
        if not self.questoes_data:
            await self.carregar_provas()
            if not self.questoes_data:
                await interaction.response.send_message("❌ Erro: Banco de questões não carregado. Verifique os logs do console.", ephemeral=True)
                return
            
        config = self.questoes_data['config']
        todas_questoes = self.questoes_data['questoes']
        
        qtd_questoes = config.get('total_questoes_aplicadas', 10)
        if len(todas_questoes) < qtd_questoes:
            questoes_selecionadas = todas_questoes
        else:
            questoes_selecionadas = random.sample(todas_questoes, qtd_questoes)

        # 3. Envia DM Inicial
        try:
            dm_channel = await interaction.user.create_dm()
            
            embed_intro = discord.Embed(
                title="🛡️ Exame de Qualificação: Co-Líder B.A.D",
                description=f"Olá, {interaction.user.mention}.",
                color=discord.Color.gold()
            )
            embed_intro.add_field(name="🔢 Questões", value=f"**{len(questoes_selecionadas)} questões** sorteadas.", inline=True)
            embed_intro.add_field(name="⏱️ Tempo", value="**2 minutos** por questão.", inline=True)
            embed_intro.add_field(name="🎯 Aprovação", value=f"Mínimo de **{config['acertos_para_aprovar']}** acertos.", inline=False)
            embed_intro.add_field(name="⚠️ Atenção", value="Ao clicar em 'Começar', o tempo conta imediatamente. O contador regressivo aparecerá em cada questão.", inline=False)
            
            view_intro = IntroView()
            await dm_channel.send(embed=embed_intro, view=view_intro)
            await interaction.response.send_message("📩 Enviei as instruções da prova no seu privado (DM).", ephemeral=True)

            timeout_intro = await view_intro.wait()
            if timeout_intro or not view_intro.confirmado:
                return

        except discord.Forbidden:
            await interaction.response.send_message("❌ Habilite mensagens diretas (DM) para fazer a prova.", ephemeral=True)
            return

        # 4. Início da Prova
        acertos = 0
        erros_detalhados = []
        
        msg_prova = await dm_channel.send("🚀 **Iniciando a prova em 3 segundos...**")
        await discord.utils.sleep_until(datetime.now() + timedelta(seconds=3))

        for i, questao in enumerate(questoes_selecionadas):
            view = ProvaView(questao, len(questoes_selecionadas), i+1)
            
            msg_pergunta = await dm_channel.send(embed=view.embed, view=view)
            
            await view.wait()
            
            if view.value is None:
                await dm_channel.send("❌ **Tempo Esgotado!** Prova encerrada.")
                proxima_tentativa = datetime.now() + timedelta(hours=1)
                self.cooldowns[user_id] = proxima_tentativa.isoformat()
                await self.salvar_backup_cooldowns()
                return

            if view.value == questao['correta']:
                acertos += 1
            else:
                alternativas = questao['alternativas']
                erros_detalhados.append({
                    "pergunta": questao['pergunta'],
                    "escolhida": alternativas[view.value],
                    "correta": alternativas[questao['correta']]
                })
            
            view.embed.description = f"**{questao['pergunta']}**" 
            view.embed.set_footer(text="Respondida.")
            await msg_pergunta.edit(view=None, embed=view.embed)
            
        # 5. Finalização
        passou = acertos >= config['acertos_para_aprovar']
        
        embed_user = discord.Embed(
            title="📊 Resultado Final",
            description=f"Você acertou **{acertos} de {len(questoes_selecionadas)}** questões.",
            color=discord.Color.green() if passou else discord.Color.red()
        )
        
        if passou:
            embed_user.add_field(name="Status", value="✅ **APROVADO!** Aguarde contato da liderança.")
        else:
            dias_cooldown = config.get('tempo_cooldown_dias', 3)
            embed_user.add_field(name="Status", value=f"❌ **REPROVADO**.\nTente novamente em **{dias_cooldown} dias**.")
            proxima_tentativa = datetime.now() + timedelta(days=dias_cooldown)
            self.cooldowns[user_id] = proxima_tentativa.isoformat()
            await self.salvar_backup_cooldowns()
            
        await dm_channel.send(embed=embed_user)

        # 6. Log para Admin
        try:
            # AJUSTE SEU ID DE LOG AQUI
            log_channel_id = 810674051277651980 
            log_channel = self.client.get_channel(log_channel_id)
            
            if log_channel:
                embed_admin = discord.Embed(
                    title=f"📑 Relatório: {interaction.user.name}",
                    color=discord.Color.green() if passou else discord.Color.red(),
                    timestamp=datetime.now()
                )
                embed_admin.set_thumbnail(url=interaction.user.avatar.url if interaction.user.avatar else None)
                embed_admin.add_field(name="Nota", value=f"{acertos}/{len(questoes_selecionadas)}")
                embed_admin.add_field(name="Resultado", value="✅ APROVADO" if passou else "❌ REPROVADO")
                
                if erros_detalhados:
                    texto_erros = ""
                    for idx, erro in enumerate(erros_detalhados):
                        if idx >= 5: 
                            texto_erros += f"\n... e mais {len(erros_detalhados)-5} erros."
                            break
                        texto_erros += f"**Q:** {erro['pergunta']}\n🔴 {erro['escolhida']}\n🟢 {erro['correta']}\n\n"
                    
                    if len(texto_erros) > 1024: texto_erros = texto_erros[:1020] + "..."
                    embed_admin.add_field(name="Erros", value=texto_erros, inline=False)

                await log_channel.send(embed=embed_admin)
        except Exception:
            pass

async def setup(client: commands.Bot):
    await client.add_cog(SistemaProva(client))
