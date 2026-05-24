import discord
import json
import os
import io
import random
import asyncio
from datetime import datetime, timedelta
from discord.ext import commands
from discord import app_commands, ui
from dotenv import load_dotenv
from mongo_db import salvar_aprovacao_pendente, get_aprovacao_pendente, deletar_aprovacao_pendente, listar_aprovacoes_pendentes, atualizar_status_aprovacao

# --- CONFIGURAÇÃO DE CANAIS ---
ID_CANAL_BACKUP = 1460621468152107095   # Canal para enviar o JSON
ID_CANAL_RELATORIO = 1460621862034997349 # Canal para enviar a análise (Embed)

# Carrega ID do dono do .env
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
try:
    OWNER_ID = int(os.getenv("DONO_ID") or os.getenv("OWNER_ID"))
except (ValueError, TypeError):
    OWNER_ID = None

# --- CLASSES DE INTERFACE ---

class IntroView(ui.View):
    def __init__(self, cog=None, user_id=None, questoes=None, config=None):
        super().__init__(timeout=None)
        self.cog = cog
        self.user_id = user_id
        self.questoes = questoes
        self.config = config
        self.confirmado = False

        btn_iniciar = ui.Button(label="Começar Avaliação", style=discord.ButtonStyle.green, emoji="✅", custom_id=f"prova_iniciar:{user_id}")
        btn_iniciar.callback = self._confirmar
        self.add_item(btn_iniciar)

        btn_cancelar = ui.Button(label="Cancelar", style=discord.ButtonStyle.red, emoji="✖️", custom_id=f"prova_cancelar:{user_id}")
        btn_cancelar.callback = self._cancelar
        self.add_item(btn_cancelar)

    async def _confirmar(self, interaction: discord.Interaction):
        self.confirmado = True
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()

        questoes = self.questoes
        config = self.config
        if not questoes or not config:
            dados = get_aprovacao_pendente(self.user_id)
            if dados:
                questoes = dados.get("questoes")
                config = dados.get("config")

        if not questoes or not config:
            return

        deletar_aprovacao_pendente(self.user_id)
        await self.cog._run_exam_loop(interaction.channel, interaction.user, self.user_id, questoes, config)

    async def _cancelar(self, interaction: discord.Interaction):
        self.confirmado = False
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="❌ Avaliação cancelada.", view=self, embed=None)
        deletar_aprovacao_pendente(self.user_id)
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
        alternativas_texto = []
        for i, (indice_original, texto) in enumerate(alternativas_com_indice):
            letra = chr(65 + i) # A, B, C, D...
            options.append(discord.SelectOption(label=f"{letra}) {texto[:95]}", value=str(indice_original)))
            alternativas_texto.append(f"**{letra})** {texto}")

        self.select = discord.ui.Select(placeholder="Selecione a resposta correta...", options=options)
        self.select.callback = self.callback
        self.add_item(self.select)

        self.embed = discord.Embed(
            title=f"📝 Questão {atual}/{total}",
            description=f"**{questao['pergunta']}**\n\n⏳ **Tempo restante:** <t:{timestamp_fim}:R>",
            color=discord.Color.blue()
        )
        self.embed.add_field(name="Alternativas", value="\n\n".join(alternativas_texto), inline=False)
        self.embed.set_footer(text="Selecione a letra correspondente no menu abaixo.")

    async def callback(self, interaction: discord.Interaction):
        self.value = int(self.select.values[0])
        self.select.disabled = True
        await interaction.response.defer() # Apenas reconhece, não envia msg nova
        self.stop()

