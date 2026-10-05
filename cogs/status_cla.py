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
from typing import Any, Dict, List, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands, tasks

from core import runtime
from core import settings as st

COC_EMAIL = os.getenv("COC_EMAIL")
COC_PASSWORD = os.getenv("COC_PASSWORD")

#: Emoji do canal -> chave do dado que ele mostra.
EMOJIS_PADRAO = {
    "👥": "membros",
    "⭐": "estrelas",
    "🏆": "trofeus",
    "⚔️": "vitorias_guerra",
    "🔥": "streak",
    "🕒": "tempo",
}

_client = None


async def _coc():
    global _client
    if _client is not None:
        return _client
    if not (COC_EMAIL and COOC_PASSWORD):
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
    """Extrai os números do clã, tolerando campos ausentes na API."""
    def get(*nomes, padrao="?"):
        for n in nomes:
            v = getattr(clan, n, None)
            if v is not None:
                return v
        return padrao

    return {
        "membros": str(get("members", "member_count", padrao=0)),
        "estrelas": str(get("stars")),
        "trofeus": str(get("trophies")),
        "vitorias_guerra": str(get("war_wins")),
        "streak": str(get("war_streak")),
        "tempo": str(get("last_join_date", "last_seen", padrao="—")),
    }


class StatusCla(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client

    async def cog_unload(self):
        await _fechar()
        if self.update_status.is_running():
            self.update_status.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        if not (COC_EMAIL and COOC_PASSWORD):
            runtime.log("AVISO", "StatusCla: sem credenciais, inativo", "clash")
            return
        if not self.update_status.is_running():
            self.update_status.start()

    # ------------------------------------------------------------------

    @staticmethod
    def _achar_canais(guild: discord.Guild, categoria_id: int) -> Dict[str, discord.VoiceChannel]:
        """Mapeia os canais da categoria por emoji, com fallback por nome."""
        categoria = guild.get_channel(categoria_id) if categoria_id else None
        canais = categoria.voice_channels if categoria is not None else \
            [c for c in guild.voice_channels]

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
            # Sem emojis: tenta achar por palavra no nome.
            for ch in canais:
                nome = (ch.name or "").lower()
                for chave in ("membros", "member", "people"):
                    if chave in nome and "membros" not in mapa:
                        mapa["membros"] = ch
                for chave in ("estrela", "star"):
                    if chave in nome and "estrelas" not in mapa:
                        mapa["estrelas"] = ch
                for chave in ("trofeu", "troph"):
                    if chave in nome and "trofeus" not in mapa:
                        mapa["trofeus"] = ch
        return mapa

    async def _atualizar_um(self, guild: discord.Guild, cfg: Dict[str, Any]) -> Optional[str]:
        games = cfg.get("games") or {}
        if not games.get("coc", {}).get("enabled"):
            return None
        coc = games["coc"]
        tag = coc.get("clan_tag")
        if not tag:
            return "sem tag de clã"

        canais = coc.get("status_channel_ids") or {}
        if not canais:
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
        for chave, canal_id in canais.items():
            canal = guild.get_channel(canal_id)
            if canal is None or not isinstance(canal, discord.VoiceChannel):
                continue
            valor = dados.get(chave, "?")
            nome_novo = canal.name.split(" ", 1)[-1] if " " in canal.name else canal.name
            # Preserva o emoji/nome original e troca só o valor.
            partes = (canal.name or "").split(" ")
            prefixo = partes[0] if len(partes) > 1 else chave
            novo = f"{prefixo} {valor}"
            if novo != canal.name and len(novo) <= 100:
                try:
                    await canal.edit(name=novo, reason=f"AURA status {tag}")
                    atualizados += 1
                except discord.Forbidden:
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
                if resultado and "atualizado" not in resultado:
                    runtime.log("AVISO", f"StatusCla em {guild.name}: {resultado}", "clash")
            except Exception as exc:
                runtime.log("ERRO", f"StatusCla falhou em {guild.name}: {exc}", "clash")

    @update_status.before_loop
    async def _antes(self):
        await self.client.wait_until_ready()
        await asyncio.sleep(45)

    # ------------------------------------------------------------------
    # Comandos
    # ------------------------------------------------------------------

    grupo = app_commands.Group(name="status-cla", description="Status do clã (canais de voz).")

    @grupo.command(name="forcar", description="Atualiza os canais de status agora.")
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    async def forcar(self, interaction: discord.Interaction):
        guild = interaction.guild
        cfg = await st.get_config_cached(guild.id, guild_name=guild.name)
        await interaction.response.defer(ephemeral=True)
        resultado = await self._atualizar_um(guild, cfg)
        await interaction.followup.send(
            f"✅ {resultado}" if resultado and "atualizado" in resultado
            else f"⚠️ {resultado or 'módulo desligado aqui'}", ephemeral=True)

    @grupo.command(name="ver", description="Mostra o mapeamento de canais de status.")
    @commands.guild_only()
    async def ver(self, interaction: discord.Interaction):
        guild = interaction.guild
        cfg = await st.get_config_cached(guild.id, guild_name=guild.name)
        coc = (cfg.get("games") or {}).get("coc") or {}
        canais = coc.get("status_channel_ids") or {}

        e = discord.Embed(title=f"🕒 Status do clã · {guild.name}",
                          color=discord.Color.blurple())
        e.add_field(name="Clã", value=f"`{coc.get('clan_tag') or '—'}`", inline=True)
        e.add_field(name="Ativo", value="sim" if coc.get("enabled") else "não", inline=True)
        e.add_field(name="Credenciais", value="ok" if (COC_EMAIL and COOC_PASSWORD)
                    else "faltando no .env", inline=True)
        linhas = []
        for chave, canal_id in canais.items():
            canal = guild.get_channel(canal_id)
            linhas.append(f"**{chave}** → {canal.mention if canal else '`canal ausente`'}")
        e.add_field(name="Canais mapeados", value="\n".join(linhas) or "—", inline=False)
        e.set_footer(text="Ajuste o mapeamento no painel web → Jogos")
        await interaction.response.send_message(embed=e, ephemeral=True)

    @grupo.command(name="auto-detectar", description="Detecta canais por emoji e sugere o mapeamento.")
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    async def auto_detectar(self, interaction: discord.Interaction):
        guild = interaction.guild
        cfg = await st.get_config_cached(guild.id, guild_name=guild.name)
        coc = (cfg.get("games") or {}).get("coc") or {}
        canais = coc.get("status_channel_ids") or {}
        achados = self._achar_canais(guild, canais.get("categoria_id"))

        if not achados:
            return await interaction.response.send_message(
                "Não encontrei canais de status por emoji. Configure manualmente no painel.",
                ephemeral=True)

        linhas = [f"`{chave}` → {ch.id} ({ch.name})" for chave, ch in achados.items()]
        await interaction.response.send_message(
            "Encontrei estes canais. Copie o mapeamento para o painel "
            "(Jogos → Canais de status):\n```\n" + "\n".join(linhas) + "\n```",
            ephemeral=True)


async def setup(client: commands.Bot) -> None:
    await client.add_cog(StatusCla(client))