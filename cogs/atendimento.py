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
    #Parte do Braixen's House
    id_cargo_atendente = int(os.getenv("id_cargo_atendente")) 
    id_categoria_staff = int(os.getenv("id_categoria_staff")) 
    id_servidor_bh = int(os.getenv("id_servidor_bh")) 
    id_canal_logs_bh = int(os.getenv("id_canal_logs_bh")) 
    id_canal_avaliacao = int(os.getenv("id_canal_avaliacao"))


    #Parte do Segundo servidor
    id_cargo_tribunal = int(os.getenv("id_cargo_tribunal")) 
    id_categoria_tribunal = int(os.getenv("id_categoria_tribunal")) 
    id_servidor_tribunal= int(os.getenv("id_servidor_tribunal")) 
    id_canal_logs_tri= int(os.getenv("id_canal_logs_tri")) 

except (ValueError, TypeError) as e:
    print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    print("!!! ERRO CRÍTICO AO CARREGAR CONFIGURAÇÕES DE ATENDIMENTO                   !!!")
    print("!!! Verifique se TODAS as variáveis de ambiente no arquivo .env ou          !!!")
    print("!!! na sua plataforma de hospedagem (Render.com) estão definidas e          !!!")
    print("!!! são números de ID válidos. O erro foi:                                  !!!")
    print(f"!!! {e}                                      !!!")
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

