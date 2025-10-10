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
    id_cargo_atendente = int(os.getenv("id_cargo_atendente")) #Coloque aqui o ID do cargo de atendente do primeiro servidor
    id_categoria_staff = int(os.getenv("id_categoria_staff")) #Coloque aqui o ID da caregoria onde deseja que os tickets sejam criados (para primeiro servidor)
    id_servidor_bh = int(os.getenv("id_servidor_bh")) #ID do primeiro servidor
    id_canal_logs_bh = int(os.getenv("id_canal_logs_bh")) #ID do canal de logs do primeiro servidor
    id_canal_avaliacao = int(os.getenv("id_canal_avaliacao")) #ID do canal para envio das avaliações


    #Parte do Segundo servidor
    id_cargo_tribunal = int(os.getenv("id_cargo_tribunal")) #Coloque aqui o ID do cargo de atendente do segundo servidor
    id_categoria_tribunal = int(os.getenv("id_categoria_tribunal")) #Coloque aqui o ID da caregoria onde deseja que os tickets sejam criados (para Segundo servidor)
    id_servidor_tribunal= int(os.getenv("id_servidor_tribunal")) #ID do segundo servidor
    id_canal_logs_tri= int(os.getenv("id_canal_logs_tri")) #ID do canal de logs do segundo servidor

except (ValueError, TypeError) as e:
    print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    print("!!! ERRO CRÍTICO AO CARREGAR CONFIGURAÇÕES DE ATENDIMENTO                   !!!")
    print("!!! Verifique se TODAS as variáveis de ambiente no arquivo .env ou          !!!")
    print("!!! na sua plataforma de hospedagem (Render.com) estão definidas e          !!!")
    print("!!! são números de ID válidos. O erro foi:                                  !!!")
    print(f"!!! {e}                                      !!!")
    print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    config_valida = False


#Variaveis de USO GLOBAL| Se Quiser editar só edite o emojiglobal blz, o resto deixe do jeito que está
emojiglobal = "🦊"
tipoticket = "1"
staff = "1"
mensagemcanal = "1"
categoriadeatendimento = "1"
botname = "1"
botavatar = "1"

