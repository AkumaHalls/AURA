import discord,os,asyncio
from discord.ext import commands
from discord import app_commands,utils
from datetime import datetime
from cogs.owner import getdonoid,getmensagemerro
from dotenv import load_dotenv

#GET INFO USO
donoid = getdonoid()
mensagemerro = getmensagemerro()

#CARREGA E LE O ARQUIVO .env na raiz
load_dotenv(os.path.join(os.path.dirname(__file__), '.env')) #load .env da raiz

# Flag para verificar se a configuração é válida
config_valida = True

try:
    #VARIAVEIS NECESSARIAS
    id_cargo_atendente = int(os.getenv("id_cargo_atendente")) 
    id_categoria_staff = int(os.getenv("id_categoria_staff")) 
    id_servidor_bh = int(os.getenv("id_servidor_bh")) 
    id_canal_logs_bh = int(os.getenv("id_canal_logs_bh")) 
    id_canal_avaliacao = int(os.getenv("id_canal_avaliacao"))

    #Parte do Segundo servidor (se houver)
    id_servidor_tribunal= int(os.getenv("id_servidor_tribunal"))
    id_canal_logs_tri= int(os.getenv("id_canal_logs_tri"))

except (ValueError, TypeError) as e:
    print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    print("!!! ERRO CRÍTICO AO CARREGAR CONFIGURAÇÕES DE ATENDIMENTO                   !!!")
    print("!!! Verifique se TODAS as variáveis de ambiente (IDs) estão definidas.      !!!")
    print(f"!!! Erro específico: {e}                                      !!!")
    print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    config_valida = False


#Variaveis de USO GLOBAL
emojiglobal = "⚔️"
tipoticket = "1"
staff = "1"
mensagemcanal = "1"
categoriadeatendimento = "1"
botname = "1"
botavatar = "1"