#PAINEIS DE USO NAS COMUNIDADES
#PAINEL SUPORTE DO CLÃ (Clash of Clans)
class suporte_cla(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(value="regras_cla",label="Dúvidas sobre Regras do Clã", emoji="📜"),
            discord.SelectOption(value="guerras_cwl",label="Ajuda com Guerras ou CWL", emoji="⚔️"),
            discord.SelectOption(value="doacoes",label="Problemas com Doações", emoji="🛡️"),
            discord.SelectOption(value="denuncia",label="Denunciar um Membro", emoji="🚨"),
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
            tipoticket = "Ticket de Dúvidas sobre Regras"
            staff = id_cargo_atendente
            mensagemcanal = "Por favor, descreva sua dúvida sobre as regras do clã para que um líder ou co-líder possa te ajudar."
            categoriadeatendimento = id_categoria_staff
            await interaction.response.send_message("**Dúvidas sobre as regras?**\n\nAntes de abrir um ticket, por favor, verifique o canal de regras do nosso clã. Se a sua dúvida não for respondida lá, abra um ticket no botão abaixo.", ephemeral=True, view=CreateTicket())

        elif self.values[0] == "guerras_cwl":
            emojiglobal = "⚔️"
            tipoticket = "Ticket de Guerras e CWL"
            staff = id_cargo_atendente
            mensagemcanal = "Por favor, detalhe seu problema ou dúvida sobre a Guerra de Clãs ou a Liga de Guerra. Se for sobre uma base inimiga, envie um print dela."
            categoriadeatendimento = id_categoria_staff
            await interaction.response.send_message("**Precisa de ajuda com a Guerra?**\n\nSe você tem dúvidas sobre qual vila atacar, estratégias, ou algum problema na guerra, abra um ticket para conversar com a liderança.", ephemeral=True, view=CreateTicket())

        elif self.values[0] == "doacoes":
            emojiglobal = "🛡️"
            tipoticket = "Ticket sobre Doações"
            staff = id_cargo_atendente
            mensagemcanal = "Informe qual o problema que você está tendo com as doações (tropas erradas, falta de doação, etc)."
            categoriadeatendimento = id_categoria_staff
            await interaction.response.send_message("**Problemas com doações?**\n\nSe alguém não está seguindo as regras de doação ou você tem alguma outra questão, abra um ticket.", ephemeral=True, view=CreateTicket())

        elif self.values[0] == "denuncia":
            emojiglobal = "🚨"
            tipoticket = "Ticket de Denúncia"
            staff = id_cargo_atendente
            mensagemcanal = "Para a sua denúncia, por favor, escreva detalhadamente o que aconteceu e, se possível, envie prints como prova."
            categoriadeatendimento = id_categoria_staff
            await interaction.response.send_message("**Deseja denunciar um membro?**\n\nPara denunciar alguém por comportamento inadequado, por favor, tenha em mãos o **motivo, o nome do membro e provas (prints)**. Abra um ticket para prosseguir.", ephemeral=True, view=CreateTicket())

        elif self.values[0] == "sugestao":
            emojiglobal = "💡"
            tipoticket = "Ticket de Sugestão"
            staff = id_cargo_atendente
            mensagemcanal = "Agradecemos sua ajuda! Por favor, escreva sua sugestão para o clã da forma mais detalhada possível."
            categoriadeatendimento = id_categoria_staff
            await interaction.response.send_message("**Tem uma sugestão para melhorar o clã?**\n\nAdoramos ouvir novas ideias! Abra um ticket para compartilhar sua sugestão com a liderança.", ephemeral=True, view=CreateTicket())

        elif self.values[0] == "recrutamento":
            emojiglobal = "📈"
            tipoticket = "Ticket de Recrutamento"
            staff = id_cargo_atendente
            mensagemcanal = "Olá! Se você tem interesse em recrutar um amigo ou quer saber mais sobre nosso processo de recrutamento, por favor, nos informe aqui."
            categoriadeatendimento = id_categoria_staff
            await interaction.response.send_message("**Interessado em recrutamento?**\n\nSe você quer convidar um amigo para o clã ou tem alguma dúvida sobre os requisitos, abra um ticket.", ephemeral=True, view=CreateTicket())
        
        elif self.values[0] == "outros":
            emojiglobal = "❔"
            tipoticket = "Ticket de Outros Assuntos"
            staff = id_cargo_atendente
            mensagemcanal = "Por favor, descreva em detalhes o motivo do seu contato para que possamos te ajudar da melhor forma."
            categoriadeatendimento = id_categoria_staff
            await interaction.response.send_message("**Seu assunto não está na lista?**\n\nSem problemas! Crie um ticket clicando no botão abaixo e explique sua situação.", ephemeral=True, view=CreateTicket())


#PAINEL PERSISTENTE
class DropdownSuporte(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(suporte_cla())


#BOTÂO CRIAR TICKET
class CreateTicket(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.value=None

    @discord.ui.button(label="Abrir Ticket",style=discord.ButtonStyle.green,emoji="✅")
    async def ticket(self,interaction: discord.Interaction, button: discord.ui.Button):
        global emojiglobal, staff, categoriadeatendimento, tipoticket
        self.value = True
        self.stop()
        
        atendente = interaction.guild.get_role(staff)
        categoria = interaction.guild.get_channel(categoriadeatendimento)
        
        ticket = utils.get(interaction.guild.text_channels, name =  f"{emojiglobal}┃{interaction.user.name.lower().replace(' ', '-')}-{interaction.user.id}")
        
        if ticket is not None:
            await interaction.response.send_message(f"Ei, você já tem um atendimento sobre isso em andamento aqui: {ticket.mention}!", ephemeral=True)
        else:
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.user: discord.PermissionOverwrite(read_messages=True,send_messages=True,use_application_commands=True),
                atendente: discord.PermissionOverwrite(read_messages=True,send_messages=True,use_application_commands=True)
            }
            channel_name = f"{emojiglobal}┃{interaction.user.name}-{interaction.user.id}"
            ticket = await interaction.guild.create_text_channel(name=channel_name, category=categoria, overwrites=overwrites)
            
            await interaction.response.send_message(f"Criei um ticket para você! Acesse aqui: {ticket.mention}", ephemeral=True)

            embedticket = discord.Embed(
                colour=discord.Color.gold(),
                description=f"**Tópico:** {tipoticket}\n**Responsável:** {atendente.mention}"
            )
            embedticket.set_author(name=f"Atendimento - {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
            embedticket.set_footer(text="Use /atendimento fechar para encerrar o ticket.")
            
            await ticket.send(f"Olá {interaction.user.mention}, seu ticket foi criado!", embed=embedticket)
            if mensagemcanal != "1":
                await ticket.send(f"**Instruções:**\n{mensagemcanal}")


#Botão deletar ticket
class DeleteTicket(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.value=None

    @discord.ui.button(label="Encerrar Ticket",style=discord.ButtonStyle.red,emoji="🗑️")
    async def confirm(self,interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        self.stop()
        
        mod = interaction.guild.get_role(id_cargo_atendente)
        
        if str(interaction.user.id) in interaction.channel.name or (mod and mod in interaction.user.roles):
            await interaction.response.send_message(f"O ticket será encerrado e arquivado em 5 segundos...", ephemeral=True)
            
            if os.path.exists(f"{interaction.channel.id}.md"):
                return await interaction.followup.send(f"Uma transcrição já está sendo gerada!", ephemeral = True)

            log_channel_id = id_canal_logs_bh
            log_channel = interaction.guild.get_channel(log_channel_id)

            if log_channel:
                with open(f"{interaction.channel.id}.md", 'a',encoding="utf-8") as f:
                    f.write(f"# Histórico de {interaction.channel.name}:\n\n")
                    async for message in interaction.channel.history(limit = None, oldest_first = True):
                        created = datetime.strftime(message.created_at, "%d/%m/%Y às %H:%M:%S")
                        f.write(f"[{created}] {message.author}: {message.clean_content}\n")
                    generated = datetime.now().strftime("%d/%m/%Y às %H:%M:%S")
                    f.write(f"\n*Gerado em {generated} (UTC)*")
                
                with open(f"{interaction.channel.id}.md", 'rb') as f:
                    await log_channel.send(file = discord.File(f, f"{interaction.channel.name}.md"))
                os.remove(f"{interaction.channel.id}.md")
            
            await asyncio.sleep(5)
            await interaction.channel.delete()
        else:
            await interaction.response.send_message("Você não tem permissão para fechar este ticket.", ephemeral=True)


#INICIO DA CLASSE
class atendimento(commands.Cog):
    def __init__(self, client: commands.Bot) -> None:
        global botname, botavatar
        self.client = client
        
        if self.client.user:
            botname = self.client.user.name
            botavatar = self.client.user.avatar
        
        self.client.add_view(DropdownSuporte())

    @commands.Cog.listener()
    async def on_ready(self):
        if not botname and self.client.user:
            globals()['botname'] = self.client.user.name
            globals()['botavatar'] = self.client.user.avatar
        print("Cog atendimento (Clash of Clans) carregado.")
  
    #GRUPO PAINEIS DE ATENDIMENTO DO BOT 
    painel=app_commands.Group(name="painel",description="Comandos de paineis de atendimento do bot.")

    @painel.command(name = 'suporte', description='⚔️ Crie um painel de suporte para o clã.')
    @commands.has_permissions(manage_guild=True)
    async def suportebh(self,interaction: discord.Interaction):
        print (f"Usuario: {interaction.user.name} usou painel suporte no servidor {interaction.guild.name}")
        
        embed1 = discord.Embed(
            colour=discord.Color.dark_gold(),
            title=f"🛡️ Central de Atendimento - {interaction.guild.name} 🛡️",
            description="Bem-vindo à central de ajuda do nosso clã! Use o menu abaixo para selecionar o motivo do seu contato e abrir um ticket. Um líder ou co-líder irá te ajudar em breve."
        )
        embed1.set_image(url="https://clashofclans.com/uploaded-images/1545041492_1544101918_coc-news-update-dec-1.jpg")
        embed1.set_footer(text=f"Atendimento do Clã {interaction.guild.name}")

        await interaction.response.send_message("Painel de suporte criado!",ephemeral=True)
        await interaction.channel.send(embed=embed1,view=DropdownSuporte()) 

    #GRUPO DE ATENDIMENTO DO BOT 
    atendi=app_commands.Group(name="atendimento",description="Comandos de atendimento do bot.")

    @atendi.command(name="fechar",description='🗑️ Feche um atendimento em andamento.')
    async def fecharticket(self,interaction: discord.Interaction):
        if "┃" in interaction.channel.name:
            await interaction.response.send_message("Você tem certeza que deseja encerrar este atendimento?", view=DeleteTicket(), ephemeral=True)
        else:
            await interaction.response.send_message("Este comando só pode ser usado em um canal de ticket.", ephemeral=True)

    @atendi.command(name="adicionar",description='➕ Adicione um membro ao ticket.')
    @app_commands.describe(membro="O membro que você deseja adicionar ao ticket.")
    async def adicionar(self,interaction: discord.Interaction,membro: discord.Member):
        if "┃" in interaction.channel.name:
            await interaction.channel.set_permissions(membro, read_messages=True, send_messages=True)
            await interaction.response.send_message(embed=discord.Embed(
                colour=discord.Color.green(),
                title="✅ Membro Adicionado",
                description=f"{membro.mention} foi adicionado a este ticket."
            ))
        else:
            await interaction.response.send_message("Este comando só pode ser usado em um canal de ticket.",ephemeral=True)

    @atendi.command(name="remover",description='➖ Remove um membro do ticket.')
    @app_commands.describe(membro="O membro que você deseja remover do ticket.")
    async def remover(self,interaction: discord.Interaction,membro: discord.Member):
        if "┃" in interaction.channel.name:
            await interaction.channel.set_permissions(membro, overwrite=None)
            await interaction.response.send_message(embed=discord.Embed(
                colour=discord.Color.red(),
                title="❌ Membro Removido",
                description=f"{membro.mention} foi removido deste ticket."
            ))
        else:
            await interaction.response.send_message("Este comando só pode ser usado em um canal de ticket.",ephemeral=True)

async def setup(client:commands.Bot) -> None:
    if config_valida:
        await client.add_cog(atendimento(client))
    else:
        print("O Cog 'atendimento' não foi carregado devido a um erro de configuração nas variáveis de ambiente.")

