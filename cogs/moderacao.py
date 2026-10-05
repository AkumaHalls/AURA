"""
AURA · Cog de Moderação
-----------------------
Filtros automatos configuráveis POR SERVIDOR no painel:

    palavras proibidas   lista de termos (palavra inteira, "contém" ou regex)
    links                bloquear tudo, só convites, ou lista branca de domínios
    convites             discord.gg e afins
    caixa alta           acima de X% de letras maiúsculas
    flood                N mensagens em X segundos
    duplicadas           mesma mensagem repetida N vezes
    menções              excesso de @pessoas / @cargos
    zerospace            caracteres invisíveis usados para burlar o filtro

Cada filtro tem sua própria ação (nada / apagar / avisar / timeout / banir) e
participa da escalada progressiva configurada no painel.

Também traz os comandos manuais no estilo Loritta: /mod warn, /mod punir,
/mod limpar-infrações, /mod registro, /mod trancar, /mod destrancar, etc.
"""

from __future__ import annotations

import re
import time
import unicodedata
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands

import mongo_db
from core import runtime
from core import settings as st
from core.placeholders import render

# --------------------------------------------------------------------------
# Regexes compilados
# --------------------------------------------------------------------------

RE_URL = re.compile(
    r"(?:https?://|www\.|discord\.gg|discord(?:app)?\.com/invite|invite\.gg|"
    r"t\.me/|youtu\.be|bit\.ly|tinyurl|wa\.me|bit\.do|gg\.gg|raw\.githubusercontent)",
    re.IGNORECASE,
)

RE_INVITE = re.compile(
    r"(?:discord(?:app)?\.com/invite|discord\.gg|discord\.me|dsc\.gg|invite\.gg|"
    r"discord\.li|discord\.io)\s*/?\s*([\w-]{2,64})",
    re.IGNORECASE,
)

RE_MENTION = re.compile(r"<@!?(\d{15,25})>")
RE_ROLE_MENTION = re.compile(r"<@&(\d{15,25})>")

#: Caracteres invisíveis usados para esconder palavras proibidas.
INVISIBLE = "‌‍⁠﻿᠎" + "".join(chr(c) for c in range(0x200B, 0x2010))


def strip_invisible(text: str) -> str:
    return "".join(ch for ch in text if ch not in INVISIBLE)


def normalize_text(text: str) -> str:
    """Minúsculas sem acento, para casar 'idiota' com 'Idiota' e 'ídiota'."""
    t = unicodedata.normalize("NFD", strip_invisible(text).lower())
    return "".join(ch for ch in t if unicodedata.category(ch) != "Mn")


#: Regex compiladas por guild, para não recompilar a cada mensagem.
_pattern_cache: Dict[str, Dict[str, Any]] = {}
_pattern_cache_at: Dict[str, float] = {}
PATTERN_TTL = 300.0

#: Histórico em memória para flood/duplicatas.
_track: Dict[Tuple[str, str], List[float]] = {}
_dup_track: Dict[Tuple[str, str], List[Tuple[float, str]]] = {}


def _purged(now: float) -> None:
    if len(_track) > 4000:
        for k in [k for k, v in _track.items() if not v or v[-1] < now - 600]:
            _track.pop(k, None)
    if len(_dup_track) > 4000:
        for k in [k for k, v in _dup_track.items() if not v or v[-1][0] < now - 600]:
            _dup_track.pop(k, None)


# --------------------------------------------------------------------------
# Veredito de um filtro
# --------------------------------------------------------------------------

class Veredito:
    __slots__ = ("filtro", "motivo", "severidade", "acao", "detalhe")

    def __init__(self, filtro: str, motivo: str, severidade: str = "media",
                 acao: str = "apagar", detalhe: str = None):
        self.filtro = filtro
        self.motivo = motivo
        self.severidade = severidade
        self.acao = acao
        self.detalhe = detalhe


