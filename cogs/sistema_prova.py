import discord
import json
import os
import io
import random
from datetime import datetime, timedelta
from discord.ext import commands
from discord import app_commands, ui

# --- CONFIGURAÇÃO DE CANAIS E CARGOS ---
ID_CANAL_BACKUP = 1460621468152107095   # Canal para enviar o JSON
ID_CANAL_RELATORIO = 1460621862034997349 # Canal para enviar a análise (Embed)

# IDs dos cargos permitidos a usar o comando
CARGOS_PERMITIDOS = [
    1362076878458065041, # Admin
    1460665766826475710  # Em treinamento
]

# --- CLASSES DE INTERFACE ---

class IntroView(ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.confirmado = False

    @ui.button(label="Começar Avaliação", style=discord.ButtonStyle.green, emoji="✅")
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmado = True
        # Desabilita botões após clicar
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
        TEMPO_POR_QUESTAO = 120 # 2 minutos por questão
        super().__init__(timeout=TEMPO_POR_QUESTAO) 
        self.value = None
        self.questao = questao
        timestamp_fim = int(datetime.now().timestamp() + TEMPO_POR_QUESTAO)
        
        # Mistura as alternativas para não ficarem sempre na mesma ordem
        alternativas_com_indice = list(enumerate(questao['alternativas']))
        random.shuffle(alternativas_com_indice)
        
        options = []
        for i, (indice_original, texto) in enumerate(alternativas_com_indice):
            letra = chr(65 + i) # A, B, C, D...
            # Discord limita o label a 100 caracteres
            label_texto = texto[:98] + ".." if len(texto) > 98 else texto
            options.append(discord.SelectOption(label=f"{letra}) {label_texto}", value=str(indice_original)))

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
        await interaction.response.defer() # Apenas reconhece, não envia msg nova
        self.stop()

# --- CLASSE PRINCIPAL DA COG ---

class SistemaProva(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client
        self.cooldowns = {} 
        self.questoes_data = {} 
        self.last_error = None

    async def carregar_provas(self):
        self.last_error = None
        try:
            # Tenta encontrar o arquivo subindo um nível (raiz do bot)
            caminho_arquivo = os.path.join(os.path.dirname(__file__), '..', 'provas.json')
            
            if not os.path.exists(caminho_arquivo):
                caminho_arquivo = "provas.json" # Tenta na pasta atual

            if not os.path.exists(caminho_arquivo):
                self.last_error = f"Arquivo 'provas.json' não encontrado."
                print(f"SistemaProva: {self.last_error}")
                return

            with open(caminho_arquivo, 'r', encoding='utf-8-sig') as f:
                self.questoes_data = json.load(f)
            
            print(f"SistemaProva: Questões carregadas com sucesso!")

        except Exception as e:
            self.last_error = f"Erro ao carregar JSON: {e}"
            print(f"SistemaProva: {self.last_error}")

    async def carregar_backup_cooldowns(self):
        # Tenta recuperar cooldowns de reinícios anteriores via canal de backup (opcional)
        await self.client.wait_until_ready()
        try:
            canal_backup = self.client.get_channel(ID_CANAL_BACKUP)
            if not canal_backup: return
            # Procura a última mensagem que tenha anexo de cooldowns
            async for message in canal_backup.history(limit=5):
                if message.attachments and message.content.startswith("System_Cooldowns"):
                    arquivo = await message.attachments[0].read()
                    self.cooldowns = json.loads(arquivo.decode('utf-8'))
                    print("SistemaProva: Cooldowns restaurados do backup.")
                    return
        except Exception:
            self.cooldowns = {}

    async def salvar_backup_cooldowns(self):
        # Salva o estado atual dos cooldowns no canal de backup para persistência
        try:
            canal_backup = self.client.get_channel(ID_CANAL_BACKUP)
            if not canal_backup: return
            arquivo_memoria = io.StringIO(json.dumps(self.cooldowns, indent=4))
            arquivo_discord = discord.File(arquivo_memoria, filename="cooldowns_backup.json")
            await canal_backup.send(content=f"System_Cooldowns - Backup automático - {datetime.now()}", file=arquivo_discord)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_ready(self):
        await self.carregar_provas()
        await self.carregar_backup_cooldowns()

    @app_commands.command(name="iniciar-prova", description="Inicia o teste para Co-Líder.")
    async def iniciar_prova(self, interaction: discord.Interaction):
        
        # 1. VERIFICAÇÃO DE PERMISSÃO (CARGOS)
        tem_permissao = False
        user_roles_ids = [role.id for role in interaction.user.roles]
        
        for cargo_id in CARGOS_PERMITIDOS:
            if cargo_id in user_roles_ids:
                tem_permissao = True
                break
        
        # Se for admin do servidor, também permite (opcional, segurança extra)
        if interaction.user.guild_permissions.administrator:
            tem_permissao = True

        if not tem_permissao:
            await interaction.response.send_message("❌ Você não tem permissão (Cargo Admin ou Treinamento necessário) para usar este comando.", ephemeral=True)
            return

        # 2. CARREGAMENTO DAS QUESTÕES
        if not self.questoes_data:
            await self.carregar_provas()
            if not self.questoes_data:
                await interaction.response.send_message(f"🚨 Erro interno: Não foi possível carregar a prova. Contate o desenvolvedor.", ephemeral=True)
                return

        # 3. VERIFICAÇÃO DE COOLDOWN (REPROVAÇÃO RECENTE)
        user_id = str(interaction.user.id)
        if user_id in self.cooldowns:
            data_liberacao = datetime.fromisoformat(self.cooldowns[user_id])
            if datetime.now() < data_liberacao:
                ts = int(data_liberacao.timestamp())
                await interaction.response.send_message(f"❌ Você realizou uma prova recentemente. Tente novamente <t:{ts}:R>.", ephemeral=True)
                return
            
        config = self.questoes_data['config']
        todas_questoes = self.questoes_data['questoes']
        
        qtd_questoes = config.get('total_questoes_aplicadas', 10)
        if len(todas_questoes) < qtd_questoes:
            questoes_selecionadas = todas_questoes
        else:
            questoes_selecionadas = random.sample(todas_questoes, qtd_questoes)

        # 4. INÍCIO DO PROCESSO (DM)
        try:
            dm_channel = await interaction.user.create_dm()
            
            embed_intro = discord.Embed(
                title="🛡️ Exame de Qualificação: Co-Líder B.A.D",
                description=f"Olá, {interaction.user.mention}.",
                color=discord.Color.gold()
            )
            embed_intro.add_field(name="🔢 Questões", value=f"**{len(questoes_selecionadas)} questões**.", inline=True)
            embed_intro.add_field(name="⏱️ Tempo", value="**2 minutos** por questão.", inline=True)
            embed_intro.add_field(name="ℹ️ Info", value="Ao responder, a pergunta será apagada para segurança.", inline=False)
            
            view_intro = IntroView()
            await dm_channel.send(embed=embed_intro, view=view_intro)
            
            # Avisa no servidor que enviou a DM
            await interaction.response.send_message("📩 Enviei as instruções da prova no seu privado (DM).", ephemeral=True)

            if await view_intro.wait() or not view_intro.confirmado: return

        except discord.Forbidden:
            await interaction.response.send_message("❌ Não consegui enviar DM. Habilite mensagens diretas no servidor.", ephemeral=True)
            return

        acertos = 0
        respostas_detalhadas = [] # Armazena tudo para o relatório
        
        msg_inicio = await dm_channel.send("🚀 **A prova vai começar em 3 segundos...**")
        await discord.utils.sleep_until(datetime.now() + timedelta(seconds=3))
        try: await msg_inicio.delete()
        except: pass

        # 5. LOOP DE QUESTÕES
        for i, questao in enumerate(questoes_selecionadas):
            view = ProvaView(questao, len(questoes_selecionadas), i+1)
            
            # Envia a pergunta
            msg_pergunta = await dm_channel.send(embed=view.embed, view=view)
            
            # Espera a resposta
            await view.wait()
            
            # --- LÓGICA ANTI-COLA: APAGAR A PERGUNTA ---
            try:
                await msg_pergunta.delete()
            except Exception:
                pass # Se não der pra apagar (já apagada), segue o jogo

            if view.value is None:
                await dm_channel.send("❌ **Tempo Esgotado!** Prova encerrada automaticamente.")
                # Aplica cooldown curto em caso de timeout
                self.cooldowns[user_id] = (datetime.now() + timedelta(minutes=30)).isoformat()
                await self.salvar_backup_cooldowns()
                return

            alternativa_escolhida = questao['alternativas'][view.value]
            alternativa_correta = questao['alternativas'][questao['correta']]

            dados_resposta = {
                "id": questao['id'],
                "pergunta": questao['pergunta'],
                "escolhida": alternativa_escolhida,
                "correta": alternativa_correta,
                "acertou": False
            }

            if view.value == questao['correta']:
                acertos += 1
                dados_resposta["acertou"] = True
            
            respostas_detalhadas.append(dados_resposta)
            
        # 6. CÁLCULO DO RESULTADO
        passou = acertos >= config['acertos_para_aprovar']
        cor = discord.Color.green() if passou else discord.Color.red()
        
        # Se reprovou, aplica cooldown definido no JSON
        if not passou:
            dias = config.get('tempo_cooldown_dias', 3)
            self.cooldowns[user_id] = (datetime.now() + timedelta(days=dias)).isoformat()
            await self.salvar_backup_cooldowns()

        # 7. MENSAGEM FINAL AO USUÁRIO (Sem dar o resultado detalhado)
        embed_fim = discord.Embed(
            title="✅ Prova Finalizada",
            description="Suas respostas foram enviadas para o nosso sistema.\n\n**Aguarde!** Um administrador analisará seu desempenho e entrará em contato em breve com o resultado oficial.",
            color=discord.Color.blue()
        )
        await dm_channel.send(embed=embed_fim)

        # 8. GERAÇÃO DE RELATÓRIOS (ADMIN)

        # --- A. CANAL DE RELATÓRIO (Embed Visual) ---
        canal_relatorio = self.client.get_channel(ID_CANAL_RELATORIO)
        if canal_relatorio:
            embed_admin = discord.Embed(title=f"📑 Avaliação: {interaction.user.name}", color=cor)
            embed_admin.set_thumbnail(url=interaction.user.display_avatar.url)
            embed_admin.add_field(name="Usuário", value=f"{interaction.user.mention} (`{interaction.user.id}`)", inline=True)
            embed_admin.add_field(name="Nota", value=f"**{acertos}/{len(questoes_selecionadas)}**", inline=True)
            embed_admin.add_field(name="Resultado Automático", value="🟢 APROVADO" if passou else "🔴 REPROVADO", inline=True)
            embed_admin.set_footer(text=f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}")

            # Adiciona os erros ao Embed (com tratamento para não cortar texto)
            erros = [r for r in respostas_detalhadas if not r['acertou']]
            
            if erros:
                texto_erros = ""
                contador_campo = 1
                
                for erro in erros:
                    bloco = f"**Q:** {erro['pergunta']}\n❌ {erro['escolhida']}\n✅ {erro['correta']}\n\n"
                    
                    # Se adicionar esse bloco passar de 1000 caracteres, cria o campo e limpa
                    if len(texto_erros) + len(bloco) > 1000:
                        embed_admin.add_field(name=f"❌ Erros (Parte {contador_campo})", value=texto_erros, inline=False)
                        texto_erros = bloco
                        contador_campo += 1
                    else:
                        texto_erros += bloco
                
                # Adiciona o que sobrou
                if texto_erros:
                    embed_admin.add_field(name=f"❌ Erros (Parte {contador_campo})", value=texto_erros, inline=False)
            else:
                embed_admin.add_field(name="Desempenho", value="🏆 Gabaritou a prova!", inline=False)

            await canal_relatorio.send(embed=embed_admin)

        # --- B. CANAL DE BACKUP (Arquivo JSON Completo) ---
        canal_backup = self.client.get_channel(ID_CANAL_BACKUP)
        if canal_backup:
            dados_backup = {
                "user_tag": interaction.user.name,
                "user_id": interaction.user.id,
                "data": datetime.now().isoformat(),
                "nota": acertos,
                "total": len(questoes_selecionadas),
                "aprovado_sistema": passou,
                "respostas": respostas_detalhadas
            }
            
            arquivo_memoria = io.StringIO(json.dumps(dados_backup, indent=4, ensure_ascii=False))
            arquivo_anexo = discord.File(arquivo_memoria, filename=f"prova_{interaction.user.name}_{int(datetime.now().timestamp())}.json")
            
            await canal_backup.send(content=f"💾 **Backup de Prova:** {interaction.user.mention}", file=arquivo_anexo)

async def setup(client: commands.Bot):
    await client.add_cog(SistemaProva(client))
