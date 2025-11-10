import discord
import os
import asyncio
from discord.ext import commands
from dotenv import load_dotenv

# Carrega as variáveis de ambiente do arquivo .env na raiz do projeto
# O '..' sobe um nível de diretório para encontrar o .env
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# Tenta carregar os IDs do arquivo .env
config_valida = False
try:
    CANAL_REGISTRO_ID = int(os.getenv("CANAL_REGISTRO_ID"))
    CARGO_MEMBRO_ID = int(os.getenv("CARGO_MEMBRO_ID"))
    CARGO_BANIDO_ID = int(os.getenv("CARGO_BANIDO_ID"))
    
    # Verifica se todos os IDs foram carregados
    if all([CANAL_REGISTRO_ID, CARGO_MEMBRO_ID, CARGO_BANIDO_ID]):
        config_valida = True
    else:
        raise ValueError("Uma ou mais variáveis de ambiente do autorole não foram encontradas.")

except (ValueError, TypeError):
    print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    print("!!! AVISO CRÍTICO: IDs para o Autorole não foram configurados no .env.      !!!")
    print("!!! O cog de autorole não funcionará corretamente.                           !!!")
    print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")

# Início da classe da Cog
class Autorole(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self):
        """Evento que é acionado quando a Cog está pronta."""
        print("Cog Autorole carregado.")
        if not config_valida:
            print("-> AVISO: O Cog Autorole foi carregado, mas está desativado por falta de configuração no arquivo .env.")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Evento que é acionado a cada mensagem enviada no servidor."""
        # Ignora a verificação se a configuração for inválida ou se a mensagem for de um bot
        if not config_valida or message.author.bot:
            return

        # Verifica se a mensagem foi enviada no canal correto e tem o conteúdo esperado
        if message.channel.id == CANAL_REGISTRO_ID and message.content.lower() == "liberar":
            membro = message.author
            guild = message.guild

            # Busca os objetos de cargo no servidor pelos IDs
            cargo_membro = guild.get_role(CARGO_MEMBRO_ID)
            cargo_banido = guild.get_role(CARGO_BANIDO_ID)

            if not cargo_membro or not cargo_banido:
                print(f"ERRO AUTOROLE: O cargo de membro (ID: {CARGO_MEMBRO_ID}) ou de banido (ID: {CARGO_BANIDO_ID}) não foi encontrado no servidor '{guild.name}'.")
                return

            if cargo_banido in membro.roles:
                print(f"Autorole ignorado para '{membro.name}' pois possui o cargo '{cargo_banido.name}'.")
                try:
                    await message.add_reaction("❌")
                except discord.Forbidden:
                    print("AVISO: Não tenho permissão para adicionar reações no canal de registro.")
                return

            if cargo_membro not in membro.roles:
                try:
                    # Ação 1: Adicionar o cargo (crítico)
                    await membro.add_roles(cargo_membro, reason="Autorole por palavra-chave 'Liberar'.")
                    print(f"Cargo '{cargo_membro.name}' adicionado para {membro.name}.")
                    
                    # Ação 2: Reagir para dar feedback imediato (Como solicitado)
                    await message.add_reaction("✅") # Este é o :white_check_mark:

                except discord.Forbidden:
                    print(f"ERRO DE PERMISSÃO: Não foi possível adicionar o cargo '{cargo_membro.name}' para {membro.name} OU reagir à mensagem.")
                    try:
                        await message.add_reaction("⚠️")
                    except discord.Forbidden:
                        pass # Ignora se não conseguir reagir
                    return # Para a execução aqui
                except discord.HTTPException as e:
                    print(f"ERRO HTTP ao adicionar cargo ou reagir: {e}")
                    await message.add_reaction("⚠️")
                    return

                # Ação 3: Enviar a mensagem de boas-vindas (Como solicitado)
                try:
                    async with message.channel.typing():
                        await asyncio.sleep(1.0) # Tempo de digitação reduzido
                    
                    # --- MENSAGEM MELHORADA AQUI ---
                    mensagem_boas_vindas = await message.channel.send(f"✅ Acesso liberado, {membro.mention}! Seu registro foi validado e as portas do clã estão abertas. Seja bem-vindo(a)!")
                    
                    # Tempo de exclusão da mensagem alterado para 5 minutos
                    await asyncio.sleep(300) 
                    await mensagem_boas_vindas.delete()
                
                except discord.Forbidden:
                    print(f"ERRO DE PERMISSÃO: Não tenho permissão para ENVIAR ou APAGAR mensagens no canal '{message.channel.name}'. Verifique as permissões do bot.")
                except Exception as e:
                    print(f"ERRO inesperado ao enviar/apagar a mensagem de boas-vindas: {e}")
            else:
                # Se o membro já tinha o cargo, apenas reage para confirmar que viu
                await message.add_reaction("👍")


async def setup(client: commands.Bot) -> None:
    """Função para carregar a Cog no bot."""
    await client.add_cog(Autorole(client))
