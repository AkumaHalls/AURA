# -*- coding: utf-8 -*-
import discord
from discord.ext import commands, tasks
from discord import app_commands
import coc
from coc import errors as coc_errors
import asyncio
import os
import logging
import json # Mantido para carregar 'registrations.json'
from datetime import datetime
import pytz
from dotenv import load_dotenv

# --- Configuração de Logging para este Cog ---
log_formatter = logging.Formatter('%(asctime)s-%(levelname)s-[%(funcName)s]: %(message)s')
file_handler = logging.FileHandler("clashlog_cog.log", encoding='utf-8')
file_handler.setFormatter(log_formatter)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(log_formatter)
logger = logging.getLogger("clashlog-manager-cog")
logger.setLevel(logging.INFO)
if not logger.handlers:
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
logger.info("Logging para clashlog_manager.py configurado.")


# --- Constantes e Arquivos ---
# Acessa as variáveis de ambiente do .env na raiz
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
EMAIL = os.getenv('COC_EMAIL')
PASSWORD = os.getenv('COC_PASSWORD')

# IDs e Tag FIXOS, lidos diretamente do .env
COC_CLAN_TAG = os.getenv('CLAN_TAG')
REGISTRATION_CHANNEL_ID = int(os.getenv('REGISTRATION_CHANNEL_ID', 0))
LOG_CHANNEL_ID = int(os.getenv('LOG_CHANNEL_ID', 0))
APPROVAL_LOG_CHANNEL_ID = int(os.getenv('APPROVAL_LOG_CHANNEL_ID', 0))

# --- MODIFICAÇÃO: Carregando Cargos e Mensagem de Kick do .env ---
try:
    COC_MEMBER_ROLE_ID = int(os.getenv('COC_MEMBER_ROLE_ID', 0))
    COC_ELDER_ROLE_ID = int(os.getenv('COC_ELDER_ROLE_ID', 0))
    COC_COLEADER_ROLE_ID = int(os.getenv('COC_COLEADER_ROLE_ID', 0))
    KICK_MESSAGE = os.getenv('KICK_MESSAGE', "Você foi removido do servidor por não fazer mais parte do clã.")
    
    # Cria um dicionário 'config_roles' similar ao que existia antes
    config_roles = {
        "member": COC_MEMBER_ROLE_ID,
        "admin": COC_ELDER_ROLE_ID,  # admin e elder usam o mesmo cargo
        "elder": COC_ELDER_ROLE_ID,
        "coleader": COC_COLEADER_ROLE_ID,
        "leader": COC_COLEADER_ROLE_ID # coleader e leader usam o mesmo cargo
    }
    
    # Validação simples
    if not all([COC_MEMBER_ROLE_ID, COC_ELDER_ROLE_ID, COC_COLEADER_ROLE_ID]):
         raise ValueError("IDs de cargos não encontrados no .env")
    
    logger.info("Configuração de cargos do Clash Log carregada do .env com sucesso.")
    
except (ValueError, TypeError):
    logger.critical("ERRO CRÍTICO: IDs de Cargos (COC_MEMBER_ROLE_ID, etc.) não encontrados ou inválidos no .env.")
    config_roles = None # Define como None para falhar as verificações
    KICK_MESSAGE = "Você foi removido do servidor por não fazer mais parte do clã." # Padrão
# --- FIM DA MODIFICAÇÃO ---


REGISTRATIONS_FILE = "registrations.json"
COC_KEY_NAME = "clashlogsbot"

try:
    TIMEZONE = pytz.timezone('America/Sao_Paulo')
except pytz.UnknownTimeZoneError:
    TIMEZONE = pytz.utc


# --- Variáveis de Estado Global (dentro do escopo do módulo) ---
registrations = {}
coc_client = None

# Flag de validação inicial
CONFIG_VALIDA_COC = False
if not EMAIL or not PASSWORD:
    logger.critical("ERRO CRÍTICO: COC_EMAIL ou COC_PASSWORD não encontrados no .env.")