def build_patterns(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Compila (e cacheia) as expressões dos termos proibidos de um servidor."""
    gid = str(cfg.get("guild_id"))
    ts = _pattern_cache_at.get(gid, 0)
    if time.time() - ts < PATTERN_TTL and gid in _pattern_cache:
        return _pattern_cache[gid]

    padroes = []
    for item in (cfg.get("moderation", {}).get("words", {}) or {}).get("terms", []) or []:
        termo = item.get("term", "")
        modo = item.get("mode", "palavra")
        sev = item.get("severity", "media")
        try:
            if modo == "regex":
                rx = re.compile(termo, re.IGNORECASE)
            elif modo == "contem":
                rx = re.compile(re.escape(normalize_text(termo)), re.IGNORECASE)
            else:  # palavra inteira
                base = normalize_text(termo)
                if not base:
                    continue
                partes = [re.escape(p) for p in base.split()]
                rx = re.compile(r"(?<!\w)" + r"\s*".join(partes) + r"(?!\w)", re.IGNORECASE)
        except re.error:
            runtime.log("AVISO", f"Regex inválido ignorado no servidor {gid}: {termo!r}", "mod")
            continue
        padroes.append({"rx": rx, "termo": termo, "modo": modo, "severidade": sev})

    _pattern_cache[gid] = padroes
    _pattern_cache_at[gid] = time.time()
    return padroes


def checar_palavras(texto: str, cfg: Dict[str, Any]) -> Optional[Veredito]:
    norm = normalize_text(texto)
    for p in build_patterns(cfg):
        if p["rx"].search(norm):
            return Veredito(
                filtro="palavra_proibida",
                motivo=f"Uso da palavra proibida `{p['termo']}`",
                severidade=p["severidade"],
                detalhe=p["termo"],
            )
    return None


def checar_links(texto: str, links_cfg: Dict[str, Any]) -> Optional[Veredito]:
    m = RE_URL.search(texto)
    if not m:
        return None

    achado = m.group(0).lower()
    dominio = ""

    dm = re.search(r"https?://([^/\s]+)", texto, re.IGNORECASE)
    if dm:
        dominio = dm.group(1).split("/")[0].lower()

    modo = links_cfg.get("mode", "bloquear_convites")
    permitidos = links_cfg.get("allowed_domains") or []

    if permitido(dominio or achado, permitidos):
        return None

    if modo == "lista_branca":
        return Veredito(
            filtro="link",
            motivo=f"Link `{dominio or achado}` fora da lista de domínios permitidos",
            detalhe=dominio or achado,
        )
    if modo == "bloquear_convites":
        if RE_INVITE.search(texto):
            return Veredito(filtro="link", motivo="Convite de servidor em link bloqueado",
                            detalhe=achado)
        return None
    # bloquear_tudo
    return Veredito(
        filtro="link",
        motivo=f"Link não permitido (`{dominio or achado}`)",
        detalhe=dominio or achado,
    )


def permitido(dominio: str, permitidos: List[str]) -> bool:
    if not dominio:
        return False
    d = dominio.lower().lstrip("@.")
    for p in permitidos or []:
        p = str(p).lower().lstrip("@.")
        if d == p or d.endswith("." + p) or p == "*":
            return True
    return False


def checar_caps(texto: str, caps_cfg: Dict[str, Any]) -> Optional[Veredito]:
    letras = [c for c in texto if c.isalpha()]
    if len(letras) < int(caps_cfg.get("min_chars", 12)):
        return None
    maiusculas = sum(1 for c in letras if c.isupper())
    pct = (maiusculas / len(letras)) * 100
    if pct >= int(caps_cfg.get("percent", 70)):
        return Veredito(filtro="caps", motivo=f"Mensagem em {pct:.0f}% caixa alta",
                        detalhe=f"{pct:.0f}%")
    return None


def checar_zerospace(texto: str, zs_cfg: Dict[str, Any]) -> Optional[Veredito]:
    limpas = [c for c in texto if c.isprintable() and not c.isspace()]
    invisiveis = sum(1 for c in texto if c in INVISIBLE)
    if invisiveis >= 3 and len(limpas) >= int(zs_cfg.get("min_chars", 12)):
        return Veredito(filtro="zerospace",
                        motivo="Mensagem com caracteres invisíveis",
                        detalhe=f"{invisiveis} caracteres ocultos")
    return None


def checar_mencoes(message: discord.Message, mencoes_cfg: Dict[str, Any]) -> Optional[Veredito]:
    n_users = len(RE_MENTION.findall(message.content))
    n_roles = len(RE_ROLE_MENTION.findall(message.content))
    if n_users > int(mencoes_cfg.get("max_user_mentions", 6)):
        return Veredito(filtro="mencao", motivo=f"{n_users} menções a pessoas numa mensagem",
                        detalhe=str(n_users))
    if n_roles > int(mencoes_cfg.get("max_role_mentions", 2)):
        return Veredito(filtro="mencao", motivo=f"{n_roles} menções a cargos numa mensagem",
                        detalhe=str(n_roles))
    return None


def checar_flood(guild_id: str, user_id: str, janela: int, limite: int) -> Optional[Veredito]:
    agora = time.time()
    chave = (str(guild_id), str(user_id))
    tempos = _track.setdefault(chave, [])
    tempos.append(agora)
    corte = agora - janela
    while tempos and tempos[0] < corte:
        tempos.pop(0)
    if len(tempos) > limite:
        return Veredito(
            filtro="flood",
            motivo=f"{len(tempos)} mensagens em {janela}s",
            detalhe=f"{len(tempos)}/{limite}",
            severidade="alta",
        )
    return None


def checar_duplicata(guild_id: str, user_id: str, texto: str,
                     janela: int, limite: int) -> Optional[Veredito]:
    agora = time.time()
    chave = (str(guild_id), str(user_id))
    alvo = texto.strip().lower()
    if not alvo:
        return None
    itens = _dup_track.setdefault(chave, [])
    itens.append((agora, alvo))
    corte = agora - janela
    while itens and itens[0][0] < corte:
        itens.pop(0)
    repeticoes = sum(1 for _, t in itens if t == alvo)
    if repeticoes > limite:
        return Veredito(
            filtro="duplicada",
            motivo=f"Mensagem repetida {repeticoes}x em {janela}s",
            detalhe=f"{repeticoes}/{limite}",
            severidade="media",
        )
    return None


# --------------------------------------------------------------------------
# Cog
# --------------------------------------------------------------------------

class Moderacao(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client
        self.client.add_view(ConfigModView())

    async def cog_unload(self):
        _pattern_cache.clear()
        _pattern_cache_at.clear()
        _track.clear()
        _dup_track.clear()

    # ---------------- listener principal ----------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.webhook_id:
            return
        guild = message.guild
        if guild is None:
            return

        try:
            cfg = await st.get_config_cached(guild.id, guild_name=guild.name)
        except Exception as exc:
            runtime.log("ERRO", f"moderação: falha ao ler config: {exc}", "mod")
            return

        mod = cfg.get("moderation") or {}
        if not mod.get("enabled") or not st.module_enabled(cfg, "moderacao"):
            return

        # Canais e cargos ignorados
        if message.channel.id in (mod.get("ignored_channels") or []):
            return
        roles_user = {r.id for r in message.author.roles}
        if roles_user.intersection(mod.get("ignored_roles") or []):
            return
        if roles_user.intersection((mod.get("escalation") or {}).get("exempt_roles") or []):
            return
        if any(r.permissions.administrator for r in message.author.roles):
            return
        if self._is_staff(message, cfg):
            return

        texto = message.content
        if not texto or not texto.strip():
            return

        agora = time.time()
        _purged(agora)

        vereditos: List[Veredito] = []

        w = mod.get("words") or {}
        if w.get("enabled") and w.get("terms"):
            v = checar_palavras(texto, cfg)
            if v:
                v.acao = w.get("action", "apagar")
                v.motivo = w.get("message") or v.motivo
                vereditos.append(v)

        inv = mod.get("invites") or {}
        if inv.get("enabled"):
            m = RE_INVITE.search(texto)
            if m:
                codigo = m.group(1)
                alvo = f"https://discord.gg/{codigo}"
                try:
                    invite = await self.client.fetch_invite(codigo)
                    nome = getattr(invite.guild, "name", None)
                    if nome:
                        alvo = f"**{nome}** — `{alvo}`"
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass
                v = Veredito(filtro="convite", motivo=inv.get("message") or "Convite de servidor",
                             severidade="alta", detalhe=alvo)
                v.acao = inv.get("action", "apagar")
                vereditos.append(v)

        lk = mod.get("links") or {}
        if lk.get("enabled") and lk.get("mode") != "desativado":
            v = checar_links(texto, lk)
            if v:
                v.acao = lk.get("action", "apagar")
                v.motivo = lk.get("message") or v.motivo
                vereditos.append(v)

        cp = mod.get("caps") or {}
        if cp.get("enabled"):
            v = checar_caps(texto, cp)
            if v:
                v.acao = cp.get("action", "apagar")
                v.motivo = cp.get("message") or v.motivo
                vereditos.append(v)

        zs = mod.get("zerospace") or {}
        if zs.get("enabled"):
            v = checar_zerospace(texto, zs)
            if v:
                v.acao = zs.get("action", "apagar")
                v.motivo = zs.get("message") or v.motivo
                vereditos.append(v)

        mn = mod.get("mentions") or {}
        if mn.get("enabled"):
            v = checar_mencoes(message, mn)
            if v:
                v.acao = mn.get("action", "apagar")
                v.motivo = mn.get("message") or v.motivo
                vereditos.append(v)

        fl = mod.get("flood") or {}
        if fl.get("enabled"):
            v = checar_flood(guild.id, message.author.id,
                             int(fl.get("window_seconds", 8)), int(fl.get("max_messages", 6)))
            if v:
                v.acao = fl.get("action", "apagar")
                v.motivo = fl.get("message") or v.motivo
                vereditos.append(v)

        dp = mod.get("duplicate") or {}
        if dp.get("enabled"):
            v = checar_duplicata(guild.id, message.author.id, texto,
                                 int(dp.get("window_seconds", 30)), int(dp.get("max_repeats", 3)))
            if v:
                v.acao = dp.get("action", "apagar")
                v.motivo = dp.get("message") or v.motivo
                vereditos.append(v)

        if not vereditos:
            return

        # O mais grave primeiro.
        peso = {"alta": 3, "media": 2, "baixa": 1}
        pior = sorted(vereditos, key=lambda v: peso.get(v.severidade, 0), reverse=True)[0]

        await self._aplicar(message, cfg, mod, pior, [v.filtro for v in vereditos],
                           texto[:400])

    # ---------------- aplicação da punição ----------------

    def _is_staff(self, message: discord.Message, cfg: Dict[str, Any]) -> bool:
        tk = cfg.get("tickets") or {}
        staff_ids = {tk.get("staff_role_id")}
        for c in (cfg.get("tickets") or {}).get("categories") or []:
            staff_ids.add(c.get("staff_role_id"))
        staff_ids.discard(None)
        if not staff_ids:
            return False
        return bool({r.id for r in message.author.roles}.intersection(staff_ids))

    async def _aplicar(self, message: discord.Message, cfg, mod, v: Veredito,
                       filtros: List[str], evidencia: str = ""):
        guild = message.guild
        member = message.author
        acao = v.acao or "nada"

        escal = mod.get("escalation") or {}
        total = mongo_db.contar_infracoes(guild.id, member.id)
        proxima = total + 1

        if escal.get("enabled") and acao in ("apagar", "avisar"):
            passo = self._passo_escalada(escal, proxima)
            if passo:
                acao = passo.get("action", acao)

        if acao == "nada" and not mod.get("log_channel_id"):
            return

        # Apagar (com aviso no chat se configurado)
        if acao == "avisar":
            try:
                await message.reply(
                    f"⚠️ {member.mention} — {v.motivo}",
                    delete_after=15,
                )
            except discord.Forbidden:
                pass
        elif acao == "apagar":
            try:
                await message.delete()
            except (discord.Forbidden, discord.HTTPException):
                pass

        punicao_aplicada = "nenhuma"
        if acao == "timeout":
            segundos = self._segundos_timeout(escal, proxima)
            try:
                await member.timeout(timedelta(seconds=segundos),
                                     reason=f"AURA: {v.motivo}")
                punicao_aplicada = f"timeout {segundos}s"
            except (discord.Forbidden, discord.HTTPException) as exc:
                runtime.log("AVISO", f"timeout falhou em {guild.name}: {exc}", "mod")
        elif acao == "banir":
            try:
                await member.ban(reason=f"AURA: {v.motivo}", delete_message_days=1)
                punicao_aplicada = "ban"
            except (discord.Forbidden, discord.HTTPException) as exc:
                runtime.log("AVISO", f"ban falhou em {guild.name}: {exc}", "mod")

        mongo_db.registrar_infracao(
            guild.id, member.id, str(member), guild.name,
            motivo=v.motivo, filtro=",".join(filtros), severidade=v.severidade,
            punicao=punicao_aplicada,
            evidencia=(evidencia or message.content or "")[:400],
            extras={"message_id": str(message.id), "channel_id": str(message.channel.id),
                    "acoes_no_vetor": acao, "total_acumulado": proxima},
        )

        if escal.get("dm_user") and acao in ("timeout", "banir", "avisar"):
            await self._dm(member, cfg, guild, v, acao, proxima)

        await self._log_punicao(guild, cfg, mod, member, v, acao, punicao_aplicada,
                                total, filtros)

        runtime.log(
            "AVISO",
            f"[{guild.name}] {member} · {v.filtro} · {acao} · {proxima}ª ocorrência",
            "mod",
        )

    @staticmethod
    def _passo_escalada(escal: Dict[str, Any], n: int) -> Optional[Dict[str, Any]]:
        escolhido = None
        for passo in escal.get("steps") or []:
            if n >= int(passo.get("after", 999)):
                escolhido = passo
            else:
                break
        return escolhido

    @staticmethod
    def _segundos_timeout(escal: Dict[str, Any], n: int) -> int:
        passo = Moderacao._passo_escalada(escal, n)
        if passo and passo.get("seconds"):
            return int(passo["seconds"])
        return 300

    async def _dm(self, member, cfg, guild, v: Veredito, acao: str, n: int):
        try:
            dm = await member.create_dm()
        except discord.Forbidden:
            return
        if acao == "timeout":
            texto = (f"🔇 Você foi silenciado automaticamente no servidor **{guild.name}** "
                     f"por {v.motivo}.\nDuração: {int(self._segundos_timeout(cfg['moderation']['escalation'], n)) // 60} min.")
        elif acao == "banir":
            texto = (f"🔨 Você foi banido de **{guild.name}** por {v.motivo}.\n"
                     f"Se achar enganoso, abra um ticket para recorrer.")
        else:
            texto = (f"⚠️ Sua mensagem no **{guild.name}** foi marcada por {v.motivo}\n"
                     f"Esta é a ocorrência nº {n}. Take cuidado para não ser punido.")
        try:
            await dm.send(texto[:1900])
        except discord.Forbidden:
            pass

    async def _log_punicao(self, guild, cfg, mod, member, v: Veredito,
                           acao: str, punicao: str, total: int,
                           filtros: Optional[List[str]] = None):
        canal_id = mod.get("punish_channel_id") or mod.get("log_channel_id")
        if not canal_id:
            return
        canal = guild.get_channel(int(canal_id))
        if canal is None or not hasattr(canal, "send"):
            return

        cores = {"apagar": discord.Color.orange(), "avisar": discord.Color.yellow(),
                 "timeout": discord.Color.red(), "banir": discord.Color.dark_red(),
                 "nada": discord.Color.greyple()}
        e = discord.Embed(
            title="🔨 Ação de moderação automática",
            color=cores.get(acao, discord.Color.greyple()),
        )
        e.add_field(name="Membro", value=f"{member.mention}\n`{member.id}`", inline=True)
        e.add_field(name="Filtros", value=", ".join(filtros or [v.filtro]), inline=True)
        e.add_field(name="Ocorrências", value=f"#{total + 1}", inline=True)
        e.add_field(name="Motivo", value=v.motivo[:1024], inline=False)
        if v.detalhe:
            e.add_field(name="Detalhe", value=str(v.detalhe)[:1024], inline=False)
        e.add_field(name="Punição", value=punicao or acao, inline=False)
        e.set_footer(text=f"AURA · {guild.name} · canal #{canal.id}")
        e.set_thumbnail(url=member.display_avatar.url)
        try:
            await canal.send(embed=e)
        except discord.Forbidden:
            pass

    # ======================================================================
    # Comandos manuais
    # ======================================================================

    async def _aviso_punicao(self, cfg, guild, mod_user, membro, texto, total):
        """Avisa o canal de punições sobre uma ação manual (timeout, aviso…)."""
        canal_id = (cfg.get("moderation", {}).get("punish_channel_id")
                    or cfg.get("moderation", {}).get("log_channel_id"))
        if not canal_id:
            return
        canal = guild.get_channel(int(canal_id))
        if canal is None:
            return
        e = discord.Embed(title="🔨 Moderação", color=discord.Color.red())
        e.add_field(name="Membro", value=membro.mention, inline=True)
        e.add_field(name="Moderador", value=mod_user.mention, inline=True)
        e.add_field(name="Motivo", value=str(texto)[:1000], inline=False)
        e.set_footer(text=f"Total de infrações: {total}")
        try:
            await canal.send(embed=e)
        except discord.Forbidden:
            pass

    mod = app_commands.Group(name="mod", description="Comandos de moderação do AURA.")

    async def _cfg_de(self, interaction) -> Optional[dict]:
        cfg = await st.get_config_cached(interaction.guild.id, guild_name=interaction.guild.name)
        if not st.module_enabled(cfg, "moderacao"):
            await interaction.response.send_message(
                "⚠️ O módulo de moderação está desligado neste servidor. "
                "Ative em **Painel → {0} → Moderação**.".format(interaction.guild.name),
                ephemeral=True,
            )
            return None
        return cfg

    @mod.command(name="status", description="Mostra como a moderação está configurada aqui.")
    @commands.guild_only()
    async def mod_status(self, interaction: discord.Interaction):
        cfg = await st.get_config_cached(interaction.guild.id, guild_name=interaction.guild.name)
        mod_cfg = cfg.get("moderation") or {}
        ativos = [
            nome for nome, chave in (
                ("Palavras proibidas", "words"), ("Links", "links"), ("Convites", "invites"),
                ("Caixa alta", "caps"), ("Flood", "flood"), ("Duplicadas", "duplicate"),
                ("Menções", "mentions"), ("Zerospace", "zerospace"),
            )
            if (mod_cfg.get(chave) or {}).get("enabled")
        ]
        termos = len((mod_cfg.get("words") or {}).get("terms") or [])
        pronto, motivo = st.moderation_ready(cfg)

        e = discord.Embed(title=f"🛡️ Moderação · {interaction.guild.name}",
                          color=discord.Color.green() if pronto else discord.Color.orange())
        e.add_field(
            name="Estado",
            value=("✅ Módulo ativo" if st.module_enabled(cfg, "moderacao") else "❌ Módulo desligado")
            + (" e com filtros prontos" if pronto else ""),
            inline=False,
        )
        e.add_field(name="Filtros ativos", value=", ".join(ativos) or "nenhum", inline=False)
        e.add_field(name="Termos bloqueados", value=str(termos), inline=True)
        e.add_field(
            name="Escalada",
            value="\n".join(
                f"• {s['after']}× → {s['action']}" for s in (mod_cfg.get("escalation") or {}).get("steps", [])
            ) or "desativada",
            inline=False,
        )
        e.add_field(
            name="Exceções",
            value=f"Cargos ignorados: {len(mod_cfg.get('ignored_roles') or [])} · "
                  f"Canais ignorados: {len(mod_cfg.get('ignored_channels') or [])}",
            inline=True,
        )
        e.set_footer(text="AURA · painel de configuração no servidor")
        await interaction.response.send_message(embed=e, ephemeral=True)

    @mod.command(name="avisar", description="[Staff] Dá um aviso formal a um membro (conta como infração).")
    @app_commands.describe(membro="Quem avisar", motivo="Por quê")
    @commands.has_permissions(kick_members=True)
    async def mod_warn(self, interaction: discord.Interaction, membro: discord.Member, motivo: str):
        cfg = await self._cfg_de(interaction)
        if cfg is None:
            return
        guild = interaction.guild
        total = mongo_db.contar_infracoes(guild.id, membro.id)
        mongo_db.registrar_infracao(
            guild.id, membro.id, str(membro), guild.name,
            motivo=motivo, filtro="aviso_manual", severidade="media", punicao="aviso",
            mod_id=str(interaction.user.id), mod_name=str(interaction.user),
        )
        embed = discord.Embed(
            title="⚠️ Aviso formal",
            description=motivo[:1024],
            color=discord.Color.yellow(),
        )
        embed.set_footer(text=f"{interaction.guild.name} · aviso nº {total + 1}")
        try:
            dm = await membro.create_dm()
            await dm.send(embed=embed)
            dm_ok = True
        except discord.Forbidden:
            dm_ok = False

        mod_canal = (cfg["moderation"].get("punish_channel_id")
                     or cfg["moderation"].get("log_channel_id"))
        if mod_canal:
            canal = guild.get_channel(int(mod_canal))
            if canal:
                log = discord.Embed(title="⚠️ Aviso aplicado", color=discord.Color.yellow())
                log.add_field(name="Membro", value=membro.mention, inline=True)
                log.add_field(name="Moderador", value=interaction.user.mention, inline=True)
                log.add_field(name="Motivo", value=motivo[:1000], inline=False)
                log.add_field(name="DM entregue", value="sim" if dm_ok else "não", inline=True)
                log.set_footer(text=f"Total acumulado: {total + 1}")
                try:
                    await canal.send(embed=log)
                except discord.Forbidden:
                    pass

        await interaction.response.send_message(
            f"⚠️ Aviso aplicado a {membro.mention} (acumulado: {total + 1})."
            + ("" if dm_ok else " — não consegui enviar a DM."),
            ephemeral=True,
        )

    @mod.command(name="silenciar", description="[Staff] Silencia um membro (timeout nativo do Discord).")
    @app_commands.describe(membro="Quem silenciar", minutos="Duração em minutos (máx. 40320)")
    @commands.has_permissions(moderate_members=True)
    async def mod_timeout(self, interaction: discord.Interaction, membro: discord.Member, minutos: int = 10):
        cfg = await self._cfg_de(interaction)
        if cfg is None:
            return
        segundos = max(60, min(40320 * 60, minutos * 60))
        guild = interaction.guild
        try:
            await membro.timeout(timedelta(seconds=segundos), reason=f"{interaction.user}: mod timeout")
        except discord.Forbidden:
            await interaction.response.send_message("❌ Sem permissão para silenciar esse membro.", ephemeral=True)
            return

        total = mongo_db.contar_infracoes(guild.id, membro.id)
        mongo_db.registrar_infracao(
            guild.id, membro.id, str(membro), guild.name,
            motivo=f"Timeout de {minutos} min", filtro="timeout_manual", severidade="alta",
            punicao=f"timeout {segundos}s", mod_id=str(interaction.user.id),
            mod_name=str(interaction.user),
        )
        mongo_db.registrar_modlog(
            guild.id, guild.name, "timeout", str(membro), str(membro.id),
            str(interaction.user.id), str(interaction.user), f"{minutos} minutos",
        )
        await self._aviso_punicao(cfg, guild, interaction.user, membro,
                                  f"🔇 Silenciado por {minutos} minutos.", total + 1)
        await interaction.response.send_message(
            f"🔇 {membro.mention} silenciado por {minutos} min.", ephemeral=True)

    @mod.command(name="remover-silencio", description="[Staff] Tira o silenciamento (timeout).")
    @app_commands.describe(membro="Quem liberar")
    @commands.has_permissions(moderate_members=True)
    async def mod_untimeout(self, interaction: discord.Interaction, membro: discord.Member):
        guild = interaction.guild
        try:
            await membro.timeout(None)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
            return
        mongo_db.registrar_modlog(
            guild.id, guild.name, "untimeout", str(membro), str(membro.id),
            str(interaction.user.id), str(interaction.user), "silêncio removido",
        )
        await interaction.response.send_message(f"✅ Silêncio de {membro.mention} removido.", ephemeral=True)

    @mod.command(name="limpar-infrações", description="[Staff] Zera o histórico de infrações de um membro.")
    @app_commands.describe(membro="Membro", confirmar="Digite SIM para confirmar")
    @commands.has_permissions(kick_members=True)
    async def mod_clear(self, interaction: discord.Interaction, membro: discord.Member,
                        confirmar: str = "SIM"):
        guild = interaction.guild
        if str(confirmar).strip().upper() not in ("SIM", "S", "YES", "CONFIRMAR"):
            await interaction.response.send_message(
                "Para confirmar, repita o comando com `confirmar: SIM`.", ephemeral=True)
            return
        n = mongo_db.apagar_infracoes(guild.id, membro.id)
        _track.pop((str(guild.id), str(membro.id)), None)
        _dup_track.pop((str(guild.id), str(membro.id)), None)
        mongo_db.registrar_modlog(
            guild.id, guild.name, "clear_infracoes", str(membro), str(membro.id),
            str(interaction.user.id), str(interaction.user), f"{n} registro(s) removidos",
        )
        await interaction.response.send_message(
            f"🧹 {n} infração(ões) removida(s) de {membro.mention}.", ephemeral=True)

    @mod.command(name="infrações", description="[Staff] Histórico de infrações de um membro.")
    @app_commands.describe(membro="Membro a consultar")
    @commands.has_permissions(kick_members=True)
    async def mod_hist(self, interaction: discord.Interaction, membro: discord.Member):
        hist = mongo_db.historico_infracoes(interaction.guild.id, str(membro.id), 15)
        total = mongo_db.contar_infracoes(interaction.guild.id, membro.id)
        if not hist:
            await interaction.response.send_message(
                f"✅ {membro.mention} não tem infrações registradas.", ephemeral=True)
            return
        linhas = []
        for h in hist:
            quando = f"<t:{int(h.get('ts', 0))}:R>"
            linhas.append(f"`{quando}` · **{h.get('filtro')}** → {h.get('punicao')}\n"
                          f"> {(h.get('motivo') or '')[:120]}")
        e = discord.Embed(
            title=f"📋 Infrações de {membro}",
            description=f"Total registrado: **{total}**\n\n" + "\n\n".join(linhas[:12])[:3800],
            color=discord.Color.red() if total >= 3 else discord.Color.orange(),
        )
        e.set_thumbnail(url=membro.display_avatar.url)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @mod.command(name="registro", description="[Staff] Últimas punições aplicadas no servidor.")
    @commands.has_permissions(kick_members=True)
    async def mod_log(self, interaction: discord.Interaction):
        guild = interaction.guild
        itens = mongo_db.listar_modlog(guild.id, limite=15)
        if not itens:
            await interaction.response.send_message("Nada registrado ainda.", ephemeral=True)
            return
        linhas = []
        for it in itens:
            ts = int(it.get("ts", 0))
            linhas.append(f"`{it.get('acao')}` · <t:{ts}:R> · "
                          f"**{it.get('alvo') or '—'}** → {(it.get('motivo') or '')[:90]}")
        e = discord.Embed(title=f"📜 Registro de moderação · {guild.name}",
                          description="\n".join(linhas), color=discord.Color.blurple())
        await interaction.response.send_message(embed=e, ephemeral=True)

    @mod.command(name="trancar", description="[Staff] Tranca um canal para @everyone.")
    @app_commands.describe(canal="Canal a trancar (padrão: este)")
    @commands.has_permissions(manage_channels=True)
    async def mod_lock(self, interaction: discord.Interaction, canal: discord.TextChannel = None):
        alvo = canal or interaction.channel
        if not isinstance(alvo, discord.TextChannel):
            await interaction.response.send_message("Esse canal não aceita bloqueio.", ephemeral=True)
            return
        await alvo.set_permissions(alvo.guild.default_role, send_messages=False,
                                  reason=f"{interaction.user} trancou o canal")
        mongo_db.registrar_modlog(
            interaction.guild.id, interaction.guild.name, "lock", alvo.name, str(alvo.id),
            str(interaction.user.id), str(interaction.user), "canal trancado",
        )
        await interaction.response.send_message(f"🔒 {alvo.mention} trancado.", ephemeral=True)

    @mod.command(name="destrancar", description="[Staff] Destrava um canal.")
    @app_commands.describe(canal="Canal a destrancar (padrão: este)")
    @commands.has_permissions(manage_channels=True)
    async def mod_unlock(self, interaction: discord.Interaction, canal: discord.TextChannel = None):
        alvo = canal or interaction.channel
        if not isinstance(alvo, discord.TextChannel):
            await interaction.response.send_message("Esse canal não aceita desbloqueio.", ephemeral=True)
            return
        await alvo.set_permissions(alvo.guild.default_role, send_messages=None,
                                  reason=f"{interaction.user} destrancou o canal")
        mongo_db.registrar_modlog(
            interaction.guild.id, interaction.guild.name, "unlock", alvo.name, str(alvo.id),
            str(interaction.user.id), str(interaction.user), "canal destrancado",
        )
        await interaction.response.send_message(f"🔓 {alvo.mention} destrancado.", ephemeral=True)

    @mod.command(name="simular", description="Testa os filtros sem punir de verdade.")
    @app_commands.describe(texto="Mensagem para testar")
    async def mod_test(self, interaction: discord.Interaction, texto: str):
        cfg = await st.get_config_cached(interaction.guild.id, guild_name=interaction.guild.name)
        mod_cfg = cfg.get("moderation") or {}
        achados = []

        if (mod_cfg.get("words") or {}).get("enabled"):
            v = checar_palavras(texto, cfg)
            if v:
                achados.append(f"🔴 **{v.filtro}** — {v.motivo} → {v.acao}")
        if (mod_cfg.get("invites") or {}).get("enabled") and RE_INVITE.search(texto):
            achados.append("🔴 **convite** — convite de Discord detectado")
        if (mod_cfg.get("links") or {}).get("enabled") and (mod_cfg["links"].get("mode") != "desativado"):
            v = checar_links(texto, mod_cfg["links"])
            if v:
                achados.append(f"🔴 **{v.filtro}** — {v.motivo} → {v.acao}")
        if (mod_cfg.get("caps") or {}).get("enabled"):
            v = checar_caps(texto, mod_cfg["caps"])
            if v:
                achados.append(f"🟠 **caps** — {v.motivo}")
        if (mod_cfg.get("zerospace") or {}).get("enabled"):
            v = checar_zerospace(texto, mod_cfg["zerospace"])
            if v:
                achados.append(f"🟠 **zerospace** — {v.motivo}")

        e = discord.Embed(
            title="🧪 Simulação de moderação",
            description=(f"Mensagem testada:\n>>> {texto[:500]}\n\n"
                        + ("\n".join(achados) if achados
                           else "✅ Nenhum filtro dispararia nesta mensagem.")),
            color=discord.Color.red() if achados else discord.Color.green(),
        )
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="modconfig", description="Resumo da moderação deste servidor.")
    @commands.guild_only()
    async def modconfig(self, interaction: discord.Interaction):
        await self.mod_status.callback(self, interaction)


class ConfigModView(discord.ui.View):
    """
    Painel rápido de configuração da moderação dentro do Discord.

    Registrada com `add_view`, então precisa ser persistente: todo item tem
    `custom_id` e a view não tem timeout. Sem isso o `add_view` levanta
    ValueError e o cog inteiro não carrega.
    """

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Meu painel", style=discord.ButtonStyle.primary, emoji="⚙️",
        custom_id="aura:mod:painel",
    )
    async def painel(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = await st.get_config_cached(interaction.guild.id, guild_name=interaction.guild.name)
        mod_cfg = cfg.get("moderation") or {}
        e = discord.Embed(
            title=f"🛡️ Moderação · {interaction.guild.name}",
            description="A configuração completa é feita no painel web do AURA.",
            color=discord.Color.blurple(),
        )
        e.add_field(name="Estado", value="ativa" if st.module_enabled(cfg, "moderacao") else "desligada")
        e.add_field(name="Termos bloqueados",
                    value=str(len((mod_cfg.get("words") or {}).get("terms") or [])))
        e.add_field(name="Canais ignorados", value=str(len(mod_cfg.get("ignored_channels") or [])))
        e.add_field(name="Cargos ignorados", value=str(len(mod_cfg.get("ignored_roles") or [])))
        await interaction.response.send_message(embed=e, ephemeral=True)


async def setup(client: commands.Bot) -> None:
    await client.add_cog(Moderacao(client))
