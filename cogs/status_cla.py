"""
AURA · Status do clã
-------------------
Renomeia os canais de voz de status do clã com os dados do Clash of Clans,
configurados POR SERVIDOR no painel web.

    /status-cla configurar   escolhe a categoria e os canais
    /status-cla forcar       atualiza agora
    /status-cla ver          mostra o que está configurado

Cada canal é mapeado pelo emoji do nome. Aceita os mesmos emojis de sempre,
mas qualquer um pode ser configurado pelo painel.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands, tasks

from core import runtime
from core import settings as st

COC_EMAIL = os.getenv("COC_EMAIL")
COC_PASSWORD = os.getenv("COC_PASSWORD")

#: Emoji do canal -> chave do dado que ele mostra. É o mesmo mapeamento da B.A.D,
#: para os canais já existentes continuarem sendo reconhecidos sem reconfigurar.
EMOJIS_PADRAO = {
    "👥": "membros",
    "⭐": "nivel",
    "🏆": "trofeus",
    "⚔️": "guerras",
    "🔥": "streak",
    "🕒": "data",
}

#: Chaves antigas/alternativas do painel -> chave canônica da B.A.D.
_ALIAS = {
    "estrelas": "nivel",
    "nivel": "nivel",
    "vitorias_guerra": "guerras",
    "guerras": "guerras",
    "tempo": "data",
    "data": "data",
    "membros": "membros",
    "trofeus": "trofeus",
    "streak": "streak",
}


def _saudavel(resultado: Optional[str]) -> bool:
    """
    Diz se o resultado do update é "tudo certo" — inclusive quando nada mudou.

    "nada mudou" é sucesso (os canais já estavam certos); só "sem tag",
    "sem canais", "sem credenciais" e erro de API contam como problema.
    """
    if not resultado:
        return False
    return not resultado.startswith(("sem ", "API do Clash"))


def _fuso_brasilia():
    """America/Sao_Paulo quando houver tzdata; senão UTC-3 (o Brasil não tem mais horário de verão)."""
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("America/Sao_Paulo")
    except Exception:
        return timezone(timedelta(hours=-3))


_FUSO = _fuso_brasilia()

_client = None


async def _coc():
    global _client
    if _client is not None:
        return _client
    if not (COC_EMAIL and COC_PASSWORD):
        return None
    try:
        from coc import Client as CocClient
    except ImportError:
        return None
    _client = CocClient(email=COC_EMAIL, password=COC_PASSWORD)
    try:
        await _client.login()
    except Exception as exc:
        runtime.log("ERRO", f"StatusCla: login falhou: {exc}", "clash")
        _client = None
    return _client


async def _fechar():
    global _client
    if _client is not None:
        try:
            await _client.logout()
        except Exception:
            pass
        _client = None


def _numeros(clan: Any) -> Dict[str, str]:
    """
    Monta o nome final de cada canal de status, exatamente no formato da B.A.D.

    A API do `coc` expõe `member_count`, `level`, `points` e `war_win_streak` —
    antes o código lia `members`/`stars`/`trophies`/`war_streak`, que não existem
    nesses objetos, e por isso os canais ficavam em "?".
    """
    def get(*nomes, padrao=None):
        for n in nomes:
            v = getattr(clan, n, None)
            if v is not None:
                return v
        return padrao

    horario = datetime.now(_FUSO).strftime("%d/%m %H:%M")
    membros = get("member_count", "members", padrao="?")
    return {
        "membros": f"👥 Membros: {membros}/50",
        "nivel": f"⭐ Nível: {get('level', 'nivel', padrao='?')}",
        "trofeus": f"🏆 Troféus: {get('points', 'trophies', padrao='?')}",
        "guerras": f"⚔️ Guerras Ganhas: {get('war_wins', padrao='?')}",
        "streak": f"🔥 Win Streak: {get('war_win_streak', 'war_streak', padrao='?')}",
        "data": f"🕒 Atualizado: {horario}",
    }


class StatusCla(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client
        #: motivo ja avisado por servidor, para nao repetir o mesmo AVISO.
        self._avisado: Dict[int, Optional[str]] = {}

    async def cog_unload(self):
        await _fechar()
        if self.update_status.is_running():
            self.update_status.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        if not (COC_EMAIL and COC_PASSWORD):
            runtime.log("AVISO", "StatusCla: sem credenciais, inativo", "clash")
            return
        if not self.update_status.is_running():
            self.update_status.start()

    # ------------------------------------------------------------------

    @staticmethod
    def _achar_categoria(guild: discord.Guild, categoria_id: Any = None) -> Optional[discord.CategoryChannel]:
        """Categoria de status: a configurada, ou a que tem "status" + "clã" no nome (como a B.A.D)."""
        if categoria_id:
            cat = guild.get_channel(int(categoria_id)) if str(categoria_id).isdigit() else None
            if isinstance(cat, discord.CategoryChannel):
                return cat
        for cat in guild.categories:
            nome = cat.name.lower()
            if "status" in nome and ("clã" in nome or "cla" in nome):
                return cat
        for cat in guild.categories:
            if "status" in cat.name.lower():
                return cat
        return None

    @classmethod
    def _achar_canais(cls, guild: discord.Guild, categoria_id: Any = None) -> Dict[str, discord.VoiceChannel]:
        """Mapeia os canais da categoria de status por emoji (como a B.A.D).

        Sem categoria reconhecida, não devolve nada — não saímos renomeando
        canais de voz aleatórios do servidor.
        """
        categoria = cls._achar_categoria(guild, categoria_id)
        if categoria is None:
            return {}
        canais = categoria.voice_channels

        mapa: Dict[str, discord.VoiceChannel] = {}
        for ch in canais:
            nome = ch.name or ""
            for emoji, chave in EMOJIS_PADRAO.items():
                if chave in mapa:
                    continue
                if emoji in nome:
                    mapa[chave] = ch
                    break

        if len(mapa) < 3:
            # Sem emojis: tenta achar ao menos o contador de membros pelo nome.
            for ch in canais:
                nome = (ch.name or "").lower()
                if "membros" not in mapa and ("membros" in nome or "member" in nome
                                              or "people" in nome):
                    mapa["membros"] = ch
        return mapa

    async def _atualizar_um(self, guild: discord.Guild, cfg: Dict[str, Any]) -> Optional[str]:
        games = cfg.get("games") or {}
        if not st.module_enabled(cfg, "games") or not games.get("coc", {}).get("enabled"):
            return None
        coc = games["coc"]
        tag = coc.get("clan_tag")
        if not tag:
            return "sem tag de clã"

        canais_ids = coc.get("status_channel_ids") or {}

        # 1) Mapeamento explícito do painel (aceita as chaves antigas via _ALIAS).
        mapa: Dict[str, discord.VoiceChannel] = {}
        for chave, canal_id in canais_ids.items():
            canonica = _ALIAS.get(str(chave))
            if not canonica or canonica in mapa:
                continue
            cid = int(canal_id) if str(canal_id).isdigit() else None
            canal = guild.get_channel(cid) if cid else None
            if isinstance(canal, discord.VoiceChannel):
                mapa[canonica] = canal

        # 2) Sem mapeamento suficiente, descobre a categoria sozinho — o que a
        #    B.A.D fazia. Assim funciona mesmo sem ninguém preencher o painel.
        if len(mapa) < 3:
            for chave, canal in self._achar_canais(guild, canais_ids.get("categoria_id")).items():
                mapa.setdefault(chave, canal)

        if not mapa:
            return "sem canais de status mapeados"

        api = await _coc()
        if api is None:
            return "sem credenciais da API do .env"

        try:
            clan = await api.get_clan(tag)
        except Exception as exc:
            return f"API do Clash: {exc}"

        dados = _numeros(clan)
        atualizados = 0
        for chave, canal in mapa.items():
            novo = dados.get(chave)
            if novo and canal.name != novo and len(novo) <= 100:
                try:
                    await canal.edit(name=novo, reason=f"AURA status {tag}")
                    atualizados += 1
                    await asyncio.sleep(1.5)  # evita rate limit, como na B.A.D
                except discord.Forbidden:
                    pass
                except discord.HTTPException:
                    pass

        try:
            import mongo_db
            mongo_db.registrar_auditoria(
                guild.id, guild.name, "status_cla_atualizado", "games", None,
                f"{atualizados} canais de {tag}")
        except Exception:
            pass

        return f"{atualizados} canal(is) atualizado(s)" if atualizados else \
            "nada mudou (os canais já estavam certos)"

    @tasks.loop(minutes=10)
    async def update_status(self):
        await self.client.wait_until_ready()
        for guild in self.client.guilds:
            try:
                cfg = await st.get_config_cached(guild.id, guild_name=guild.name)
                resultado = await self._atualizar_um(guild, cfg)
                self._avisar(guild, resultado)
            except Exception as exc:
                runtime.log("ERRO", f"StatusCla falhou em {guild.name}: {exc}", "clash")

    def _avisar(self, guild: discord.Guild, resultado: Optional[str]) -> None:
        """
        Fala uma vez por motivo.

        Sem isso o módulo desligado era 100% silencioso — `_atualizar_um`
        devolve None e o log era pulado — então "parou de atualizar" não deixava
        rastro nenhum. Repete só quando o motivo muda, para o loop de 10
        minutos não virar spam.
        """
        if _saudavel(resultado):
            self._avisado.pop(guild.id, None)
            return
        if self._avisado.get(guild.id) == resultado:
            return
        self._avisado[guild.id] = resultado
        runtime.log("AVISO", f"StatusCla parado em {guild.name}: "
                             f"{resultado or 'módulo desligado'}", "clash")

    @update_status.before_loop
    async def _antes(self):
        await self.client.wait_until_ready()
        await asyncio.sleep(45)

    # ------------------------------------------------------------------
    # Comandos
    # ------------------------------------------------------------------

    grupo = app_commands.Group(name="status-cla", description="Status do clã (canais de voz).", guild_only=True)

    @grupo.command(name="forcar", description="Atualiza os canais de status agora.")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_channels=True)
    async def forcar(self, interaction: discord.Interaction):
        guild = interaction.guild
        await interaction.response.defer(ephemeral=True)
        cfg = await st.get_config_cached(guild.id, guild_name=guild.name)
        resultado = await self._atualizar_um(guild, cfg)
        emoji = "✅" if _saudavel(resultado) else "⚠️"
        await interaction.followup.send(
            f"{emoji} {resultado or 'módulo desligado aqui'}", ephemeral=True)

    @grupo.command(name="ver", description="Mostra o mapeamento de canais de status.")
    @app_commands.guild_only()
    async def ver(self, interaction: discord.Interaction):
        guild = interaction.guild
        cfg = await st.get_config_cached(guild.id, guild_name=guild.name)
        coc = (cfg.get("games") or {}).get("coc") or {}
        canais = coc.get("status_channel_ids") or {}

        e = discord.Embed(title=f"🕒 Status do clã · {guild.name}",
                          color=discord.Color.blurple())
        e.add_field(name="Clã", value=f"`{coc.get('clan_tag') or '—'}`", inline=True)
        e.add_field(name="Ativo", value="sim" if coc.get("enabled") else "não", inline=True)
        e.add_field(name="Credenciais", value="ok" if (COC_EMAIL and COC_PASSWORD)
                    else "faltando no .env", inline=True)
        linhas = []
        for chave, canal_id in canais.items():
            if chave == "categoria_id":
                continue
            canal = guild.get_channel(int(canal_id)) if str(canal_id).isdigit() else None
            linhas.append(f"**{chave}** → {canal.mention if canal else '`canal ausente`'}")
        e.add_field(name="Canais mapeados", value="\n".join(linhas) or "—", inline=False)
        e.set_footer(text="Ajuste o mapeamento no painel web → Jogos")
        await interaction.response.send_message(embed=e, ephemeral=True)

    @grupo.command(name="auto-detectar",
                   description="Detecta canais por emoji e grava o mapeamento.")
    @app_commands.describe(aplicar="Grava o mapeamento detectado (padrão: só mostra)")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_channels=True)
    async def auto_detectar(self, interaction: discord.Interaction,
                            aplicar: bool = False):
        guild = interaction.guild
        cfg = await st.get_config_cached(guild.id, guild_name=guild.name)
        coc = dict(((cfg.get("games") or {}).get("coc") or {}))
        canais = dict(coc.get("status_channel_ids") or {})
        achados = self._achar_canais(guild, canais.get("categoria_id"))

        if not achados:
            return await interaction.response.send_message(
                "Não encontrei canais de status por emoji. Configure manualmente no painel.",
                ephemeral=True)

        if aplicar:
            # Grava no Mongo + atualiza canais (login na API do Coc + sleep por
            # canal) pode passar dos 3s — deferir antes evita "o aplicativo não
            # respondeu".
            await interaction.response.defer(ephemeral=True)
            for chave, ch in achados.items():
                canais[chave] = ch.id
            coc["status_channel_ids"] = canais
            if "coc" not in cfg.get("games", {}):
                cfg.setdefault("games", {})["coc"] = coc
            else:
                cfg["games"]["coc"] = coc
            import mongo_db

            if not mongo_db.upsert_guild_config(guild.id, cfg, updated_by="status-cla"):
                return await interaction.followup.send(
                    "❌ Não consegui gravar no banco. Confira a conexão do Mongo.",
                    ephemeral=True)
            st.invalidate(str(guild.id))
            resultado = await self._atualizar_um(guild, cfg)
            linhas = "\n".join(f"`{k}` → {c.id} ({c.name})"
                               for k, c in achados.items())
            return await interaction.followup.send(
                f"✅ Mapeamento gravado ({len(achados)} canais).\n{linhas}\n\n"
                f"Status do Clã: {resultado or 'módulo desligado aqui'}",
                ephemeral=True)

        linhas = [f"`{chave}` → {ch.id} ({ch.name})" for chave, ch in achados.items()]
        await interaction.response.send_message(
            "Encontrei estes canais. Copie o mapeamento para o painel "
            "(Jogos → Canais de status):\n```\n" + "\n".join(linhas) + "\n```\n"
            "Ou rode de novo com `aplicar:sim` que eu gravo por você.",
            ephemeral=True)


async def setup(client: commands.Bot) -> None:
    await client.add_cog(StatusCla(client))