elif not COC_CLAN_TAG or not REGISTRATION_CHANNEL_ID or not LOG_CHANNEL_ID or not APPROVAL_LOG_CHANNEL_ID:
    logger.critical("ERRO CRÍTICO: Uma ou mais variáveis FIXAS (CLAN_TAG, IDs de canais) não estão no .env. O cog não iniciará totalmente.")
else:
    CONFIG_VALIDA_COC = True

# --- Funções Utilitárias para JSON ---
def load_json(filename):
    """Carrega dados de um arquivo JSON."""
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Erro ao carregar {filename}: {e}")
            return {}
    logger.warning(f"Arquivo {filename} não encontrado, iniciando com dados vazios.")
    return {}

def save_json(data, filename):
    """Salva dados em um arquivo JSON."""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        logger.debug(f"Dados salvos em {filename}")
        return True
    except IOError as e:
        logger.error(f"Erro ao salvar {filename}: {e}")
        return False

# --- Inicialização do Cliente CoC ---
async def initialize_coc_client():
    """Tenta logar no CoC API usando Email/Senha."""
    global coc_client
    logger.info("--- Iniciando Login Cliente CoC ---")
    for attempt in range(1, 4):
        try:
            logger.info(f"[Tentativa {attempt}/3] Tentando login com Email/Senha...")
            temp_client = coc.Client(key_count=1, key_names=COC_KEY_NAME, throttle_limit=20)
            await asyncio.wait_for(temp_client.login(EMAIL, PASSWORD), timeout=90.0)
            if hasattr(temp_client, 'http') and temp_client.http:
                 coc_client = temp_client
                 logger.info(f"[Tentativa {attempt}/3] Login CoC e inicialização do Client OK.")
                 return True
            else:
                 logger.error(f"[Tentativa {attempt}/3] Login CoC OK, mas sessão HTTP falhou.")
                 await temp_client.close()
        except coc_errors.AuthenticationError as e_auth:
            logger.error(f"[Tentativa {attempt}/3] Falha de autenticação CoC: {e_auth}. Verifique email/senha.")
            return False
        except asyncio.TimeoutError:
            logger.error(f"[Tentativa {attempt}/3] Timeout durante o login CoC.")
        except Exception as e_login:
            logger.error(f"[Tentativa {attempt}/3] Erro inesperado no login CoC: {e_login}", exc_info=True)
            if 'temp_client' in locals() and temp_client:
                await temp_client.close()
        
        if attempt < 3:
            wait_time = 20 * attempt
            logger.info(f"Aguardando {wait_time}s antes da próxima tentativa...")
            await asyncio.sleep(wait_time)
            
    logger.critical("--- Falha em todas as tentativas de login CoC ---")
    coc_client = None
    return False

