import discord
import json
import os
import io
import random
from datetime import datetime, timedelta
from discord.ext import commands
from discord import app_commands, ui

# --- CONFIGURAÇÃO ---
ID_CANAL_BACKUP = 123456789012345678 # Ajuste conforme necessário

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
        self.erro_detalhado = None # Variável para guardar o erro exato

    async def carregar_provas(self):
        """Tenta carregar o JSON e guarda o erro se falhar"""
        self.erro_detalhado = None
        try:
            # Tenta 3 estratégias de caminho para garantir que acha o arquivo
            caminhos_tentativa = [
                "provas.json", # Na pasta de trabalho atual
                os.path.join(os.getcwd(), "provas.json"), # Absoluto da raiz
                os.path.join(os.path.dirname(__file__), '..', 'provas.json') # Relativo à Cog
            ]

            arquivo_encontrado = None
            for caminho in caminhos_tentativa:
                if os.path.exists(caminho):
                    arquivo_encontrado = caminho
                    break
            
            if not arquivo_encontrado:
                # Se não achar, lista os arquivos da pasta para sabermos o que tem lá
                arquivos_locais = os.listdir(os.getcwd())
                self.erro_detalhado = f"Arquivo 'provas.json' não encontrado.\n📂 Diretório atual: `{os.getcwd()}`\n📄 Arquivos visíveis: `{arquivos_locais}`"
                print(self.erro_detalhado)
                return

            with open(arquivo_encontrado, 'r', encoding='utf-8') as f:
                self.questoes_data = json.load(f)
            
            print(f"SistemaProva: Sucesso lendo de {arquivo_encontrado}")

        except json.JSONDecodeError as e:
            self.erro_detalhado = f"O arquivo 'provas.json' existe mas está com erro de digitação (vírgula ou chave errada).\nErro: `{e}`"
            print(self.erro_detalhado)
        except Exception as e:
            self.erro_detalhado = f"Erro inesperado ao abrir arquivo: `{e}`"
            print(self.erro_detalhado)

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

    # --- COMANDO DE DIAGNÓSTICO ---
    @app_commands.command(name="debug-provas", description="[Admin] Verifica onde está o arquivo de provas.")
    @commands.has_permissions(administrator=True)
    async def debug_provas(self, interaction: discord.Interaction):
        await self.carregar_provas() # Força recarregamento
        
        embed = discord.Embed(title="🕵️ Diagnóstico do Sistema de Provas", color=discord.Color.orange())
        embed.add_field(name="Diretório de Trabalho", value=f"`{os.getcwd()}`", inline=False)
        
        # Lista arquivos na raiz
        try:
            files = os.listdir(os.getcwd())
            files_str = ", ".join([f for f in files if f.endswith('.json') or f.endswith('.py')])
            embed.add_field(name="Arquivos na Raiz", value=f"`{files_str[:1000]}`", inline=False)
        except:
            embed.add_field(name="Arquivos na Raiz", value="Erro ao listar.", inline=False)

        if self.questoes_data:
            qtd = len(self.questoes_data.get('questoes', []))
            embed.add_field(name="Status", value=f"✅ **Carregado com Sucesso!**\nQuestões encontradas: {qtd}", inline=False)
            embed.color = discord.Color.green()
        else:
            erro = self.erro_detalhado or "Erro desconhecido."
            embed.add_field(name="Status", value=f"❌ **Falha ao Carregar**", inline=False)
            embed.add_field(name="Detalhe do Erro", value=erro[:1024], inline=False)
            embed.color = discord.Color.red()

        await interaction.response.send_message(embed=embed, ephemeral=True)


    @app_commands.command(name="iniciar-prova", description="Inicia o teste para Co-Líder.")
    async def iniciar_prova(self, interaction: discord.Interaction):
        # Tenta carregar se estiver vazio
        if not self.questoes_data:
            await self.carregar_provas()
            
            # SE FALHAR DE NOVO, MOSTRA O ERRO PRO USUARIO
            if not self.questoes_data:
                erro_msg = self.erro_detalhado or "Erro interno desconhecido."
                await interaction.response.send_message(
                    f"⚠️ **Erro Técnico:** Não foi possível carregar o banco de questões.\n\n**O que aconteceu:**\n{erro_msg}\n\n*Avise o programador.*", 
                    ephemeral=True
                )
                return

        # Lógica normal da prova continua aqui...
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
            log_channel = self.client.get_channel(810674051277651980) # ID DO SEU LOG AQUI
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
