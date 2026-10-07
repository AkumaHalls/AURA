"""
AURA · Boas-vindas
------------------
Manda a mensagem de boas-vindas na entrada e a de despedida na saída do membro,
além da DM opcional e do log. Tudo configurado POR SERVIDOR no painel.

Antes este módulo só existia no painel: salvava a config no Mongo e nada
executava. Este cog é quem faz a config acontecer.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import discord
from discord.ext import commands

from core import runtime
from core import settings as st
from core.placeholders import render


async def _carregar(guild: discord.Guild) -> Optional[Dict[str, Any]]:
    try:
        return await st.get_config_cached(guild.id, guild_name=guild.name)
    except Exception as exc:
        runtime.log("ERRO", f"boas_vindas: config: {exc}", "boas_vindas")
        return None


def _ativo(cfg: Dict[str, Any]) -> bool:
    return bool(st.module_enabled(cfg, "boas_vindas") and (cfg.get("boas_vindas") or {}).get("enabled"))


async def _enviar(canal, texto: str) -> None:
    if not texto:
        return
    try:
        await canal.send(texto[:2000])
    except (discord.Forbidden, discord.HTTPException) as exc:
        runtime.log("AVISO", f"boas_vindas: não consegui enviar em #{getattr(canal, 'name', '?')}: {exc}",
                    "boas_vindas")


async def _logar(guild: discord.Guild, canal_id: Any, texto: str) -> None:
    if not canal_id or not texto:
        return
    canal = guild.get_channel(int(canal_id)) if str(canal_id).isdigit() else None
    if isinstance(canal, discord.TextChannel):
        await _enviar(canal, texto)


class BoasVindas(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self):
        runtime.log("INFO", "Boas-vindas carregado (config por servidor)", "boas_vindas")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        guild = member.guild
        cfg = await _carregar(guild)
        if cfg is None or not _ativo(cfg):
            return

        bv = cfg["boas_vindas"]
        canal = guild.get_channel(bv.get("channel_id")) if bv.get("channel_id") else None
        if isinstance(canal, discord.TextChannel):
            await _enviar(canal, render(
                bv.get("message") or "", user=member, member=member,
                guild=guild, channel=canal))

        if bv.get("send_dm"):
            dm = render(bv.get("dm_message") or "", user=member, member=member, guild=guild)
            if dm:
                try:
                    await member.send(dm[:2000])
                except (discord.Forbidden, discord.HTTPException):
                    pass

        await _logar(guild, bv.get("log_channel_id"),
                     f"📥 {member.mention} entrou. Agora somos "
                     f"{guild.member_count} membros.")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.bot:
            return
        guild = member.guild
        cfg = await _carregar(guild)
        if cfg is None or not _ativo(cfg):
            return

        bv = cfg["boas_vindas"]
        canal = guild.get_channel(bv.get("channel_id")) if bv.get("channel_id") else None
        if isinstance(canal, discord.TextChannel):
            await _enviar(canal, render(
                bv.get("leave_message") or "", user=member, member=member,
                guild=guild, channel=canal))

        await _logar(guild, bv.get("log_channel_id"),
                     f"📤 {member} saiu. Agora somos {guild.member_count} membros.")


async def setup(client: commands.Bot) -> None:
    await client.add_cog(BoasVindas(client))