# --- Função auxiliar para verificar e atualizar um único membro ---
async def verify_single_member(member: discord.Member, expected_tag: str, guild: discord.Guild):
    """Verifica o status CoC de um membro específico e atualiza cargos/expulsa se necessário."""
    global coc_client, registrations # Removido 'config'

    # Usando a TAG FIXA do .env
    clan_tag = COC_CLAN_TAG 

    # MODIFICADO: Checa 'config_roles' em vez de 'config'
    if not coc_client or not config_roles or not guild or not clan_tag:
        logger.debug(f"Pulando verificação individual para {member}: cliente CoC ou config de cargos indisponível.")
        return

    discord_id_str = str(member.id)
    logger.debug(f"Verificando membro individual: {member} ({discord_id_str}), tag esperada: {expected_tag}")

    try:
        clan = await asyncio.wait_for(coc_client.get_clan(clan_tag), timeout=20.0)
        member_data = clan.get_member(expected_tag)

        current_roles = {role.id for role in member.roles}
        # MODIFICADO: Usa 'config_roles'
        all_managed_role_ids = set(config_roles.values())
        current_managed_roles = current_roles.intersection(all_managed_role_ids)
        log_channel = guild.get_channel(LOG_CHANNEL_ID)

        if member_data:
            # Membro ENCONTRADO no clã
            player_role_coc = member_data.role.in_game_name.lower()
            # MODIFICADO: Usa 'config_roles'
            expected_role_id = config_roles.get(player_role_coc)
            expected_role = guild.get_role(expected_role_id) if expected_role_id else None

            if not expected_role:
                logger.error(f"Cargo Discord para CoC role '{player_role_coc}' (ID: {expected_role_id}) não encontrado.")
                return

            roles_to_remove = [guild.get_role(rid) for rid in current_managed_roles if rid != expected_role_id]
            roles_to_remove = [r for r in roles_to_remove if r and guild.me.top_role > r] # Só remove se puder
            
            if roles_to_remove:
                 await member.remove_roles(*roles_to_remove, reason=f"Correção de cargo - Verificação periódica")

            if expected_role_id not in current_roles:
                if guild.me.top_role > expected_role:
                     await member.add_roles(expected_role, reason=f"Cargo correto ({player_role_coc}) - Verificação periódica")
                else:
                     logger.warning(f"Não foi possível adicionar cargo {expected_role.name} a {member} - Hierarquia insuficiente.")

        else:
            # Membro NÃO ENCONTRADO no clã com a tag registrada
            logger.info(f"Membro {member} ({expected_tag}) não encontrado no clã {clan_tag}. Removendo cargos/expulsando...")

            roles_to_remove = [guild.get_role(rid) for rid in current_managed_roles]
            roles_to_remove = [r for r in roles_to_remove if r and guild.me.top_role > r]
            if roles_to_remove:
                 await member.remove_roles(*roles_to_remove, reason="Não está mais no clã - Verificação")

            if discord_id_str in registrations:
                 del registrations[discord_id_str]
                 save_json(registrations, REGISTRATIONS_FILE)

            # MODIFICADO: Usa 'KICK_MESSAGE' global
            kick_msg = KICK_MESSAGE
            try:
                 await member.send(kick_msg)
            except discord.Forbidden:
                 logger.warning(f"Não foi possível enviar DM de expulsão para {member}.")
            
            await asyncio.sleep(1) # Espera um pouco antes de tentar expulsar
            
            try:
                await member.kick(reason="Não encontrado no clã durante verificação periódica.")
                if log_channel:
                    await log_channel.send(f"👢 Membro {member.mention} (`{discord_id_str}`) expulso automaticamente por não ser encontrado no clã com a tag `{expected_tag}`.")
            except discord.Forbidden:
                 logger.error(f"Falha ao expulsar {member}: Permissão 'Expulsar Membros' ausente ou hierarquia.")
                 if log_channel:
                     await log_channel.send(f"⚠️ Falha ao expulsar {member.mention} (`{discord_id_str}`). Verificar permissões/hierarquia.")
            except Exception as e_kick:
                 logger.error(f"Erro inesperado ao expulsar {member}: {e_kick}")

    except coc_errors.AuthenticationError:
        logger.critical(f"Erro de autenticação CoC durante verificação. Tentando relogar...")
        await initialize_coc_client()
    except coc_errors.ClashOfClansException as e_coc:
        logger.error(f"Erro API CoC ao verificar {member} ({expected_tag}): {e_coc}")
    except asyncio.TimeoutError:
        logger.warning(f"Timeout ao verificar {member} ({expected_tag}).")
    except Exception as e:
        logger.error(f"Erro inesperado ao verificar membro {member}: {e}", exc_info=True)