#PAINEIS DE USO NAS COMUNIDADES
#PAINEL SUPORTE BRAIXEN HOUSE
class suporte_bh(discord.ui.Select): #a class aqui recebeu o nome de Dropdown para cada classe tem que ter Nomes diferentes viu nos proximos você vai ver que eu mudei
    def __init__(self):
        options = [ #Opções do dropdown (Aqui são listadas todas as opções do menu pode adicionar ou remover se necessario) divirta-se
            
            #Ajuda adicional Value(condição para buscar resposta no Callback)| Label (texto que será exibido no menu no chat do discord) | Emoji (é só o emoji)
            
            discord.SelectOption(value="duvidas",label="Dúvidas sobre temas gerais.", emoji="⁉️"),
            discord.SelectOption(value="denuncia",label="Faça uma Denúncia.", emoji="🚨"),
            discord.SelectOption(value="bugs",label="informe um bug no servidor.", emoji="🐞"),
            discord.SelectOption(value="solicitacao",label="Solicitações de cargos ou conversões.", emoji="🔔"),
            discord.SelectOption(value="premiacao",label="Resgatar um prêmio de evento.", emoji="🎁"),
            discord.SelectOption(value="vip",label="Compre seu vip.", emoji="🌟"),
            discord.SelectOption(value="sugestao",label="Envie uma sugestão.", emoji="💡"),
            discord.SelectOption(value="parceria",label="Desejo divulgar no Braixen's House.", emoji="🤝"),
            discord.SelectOption(value="Staff",label="Vire um Staff no Braixen's House.", emoji="💼"),
            discord.SelectOption(value="foxcloud",label="Estado do nosso servidor.", emoji="🖥️"),
            discord.SelectOption(value="outros",label="Nenhuma das opções acima.", emoji="🦊"),
        ]
        super().__init__(
            placeholder="Selecione uma opção...", #Placeholder exibe um texto padrão quando não é selecionado nada pelo usuario
            min_values=1,
            max_values=1,
            options=options,
            custom_id="persistent_view:dropdown_help" #a ID do seu Dropdown | Importante caso tenha mais de 1 viu pois você tem que editar ele
        )
    async def callback(self, interaction: discord.Interaction): #Retorno do que foi selecionado no menu Dropdown
        # global = to puxando variaveis de fora do codigo para editar elas aqui, são as que estão na linha 5 a 19
        global emojiglobal #Puxa a variavel emoji global para editar posteriormente
        global tipoticket #Puxa a variavel do tipo de ticket para editar posteriormente
        global staff #Puxa a variavel staff para editar posteriormente
        global mensagemcanal #Puxa a variavel de mensagem do canal para editar posteriormente
        global categoriadeatendimento #Puxa a categoria de atendimento para editar posteriormente

        #Abaixo são as condições elas vão usar o VALUE para entrar em uma condição
        if self.values[0] == "duvidas": # < puxo o valor selecionado e verifico se ele é igual a duvidas se sim ele roda a condição, se não ele vai para as proximas.
            emojiglobal = "⁉️" #definindo o emoji antes "1" para o ⁉️
            tipoticket = "Ticket de dúvidas" #definindo o tipo de ticket
            staff = id_cargo_atendente #indicando qual é o staff para esse ticket
            mensagemcanal = "1" #define mensagem do canal | nesse aqui não é usado então eu deixei padrão 1 em outros você verá que terá isso.
            categoriadeatendimento = id_categoria_staff #definindo a categoria de atendimento onde ele deve criar o ticket
            await interaction.response.send_message("**Dúvidas Gerais?** \n\nSabia que temos um canal exclusivo onde você pode ser ajudado por todos. \nTodas as dúvidas estão centralizadas em <#1027376614054576138> e você pode pesquisar lá dentro, se não tiver sua dúvida você mesmo pode postar lá e aguardar alguém te responder.",ephemeral=True) #resposta para a interação texto padrão com o ephemeral ativado (ephemeral é aquelas mensagem que só o proprio membro ve)
    # Daqui para baixo e copia e cola mudando as variaveis, lembre-se as opções aqui devem iniciar primeiro com um if (linha 74) e depois tudo com elif blz, e a quantidade de opções aqui deve ser igual ao dropdown lá em cima, cada dropdown lá tem que ter uma condição aqui.
    # o CreateTicket é o botão de abertura de ticket, aqui puxamos ele mas o codigo dele ta lá em baixo perdido.
        elif self.values[0] == "denuncia":
            emojiglobal = "🚨"
            tipoticket = "Ticket de Denúncias"
            staff = id_cargo_atendente
            mensagemcanal = "**Para a sua denúncia por favor escreva detalhadamente o acontecimento e envia captura de tela ou anexo como prova da sua denuncia, agilize seu atendimento enviando agora mesmo as informações.**"
            categoriadeatendimento = id_categoria_staff
            await interaction.response.send_message("**Deseja denúciar alguém?** \n\nPara **denúnciar** alguém por favor tenha em maos **motivo da denúncia, autor (usuario ou ID) e provas.** \n\nPara prosseguir com sua denúncia abra o ticket abaixo.",ephemeral=True,view=CreateTicket())
      
        elif self.values[0] == "bugs":
            emojiglobal = "🐞"
            tipoticket = "Ticket de Bugs e Problemas"
            staff = id_cargo_atendente
            mensagemcanal = "**Envie uma captura de tela do seu bug aqui neste canal e nos conte como você encontrou esse bug para que possamos resolver.**"
            categoriadeatendimento = id_categoria_staff
            await interaction.response.send_message("**Encontrou um bug em nosso servidor?** \n\nPara reportar um bug em nosso servidor tenha em mãos o **maximo de detalhes** sobre o bug relatado, inclua **capturas de tela** e **descreva detalhadamente.** \nAbra o ticket com o botão abaixo.",ephemeral=True,view=CreateTicket())
        
        elif self.values[0] == "solicitacao":
            emojiglobal = "🔔"
            tipoticket = "Ticket de Solicitações"
            staff = id_cargo_atendente
            mensagemcanal = "**Adiante seu atendimento enviando as informações da sua solicitação, assim que o atendente chegar ele já resolve seu caso imediatamente.**"
            categoriadeatendimento = id_categoria_staff
            await interaction.response.send_message("**Solicitações?** \n\nVocê pode solicitar por varios serviços como por exemplo: \n\n*Mudanças no servidor.* \n*Novos cargos. *\n*Novas Categorias.* \n*Novos Canais.* \n\nAbra o ticket com o botão abaixo.",ephemeral=True,view=CreateTicket())

        elif self.values[0] == "premiacao":
            emojiglobal = "🎁"
            tipoticket = "Ticket de Retirada de Prêmios"
            staff = id_cargo_atendente
            mensagemcanal = "**adiante seu atendimento informando qual é o prêmio que você deseja retirar assim que o atendente chegar ele já sabe do que se trata.**"
            categoriadeatendimento = id_categoria_staff
            await interaction.response.send_message("**Ganhou um Prêmio?** \n\nRetire aqui mesmo seu prêmio de eventos realizados e que sejam entregues pelo Braixen's House. \nAbra o ticket com o botão abaixo.",ephemeral=True,view=CreateTicket())
        
        elif self.values[0] == "sugestao":
            emojiglobal = "💡"
            tipoticket = "Ticket de Sugestões"
            staff = id_cargo_atendente
            mensagemcanal = "1"
            categoriadeatendimento = id_categoria_staff
            await interaction.response.send_message("**Sugestões?** \n\nSabia que temos um canal exclusivo para o envio de sugestões. \nTodas as Súgestões estão centralizadas no <#1027376614054576138> você pode filtrar sua busca ou escrever uma do zero, mas seja bastante detalhista em sua sugestão blz.",ephemeral=True)
        
        elif self.values[0] == "parceria":
            emojiglobal = "🤝"
            tipoticket = "Ticket de divulgações"
            staff = id_cargo_atendente
            mensagemcanal = "O Braixen's House está sujeito a avaliação de requisitos e a possiveis cobranças pela sua divulgação. \n\nNesta Modalidade **todas as parcerias** precisam ser feitas em conjunto com um **sorteio** pois será dessa forma que iremos efetuar **sua divulgação.**\n*Adiante seu atendimento enviando o link do seu servidor para fazermos a analise dele*"
            categoriadeatendimento = id_categoria_staff
            await interaction.response.send_message("**Deseja divulgar algo no STF/ASGARD?** \nPara **divulgar seu servidor, bot ou outros projetos.**\nO *Braixen's House* pode **te ajudar com isso** mas estamos **sujeito a avaliação de requisitos** e a possiveis **cobranças pela sua divulgação**. \n\nNesta Modalidade **todas as parcerias** precisam ser feitas em conjunto com um **sorteio** pois será dessa forma que iremos efetuar **sua divulgação.**\n**Visite o Canal** de <#982990181307142174> e **confirá os topicos 2 e 3** que informamos com detalhes como **funciona e como avaliamos**.\n\n **Não abra o ticket sem ler sobre nosso protocolo.**",ephemeral=True,view=CreateTicket())
        
        elif self.values[0] == "Staff":
            emojiglobal = "💼"
            tipoticket = "Ticket de Formulário staff"
            staff = id_cargo_atendente
            mensagemcanal = "1"
            categoriadeatendimento = id_categoria_staff
            await interaction.response.send_message("**Deseja fazer parte do time STF/ASGARD?** \n\nSabia que temos um formulário para quem está interessado em se tornar um staff você pode abrir ele e verificar se estamos aceitando novos formulários, Olha ta aqui o link: \nhttps://docs.google.com/forms/d/e/1FAIpQLSeZGFDS7g5oiaFV6lE2KiErLCAQXazW3SY9tieWeT5zrlOF5g/viewform?usp=sf_link",ephemeral=True)

        elif self.values[0] == "vip":
            emojiglobal = "🌟"
            tipoticket = "Ticket de Compra de vip"
            staff = id_cargo_atendente
            mensagemcanal = "**Já sabe qual plano vai querer? se não visite <#1072176670196367420> e escolha seu plano e depois volte aqui.**\n\n **Adiante seu atendimento indicando se deseja comprar por sonhos ou por Tails coin e o plano desejado.** \n Compras por tails coin use o comando T!pagar Valor @domembro"
            categoriadeatendimento = id_categoria_staff
            await interaction.response.send_message("**Deseja Comprar seu Vip?** \n\nPara comprar seu vip mensal abra um ticket com o botão abaixo.\n\n*Sabia que você pode comprar a assinatura vitalícia diretamente pela loja do AKUMA usando `T!buy 1` super simples e fácil* ",ephemeral=True,view=CreateTicket())

        
        elif self.values[0] == "foxcloud":
            emojiglobal = "🖥️"
            tipoticket = "Ticket de serviços Foxcloud"
            staff = id_cargo_atendente
            mensagemcanal = "**adiante seu atendimento enviando seu problema incluindo captura de tela, assim que o atendente chegar ele já sabe do que se trata.**"
            categoriadeatendimento = id_categoria_staff
            await interaction.response.send_message("**Problemas com o servidor FoxCloud?** \n\n*Já conhece nossos varios serviços?* \nconsulte todos em <#970376187606097980>. \n\nCaso você tenha dificuldades de acesso aos serviços ou percebeu que um de nossos bots está offline, verifique se já avisamos em <#888567677784829982> ou no nosso canal de <#1009948353251004557>\ncaso não tenhamos informado nada por favor abra um ticket abaixo",ephemeral=True,view=CreateTicket())
       
        elif self.values[0] == "outros":
            emojiglobal = "🦊"
            tipoticket = "Ticket de Outros Motivos"
            staff = id_cargo_atendente
            mensagemcanal = "**Por favor descreva o motivo do seu contato, assim que o atendente chegar ele já sabe do que se trata.**"
            categoriadeatendimento = id_categoria_staff
            await interaction.response.send_message("**Não tem sua Questão?** \n\nNão tem problema, por favor crie um ticket clicando no botão abaixo",ephemeral=True,view=CreateTicket())