#PAINEL SUPORTE DO CLÃ (Clash of Clans)
class suporte_cla(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(value="regras_cla",label="Dúvidas sobre Regras do Clã", emoji="📜"),
            discord.SelectOption(value="guerras_cwl",label="Ajuda com Guerras ou CWL", emoji="⚔️"),
            discord.SelectOption(value="doacoes",label="Problemas com Doações", emoji="🛡️"),
            discord.SelectOption(value="denuncia",label="Denunciar um Membro", emoji="🚨"),
            discord.SelectOption(value="apelo_ban",label="Apelar de um Banimento", emoji="🔨"),
            discord.SelectOption(value="sugestao",label="Sugestões para o Clã", emoji="💡"),
            discord.SelectOption(value="recrutamento",label="Interesse em Recrutamento", emoji="📈"),
            discord.SelectOption(value="outros",label="Outros Assuntos", emoji="❔"),
        ]
        super().__init__(
            placeholder="Selecione um tópico para o suporte...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="persistent_view:dropdown_clash_support"
        )
    async def callback(self, interaction: discord.Interaction):
        global emojiglobal, tipoticket, staff, mensagemcanal, categoriadeatendimento

        if self.values[0] == "regras_cla":
            emojiglobal = "📜"
            tipoticket = "Dúvidas sobre Regras"
            staff = id_cargo_atendente
            mensagemcanal = "Por favor, descreva sua dúvida sobre as regras do clã para que um líder ou co-líder possa te ajudar."
            categoriadeatendimento = id_categoria_staff
            await interaction.response.send_message("**Dúvidas sobre as regras?**\n\nAntes de abrir um ticket, por favor, verifique o canal de regras. Se a sua dúvida não for respondida lá, abra um ticket no botão abaixo.", ephemeral=True, view=CreateTicket())

        elif self.values[0] == "guerras_cwl":
            emojiglobal = "⚔️"
            tipoticket = "Guerras e CWL"
            staff = id_cargo_atendente
            mensagemcanal = "Por favor, detalhe seu problema ou dúvida sobre a Guerra de Clãs ou a Liga de Guerra. Se for sobre uma base inimiga, envie um print dela."
            categoriadeatendimento = id_categoria_staff
            await interaction.response.send_message("**Precisa de ajuda com a Guerra?**\n\nSe você tem dúvidas sobre qual vila atacar ou estratégias, abra um ticket para conversar com a liderança.", ephemeral=True, view=CreateTicket())

        elif self.values[0] == "doacoes":
            emojiglobal = "🛡️"
            tipoticket = "Doações"
            staff = id_cargo_atendente
            mensagemcanal = "Informe qual o problema que você está tendo com as doações (tropas erradas, falta de doação, etc)."
            categoriadeatendimento = id_categoria_staff
            await interaction.response.send_message("**Problemas com doações?**\n\nSe alguém não está seguindo as regras de doação ou você tem alguma outra questão, abra um ticket.", ephemeral=True, view=CreateTicket())

        elif self.values[0] == "denuncia":
            emojiglobal = "🚨"
            tipoticket = "Denúncia"
            staff = id_cargo_atendente
            mensagemcanal = "Para a sua denúncia, por favor, escreva detalhadamente o que aconteceu e, se possível, envie prints como prova."
            categoriadeatendimento = id_categoria_staff
            await interaction.response.send_message("**Deseja denunciar um membro?**\n\nPara denunciar alguém, tenha em mãos o **motivo, o nome do membro e provas (prints)**. Abra um ticket para prosseguir.", ephemeral=True, view=CreateTicket())

        elif self.values[0] == "apelo_ban":
            emojiglobal = "🔨"
            tipoticket = "Apelo de Banimento"
            staff = id_cargo_atendente
            mensagemcanal = "Para seu apelo, por favor, informe sua **TAG de jogador do Clash of Clans**, o **motivo do banimento** (se souber) e **por que você acredita que a punição deve ser revertida**."
            categoriadeatendimento = id_categoria_staff
            await interaction.response.send_message("**Você foi banido do clã e deseja apelar?**\n\nEntendemos que erros podem acontecer. Para que possamos analisar seu caso, por favor, abra um ticket.", ephemeral=True, view=CreateTicket())

        elif self.values[0] == "sugestao":
            emojiglobal = "💡"
            tipoticket = "Sugestão"
            staff = id_cargo_atendente
            mensagemcanal = "Agradecemos sua ajuda! Por favor, escreva sua sugestão para o clã da forma mais detalhada possível."
            categoriadeatendimento = id_categoria_staff
            await interaction.response.send_message("**Tem uma sugestão para melhorar o clã?**\n\nAdoramos ouvir novas ideias! Abra um ticket para compartilhar sua sugestão com a liderança.", ephemeral=True, view=CreateTicket())

        elif self.values[0] == "recrutamento":
            emojiglobal = "📈"
            tipoticket = "Recrutamento"
            staff = id_cargo_atendente
            mensagemcanal = "Olá! Se você tem interesse em recrutar um amigo ou quer saber mais sobre nosso processo de recrutamento, por favor, nos informe aqui."
            categoriadeatendimento = id_categoria_staff
            await interaction.response.send_message("**Interessado em recrutamento?**\n\nSe você quer convidar um amigo para o clã ou tem alguma dúvida sobre os requisitos, abra um ticket.", ephemeral=True, view=CreateTicket())
        
        elif self.values[0] == "outros":
            emojiglobal = "❔"
            tipoticket = "Outros Assuntos"
            staff = id_cargo_atendente
            mensagemcanal = "Por favor, descreva em detalhes o motivo do seu contato para que possamos te ajudar da melhor forma."
            categoriadeatendimento = id_categoria_staff
            await interaction.response.send_message("**Seu assunto não está na lista?**\n\nSem problemas! Crie um ticket clicando no botão abaixo.", ephemeral=True, view=CreateTicket())