class OwnerApprovalView(ui.View):
    def __init__(self, cog, user_id, user=None, dm_channel=None, questoes=None, config=None):
        super().__init__(timeout=None)
        self.cog = cog
        self.user_id = user_id
        self.user = user
        self.dm_channel = dm_channel
        self.questoes = questoes
        self.config = config

        btn_aprovar = ui.Button(label="Aprovar", style=discord.ButtonStyle.green, emoji="✅", custom_id=f"prova_aprovar:{user_id}")
        btn_aprovar.callback = self._approve
        self.add_item(btn_aprovar)

        btn_negar = ui.Button(label="Negar", style=discord.ButtonStyle.red, emoji="✖️", custom_id=f"prova_negar:{user_id}")
        btn_negar.callback = self._deny
        self.add_item(btn_negar)

    async def _approve(self, interaction: discord.Interaction):
        if interaction.user.id != OWNER_ID:
            return await interaction.response.send_message("Apenas o dono do bot pode aprovar.", ephemeral=True)

        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="✅ **Usuário aprovado!** A prova será iniciada no privado dele.", view=self, embed=None)

        user = self.user
        if user is None:
            try:
                user = await self.cog.client.fetch_user(int(self.user_id))
            except:
                return

        dm_channel = self.dm_channel
        if dm_channel is None:
            try:
                dm_channel = await user.create_dm()
            except:
                return

        questoes = self.questoes
        config = self.config
        if not questoes or not config:
            dados = get_aprovacao_pendente(self.user_id)
            if dados:
                questoes = dados.get("questoes")
                config = dados.get("config")

        if not questoes or not config:
            return

        await dm_channel.send("✅ **Você foi aprovado para realizar a prova de Co-Líder!** Prepare-se, o exame vai começar em instantes...")
        await self.cog._run_exam(dm_channel, user, self.user_id, questoes, config)

    async def _deny(self, interaction: discord.Interaction):
        if interaction.user.id != OWNER_ID:
            return await interaction.response.send_message("Apenas o dono do bot pode negar.", ephemeral=True)

        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="❌ **Solicitação negada.**", view=self, embed=None)
        deletar_aprovacao_pendente(self.user_id)

        user = self.user
        dm_channel = self.dm_channel
        if user is None:
            try:
                user = await self.cog.client.fetch_user(int(self.user_id))
            except:
                return
        if dm_channel is None and user:
            try:
                dm_channel = await user.create_dm()
            except:
                return

        if dm_channel:
            await dm_channel.send("❌ Sua solicitação para realizar a prova foi **negada** pela liderança.")

# --- CLASSE PRINCIPAL DA COG ---