# UFAAA, se chegou até aqui seu primeiro painel já está quase configurado eu acho, daqui para baixo é mais coisa importante viu.

#PAINEIS PERSISTENTES 
# Isso aqui é importante, essa parte aqui indica que os paineis que criamos devem ser pesistentes, então toda vez que você reiniciar seu bot e já tiver um painel criado ele automaticamente puxa o já existente, assim você não precisa criar um novo toda vez blz.
# CADA DROPDOWN deve receber um custom_id diferente então elas são diferentes para não confundir esse cara aqui, se elas forem iguais vai bugar esse cara

#PAINEl PERSISTENTES SUPORTE BRAIXEN HOUSE
class DropdownSuporte(discord.ui.View): # Olha a classe aqui, ela é diferente das lá de cima blz.
    def __init__(self): #não me pergunta pq eu não sei oque é só coloca que precisa.
        super().__init__(timeout=None) #isso aqui define o tempo que o painel vai expirar, nesse caso none é NUNCAAAAA.
        self.add_item(suporte_bh())#isso aqui eu to falando que ele vai adicionar o dropdown de novo em caso de reinicio.

# PAINEL CONTRATAÇÂO BRAIXEN HOUSE
# PAINEL DE CONTRATAÇÂO TAMBÉM PARA O PRIMEIRO SERVIDOR, MESMAS COISAS DO PRIMEIRO SÒ MUDA VARIAVEL

class contratacao_bh(discord.ui.Select): # Olha a classe aqui antes a outra era Dropdown, pela minha falta de criatividade vai Dropdown2
    def __init__(self):
        options = [#Opções do dropdown| mesma pegada do outro porem com opções diferentes e bem menor rsrsrsr
            discord.SelectOption(value="bots",label="Quero desenvolver meu proprio bot.", emoji="🤖"),
            discord.SelectOption(value="servidor",label="Quero montar um servidor.", emoji="🛡️"),
            discord.SelectOption(value="outros",label="Outras Solicitações.", emoji="🌐"),
        ]
        super().__init__(
            placeholder="Selecione uma opção...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="persistent_view:dropdown_sevice" #OUUUUUU lembra disso aqui, cada dropdown tem sua propria ID para não ter erro, compare com o de cima e veja a diferença
        )
    async def callback(self, interaction: discord.Interaction): #Retorno seleção Dropdown do painel de contratação
        #mesma coisa do de cima, Puxando variaveis para usar e editar rsrsrs
        global emojiglobal
        global tipoticket
        global staff
        global mensagemcanal
        global categoriadeatendimento

            #mesmo esquema de condição do de lá de cima blz define as coisas, verifica o values e responde
        if self.values[0] == "bots":
            emojiglobal = "🤖"
            tipoticket = "Ticket de Desenvolvimento de Bots"
            staff = id_cargo_atendente
            mensagemcanal = "Conte para a gente como você deseja o seu bot? se já tem alguma coisa fale sobre ela para que possamos te ajudar."
            categoriadeatendimento = id_categoria_staff
            await interaction.response.send_message("**Deseja ter seu proprio bot?** \n\npois bem o Akuma tem alguns conhecimentos e é bem provável que ele tenha uma solução para você.\n\nabre um ticket ai para ele te ajudar.",ephemeral=True,view=CreateTicket())
       
        elif self.values[0] == "servidor":
            emojiglobal = "💻"
            tipoticket = "Ticket de Montagem de Servidores"
            staff = id_cargo_atendente
            mensagemcanal = "Você já tem uma ideia de como deseja seu servidor? qual tema ele irá abordar? escreva aqui para a gente saber e poder te ajudar."
            categoriadeatendimento = id_categoria_staff
            await interaction.response.send_message("**Deseja ajuda para montar seu proprio servidor?** \n\no Akuma oferece o serviço de montagem de servidores que inclui **planejamento** e **implantação** de toda a estrutura e configuração de bots populares.\n\no Valor inicial dos serviços é de R$ 40,00 Reais. \n*podendo haver acrecimos com base no tamanho do projeto* \n\n**Não aceitamos pagamento** em Sonhos, Foxcoin ou qualquer outra moeda de bot.",ephemeral=True,view=CreateTicket())
        elif self.values[0] == "outros":
            emojiglobal = "🌐"
            tipoticket = "Ticket de Outras Solicitações"
            staff = id_cargo_atendente
            mensagemcanal = "Conta para a gente oque você deseja solicitar de serviço."
            categoriadeatendimento = id_categoria_staff
            await interaction.response.send_message("**Não tem sua solicitação listada?** \n\nNão se preocupe, crie um ticket assim mesmo.",ephemeral=True,view=CreateTicket())