class ClashLogManager(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client
        self.client.loop.create_task(self.load_clash_data_and_start_task())

    async def cog_unload(self):
        """Chamado quando o cog é descarregado, para garantir que a tarefa de loop e o cliente CoC sejam parados."""
        if self.verify_members_task.is_running():
            self.verify_members_task.stop()
            logger.info("Tarefa de verificação periódica parada.")
        global coc_client
        if coc_client:
            try:
                await coc_client.close()
                logger.info("Cliente CoC fechado.")
            except Exception as e:
                logger.error(f"Erro ao fechar cliente CoC no unload: {e}")

    async def load_clash_data_and_start_task(self):
        """Carrega dados JSON e inicia o cliente CoC e a tarefa de loop após o bot estar pronto."""
        await self.client.wait_until_ready()
        
        global registrations # Removido 'config'
        
        # Lê apenas os registros
        registrations = load_json(REGISTRATIONS_FILE)
        # Removido load_json(CONFIG_FILE)
        logger.info(f"Registros Clash Log carregados ({len(registrations)} usuários).")

        if not CONFIG_VALIDA_COC:
            logger.critical("O Cog ClashLogManager não iniciará suas funcionalidades CoC por falta de variáveis fixas no .env.")
            return

        # Inicializa o cliente CoC
        if await initialize_coc_client():
            logger.info("Cliente CoC inicializado com sucesso.")
            # Inicia a tarefa APENAS se o cliente CoC funcionou E se não estiver rodando
            if not self.verify_members_task.is_running():
                self.verify_members_task.start()
                logger.info("Tarefa de verificação periódica iniciada.")
            else:
                 logger.warning("Tarefa de verificação periódica já estava rodando.")
        else:
            logger.critical("Falha ao inicializar cliente CoC. Funcionalidade de verificação/registro estará DESABILITADA.")


    @commands.Cog.listener()
    async def on_ready(self):
        """Evento que é acionado quando a Cog está pronta."""
        logger.info("Cog ClashLogManager (Clash of Clans) carregado.")

    # --- Tarefa de Verificação Periódica (a cada 1 hora) ---
    @tasks.loop(hours=1)
    async def verify_members_task(self):
        """Verifica periodicamente todos os membros registrados."""
        global coc_client, registrations # Removido 'config'

        # MODIFICADO: Checa 'config_roles'
        if not coc_client or not config_roles or not COC_CLAN_TAG or not self.client.guilds:
            logger.warning("Pulando tarefa de verificação: Requisitos não atendidos.")
            return

        regs_copy = registrations.copy()

        logger.info(f"--- Iniciando Tarefa de Verificação Periódica ({len(regs_copy)} membros registrados) ---")
        guild = self.client.guilds[0] # Assumindo que você quer rodar no primeiro guild, ajuste se tiver múltiplos
        if not guild:
            logger.error("Não foi possível obter o objeto Guild na tarefa de verificação.")
            return

        verified_count = 0
        
        for discord_id_str, player_tag in regs_copy.items():
            member = guild.get_member(int(discord_id_str))
            if not member:
                logger.warning(f"Membro registrado ID {discord_id_str} (tag: {player_tag}) não encontrado no servidor. Removendo registro.")
                if discord_id_str in registrations:
                    del registrations[discord_id_str]
                    save_json(registrations, REGISTRATIONS_FILE)
                continue

            await verify_single_member(member, player_tag, guild)
            verified_count += 1
            await asyncio.sleep(2.0) 

        logger.info(f"--- Tarefa de Verificação Periódica Concluída. Verificados: {verified_count} membros. ---")


    # --- Comandos Slash do Clash Log ---
    clash = app_commands.Group(name="clash", description="Comandos de gerenciamento de clã (Clash Log).")

    # --- COMANDO SETUP MODIFICADO ---
    @clash.command(name="setup", description="[Admin] Verifica a configuração dos canais e cargos lidos do .env.")
    @commands.has_permissions(administrator=True)
    async def setup_command(self, interaction: discord.Interaction):
        """Comando para VERIFICAR as configurações lidas do .env."""
        await interaction.response.defer(ephemeral=True, thinking=True)

        if not interaction.user.guild_permissions.administrator:
            await interaction.followup.send("❌ Você precisa ser um administrador para usar este comando.", ephemeral=True)
            return
        
        # Tenta buscar os canais e cargos para menção
        reg_channel = self.client.get_channel(REGISTRATION_CHANNEL_ID)
        app_channel = self.client.get_channel(APPROVAL_LOG_CHANNEL_ID)
        log_channel = self.client.get_channel(LOG_CHANNEL_ID)
        
        member_role = interaction.guild.get_role(COC_MEMBER_ROLE_ID)
        elder_role = interaction.guild.get_role(COC_ELDER_ROLE_ID)
        coleader_role = interaction.guild.get_role(COC_COLEADER_ROLE_ID)

        embed = discord.Embed(
            title="Verificação de Configuração do Clash Log",
            description="Esta é a configuração ATUAL carregada a partir do seu arquivo `.env` (ou variáveis de ambiente no Render).",
            color=discord.Color.blue()
        )

        # Checagem de Canais
        embed.add_field(name="Tag do Clã", value=f"`{COC_CLAN_TAG}`" if COC_CLAN_TAG else "❌ **Não definido**", inline=False)
        embed.add_field(name="Canal de Registro", value=f"{reg_channel.mention}" if reg_channel else f"❌ **Não encontrado** (ID: `{REGISTRATION_CHANNEL_ID}`)", inline=False)
        embed.add_field(name="Canal de Aprovações (Logs)", value=f"{log_channel.mention}" if log_channel else f"❌ **Não encontrado** (ID: `{LOG_CHANNEL_ID}`)", inline=False)
        embed.add_field(name="Canal de Pendentes", value=f"{app_channel.mention}" if app_channel else f"❌ **Não encontrado** (ID: `{APPROVAL_LOG_CHANNEL_ID}`)", inline=False)

        # Checagem de Cargos
        embed.add_field(name="Cargo Membro", value=f"{member_role.mention}" if member_role else f"❌ **Não encontrado** (ID: `{COC_MEMBER_ROLE_ID}`)", inline=False)
        embed.add_field(name="Cargo Ancião", value=f"{elder_role.mention}" if elder_role else f"❌ **Não encontrado** (ID: `{COC_ELDER_ROLE_ID}`)", inline=False)
        embed.add_field(name="Cargo Colíder/Líder", value=f"{coleader_role.mention}" if coleader_role else f"❌ **Não encontrado** (ID: `{COC_COLEADER_ROLE_ID}`)", inline=False)
        
        embed.add_field(name="Mensagem de Kick", value=f"```{KICK_MESSAGE}```", inline=False)

        if all([reg_channel, app_channel, log_channel, member_role, elder_role, coleader_role, COC_CLAN_TAG]):
            embed.color = discord.Color.green()
            embed.set_footer(text="✅ Todas as configurações parecem estar corretas!")
            
            # Checagem de hierarquia
            bot_member = interaction.guild.me
            roles_to_manage = [member_role, elder_role, coleader_role]
            hierarquia_ok = True
            for role in roles_to_manage:
                if bot_member.top_role <= role:
                    embed.add_field(name="⚠️ AVISO DE HIERARQUIA", value=f"Meu cargo (`{bot_member.top_role.name}`) é igual ou inferior ao cargo `{role.name}`. Não conseguirei atribuí-lo. Por favor, mova meu cargo para cima.", inline=False)
                    embed.color = discord.Color.orange()
                    hierarquia_ok = False
            
            if hierarquia_ok:
                 embed.add_field(name="Hierarquia de Cargos", value="✅ Meu cargo é mais alto que todos os cargos de clã.", inline=False)

        else:
            embed.color = discord.Color.red()
            embed.set_footer(text="❌ Faltam configurações! Verifique as variáveis no .env do Render.")

        await interaction.followup.send(embed=embed, ephemeral=True)


    @clash.command(name="registrar", description="Solicita o registro no clã com sua tag do Clash of Clans.")
    @app_commands.describe(player_tag="Sua tag de jogador no Clash of Clans (ex: #XYZABCD).")
    async def register_command(self, interaction: discord.Interaction, player_tag: str):
        """Solicita o registro de um membro para aprovação administrativa."""
        global coc_client, registrations # Removido 'config'
        await interaction.response.defer(ephemeral=True, thinking=True)

        if not COC_CLAN_TAG or not REGISTRATION_CHANNEL_ID or not APPROVAL_LOG_CHANNEL_ID:
             await interaction.followup.send("❌ O Clash Log não tem sua Tag do Clã ou IDs de Canais configurados no arquivo .env. Contate um admin para preencher as variáveis CLAN_TAG, REGISTRATION_CHANNEL_ID, LOG_CHANNEL_ID e APPROVAL_LOG_CHANNEL_ID no .env.", ephemeral=True)
             return
        
        # MODIFICADO: Checa 'config_roles'
        if not config_roles:
            await interaction.followup.send("❌ Os cargos do Clash Log não foram configurados. Peça a um admin para verificar as variáveis `COC_..._ROLE_ID` no .env e depois rodar `/clash setup` para confirmar.", ephemeral=True)
            return
            
        if not coc_client:
            await interaction.followup.send("⏳ A conexão com o Clash of Clans ainda está sendo estabelecida. Tente novamente em um minuto.", ephemeral=True)
            return

        # USA O ID FIXO DO .ENV
        if interaction.channel.id != REGISTRATION_CHANNEL_ID:
            reg_channel = self.client.get_channel(REGISTRATION_CHANNEL_ID)
            mention = f"no canal {reg_channel.mention}" if reg_channel else "no canal de registro designado"
            await interaction.followup.send(f"❌ Use este comando {mention}.", ephemeral=True)
            return

        try:
            corrected_tag = coc.utils.correct_tag(player_tag)
            if not coc.utils.is_valid_tag(corrected_tag):
                await interaction.followup.send(f"❌ A tag `{player_tag}` parece inválida. Use o formato #TAG.", ephemeral=True)
                return
        except Exception:
             await interaction.followup.send("❌ Erro ao processar a tag do jogador.", ephemeral=True)
             return

        discord_id_str = str(interaction.user.id)
        if discord_id_str in registrations and registrations[discord_id_str] == corrected_tag:
             await interaction.followup.send(f"ℹ️ Você já está registrado com a tag `{corrected_tag}`.", ephemeral=True)
             await verify_single_member(interaction.user, corrected_tag, interaction.guild)
             return

        tag_already_registered_by_other = False
        other_user_id = None
        for reg_id, reg_tag in registrations.items():
            if reg_tag == corrected_tag and reg_id != discord_id_str:
                tag_already_registered_by_other = True
                other_user_id = reg_id
                break

        if tag_already_registered_by_other:
            other_user = interaction.guild.get_member(int(other_user_id))
            other_user_mention = f"<@{other_user_id}>" if not other_user else other_user.mention
            await interaction.followup.send(f"❌ A tag `{corrected_tag}` já está registrada por outro usuário ({other_user_mention}). Se isso for um erro, contate um administrador.", ephemeral=True)
            return

        
        approval_log_channel = self.client.get_channel(APPROVAL_LOG_CHANNEL_ID)
        log_channel = self.client.get_channel(LOG_CHANNEL_ID)
        
        if not approval_log_channel:
             await interaction.followup.send("❌ Erro crítico: O canal configurado para aprovações não foi encontrado. Contate um admin.", ephemeral=True)
             if log_channel: await log_channel.send(f"🆘 **Erro Crítico:** Canal de aprovação ID `{APPROVAL_LOG_CHANNEL_ID}` não encontrado ao processar registro de {interaction.user.mention}.")
             return

        try:
            clan = await asyncio.wait_for(coc_client.get_clan(COC_CLAN_TAG), timeout=30.0)
            member_data = clan.get_member(corrected_tag)

            if member_data:
                player_name = member_data.name
                player_role_coc = member_data.role.in_game_name
                role_name_display = player_role_coc.replace("coLeader", "Co-Líder").capitalize()

                approval_message = (
                    f"📝 **Solicitação de Registro Pendente**\n\n"
                    f"👤 **Usuário Discord:** {interaction.user.mention} (`{interaction.user.id}`)\n"
                    f"🏷️ **Tag CoC:** `{corrected_tag}`\n"
                    f"🔖 **Nome no Jogo:** `{player_name}`\n"
                    f"👑 **Cargo no Clã:** {role_name_display}\n\n"
                    f"▶️ **Para aprovar:** Use `/clash aprovar usuario: {interaction.user.mention} player_tag: {corrected_tag}`\n"
                    f"❌ **Para negar:** Use `/clash negar usuario: {interaction.user.mention} player_tag: {corrected_tag} motivo: [Opcional]`"
                )
                await approval_log_channel.send(approval_message)
                await interaction.followup.send(f"✅ Sua solicitação de registro para a tag `{corrected_tag}` (`{player_name}`) foi enviada para aprovação administrativa. Você será notificado se for aprovado ou negado.", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ Jogador com a tag `{corrected_tag}` não encontrado no clã configurado (`{COC_CLAN_TAG}`). Verifique se a tag está correta e se você realmente faz parte deste clã.", ephemeral=True)
                if log_channel: await log_channel.send(f"⚠️ Falha na solicitação de registro de {interaction.user.mention}: Tag `{corrected_tag}` não encontrada no clã `{COC_CLAN_TAG}`.")


        except coc_errors.ClashOfClansException as e:
            logger.error(f"Erro API CoC no registro: {e}")
            await interaction.followup.send("❌ Ocorreu um erro ao comunicar com a API do Clash of Clans. Tente novamente mais tarde.", ephemeral=True)
        except asyncio.TimeoutError:
            await interaction.followup.send("❌ A API do Clash of Clans demorou muito para responder. Tente novamente.", ephemeral=True)
        except Exception as e:
            logger.error(f"Erro inesperado no registro: {e}", exc_info=True)
            await interaction.followup.send("❌ Ocorreu um erro inesperado. Contate um admin.", ephemeral=True)


    @clash.command(name="aprovar", description="[Admin] Aprova o registro de um usuário.")
    @app_commands.describe(
        usuario="O membro do Discord para aprovar.",
        player_tag="A tag CoC que o membro informou."
    )
    @commands.has_permissions(administrator=True)
    async def aprovar_command(self, interaction: discord.Interaction, usuario: discord.Member, player_tag: str):
        """Aprova um registro pendente, verifica novamente o cargo e atribui."""
        global coc_client, registrations # Removido 'config'
        
        if not interaction.user.guild_permissions.administrator:
             await interaction.response.send_message("❌ Apenas administradores podem usar este comando.", ephemeral=True)
             return

        await interaction.response.defer(ephemeral=True, thinking=True)
        
        # MODIFICADO: Checa 'config_roles'
        if not config_roles or not coc_client:
            await interaction.followup.send("❌ O Clash Log não está configurado (cargos) ou o cliente CoC não está pronto. Tente novamente.", ephemeral=True)
            return

        log_channel = self.client.get_channel(LOG_CHANNEL_ID)
        try:
            corrected_tag = coc.utils.correct_tag(player_tag)
        except:
             await interaction.followup.send(f"❌ A tag `{player_tag}` parece inválida.", ephemeral=True)
             return

        try:
            clan = await asyncio.wait_for(coc_client.get_clan(COC_CLAN_TAG), timeout=30.0)
            member_data = clan.get_member(corrected_tag)

            if not member_data:
                await interaction.followup.send(f"❌ Falha na aprovação: Jogador com tag `{corrected_tag}` **não encontrado no clã neste momento**.", ephemeral=True)
                if log_channel: await log_channel.send(f"❌ Falha na aprovação por {interaction.user.mention}: {usuario.mention} (tag `{corrected_tag}`) não encontrado no clã.")
                return

            player_name = member_data.name
            player_role_coc = member_data.role.in_game_name.lower()
            # MODIFICADO: Usa 'config_roles'
            role_id_to_assign = config_roles.get(player_role_coc)
            role_to_assign = interaction.guild.get_role(role_id_to_assign) if role_id_to_assign else None

            if not role_to_assign:
                await interaction.followup.send("❌ Falha na aprovação: O cargo Discord para este cargo CoC não está configurado ou não foi encontrado.", ephemeral=True)
                return

            await verify_single_member(usuario, corrected_tag, interaction.guild)

            registrations[str(usuario.id)] = corrected_tag
            save_json(registrations, REGISTRATIONS_FILE)

            await interaction.followup.send(f"✅ Registro de {usuario.mention} para a tag `{corrected_tag}` (`{player_name}`) como **{role_to_assign.name}** aprovado com sucesso! Cargos atualizados.", ephemeral=True)

            if log_channel:
                await log_channel.send(f"✅ **{interaction.user.mention}** aprovou o registro de **{usuario.mention}** (`{str(usuario.id)}`) com a tag `{corrected_tag}` como **{player_role_coc.capitalize()}**.")

            try:
                await usuario.send(f"🎉 Seu registro no servidor **{interaction.guild.name}** foi aprovado! Você recebeu o cargo **{role_to_assign.name}**.")
            except discord.Forbidden:
                pass

        except coc_errors.ClashOfClansException as e:
            logger.error(f"Erro API CoC na aprovação: {e}")
            await interaction.followup.send("❌ Erro ao comunicar com a API CoC durante a aprovação. Tente novamente.", ephemeral=True)
        except asyncio.TimeoutError:
            await interaction.followup.send("❌ API CoC demorou muito para responder durante a aprovação.", ephemeral=True)
        except Exception as e:
            logger.error(f"Erro inesperado na aprovação: {e}", exc_info=True)
            await interaction.followup.send("❌ Ocorreu um erro inesperado durante a aprovação.", ephemeral=True)


    @clash.command(name="negar", description="[Admin] Nega uma solicitação de registro pendente.")
    @app_commands.describe(
        usuario="O membro do Discord cuja solicitação será negada.",
        player_tag="A tag CoC informada na solicitação.",
        motivo="O motivo da negação (será enviado ao usuário se possível)."
    )
    @commands.has_permissions(administrator=True)
    async def negar_command(self, interaction: discord.Interaction, usuario: discord.Member, player_tag: str, motivo: str = None):
        """Nega uma solicitação de registro e loga a ação."""
        if not interaction.user.guild_permissions.administrator:
             await interaction.response.send_message("❌ Apenas administradores podem usar este comando.", ephemeral=True)
             return
        
        await interaction.response.defer(ephemeral=True)

        log_channel = self.client.get_channel(LOG_CHANNEL_ID)
        try: corrected_tag = coc.utils.correct_tag(player_tag)
        except: corrected_tag = player_tag

        await interaction.followup.send(f"✅ Solicitação de registro de {usuario.mention} para a tag `{corrected_tag}` negada.", ephemeral=True)

        if log_channel:
            log_message = f"❌ **{interaction.user.mention}** negou a solicitação de registro de **{usuario.mention}** (`{usuario.id}`) para a tag `{corrected_tag}`."
            if motivo: log_message += f"\n> Motivo: {motivo}"
            try: await log_channel.send(log_message)
            except Exception: pass

        dm_message = f"ℹ️ Sua solicitação de registro no servidor **{interaction.guild.name}** para a tag `{corrected_tag}` foi negada."
        if motivo: dm_message += f"\n\n**Motivo:** {motivo}"

        try: await usuario.send(dm_message)
        except discord.Forbidden: pass


async def setup(client: commands.Bot) -> None:
    """Função para carregar a Cog no bot."""
    if CONFIG_VALIDA_COC:
        await client.add_cog(ClashLogManager(client))
    else:
        logger.critical("O Cog 'ClashLogManager' não será carregado devido à ausência das variáveis COC_EMAIL/PASSWORD ou das variáveis fixas do .env.")
