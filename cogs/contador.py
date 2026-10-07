"""
AURA · Contador de membros
--------------------------
Renomeia o canal configurado no painel com a contagem de membros do servidor,
usando o modelo `channel_name` (ex.: `👥 Membros: {count}`).

Antes o módulo só existia no painel: a config era salva e nada atualizava o canal.
"""

from __future__ import annotations

import asyncio
from typing import Dict, Optional

import discord
from discord.ext import commands, tasks

from core import runtime
from core import settings as st
from core.placeholders import render


class Contador(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client
        self._locks: Dict[int, asyncio.Lock] = {}

    async def cog_unload(self):
        if self.atualizar.is_running():
            self.atualizar.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        runtime.log("INFO", "Contador carregado (config por servidor)", "contador")
        if not self.atualizar.is_running():
            self.atualizar.start()

    def _lock(self, guild_id: int) -> asyncio.Lock:
        return self._locks.setdefault(guild_id, asyncio.Lock())

    async def _atualizar_guild(self, guild: discord.Guild) -> None:
        async with self._lock(guild.id):
            try:
                cfg = await st.get_config_cached(guild.id, guild_name=guild.name)
            except Exception as exc:
                runtime.log("ERRO", f"contador: config: {exc}", "contador")
                return

            if not st.module_enabled(cfg, "contador"):
                return
            ct = cfg.get("contador") or {}
            if not ct.get("enabled") or not ct.get("channel_id"):
                return

            canal = guild.get_channel(int(ct["channel_id"]))
            if not isinstance(canal, discord.VoiceChannel):
                return

            nome = render(ct.get("channel_name") or "👥 Membros: {count}",
                          guild=guild, extra={"count": guild.member_count})
            nome = nome[:100]
            if nome and nome != canal.name:
                try:
                    await canal.edit(name=nome, reason="AURA contador de membros")
                except (discord.Forbidden, discord.HTTPException) as exc:
                    runtime.log("AVISO", f"contador: não consegui renomear em {guild.name}: {exc}",
                                "contador")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await asyncio.sleep(3)
        await self._atualizar_guild(member.guild)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        await asyncio.sleep(3)
        await self._atualizar_guild(member.guild)

    @tasks.loop(minutes=5)
    async def atualizar(self):
        await self.client.wait_until_ready()
        for guild in self.client.guilds:
            try:
                await self._atualizar_guild(guild)
            except Exception as exc:
                runtime.log("ERRO", f"contador falhou em {guild.name}: {exc}", "contador")

    @atualizar.before_loop
    async def _antes(self):
        await self.client.wait_until_ready()
        await asyncio.sleep(30)


async def setup(client: commands.Bot) -> None:
    await client.add_cog(Contador(client))