#PAINEL PERSISTENTE CONTRATAÇÂO BRAIXEN HOUSE - IGUAL O DE CIMA MAS PUXA O CONTRATAÇÂO
class DropdownContratacao(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(contratacao_bh())

# PAINEL DO TRIBUNAL PARA O SEGUNDO SERVIDOR | esse é usado no segundo servidor blz mas é copia e cola dos outros só mudando as variaveis.
class tribunal_bh(discord.ui.Select): # CLASSEE EDITADA DE NOVOOOOOO BIRL Dropdown3 agora
    def __init__(self):
        options = [#Opções do dropdown qe vão aparecer no dropdown
            discord.SelectOption(value="questionar",label="Quero questionar meu ban.", emoji="🔨"),
            discord.SelectOption(value="duvidas",label="Tenho dúvidas sobre meu ban.", emoji="❓"),
            discord.SelectOption(value="regras",label="Dúvidas sobre as regras.", emoji="📋"),
        ]
        super().__init__(
            placeholder="Selecione uma opção...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="persistent_view:dropdown_tribunal" #Olha a porra da ID aqui de novo e ela ta diferente viuuuu lembra disso que vamos usar depois
        )
    async def callback(self, interaction: discord.Interaction): #Retorno seleção Dropdown do painel do tribunal

        #(CTRL+V) mesma coisa do de cima, Puxando variaveis para usar e editar rsrsrs
        global emojiglobal
        global tipoticket
        global staff
        global mensagemcanal
        global categoriadeatendimento
        
        # Aqui é igualzinho aos outros, só muda as condições 🤙
        if self.values[0] == "questionar":
            emojiglobal = "🔨"
            tipoticket = "Ticket de Questionamento de Banimento"
            staff = id_cargo_tribunal
            mensagemcanal = "Por favor escreva no chat o horario que você foi banido e passe a sua ID de usuario ou seu Discord Tag."
            categoriadeatendimento = id_categoria_tribunal
            await interaction.response.send_message("**Deseja Questionar o seu banimento?** \n\nSe você foi banido do STF/ASGARD e acredita que seu banimento tenha sido injusto.\n\nabre um ticket ai e vamos revisar o seu caso.",ephemeral=True,view=CreateTicket())
       
        elif self.values[0] == "duvidas":
            emojiglobal = "❓"
            tipoticket = "Ticket de Dúvidas"
            staff = id_cargo_tribunal
            mensagemcanal = "nada"
            categoriadeatendimento = id_categoria_tribunal
            await interaction.response.send_message("**Está com dúvidas sobre o seu banimento?** \n\nBom todos os registros do STF/ASGARD estão disponívels de forma replicada neste servidor, no Canal <#1046777277582692393>.\n\nCaso você não entenda o motivo do seu banimento abra a opção de Questionar seu banimento e vamos exclarecer a todas as suas dúvidas.",ephemeral=True)
        
        elif self.values[0] == "regras":
            emojiglobal = "📋"
            tipoticket = "Ticket de Outras Solicitações"
            staff = id_cargo_tribunal
            mensagemcanal = "nada"
            categoriadeatendimento = id_categoria_tribunal
            await interaction.response.send_message("**Você tem dúvidas sobre as regras?** \n\nNão se preocupe, todas elas estão em <#810674050581659673>.",ephemeral=True)



#PAINEL PERSISTENTE TRIBUNAL BRAIXEN HOUSE - igualzinho, mas puxa o tribunal
class DropdownTribunal(discord.ui.View):
    def __init__(self): 
        super().__init__(timeout=None)
        self.add_item(tribunal_bh())


#BOTÔES DOS PAINEIS DE ATENDIMENTO
#BOTÂO CRIAR TICKET
#lembra do botão que puxamos lá em cima em um monte de opção, ele ta aquiiii
class CreateTicket(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.value=None

     # visual do botão aqui, label é o texto que vai estar no botão| Style é a cor, consulte a documentação pois tem cores especificas | Emoji é o emoji do botão
    @discord.ui.button(label="Abrir Ticket",style=discord.ButtonStyle.blurple,emoji="🦊")
    async def ticket(self,interaction: discord.Interaction, button: discord.ui.Button):
        global emojiglobal
        global staff
        global categoriadeatendimento
        self.value = True
        self.stop()
        ticket = None
                #Embed do ticket depois de apertar o botão
        embedticket = discord.Embed(
            colour=discord.Color.yellow(),
            description=f"*Atendimento: {tipoticket}*\nResponsavel: <@&{staff}>"
        )
        #a linha a baixo foi comentada pois o bot de teste não tinha avatar
        #embedticket.set_author(name=f"{botname}",icon_url=f"{botavatar}")
        embedticket.set_thumbnail(url="https://i.imgur.com/fv378Un.png")
        embedticket.set_footer(text="Você pode usar `/atendimento fechar` para encerrar o atendimento!")
                
                #comando para abrir canal normal
                #aqui defino novas condições para ser usado na verificação desse codigo.
        atendente = interaction.guild.get_role(staff)
        categoria = interaction.guild.get_channel(categoriadeatendimento)
        #a opção abaixo eu procuro nos canais se o membro já tem um ticket na opção que ele escolheu
        ticket = utils.get(interaction.guild.text_channels, name =  f"{emojiglobal}┃{interaction.user.name.lower().replace(' ', '-')}-{interaction.user.id}")
        if ticket is not None: #verifica se ticket não é none,  
            await interaction.response.send_message(f"Eiiii, você já tem esse tipo de atendimento aberto. \n\nolha seu Ticket aqui {ticket.mention}! <:hmph:969703406048526417>", ephemeral=True)
            await ticket.send(f"Por favor Continue nesse ticket {interaction.user.mention}!")
            await ticket.send("<:braixyou:1045138554021478420>")
        else: #caso contrario ele continua criando ticket
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False,send_messages=True,attach_files=True,use_application_commands=True),
                interaction.user: discord.PermissionOverwrite(read_messages=True,send_messages=True,use_application_commands=True),
                atendente: discord.PermissionOverwrite(read_messages=True,send_messages=True,use_application_commands=True)
            }
            ticket = await interaction.guild.create_text_channel(f"{emojiglobal}┃{interaction.user.name}-{interaction.user.id}",category=categoria,overwrites=overwrites)
            await interaction.response.send_message(ephemeral=True,content=f"<:BraixHappy2:988776437790158918> Criei um ticket para você! Acessa ele ai e boa sorte <:BraixThumbsub:976096456987508817>\n{ticket.mention}")
            await ticket.send(f"Avisando:<@{interaction.user.mention}>",embed=embedticket)
            await ticket.purge(limit=1)
            await ticket.send(embed=embedticket)
            async with ticket.typing():
                await asyncio.sleep(1.5)
            await ticket.send(f"Oiiie {interaction.user.mention} **Tudo bem?**")
            async with ticket.typing():
                await asyncio.sleep(1.0)
            await ticket.send(f"Seja muito bem-vindo(a) ao atendimento do **STF/ASGARD**!! <:BN:416595378956271626> ")
            async with ticket.typing():
                await asyncio.sleep(1.5)
            await ticket.send(f"**sinta-se a vontade para usar os bots aqui no chat**")
            async with ticket.typing():
                await asyncio.sleep(1.5)
            await ticket.send(f"e daqui a pouco você será **atendido** por um <@&{staff}>.")
            async with ticket.typing():
                await asyncio.sleep(1.5)
            await ticket.send(f"mas em quanto o atendente não chega eu mesmo vou assumir seu atendimento aqui por enquanto!!!")
            async with ticket.typing():
                await asyncio.sleep(1.5)
            await ticket.send(f"{mensagemcanal}")