class SistemaProva(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client
        self.cooldowns = {} 
        self.questoes_data = {} 
        self.last_error = None
        self._restaurar_aprovacoes_pendentes()

    def _restaurar_aprovacoes_pendentes(self):
        try:
            dados_pendentes = listar_aprovacoes_pendentes()
            for dados in dados_pendentes:
                user_id = dados["user_id"]
                status = dados.get("status", "aguardando_dono")
                questoes = dados.get("questoes")
                config = dados.get("config")

                if status == "aguardando_usuario":
                    view = IntroView(cog=self, user_id=user_id, questoes=questoes, config=config)
                    self.client.add_view(view)
                    print(f"SistemaProva: IntroView restaurada para user {user_id}")
                else:
                    view = OwnerApprovalView(
                        cog=self,
                        user_id=user_id,
                        questoes=questoes,
                        config=config
                    )
                    self.client.add_view(view)
                    print(f"SistemaProva: OwnerApprovalView restaurada para user {user_id}")
        except Exception as e:
            print(f"SistemaProva: Erro ao restaurar aprovações pendentes: {e}")

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

        # 1. CARREGAMENTO DAS QUESTÕES
        if not self.questoes_data:
            await self.carregar_provas()
            if not self.questoes_data:
                await interaction.response.send_message("🚨 Erro interno: Não foi possível carregar a prova. Contate o desenvolvedor.", ephemeral=True)
                return

        # 2. VERIFICAÇÃO DE COOLDOWN (REPROVAÇÃO RECENTE)
        user_id = str(interaction.user.id)
        if user_id in self.cooldowns:
            data_liberacao = datetime.fromisoformat(self.cooldowns[user_id])
            if datetime.now() < data_liberacao:
                ts = int(data_liberacao.timestamp())
                await interaction.response.send_message(f"❌ Você realizou uma prova recentemente. Tente novamente <t:{ts}:R>.", ephemeral=True)
                return

        config = self.questoes_data['config']
        todas_questoes = self.questoes_data['questoes']

        # Remove duplicatas por id (mantém a primeira ocorrência)
        ids_vistos = set()
        questoes_unicas = []
        for q in todas_questoes:
            qid = q.get("id")
            if qid not in ids_vistos:
                ids_vistos.add(qid)
                questoes_unicas.append(q)

        qtd_questoes = config.get('total_questoes_aplicadas', 10)
        if len(questoes_unicas) < qtd_questoes:
            questoes_selecionadas = questoes_unicas
        else:
            questoes_selecionadas = random.sample(questoes_unicas, qtd_questoes)

        # 3. CRIAÇÃO DA DM
        try:
            dm_channel = await interaction.user.create_dm()
        except discord.Forbidden:
            await interaction.response.send_message("❌ Não consegui enviar DM. Habilite mensagens diretas no servidor.", ephemeral=True)
            return

        # 4. APROVAÇÃO DO DONO (VIA DM)
        if OWNER_ID:
            try:
                owner = await self.client.fetch_user(OWNER_ID)
            except (discord.NotFound, discord.HTTPException):
                owner = None

            if owner:
                embed_owner = discord.Embed(
                    title="📋 Solicitação de Prova - Co-Líder",
                    description=f"{interaction.user.mention} está solicitando acesso à prova.",
                    color=discord.Color.blue()
                )
                embed_owner.set_thumbnail(url=interaction.user.display_avatar.url)
                embed_owner.add_field(name="Usuário", value=f"{interaction.user} (`{interaction.user.id}`)", inline=False)
                embed_owner.add_field(name="Servidor", value=f"{interaction.guild.name} (`{interaction.guild.id}`)", inline=False)
                embed_owner.add_field(name="Conta criada", value=f"📅 <t:{int(interaction.user.created_at.timestamp())}:R>", inline=True)
                embed_owner.add_field(name="Ingressou aqui", value=f"📅 <t:{int(interaction.user.joined_at.timestamp())}:R>", inline=True)

                cargos = [r.mention for r in interaction.user.roles if r.name != '@everyone']
                if cargos:
                    embed_owner.add_field(name="Cargos", value=" | ".join(cargos[:8]), inline=False)

                view_aprovar = OwnerApprovalView(self, user_id, interaction.user, dm_channel, questoes_selecionadas, config)
                await owner.send(embed=embed_owner, view=view_aprovar)
                salvar_aprovacao_pendente(user_id, str(interaction.user), questoes_selecionadas, config)
                await interaction.response.send_message("📩 Sua solicitação foi enviada para a liderança aprovar. **Aguarde o contato no privado!**", ephemeral=True)
                return

        # 5. Se não tem OWNER_ID configurado, inicia direto
        salvar_aprovacao_pendente(user_id, str(interaction.user), questoes_selecionadas, config, status="aguardando_usuario")
        await self._run_exam(dm_channel, interaction.user, user_id, questoes_selecionadas, config)

    async def _run_exam(self, dm_channel, user, user_id, questoes_selecionadas, config):
        """Envia o embed introdutório e aguarda o usuário iniciar a prova."""
        embed_intro = discord.Embed(
            title="🛡️ Exame de Qualificação: Co-Líder B.A.D",
            description=f"Olá, {user.mention}! Bem-vindo ao exame para **Co-Líder** do clã **B.A.D**.\n\n"
                        f"Este teste avalia seu conhecimento sobre as regras, filosofia e protocolos do clã. "
                        f"Você será aprovado se acertar **{config['acertos_para_aprovar']} de {len(questoes_selecionadas)} questões**.",
            color=discord.Color.gold()
        )
        embed_intro.add_field(name="🔢 Questões", value=f"**{len(questoes_selecionadas)}** questões sorteadas de um total de **{len(self.questoes_data['questoes'])}**.", inline=True)
        embed_intro.add_field(name="⏱️ Limite", value="**2 minutos** por questão (se esgotar, a prova é encerrada).", inline=True)
        embed_intro.add_field(name="🔒 Sigilo", value="Cada pergunta é **apagada** após respondida para evitar cola.", inline=False)
        embed_intro.add_field(name="📊 Conteúdo", value="• **Filosofia e Conduta** (Promoções, Hierarquia)\n• **Protocolos de Guerra** (Guerras, CWL)\n• **Gestão do Clã** (Doações, Eventos)\n• **Códigos MR** (Penalidades)", inline=False)

        atualizar_status_aprovacao(user_id, "aguardando_usuario")

        view_intro = IntroView(self, user_id, questoes_selecionadas, config)
        await dm_channel.send(embed=embed_intro, view=view_intro)

        await view_intro.wait()
        if not view_intro.confirmado:
            deletar_aprovacao_pendente(user_id)
            return

    async def _run_exam_loop(self, dm_channel, user, user_id, questoes_selecionadas, config):
        """Executa o loop de questões da prova."""
        acertos = 0
        respostas_detalhadas = []

        msg_inicio = await dm_channel.send("🚀 **A prova vai começar em 3 segundos...**")
        await asyncio.sleep(3)
        try:
            await msg_inicio.delete()
        except:
            pass

        # --- LOOP DE QUESTÕES ---
        for i, questao in enumerate(questoes_selecionadas):
            view = ProvaView(questao, len(questoes_selecionadas), i + 1)
            msg_pergunta = await dm_channel.send(embed=view.embed, view=view)
            await view.wait()

            try:
                await msg_pergunta.delete()
            except Exception:
                pass

            if view.value is None:
                await dm_channel.send("❌ **Tempo Esgotado!** Prova encerrada automaticamente.")
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

        # --- RESULTADO ---
        passou = acertos >= config['acertos_para_aprovar']
        cor = discord.Color.green() if passou else discord.Color.red()

        if not passou:
            dias = config.get('tempo_cooldown_dias', 3)
            self.cooldowns[user_id] = (datetime.now() + timedelta(days=dias)).isoformat()
            await self.salvar_backup_cooldowns()

        embed_fim = discord.Embed(
            title="✅ Prova Finalizada",
            description="Suas respostas foram enviadas para o nosso sistema.\n\n**Aguarde!** Um administrador analisará seu desempenho e entrará em contato em breve com o resultado oficial.",
            color=discord.Color.blue()
        )
        await dm_channel.send(embed=embed_fim)

        # --- RELATÓRIOS ---
        canal_relatorio = self.client.get_channel(ID_CANAL_RELATORIO)
        if canal_relatorio:
            embed_admin = discord.Embed(title=f"📑 Avaliação: {user.name}", color=cor)
            embed_admin.set_thumbnail(url=user.display_avatar.url)
            embed_admin.add_field(name="Usuário", value=f"{user.mention} (`{user.id}`)", inline=True)
            embed_admin.add_field(name="Nota", value=f"**{acertos}/{len(questoes_selecionadas)}**", inline=True)
            embed_admin.add_field(name="Resultado Automático", value="🟢 APROVADO" if passou else "🔴 REPROVADO", inline=True)
            embed_admin.set_footer(text=f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}")

            erros = [r for r in respostas_detalhadas if not r['acertou']]
            if erros:
                texto_erros = ""
                contador_campo = 1
                for erro in erros:
                    bloco = f"**Q:** {erro['pergunta']}\n❌ {erro['escolhida']}\n✅ {erro['correta']}\n\n"
                    if len(texto_erros) + len(bloco) > 1000:
                        embed_admin.add_field(name=f"❌ Erros (Parte {contador_campo})", value=texto_erros, inline=False)
                        texto_erros = bloco
                        contador_campo += 1
                    else:
                        texto_erros += bloco
                if texto_erros:
                    embed_admin.add_field(name=f"❌ Erros (Parte {contador_campo})", value=texto_erros, inline=False)
            else:
                embed_admin.add_field(name="Desempenho", value="🏆 Gabaritou a prova!", inline=False)

            await canal_relatorio.send(embed=embed_admin)

        canal_backup = self.client.get_channel(ID_CANAL_BACKUP)
        if canal_backup:
            dados_backup = {
                "user_tag": user.name,
                "user_id": user.id,
                "data": datetime.now().isoformat(),
                "nota": acertos,
                "total": len(questoes_selecionadas),
                "aprovado_sistema": passou,
                "respostas": respostas_detalhadas
            }
            arquivo_memoria = io.StringIO(json.dumps(dados_backup, indent=4, ensure_ascii=False))
            arquivo_anexo = discord.File(arquivo_memoria, filename=f"prova_{user.name}_{int(datetime.now().timestamp())}.json")
            await canal_backup.send(content=f"💾 **Backup de Prova:** {user.mention}", file=arquivo_anexo)

        # Salva no MongoDB (painel web)
        try:
            from mongo_db import salvar_prova
            salvar_prova(user.id, user.name, acertos, len(questoes_selecionadas), passou, respostas_detalhadas)
        except Exception:
            pass

async def setup(client: commands.Bot):
    await client.add_cog(SistemaProva(client))