#PAINEL PERSISTENTE
class DropdownSuporte(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(suporte_cla())


#BOTÂO CRIAR TICKET
class CreateTicket(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(label="Abrir Ticket",style=discord.ButtonStyle.green,emoji="✅")
    async def ticket(self,interaction: discord.Interaction, button: discord.ui.Button):
        global emojiglobal, staff, categoriadeatendimento, tipoticket, mensagemcanal
        
        atendente = interaction.guild.get_role(staff)
        categoria = interaction.guild.get_channel(categoriadeatendimento)
        
        channel_name = f"{emojiglobal}┃{interaction.user.name.lower().replace(' ', '-')}-{interaction.user.id}"
        ticket = utils.get(interaction.guild.text_channels, name=channel_name)
        
        if ticket is not None:
            await interaction.response.send_message(f"Ei, você já tem um atendimento sobre isso em andamento aqui: {ticket.mention}!", ephemeral=True)
        else:
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.user: discord.PermissionOverwrite(read_messages=True,send_messages=True,use_application_commands=True),
                atendente: discord.PermissionOverwrite(read_messages=True,send_messages=True,use_application_commands=True)
            }
            ticket = await interaction.guild.create_text_channel(name=channel_name, category=categoria, overwrites=overwrites)
            await interaction.response.send_message(f"Criei um ticket para você! Acesse aqui: {ticket.mention}", ephemeral=True)

            embedticket = discord.Embed(
                colour=discord.Color.gold(),
                description=f"**Tópico:** {tipoticket}\n**Responsável:** {atendente.mention}"
            )
            # A linha abaixo usa o ícone do servidor dinamicamente
            embedticket.set_author(name=f"Atendimento - {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
            embedticket.set_footer(text="Aguarde um momento, estou preparando o canal para você...")
            
            await ticket.send(f"Avisando: {interaction.user.mention}", embed=embedticket)
            await ticket.purge(limit=1)
            await ticket.send(embed=embedticket)
            
            # --- CONVERSA DE ABERTURA ---
            async with ticket.typing():
                await asyncio.sleep(1.5)
            await ticket.send(f"Oiiie {interaction.user.mention}, **tudo bem?**")
            async with ticket.typing():
                await asyncio.sleep(1.0)
            await ticket.send(f"Seja muito bem-vindo(a) ao atendimento do clã **{interaction.guild.name}**!")
            async with ticket.typing():
                await asyncio.sleep(1.5)
            await ticket.send(f"Daqui a pouco você será **atendido** por um {atendente.mention}.")
            async with ticket.typing():
                await asyncio.sleep(1.5)
            await ticket.send(f"Enquanto isso, por favor, nos dê o máximo de detalhes sobre o seu caso.")
            if mensagemcanal != "1":
                await ticket.send(f"```{mensagemcanal}```")


#Botão deletar ticket
class DeleteTicket(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(label="Confirmar Encerramento",style=discord.ButtonStyle.danger,emoji="🗑️")
    async def confirm(self,interaction: discord.Interaction, button: discord.ui.Button):
        mod = interaction.guild.get_role(id_cargo_atendente)
        
        if str(interaction.user.id) in interaction.channel.name or (mod and mod in interaction.user.roles):
            await interaction.response.send_message(f"Okay! Salvando o histórico e fechando este ticket em 5 segundos...")
            button.disabled = True
            await interaction.message.edit(view=self)

            log_channel = None
            if interaction.guild.id == id_servidor_bh:
                log_channel = interaction.guild.get_channel(id_canal_logs_bh)
            elif interaction.guild.id == id_servidor_tribunal:
                 log_channel = interaction.guild.get_channel(id_canal_logs_tri)

            if log_channel:
                log_filename = f"{interaction.channel.id}.md"
                with open(log_filename, 'a', encoding="utf-8") as f:
                    f.write(f"# Histórico de {interaction.channel.name}:\n\n")
                    async for message in interaction.channel.history(limit=None, oldest_first=True):
                        created = datetime.strftime(message.created_at, "%d/%m/%Y às %H:%M:%S")
                        f.write(f"[{created}] {message.author}: {message.clean_content}\n")
                    generated = datetime.now().strftime("%d/%m/%Y às %H:%M:%S")
                    f.write(f"\n*Gerado em {generated} (UTC)*")
                
                with open(log_filename, 'rb') as f:
                    await log_channel.send(f"Transcrição do ticket `{interaction.channel.name}`:", file=discord.File(f, f"{interaction.channel.name}.md"))
                os.remove(log_filename)
            
            await asyncio.sleep(5)
            await interaction.channel.delete()
        else:
            await interaction.response.send_message("Você não tem permissão para fechar este ticket.", ephemeral=True)


#INICIO DA CLASSE
class atendimento(commands.Cog):
    def __init__(self, client: commands.Bot) -> None:
        self.client = client
        self.client.add_view(DropdownSuporte())

    @commands.Cog.listener()
    async def on_ready(self):
        print("Cog atendimento (Clash of Clans) carregado.")
  
    #GRUPO PAINEIS
    painel=app_commands.Group(name="painel",description="Comandos de paineis de atendimento do bot.")

    @painel.command(name='suporte', description='⚔️ Crie um painel de suporte para o clã.')
    @commands.has_permissions(manage_guild=True)
    async def suporte(self,interaction: discord.Interaction):
        embed = discord.Embed(
            colour=discord.Color.dark_gold(),
            title=f"🛡️ Central de Atendimento - {interaction.guild.name} 🛡️",
            description="Bem-vindo à central de ajuda do nosso clã! Use o menu abaixo para selecionar o motivo do seu contato e abrir um ticket. Um líder ou co-líder irá te ajudar em breve."
        )
        # --- MUDANÇA PRINCIPAL AQUI ---
        # Usa o ícone do servidor como imagem principal do painel.
        # Se o servidor não tiver ícone, nenhuma imagem será mostrada.
        if interaction.guild.icon:
            embed.set_image(url=interaction.guild.icon.url)

        embed.set_footer(text=f"Atendimento do Clã {interaction.guild.name}")
        await interaction.response.send_message("Painel de suporte criado!",ephemeral=True)
        await interaction.channel.send(embed=embed,view=DropdownSuporte()) 

    #GRUPO DE ATENDIMENTO
    atendi=app_commands.Group(name="atendimento",description="Comandos de atendimento do bot.")

    @atendi.command(name="encerrar", description='✉️ Envia a mensagem final para encerrar um ticket.')
    @commands.has_permissions(manage_roles=True)
    async def encerrar(self, interaction: discord.Interaction):
        if "┃" not in interaction.channel.name:
            return await interaction.response.send_message("Este comando só pode ser usado em um canal de ticket.", ephemeral=True)

        membro_id_str = interaction.channel.name.split('-')[-1]
        try:
            membro = interaction.guild.get_member(int(membro_id_str))
            membro_mention = membro.mention if membro else f"(ID: {membro_id_str})"
        except ValueError:
            membro_mention = "(usuário não encontrado)"

        await interaction.response.send_message("Enviando mensagem de encerramento...", ephemeral=True)
        
        async with interaction.channel.typing():
                await asyncio.sleep(1.5)
        await interaction.channel.send(f"Olá novamente {membro_mention}!")
        async with interaction.channel.typing():
                await asyncio.sleep(2)
        await interaction.channel.send(f"Parece que seu atendimento está chegando ao fim.")
        async with interaction.channel.typing():
                await asyncio.sleep(2)
        await interaction.channel.send(f"O clã **{interaction.guild.name}** agradece o contato e esperamos que seu problema tenha sido resolvido!")
        async with interaction.channel.typing():
                await asyncio.sleep(2)
        await interaction.channel.send(f"Para finalizar e arquivar esta conversa, por favor, use o comando `/atendimento fechar` ou clique no botão abaixo se ele for exibido.")

    @atendi.command(name="fechar",description='🗑️ Inicia o processo para fechar um ticket.')
    async def fechar(self,interaction: discord.Interaction):
        if "┃" in interaction.channel.name:
            await interaction.response.send_message("Você tem certeza que deseja **encerrar e arquivar** este atendimento?", view=DeleteTicket(), ephemeral=True)
        else:
            await interaction.response.send_message("Este comando só pode ser usado em um canal de ticket.", ephemeral=True)

    @atendi.command(name="adicionar",description='➕ Adicione um membro ao ticket.')
    @app_commands.describe(membro="O membro que você deseja adicionar.")
    @commands.has_permissions(manage_roles=True)
    async def adicionar(self,interaction: discord.Interaction,membro: discord.Member):
        if "┃" in interaction.channel.name:
            await interaction.channel.set_permissions(membro, read_messages=True, send_messages=True)
            await interaction.response.send_message(embed=discord.Embed(
                colour=discord.Color.green(), title="✅ Membro Adicionado",
                description=f"{membro.mention} foi adicionado a este ticket."
            ))
        else:
            await interaction.response.send_message("Este comando só pode ser usado em um canal de ticket.",ephemeral=True)

    @atendi.command(name="remover",description='➖ Remove um membro do ticket.')
    @app_commands.describe(membro="O membro que você deseja remover.")
    @commands.has_permissions(manage_roles=True)
    async def remover(self,interaction: discord.Interaction,membro: discord.Member):
        if "┃" in interaction.channel.name:
            await interaction.channel.set_permissions(membro, overwrite=None)
            await interaction.response.send_message(embed=discord.Embed(
                colour=discord.Color.red(), title="❌ Membro Removido",
                description=f"{membro.mention} foi removido deste ticket."
            ))
        else:
            await interaction.response.send_message("Este comando só pode ser usado em um canal de ticket.",ephemeral=True)

async def setup(client:commands.Bot) -> None:
    if config_valida:
        await client.add_cog(atendimento(client))
    else:
        print("O Cog 'atendimento' não foi carregado devido a um erro de configuração nas variáveis de ambiente.")