#Botão deletar ticket
class DeleteTicket(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.value=None

    @discord.ui.button(label="Encerrar Ticket",style=discord.ButtonStyle.red,emoji="🦊")#ESPECIFICAÇÂO DO BOTÂO
    async def confirm(self,interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        self.stop()
        # puxo os mods de ambos os servidores para fazer a verificação logo abaixo
        mod = interaction.guild.get_role(id_cargo_atendente)
        mod2 = interaction.guild.get_role(id_cargo_tribunal)

        # esse IF verifica se quem ta apertando o botão ou é o cara que abriu o ticket ou o mod do primeiro servidor ou do segundo servidor.
        if str(interaction.user.id) in interaction.channel.name or mod in interaction.user.roles or mod2 in interaction.user.roles:
            #se é verdadeiro encerra o atendimento e deleta o ticker
                await interaction.channel.send(f"<a:BraixPet:969397249169842237>")
                await interaction.response.defer()
                await interaction.followup.send(f"Okay estamos salvando o seu atendimento e fechando ele...\nAtendimento fechado por: {interaction.user.name} - {interaction.user.id}")
                if os.path.exists(f"{interaction.channel.id}.md"):
                    return await interaction.followup.send(f"Uma transcrição já está sendo gerada!", ephemeral = True)
                with open(f"{interaction.channel.id}.md", 'a',encoding="utf-8") as f:
                    f.write(f"# Histórico de {interaction.channel.name}:\n\n")
                    async for message in interaction.channel.history(limit = None, oldest_first = True):
                        created = datetime.strftime(message.created_at, "%d/%m/%Y ás %H:%M:%S")
                        if message.edited_at:
                            edited = datetime.strftime(message.edited_at, "%d/%m/%Y ás %H:%M:%S")
                            f.write(f"{message.author} on {created}: {message.clean_content} (Editado em {edited})\n")
                        else:
                            f.write(f"{message.author} on {created}: {message.clean_content}\n")
                    generated = datetime.now().strftime("%d/%m/%Y ás %H:%M:%S")
                    f.write(f"\n*Gerado em {generated}\n*Time Zone: UTC*")
                with open(f"{interaction.channel.id}.md", 'rb') as f:
                    if interaction.guild.id == id_servidor_bh:
                        canal_logs = interaction.guild.get_channel(id_canal_logs_bh)
                    else:
                        canal_logs = interaction.guild.get_channel(id_canal_logs_tri)
                    await canal_logs.send(file = discord.File(f, f"{interaction.channel.name}.md"))
                os.remove(f"{interaction.channel.id}.md")
                await interaction.channel.delete()
        else:
            # se falso manda isso ai em baixo
            await interaction.response.send_message(mensagemerro)


#INICIO DA CLASSE
class atendimento(commands.Cog):
    def __init__(self, client: commands.Bot) -> None:

        #Aqui estou criando uma variavel global para usar em outra 
        global botname
        global botavatar
        self.client = client
        botname = self.client.user.name
        botavatar = self.client.user.avatar

        #Carrega os menu e adiciona eles
        self.menu_atendimento = app_commands.ContextMenu(name="Abrir Atendimento",callback=self.abrirticketmenu)
        self.client.tree.add_command(self.menu_atendimento)
        self.client.add_view(DropdownSuporte())  #carrega o Painel de Suporte
        self.client.add_view(DropdownContratacao()) #carrega o painel de contratação
        self.client.add_view(DropdownTribunal()) #carrega o painel de tribunal


    @commands.Cog.listener()
    async def on_ready(self):
        print("Cog atendimento carregado.")
    
    #Remove os menu se necessario
    async def cog_unload(self) -> None:
        self.client.tree.remove_command(self.menu_atendimento, type=self.menu_atendimento.type)
  
    #COMANDO ABRIR ATENDIMENTO MENU
    async def abrirticketmenu(self,interaction: discord.Interaction,membro: discord.Member):
        print (f"Usuario: {interaction.user.name} usou Abrir Ticket")
        await interaction.response.defer(ephemeral=True)
        if interaction.guild.id == id_servidor_bh:
            atendente = interaction.guild.get_role(id_cargo_atendente)
            categoria = interaction.guild.get_channel(id_categoria_staff)
        elif interaction.guild.id == id_servidor_tribunal:
            atendente = interaction.guild.get_role(id_cargo_tribunal)
            categoria = interaction.guild.get_channel(id_categoria_tribunal)
        else:
            await interaction.followup.send(ephemeral=True, content="<:ew:969703224825225266> Ue? Isso não funcionou como deveria... \nEsse comando é de uso exclusivo da staff nas comunidades Braixen's House <:derp:969703169670131812>")
            return
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False,send_messages=True,attach_files=True,use_application_commands=True),
            interaction.user: discord.PermissionOverwrite(read_messages=True,send_messages=True),
            membro: discord.PermissionOverwrite(read_messages=True,send_messages=True),
            atendente: discord.PermissionOverwrite(read_messages=True,send_messages=True)
        }
        if atendente in interaction.user.roles:
            ticket = await interaction.guild.create_text_channel(f"🦊┃{membro.name}-{membro.id}",overwrites=overwrites,category=categoria)
            await interaction.followup.send(ephemeral=True,content=f"Criei um ticket para você! Acessa ele ai \n{ticket.mention}")
            embedticket = discord.Embed(
                colour=discord.Color.yellow(),
                #title="Atendimento Braixen's House",
                description=f"**Olá {membro.mention}**, Bem-vindo(a) ao nosso atendimento.\n\nEsse Ticket foi aberto **diretamente pela adminstração do servidor** a fim de resolver algum problema com você então pedimos que **aguarde a nossa equipe conversar com você.**"
            )
            embedticket.set_author(name=f"{self.client.user.name}",icon_url=f"{self.client.user.avatar.url}")
            embedticket.set_thumbnail(url="https://i.imgur.com/fv378Un.png")
            await ticket.send(f"Esse Ticket foi aberto pelo administrador {interaction.user.mention} para realizar o atendimento exclusivo do membro {membro.mention}\n\n",embed=embedticket)
        else:
            await interaction.followup.send(ephemeral=True,content=mensagemerro)


    #GRUPO PAINEIS DE ATENDIMENTO DO BOT 
    painel=app_commands.Group(name="painel",description="Comandos de paineis de atendimento do bot.")

        #PAINEL DE SUPORTE DO BRAIXEN'S HOUSE
    @painel.command(name = 'suporte-bh', description='🦊⠂Crie um Menu para atendimento de suporte')
    @commands.has_permissions(manage_guild=True)
    async def suportebh(self,interaction: discord.Interaction):
        print (f"Usuario: {interaction.user.name} usou painel suporte")
        embed1 = discord.Embed(
            colour=discord.Color.yellow(),
            title="Atendimento STF/ASGARD",
            description="Seja bem-vindo(a) a nossa **seção de ajuda** do **STF/ASGARD.** \n \nAqui você pode tirar dúvidas, pedir ajuda para alguns problemas, solicitar cargos, informar sobre problemas de acesso, sugestões de mudanças entre outros basta selecionar a opção desejada."
        )
        embed1.set_image(url="https://cdn.discordapp.com/attachments/1067789510097768528/1146086873501028513/atendimento.png")
        if interaction.user.id == donoid:
            await interaction.response.send_message("Painel criado",ephemeral=True)
            await interaction.channel.send(embed=embed1,view=DropdownSuporte()) 
        else:await interaction.response.send_message(mensagemerro,ephemeral=True)


        #PAINEL DE SERVIÇOS DO BRAIXEN'S HOUSE
    @painel.command(name = 'servicos-bh', description='🦊⠂Crie um Menu para atendimento de serviços.')
    @commands.has_permissions(manage_guild=True)
    async def contatebh(self,interaction: discord.Interaction):
        print (f"Usuario: {interaction.user.name} usou painel serviços")
        embed2 = discord.Embed(
            colour=discord.Color.yellow(),
            title="Contratação Braixen's House",
            description="Seja bem-vindo(a) a nossa **seção de contrate** do **STF/ASGARD.** \n \nAqui você pode Contratar os meus serviços de Akuma para **Consultoria, Planejamento, Desenvolvimento** de servidores e **Implantação** de bots, e também os serviços dos artistas de nossa comunidade.\n\nEntão caso esteja interessado **abre um ticket ai**."
        )
        #imagem do meu embed
        embed2.set_image(url="https://cdn.discordapp.com/attachments/1067789510097768528/1146086918895964260/contrate.png")
        if interaction.user.id == donoid:
            await interaction.response.send_message("Painel criado",ephemeral=True)
            await interaction.channel.send(embed=embed2,view=DropdownContratacao())
        else:await interaction.response.send_message(mensagemerro,ephemeral=True)


        #PAINEL DO TRIBUNAL DO BRAIXEN'S HOUSE
    @painel.command(name = 'tribunal', description='🦊⠂Crie um Menu para atendimento do tribunal.')
    @commands.has_permissions(manage_guild=True)
    async def tribunalbh(self,interaction: discord.Interaction):
        print (f"Usuario: {interaction.user.name} usou painel tribunal")
        embed3 = discord.Embed(
            colour=discord.Color.yellow(),
            title="Tribunal Braixen's House",
            description="Seja bem-vindo(a) ao **Tribunal** do **STF/ASGARD.** \n \nAqui você pode verificar e contestar banimentos e avisos que aconteceram no STF/ASGARD.\n\n**Atenção** não abra ticket sem motivo, caso contrario poderemos ignorar sua solicitação."
        )
        #imagem do meu embed
        embed3.set_image(url="https://cdn.discordapp.com/attachments/1067789510097768528/1146086949057208410/tribunal.png")
        if interaction.user.id == donoid:
            await interaction.response.send_message("Painel criado",ephemeral=True)
            await interaction.channel.send(embed=embed3,view=DropdownTribunal()) 
        else:await interaction.response.send_message(mensagemerro,ephemeral=True)



    #GRUPO DE ATENDIMENTO DO BOT 
    atendi=app_commands.Group(name="atendimento",description="Comandos de paineis de atendimento do bot.")

    #COMANDO PARA FECHAR UM TICKET
    #esse cara manda um texto e manda junto o botão de fechar ticket 
    @atendi.command(name="fechar",description='📞⠂Feche um atendimento.')
    async def fecharticket(self,interaction: discord.Interaction):
        print (f"Usuario: {interaction.user.name} usou fecharticket")
        mod = interaction.guild.get_role(id_cargo_atendente)
        mod2 = interaction.guild.get_role(id_cargo_tribunal)
        if str(interaction.user.id) in interaction.channel.name or mod in interaction.user.roles or mod2 in interaction.user.roles:
            await interaction.response.send_message("<:BraixThink:969396723631939594> **Você deseja mesmo Encerrar seu atendimento?")
            await asyncio.sleep(1.5)
            await interaction.followup.send("Caso sim, use o botão abaixo.",view=DeleteTicket())
        else:
            await interaction.response.send_message(mensagemerro,ephemeral=True)

        #COMANDO DE ENVIO DE OBRIGADO
        #esse aqui manda um obrigado ao membro da equipe do servidor, reconhece automaticamente com base na id no canal.
    @atendi.command(name='encerrar', description='📞⠂Encerre um atendimento.')
    async def encerrar(self,interaction: discord.Interaction):
        print (f"Usuario: {interaction.user.name} usou obg atendimento")
        mod = interaction.guild.get_role(id_cargo_atendente)
        mod2 = interaction.guild.get_role(id_cargo_tribunal)
        membro_id = interaction.channel.name.split('-')[-1]
        membro = interaction.guild.get_member(int(membro_id))
        if str(interaction.user.id) in interaction.channel.name or mod in interaction.user.roles or mod2 in interaction.user.roles:
            await interaction.response.send_message("enviando mensagem...",ephemeral=True)
            async with interaction.channel.typing():
                    await asyncio.sleep(1.5)
            await interaction.channel.send(f"Olá novamente {membro.mention}!!!")
            async with interaction.channel.typing():
                    await asyncio.sleep(2)
            await interaction.channel.send(f"Parece que seu atendimento está chegando ao fim.")
            async with interaction.channel.typing():
                    await asyncio.sleep(2)
            await interaction.channel.send(f"O *STF/ASGARD* agradece o contato e esperamos que você não tenha ficado com nenhuma dúvida sobre sua solicitação. <:BraixHappy2:988776437790158918>")
            async with interaction.channel.typing():
                    await asyncio.sleep(2)
            await interaction.channel.send(f"Você pode **avaliar o seu atendimento** usando o comando </atendimento avaliar:1138614448840511577>.")
            async with interaction.channel.typing():
                    await asyncio.sleep(2)
            await interaction.channel.send(f"Por favor use o **comando** </atendimento fechar:1138614448840511577> para **finalizar seu atendimento**")
        else:
            await interaction.response.send_message(mensagemerro,ephemeral=True)

        #COMANDO PARA ADICIONAR ALGUEM A ALGUM ATENDIMENTO
    #esse aqui adiciona um novo membro ao atendimento atual e notifica no chat que foi adicionado
    @atendi.command(name="adicionar",description='📞⠂Adicione um membro ao atendimento.')
    @app_commands.describe(membro="informe um membro")
    async def adicionar(self,interaction: discord.Interaction,membro: discord.Member):
        print (f"Usuario: {interaction.user.name} usou add atendimento")
        mod = interaction.guild.get_role(id_cargo_atendente)
        mod2 = interaction.guild.get_role(id_cargo_tribunal)
        if str(interaction.user.id) in interaction.channel.name or mod in interaction.user.roles or mod2 in interaction.user.roles:
            resposta = discord.Embed(
                colour=discord.Color.green(),
                title="🦊┃Adicionado ao atendimento",
                description=f"Membro: {membro.mention} foi adicionado ao atendimento"
            )
            await interaction.response.send_message(embed=resposta)
            await interaction.channel.set_permissions(membro, read_messages=True,send_messages=True)
        else:
            await interaction.response.send_message(mensagemerro,ephemeral=True)


        #COMANDO PARA REMOVER ALGUEM A ALGUM ATENDIMENTO
        #esse aqui remove um membro do atendimento atual e notifica no chat que foi removido
    @atendi.command(name="remover",description='📞⠂Remove um membro do atendimento.')
    @app_commands.describe(membro="informe um membro")
    async def remover(self,interaction: discord.Interaction,membro: discord.Member):
        print (f"Usuario: {interaction.user.name} usou rem atendimento")
        mod = interaction.guild.get_role(id_cargo_atendente)
        mod2 = interaction.guild.get_role(id_cargo_tribunal)
        if str(interaction.user.id) in interaction.channel.name or mod in interaction.user.roles or mod2 in interaction.user.roles:
            resposta = discord.Embed(
                colour=discord.Color.red(),
                title="🦊┃Removeu do atendimento",
                description=f"Membro: {membro.mention} foi removido do atendimento"
            )
            await interaction.response.send_message(embed=resposta)
            await interaction.channel.set_permissions(membro, read_messages=False,send_messages=False)
        else:
            await interaction.response.send_message(mensagemerro,ephemeral=True)


                #COMANDO PARA AVALIAR O ATENDIMENTO
            #esse comando permite que o membro envie uma avaliação sobre o atendimento, o membro pode escolher o staff, indicar a nota, e adicionar um comentario, as avaliações são registradas no canal de avaliação.
    @atendi.command(name="avaliar",description='📞⠂Avalie seu atendimento na nossa comunidade.')
    @app_commands.describe(staff="informe um membro da staff para avaliar",nota="selecione uma nota para o staff",comentario="escreva um comentario adicional.")
    @app_commands.choices(nota=[app_commands.Choice(name="1", value="1"),app_commands.Choice(name="2", value="2"),app_commands.Choice(name="3", value="3"),app_commands.Choice(name="4", value="4"),app_commands.Choice(name="5", value="5"),])
    async def avaliar(self,interaction: discord.Interaction,staff: discord.Member, nota:app_commands.Choice[str],comentario:str):
        print (f"Usuario: {interaction.user.name} usou avaliar atendimento")
        canal_avaliacao = interaction.guild.get_channel(id_canal_avaliacao)
        if (nota.value == '1'):
            estrelas = "🦊"
        elif (nota.value == '2'):
            estrelas = "🦊🦊"
        elif (nota.value == '3'):
            estrelas = "🦊🦊🦊"
        elif (nota.value == '4'):
            estrelas = "🦊🦊🦊🦊"
        elif (nota.value == '5'):
            estrelas = "🦊🦊🦊🦊🦊"
    
        resposta = discord.Embed(
                colour=discord.Color.yellow()
            )
        resposta.set_thumbnail(url=staff.avatar.url)
        resposta.add_field(name="```🦊``` Staff", value=f"```{staff.name}#{staff.discriminator}```", inline=True)
        resposta.add_field(name="```⭐``` Nota", value=f"```{estrelas}```", inline=True)
        resposta.add_field(name="```🗨️``` comentário", value=f"```{comentario}```", inline=False)
        resposta.set_footer(text=f"avaliação enviada por {interaction.user.name}#{interaction.user.discriminator}")
        await canal_avaliacao.send(embed=resposta)
        await interaction.response.send_message("Recebemos sua avaliação ebaaa <:BraixHappy2:988776437790158918> muito obrigado viu <:Braixen_Kyu:984628502450016286>",ephemeral=True)

    #Comando usado para criar uma entrevista
    @atendi.command(name="entrevista",description='📞⠂Crie uma entrevista no servidor')
    async def _entrevista(self,interaction: discord.Interaction,membro: discord.Member,dia: str, horario: str):
        if interaction.user.id == donoid:
            await interaction.response.send_message("Criando seu canal de entrevistas...",ephemeral=True)
            atendente = interaction.guild.get_role(id_cargo_atendente)
            categoria = interaction.guild.get_channel(id_categoria_staff)
            overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False,send_messages=True,attach_files=True,use_application_commands=True),
            interaction.user: discord.PermissionOverwrite(read_messages=True,send_messages=True),
            membro: discord.PermissionOverwrite(read_messages=True,send_messages=True),
            atendente: discord.PermissionOverwrite(read_messages=True,send_messages=False)
            }
            entrevista = await interaction.guild.create_text_channel(f"🦊┃{dia}-{horario} - {membro.name}",overwrites=overwrites,category=categoria)
            generated = datetime.now().strftime("%m/%Y")
            embed = discord.Embed(
                colour=discord.Color.yellow(),
                #title="Atendimento Braixen's House",
                description=f"**Olá {membro.mention}**, Bem-vindo(a) ao canal de entrevista.\n\nEsse canal será usado para realizar sua  **entrevista** lembre-se ela está agendada para o **dia {dia}/{generated} ás {horario}**, peço que aguarde o Akuma entrar em contato com você nesse horario para iniciar a sua entrevista."
            )
            embed.set_author(name=f"{botname}",icon_url=f"{botavatar}")
            embed.set_thumbnail(url="https://i.imgur.com/fv378Un.png")
            await entrevista.send(f"Esse canal foi aberto pelo administrador {interaction.user.mention} para realizar a entrevista do {membro.mention}\n\n",embed=embed)
        
        else: await interaction.response.send_message(mensagemerro,ephemeral=True)


async def setup(client:commands.Bot) -> None:
    if config_valida:
        await client.add_cog(atendimento(client))
    else:
        print("O Cog 'atendimento' não foi carregado devido a um erro de configuração nas variáveis de ambiente.")
