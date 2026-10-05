"""
AURA · Provas
-------------
Exame de configuração POR SERVIDOR. Tudo que antes era fixo em variavel de
ambiente (canais, cargo que aprova, número de acertos, tempo por pergunta,
cooldown e o próprio `OWNER_ID`) agora vem da config da guild, editável pelo
painel em **Provas**.

Questões: `provas_<guild_id>.json` quando existir, senão `provas.json` da raiz.
Formato do arquivo:

    {
      "questoes": [
        {"id": 1, "pergunta": "...", "alternativas": ["a", "b", "c", "d"],
         "correta": 2}
      ]
    }

Fluxo:
    /prova iniciar        o membro responde por DM, com tempo por pergunta
    aprovação            se `require_approval`, o cargo configurado decide
    /prova criar         cria/edita o questionário em arquivo
    /prova ver           histórico das tentativas deste servidor
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import re
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import discord
from discord import app_commands, ui
from discord.ext import commands, tasks

import mongo_db
from core import runtime
from core import settings as st

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#: Onde ficam os bancos de perguntas por servidor. Fora do Docker é a raiz do
#: projeto; no Docker, um volume, para não sumir a cada recriação do container.
PASTA_DADOS = os.getenv("AURA_DATA_DIR") or RAIZ
os.makedirs(PASTA_DADOS, exist_ok=True)
ARQUIVO_PADRAO = os.path.join(PASTA_DADOS, "provas.json")

#: Banco de perguntas que vem no repositório, usado como semente no primeiro
#: start. No Docker o volume /app/dados começa vazio, então a cópia precisa vir
#: da imagem (/app/provas.json) e não do próprio volume.
SEMENTE = os.path.join(RAIZ, "provas.json")


def _garantir_semente() -> None:
    """Copia o banco inicial para a pasta de dados se ela ainda não tiver um."""
    if os.path.exists(ARQUIVO_PADRAO) or not os.path.exists(SEMENTE):
        return
    try:
        with open(SEMENTE, "rb") as origem:
            conteudo = origem.read()
        with open(ARQUIVO_PADRAO, "wb") as destino:
            destino.write(conteudo)
    except Exception as exc:
        print(f"Aviso: não consegui preparar o banco de perguntas inicial: {exc}")


_garantir_semente()

#: O Discord aceita no máximo 5 botões por linha.
MAX_ALTERNATIVAS = 5


def _embaralhar_alternativas(questao: Dict[str, Any]) -> None:
    """
    Mistura as alternativas de uma pergunta e remapeia o índice da correta,
    senão a resposta viraria outra depois da troca.
    """
    alternativas = questao.get("alternativas")
    if not isinstance(alternativas, list) or len(alternativas) < 2:
        return
    correta = questao.get("correta")
    try:
        correta = int(correta)
    except (TypeError, ValueError):
        correta = -1
    if not 0 <= correta < len(alternativas):
        return
    pares = list(enumerate(alternativas))
    random.shuffle(pares)
    questao["alternativas"] = [texto for _, texto in pares]
    questao["correta"] = next(i for i, (original, _) in enumerate(pares)
                              if original == correta)


# ==========================================================================
# Views
# ==========================================================================

class IntroView(ui.View):
    """Botões de começar/cancelar. Vive na DM, então não é persistente."""

    def __init__(self, cog: "SistemaProva", user_id: str, guild_id: int,
                 questoes: List[Dict[str, Any]], cfg: Dict[str, Any]):
        super().__init__(timeout=None)
        self.cog = cog
        self.user_id = str(user_id)
        self.guild_id = int(guild_id)
        self.questoes = questoes
        self.cfg = cfg
        self.confirmado = False

    @ui.button(label="Começar", style=discord.ButtonStyle.green, emoji="✅")
    async def _confirmar(self, interaction: discord.Interaction, button: ui.Button):
        if str(interaction.user.id) != self.user_id:
            return _nega(interaction, "Esse botão não é seu.")
        self.confirmado = True
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()
        await self.cog._rodar_exame(interaction.user, self.user_id, self.guild_id,
                                    self.questoes, self.cfg)

    @ui.button(label="Cancelar", style=discord.ButtonStyle.red, emoji="✖️")
    async def _cancelar(self, interaction: discord.Interaction, button: ui.Button):
        if str(interaction.user.id) != self.user_id:
            return _nega(interaction, "Esse botão não é seu.")
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()
        mongo_db.deletar_aprovacao_pendente(self.user_id, self.guild_id)
        await interaction.followup.send("Prova cancelada. Sem penalidade.")


class ProvaView(ui.View):
    """Uma pergunta com as alternativas e o cronômetro."""

    def __init__(self, questao: Dict[str, Any], total: int, atual: int,
                 segundos: int):
        super().__init__(timeout=segundos)
        self.questao = questao
        self.total = total
        self.atual = atual
        self.value: Optional[int] = None
        self.embed = self._montar_embed()

        for i, texto in enumerate(questao.get("alternativas") or []):
            self.add_item(_Alternativa(i, str(texto)[:100]))

    def _montar_embed(self) -> discord.Embed:
        emb = discord.Embed(
            title=f"Questão {self.atual}/{self.total}",
            description=str(self.questao.get("pergunta", ""))[:4000],
            color=discord.Color.gold(),
        )
        emb.set_footer(text="⏱️ O tempo acaba e a prova é encerrada.")
        return emb


class _Alternativa(ui.Button):
    def __init__(self, indice: int, texto: str):
        super().__init__(style=discord.ButtonStyle.secondary, label=texto[:80],
                         row=indice)
        self.indice = indice

    async def callback(self, interaction: discord.Interaction):
        view: ProvaView = self._view  # type: ignore[assignment]
        view.value = self.indice
        for item in view.children:
            item.disabled = True
        view.stop()
        await interaction.response.edit_message(view=view)


class AprovacaoView(ui.View):
    """
    Botões de aprovar/negar, restritos ao cargo de aprovador do servidor.

    A view chega por DM, então `interaction.guild` é `None` e o autor é um
    `User`, não um `Member`. Por isso o servidor é resolvido pelo ID guardado
    aqui e as permissões são checadas no membro dentro dele.
    """

    def __init__(self, cog: "SistemaProva", guild_id: int, user_id: str,
                 user_name: str, questoes: List[Dict[str, Any]], cfg: Dict[str, Any]):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = int(guild_id)
        self.user_id = str(user_id)
        self.user_name = user_name
        self.questoes = questoes
        self.cfg = cfg

    @property
    def guild(self) -> Optional[discord.Guild]:
        return self.cog.client.get_guild(self.guild_id)

    @property
    def guild_nome(self) -> str:
        guild = self.guild
        return guild.name if guild is not None else f"Servidor {self.guild_id}"

    async def _pode_decidir(self, interaction: discord.Interaction) -> bool:
        if st.eh_dono(interaction.user.id):
            return True
        guild = self.guild
        if guild is None:
            return False
        membro = guild.get_member(interaction.user.id)
        if membro is None:
            return False
        if membro.guild_permissions.administrator:
            return True
        cargo = (self.cfg or {}).get("approval_role_id")
        if not cargo:
            return False
        return any(r.id == int(cargo) for r in membro.roles)

    async def _finaliza(self, interaction: discord.Interaction, aprovado: bool):
        for item in self.children:
            item.disabled = True
        texto = ("✅ Aprovado! Pode iniciar a prova."
                 if aprovado else "❌ Negado.")
        await interaction.response.edit_message(view=self, content=texto)
        mongo_db.deletar_aprovacao_pendente(self.user_id, self.guild_id)

        guild = self.guild
        try:
            dm = await interaction.user.create_dm()
        except discord.Forbidden:
            dm = None

        if not aprovado:
            if dm:
                await dm.send(f"Sua solicitação de prova no **{self.guild_nome}** "
                              f"foi **negada**.")
            return

        alvo = guild.get_member(int(self.user_id)) if guild is not None else None
        if alvo is None:
            try:
                alvo = await self.cog.client.fetch_user(int(self.user_id))
            except (discord.NotFound, discord.HTTPException):
                return
        if dm is None:
            try:
                dm = await alvo.create_dm()
            except discord.Forbidden:
                return

        view = IntroView(self.cog, self.user_id, self.guild_id, self.questoes, self.cfg)
        await dm.send(f"✅ Liberação aprovada em **{self.guild_nome}**. "
                      f"Aperte começar.", view=view)
        mongo_db.salvar_aprovacao_pendente(
            self.user_id, self.user_name, self.questoes, self.cfg,
            status="aguardando_usuario", guild_id=self.guild_id,
        )
        self.stop()

    @ui.button(label="Aprovar", style=discord.ButtonStyle.green, emoji="✅")
    async def _aprovar(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._pode_decidir(interaction):
            return _nega(interaction, "Só o cargo de aprovador decide isso.")
        await self._finaliza(interaction, True)

    @ui.button(label="Negar", style=discord.ButtonStyle.red, emoji="✖️")
    async def _negar(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._pode_decidir(interaction):
            return _nega(interaction, "Só o cargo de aprovador decide isso.")
        await self._finaliza(interaction, False)


def _nega(interaction: discord.Interaction, texto):
    """Responde com embed ou texto, sem estourar se já respondeu."""
    extra = {"embed": texto} if isinstance(texto, discord.Embed) else {"content": texto}
    if interaction.response.is_done():
        return interaction.followup.send(ephemeral=True, **extra)
    return interaction.response.send_message(ephemeral=True, **extra)


# ==========================================================================
# Cog
# ==========================================================================

class SistemaProva(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client
        self._banco: Dict[str, Dict[str, Any]] = {}
        self._avisos: Dict[str, str] = {}
        #: Guarda para a retomada de aprovações rodar uma vez só, mesmo com
        #: o on_ready disparando mais de uma vez (reconexão).
        self._ja_retomou = False

    # ---------- carga das questões ----------

    def _caminho(self, guild_id: int) -> Optional[str]:
        """Arquivo de leitura: o do servidor, ou o da raiz como ponto de partida."""
        especifico = os.path.join(PASTA_DADOS, f"provas_{guild_id}.json")
        if os.path.exists(especifico):
            return especifico
        return ARQUIVO_PADRAO if os.path.exists(ARQUIVO_PADRAO) else None

    def _caminho_de_escrita(self, guild_id: int) -> str:
        """
        Onde gravar. Sempre o arquivo do servidor: o `provas.json` da raiz é
        semente de leitura, e escrever nele misturaria as perguntas de todos os
        servidores num banco só.
        """
        return os.path.join(PASTA_DADOS, f"provas_{int(guild_id)}.json")

    def carregar_provas(self, guild_id: int) -> Optional[Dict[str, Any]]:
        gid = str(guild_id)
        if gid in self._banco:
            return self._banco[gid]

        caminho = self._caminho(int(guild_id))
        if not caminho:
            self._avisos[gid] = (
                "Não achei `provas.json` na raiz do projeto. Crie com `/prova criar`."
            )
            return None

        try:
            with open(caminho, encoding="utf-8-sig") as fh:
                dados = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            self._avisos[gid] = f"Erro ao ler as questões: {exc}"
            runtime.log("ERRO", f"[provas] {gid}: {exc}", "provas")
            return None

        questoes = []
        vistos = set()
        for q in dados.get("questoes") or []:
            alternativas = q.get("alternativas") or []
            correta = q.get("correta")
            if len(alternativas) < 2 or not isinstance(correta, int):
                continue
            if not 0 <= correta < len(alternativas):
                continue
            if q.get("id") in vistos:
                continue
            vistos.add(q.get("id"))
            questoes.append(q)

        if not questoes:
            self._avisos[gid] = "O arquivo não tem perguntas válidas."
            return None

        self._avisos.pop(gid, None)
        self._banco[gid] = {"questoes": questoes}
        return self._banco[gid]

    @commands.Cog.listener()
    async def on_ready(self):
        runtime.log("INFO", f"Provas: {len(self.client.guilds)} servidor(es) online.", "provas")
        # Os botões vivem na DM e morrem com o processo. Quem ficou esperando
        # aprovação precisa receber o pedido de novo, senão a solicitação
        # travava no banco até o membro desistir.
        if self._ja_retomou:
            return
        self._ja_retomou = True
        try:
            await self._retomar_aprovacoes()
        except Exception as exc:
            runtime.log("ERRO", f"[provas] falha ao retomar aprovações: {exc}", "provas")

    async def _retomar_aprovacoes(self) -> int:
        """
        Reenvia o pedido de aprovação de quem ficou pendente antes do restart.

        Só o caminho `aguardando_aprovador` volta: no outro a DM já tinha sido
        aberta, e o botão do examineando também morreu com o processo — aí o
        registro é apagado para o pedido não ficar preso para sempre.
        """
        retomadas = 0
        for registro in mongo_db.listar_aprovacoes_pendentes(incluir_questoes=True):
            guild_id = registro.get("guild_id")
            if registro.get("status") != "aguardando_aprovador":
                # A DM já tinha sido aberta e o botão do examineando morreu com
                # o processo; apagar o registro deixa o pedido reinscritível.
                mongo_db.deletar_aprovacao_pendente(registro.get("user_id"), guild_id)
                continue
            guild_id = registro.get("guild_id")
            guild = self.client.get_guild(int(guild_id)) if guild_id else None
            questoes = registro.get("questoes") or []
            bloco = registro.get("config") or {}
            if guild is None or not questoes or not bloco:
                # Não dá para reabrir: limpa para o registro não ficar eterno.
                mongo_db.deletar_aprovacao_pendente(
                    registro.get("user_id"), guild_id)
                continue

            membro = guild.get_member(int(registro["user_id"]))
            if membro is None:
                mongo_db.deletar_aprovacao_pendente(
                    registro.get("user_id"), guild_id)
                continue

            try:
                avisados = await self._avisar_aprovadores(
                    guild, bloco, membro, questoes, registro["user_id"])
            except Exception as exc:
                runtime.log("ERRO", f"[provas] falha ao retomar aprovação: {exc}", "provas")
                continue
            if avisados:
                retomadas += 1
            else:
                mongo_db.deletar_aprovacao_pendente(
                    registro.get("user_id"), guild_id)

        if retomadas:
            runtime.log(
                "INFO", f"Provas: {retomadas} aprovação(ões) reenviada(s).", "provas")
        return retomadas

    # ---------- comandos ----------

    prova = app_commands.Group(
        name="prova",
        description="Exame de qualificação.",
        guild_only=True,
    )

    @prova.command(name="iniciar", description="Começa o exame deste servidor.")
    async def prova_iniciar(self, interaction: discord.Interaction):
        guild = interaction.guild
        cfg = await st.get_config_cached(guild.id, guild_name=guild.name)
        if not st.module_enabled(cfg, "provas"):
            return _nega(interaction, "O módulo de provas está desligado neste servidor.")

        bloco = cfg.get("provas") or {}
        banco = self.carregar_provas(guild.id)
        if not banco:
            return _nega(interaction, self._avisos.get(str(guild.id),
                                                        "Prova sem perguntas."))
        if interaction.user.bot:
            return _nega(interaction, "Bots não fazem prova.")

        gid = str(guild.id)
        uid = str(interaction.user.id)

        liberar = mongo_db.get_cooldown(uid, gid)
        if liberar and liberar > datetime.now():
            return _nega(interaction,
                         f"Você já fez a prova recentemente. Tente <t:{int(liberar.timestamp())}:R>.")

        total = max(1, min(len(banco["questoes"]), int(bloco.get("pass_score") or 1) * 2))
        questoes = list(banco["questoes"])
        random.shuffle(questoes)
        # Cópia profunda: embaralhar não pode mexer no banco em cache.
        selecionadas = deepcopy(questoes[:total])
        if bloco.get("shuffle_answers", True):
            for q in selecionadas:
                _embaralhar_alternativas(q)

        try:
            dm = await interaction.user.create_dm()
        except discord.Forbidden:
            return _nega(interaction, "Não consegui abrir DM. Libere mensagens "
                                      "diretas do servidor para mim.")

        if bloco.get("require_approval", True):
            avisados = await self._avisar_aprovadores(
                guild, bloco, interaction.user, selecionadas, uid)
            if avisados:
                mongo_db.salvar_aprovacao_pendente(
                    uid, str(interaction.user), selecionadas, bloco,
                    status="aguardando_aprovador", guild_id=gid,
                )
                return _nega(interaction,
                             "📩 Sua solicitação foi enviada para aprovação. "
                             "Aguarde o contato no privado.")
            mongo_db.salvar_aprovacao_pendente(
                uid, str(interaction.user), selecionadas, bloco,
                status="aguardando_usuario", guild_id=gid,
            )
        else:
            mongo_db.salvar_aprovacao_pendente(
                uid, str(interaction.user), selecionadas, bloco,
                status="aguardando_usuario", guild_id=gid,
            )

        await self._abrir_intro(dm, interaction.user, uid, guild.id, selecionadas, bloco)

    async def _abrir_intro(self, dm, user, uid: str, guild_id: int,
                           questoes: List[Dict[str, Any]], bloco: Dict[str, Any]):
        guild = self.client.get_guild(guild_id)
        titulo = bloco.get("title") or "Exame de Qualificação"
        banco = (bloco.get("bank_name") or "").strip()
        segundos = int(bloco.get("time_per_question") or 120)
        precisa = int(bloco.get("pass_score") or 1)

        emb = discord.Embed(
            title=f"🛡️ {titulo}" + (f" · {banco}" if banco else ""),
            description=(
                f"Olá, {user.mention}! Este exame é do servidor "
                f"**{guild.name if guild else guild_id}**.\n\n"
                f"São **{len(questoes)}** perguntas, **{segundos}s** cada. "
                f"Precisa de **{precisa} acertos** para passar."
            ),
            color=discord.Color.gold(),
        )
        view = IntroView(self, uid, guild_id, questoes, bloco)
        await dm.send(embed=emb, view=view)

    async def _avisar_aprovadores(self, guild: discord.Guild, bloco: Dict[str, Any],
                                  membro: discord.Member,
                                  questoes: List[Dict[str, Any]],
                                  uid: str) -> bool:
        cargo_id = bloco.get("approval_role_id")
        cargo = guild.get_role(int(cargo_id)) if cargo_id else None
        alvos = list(cargo.members) if cargo else []
        alvos = [m for m in alvos if m.id != membro.id]

        canal = guild.get_channel(bloco["notify_channel_id"]) if bloco.get("notify_channel_id") else None

        if not alvos:
            destino = guild.owner
            if destino and destino.id != membro.id:
                alvos = [destino]
        if not alvos:
            return False

        emb = discord.Embed(
            title="📋 Solicitação de prova",
            description=f"{membro.mention} quer fazer o exame deste servidor.",
            color=discord.Color.blurple(),
        )
        emb.add_field(name="Membro", value=f"{membro} (`{membro.id}`)", inline=False)
        emb.add_field(name="Servidor", value=f"{guild.name} (`{guild.id}`)", inline=False)
        emb.add_field(name="Conta criada",
                      value=f"<t:{int(membro.created_at.timestamp())}:R>", inline=True)
        emb.add_field(name="Entrou aqui",
                      value=f"<t:{int(membro.joined_at.timestamp())}:R>" if membro.joined_at else "—",
                      inline=True)

        view = AprovacaoView(self, guild.id, uid, str(membro), questoes, bloco)
        enviados = 0
        for alvo in alvos:
            try:
                await alvo.send(embed=emb, view=view)
                enviados += 1
            except (discord.Forbidden, discord.HTTPException):
                continue
        if canal is not None:
            await canal.send(embed=emb)
        return enviados > 0

    @prova.command(name="criar", description="Cria o arquivo de questões deste servidor.")
    @app_commands.describe(
        pergunta="Texto da pergunta",
        alternativas="Opções separadas por |",
        correta="Índice da alternativa certa, começando em 0",
    )
    @app_commands.default_permissions(manage_guild=True)
    async def prova_criar(self, interaction: discord.Interaction,
                          pergunta: str, alternativas: str, correta: int):
        guild = interaction.guild
        cfg = await st.get_config_cached(guild.id, guild_name=guild.name)
        if not st.eh_dono(interaction.user.id, cfg) and \
                not interaction.user.guild_permissions.manage_guild:
            return _nega(interaction, "Só manageguild ou dono do AURA.")

        opcoes = [a.strip() for a in alternativas.split("|") if a.strip()]
        if len(opcoes) < 2:
            return _nega(interaction, "Preciso de pelo menos duas alternativas.")
        if len(opcoes) > MAX_ALTERNATIVAS:
            return _nega(
                interaction,
                f"Máximo de {MAX_ALTERNATIVAS} alternativas por pergunta "
                f"(recebi {len(opcoes)}). Separe por `|`.")
        if not 0 <= correta < len(opcoes):
            return _nega(interaction, f"A alternativa correta vai de 0 a {len(opcoes) - 1}.")

        # Sempre no arquivo deste servidor, mesmo lendo a semente da raiz.
        caminho = self._caminho_de_escrita(guild.id)

        dados = {"questoes": []}
        if os.path.exists(caminho):
            try:
                with open(caminho, encoding="utf-8-sig") as fh:
                    dados = json.load(fh)
            except (OSError, json.JSONDecodeError):
                dados = {"questoes": []}
        dados.setdefault("questoes", [])

        novo_id = max([int(q.get("id") or 0) for q in dados["questoes"]] + [0]) + 1
        dados["questoes"].append({
            "id": novo_id,
            "pergunta": pergunta[:1000],
            "alternativas": opcoes,
            "correta": int(correta),
        })

        try:
            with open(caminho, "w", encoding="utf-8") as fh:
                json.dump(dados, fh, ensure_ascii=False, indent=2)
        except OSError as exc:
            return _nega(interaction, f"Não consegui gravar: {exc}")

        self._banco.pop(str(guild.id), None)
        self.carregar_provas(guild.id)
        mongo_db.registrar_auditoria(
            guild.id, guild.name, "prova_criada", "provas",
            str(interaction.user), f"pergunta {novo_id}",
        )
        await _nega(interaction, f"✅ Pergunta {novo_id} salva. Total: "
                                 f"{len(dados['questoes'])}.")

    @prova.command(name="ver", description="Mostra as perguntas deste servidor.")
    async def prova_ver(self, interaction: discord.Interaction):
        guild = interaction.guild
        cfg = await st.get_config_cached(guild.id, guild_name=guild.name)
        if not st.eh_dono(interaction.user.id, cfg) and \
                not interaction.user.guild_permissions.manage_guild:
            return _nega(interaction, "Só manageguild ou dono do AURA.")

        banco = self.carregar_provas(guild.id)
        if not banco:
            return _nega(interaction, self._avisos.get(str(guild.id), "Sem questões."))

        linhas = []
        for q in banco["questoes"][:25]:
            alternativas = " | ".join(
                f"{'✅' if i == q.get('correta') else '❌'} {a[:30]}"
                for i, a in enumerate(q.get("alternativas") or [])
            )
            linhas.append(f"**{q.get('id')}.** {str(q.get('pergunta'))[:120]}\n{alternativas}")

        await _nega(interaction, discord.Embed(
            title=f"📚 {len(banco['questoes'])} pergunta(s)",
            description=("\n\n".join(linhas) or "vazio")[:3900],
            color=discord.Color.blurple(),
        ))

    @prova.command(name="apagar", description="Remove uma pergunta deste servidor.")
    @app_commands.describe(numero="ID da pergunta, como mostra /prova ver")
    @app_commands.default_permissions(manage_guild=True)
    async def prova_apagar(self, interaction: discord.Interaction, numero: int):
        guild = interaction.guild
        cfg = await st.get_config_cached(guild.id, guild_name=guild.name)
        if not st.eh_dono(interaction.user.id, cfg) and \
                not interaction.user.guild_permissions.manage_guild:
            return _nega(interaction, "Só manageguild ou dono do AURA.")

        banco = self.carregar_provas(guild.id)
        if not banco:
            return _nega(interaction, self._avisos.get(str(guild.id), "Sem questões."))

        caminho = self._caminho_de_escrita(guild.id)
        antes = len(banco["questoes"])
        banco["questoes"] = [q for q in banco["questoes"] if int(q.get("id") or 0) != numero]

        if len(banco["questoes"]) == antes:
            return _nega(interaction, f"Não achei a pergunta {numero}.")
        if not banco["questoes"]:
            self._banco.pop(str(guild.id), None)
            return _nega(interaction, "Era a última. Apague o arquivo se quiser recomeçar.")

        if caminho:
            try:
                with open(caminho, "w", encoding="utf-8") as fh:
                    json.dump({"questoes": banco["questoes"]}, fh,
                              ensure_ascii=False, indent=2)
            except OSError as exc:
                return _nega(interaction, f"Não consegui gravar: {exc}")

        self._banco.pop(str(guild.id), None)
        mongo_db.registrar_auditoria(
            guild.id, guild.name, "prova_apagada", "provas",
            str(interaction.user), f"pergunta {numero}",
        )
        await _nega(interaction, f"🗑️ Pergunta {numero} removida.")

    # ---------- execução ----------

    async def _rodar_exame(self, user: discord.abc.User, uid: str, guild_id: int,
                           questoes: List[Dict[str, Any]], bloco: Dict[str, Any]):
        guild = self.client.get_guild(guild_id)
        segundos = int(bloco.get("time_per_question") or 120)

        try:
            dm = await user.create_dm()
        except discord.Forbidden:
            return

        aviso = await dm.send("🚀 A prova começa em 3 segundos…")
        await asyncio.sleep(3)
        try:
            await aviso.delete()
        except discord.HTTPException:
            pass

        acertos = 0
        respostas: List[Dict[str, Any]] = []

        for i, questao in enumerate(questoes, start=1):
            view = ProvaView(questao, len(questoes), i, segundos)
            msg = await dm.send(embed=view.embed, view=view)
            try:
                await view.wait()
            except asyncio.TimeoutError:
                view.stop()
            try:
                await msg.delete()
            except discord.HTTPException:
                pass

            if view.value is None:
                await dm.send("⏱️ Tempo esgotado. Prova encerrada, sem penalidade.")
                mongo_db.deletar_aprovacao_pendente(uid, guild_id)
                return

            alternativas = questao["alternativas"]
            acertou = view.value == questao["correta"]
            if acertou:
                acertos += 1
            respostas.append({
                "id": questao.get("id"),
                "pergunta": str(questao.get("pergunta", ""))[:500],
                "escolhida": alternativas[view.value],
                "correta": alternativas[questao["correta"]],
                "acertou": acertou,
            })

        passou = acertos >= int(bloco.get("pass_score") or 1)
        mongo_db.salvar_prova(user.id, str(user), acertos, len(questoes), passou,
                              respostas, guild_id=guild_id,
                              guild_name=guild.name if guild else None)
        mongo_db.registrar_auditoria(
            guild_id, guild.name if guild else str(guild_id), "prova_finalizada",
            "provas", str(user), f"{acertos}/{len(questoes)} "
                                  f"{'aprovado' if passou else 'reprovado'}",
        )
        mongo_db.deletar_aprovacao_pendente(uid, guild_id)

        emb = discord.Embed(
            title="✅ Prova finalizada" if passou else "❌ Prova finalizada",
            description=(
                f"Nota: **{acertos}/{len(questoes)}**.\n"
                + (f"Resultado registrado em **{guild.name}**."
                   if guild else "Resultado registrado.")
            ),
            color=discord.Color.green() if passou else discord.Color.red(),
        )
        await dm.send(embed=emb)

        if not passou:
            dias = int(bloco.get("cooldown_days") or 0)
            if dias > 0:
                mongo_db.set_cooldown(uid, str(guild_id), dias)
                await dm.send(f"Você pode tentar de novo em **{dias} dia(s)**.")

        await self._mandar_relatorio(guild, bloco, user, acertos, len(questoes),
                                     passou, respostas)

    async def _mandar_relatorio(self, guild: Optional[discord.Guild],
                                bloco: Dict[str, Any], user, acertos: int,
                                total: int, passou: bool,
                                respostas: List[Dict[str, Any]]) -> None:
        if guild is None:
            return
        canal = guild.get_channel(bloco["backup_channel_id"]) if bloco.get("backup_channel_id") else None
        if canal is None:
            return

        emb = discord.Embed(
            title=f"📑 Prova de {user}",
            color=discord.Color.green() if passou else discord.Color.red(),
        )
        emb.add_field(name="Nota", value=f"**{acertos}/{total}**", inline=True)
        emb.add_field(name="Resultado",
                      value="🟢 aprovado" if passou else "🔴 reprovado", inline=True)
        erros = [r for r in respostas if not r["acertou"]]
        if erros:
            texto = "\n".join(
                f"**{r['pergunta'][:80]}**\n❌ {r['escolhida'][:40]} · ✅ {r['correta'][:40]}"
                for r in erros[:6]
            )
            emb.add_field(name="Erros", value=texto[:1000], inline=False)

        try:
            await canal.send(embed=emb)
        except (discord.Forbidden, discord.HTTPException):
            pass


async def setup(client: commands.Bot) -> None:
    await client.add_cog(SistemaProva(client))