"""
AURA · Registro de atividade (Logs)
-----------------------------------
Envia para os canais configurados no painel os eventos do servidor: entradas,
saídas, mensagens apagadas, boosts e mudança de cargos.

Antes o módulo só existia no painel (config salva, nada executava). Cada evento
respeita o canal e o interruptor (`log_join`, `log_leave`, ...) do servidor.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import discord
from discord.ext import commands

from core import runtime
from core import settings as st

#: chave do evento -> (campo de canal, interruptor)
_ROTAS = {
    "join": ("join_channel_id", "log_join"),
    "leave": ("leave_channel_id", "log_leave"),
    "message_delete": ("message_channel_id", "log_message_delete"),
    "boost": ("boost_channel_id", "log_boost"),
    "role_change": ("mod_channel_id", "log_role_change"),
}


async def _carregar(guild: discord.Guild) -> Optional[Dict[str, Any]]:
    try:
        return await st.get_config_cached(guild.id, guild_name=guild.name)
    except Exception as exc:
        runtime.log("ERRO", f"registros: config: {exc}", "logs")
        return None


def _canal_do_evento(guild: discord.Guild, lg: Dict[str, Any], evento: str):
    campo, interruptor = _ROTAS[evento]
    if not lg.get(interruptor):
        return None
    canal_id = lg.get(campo)
    if not canal_id:
        return None
    canal = guild.get_channel(int(canal_id)) if str(canal_id).isdigit() else None
    return canal if isinstance(canal, discord.TextChannel) else None


async def _enviar(canal: discord.TextChannel, embed: discord.Embed) -> None:
    try:
        await canal.send(embed=embed)
    except (discord.Forbidden, discord.HTTPException) as exc:
        runtime.log("AVISO", f"registros: não consegui registrar em #{canal.name}: {exc}",
                    "logs")


class Registros(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self):
        runtime.log("INFO", "Registro de atividade carregado (config por servidor)", "logs")

    async def _lg(self, guild: discord.Guild) -> Optional[Dict[str, Any]]:
        cfg = await _carregar(guild)
        if cfg is None or not st.module_enabled(cfg, "logs"):
            return None
        lg = cfg.get("logs") or {}
        return lg if lg.get("enabled") else None

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        lg = await self._lg(member.guild)
        if not lg:
            return
        canal = _canal_do_evento(member.guild, lg, "join")
        if canal:
            e = discord.Embed(title="📥 Membro entrou", color=discord.Color.green(),
                              timestamp=discord.utils.utcnow())
            e.set_thumbnail(url=getattr(member.display_avatar, "url", None))
            e.add_field(name="Membro", value=f"{member.mention} (`{member.id}`)", inline=False)
            e.add_field(name="Conta criada", value=discord.utils.format_dt(member.created_at, "R"),
                        inline=True)
            e.set_footer(text=f"{member.guild.member_count} membros agora")
            await _enviar(canal, e)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.bot:
            return
        lg = await self._lg(member.guild)
        if not lg:
            return
        canal = _canal_do_evento(member.guild, lg, "leave")
        if canal:
            e = discord.Embed(title="📤 Membro saiu", color=discord.Color.red(),
                              timestamp=discord.utils.utcnow())
            e.set_thumbnail(url=getattr(member.display_avatar, "url", None))
            e.add_field(name="Membro", value=f"`{member}` (`{member.id}`)", inline=False)
            e.add_field(name="Entrou em", value=(discord.utils.format_dt(member.joined_at, "R")
                                                 if member.joined_at else "—"), inline=True)
            e.set_footer(text=f"{member.guild.member_count} membros agora")
            await _enviar(canal, e)

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        # O evento `on_message_delete` só dispara para mensagens no cache — na
        # prática, quase nada. O `raw` cobre todo mundo; o conteúdo só existe
        # quando a mensagem ainda estava no cache.
        if payload.guild_id is None:
            return
        guild = self.client.get_guild(payload.guild_id)
        if guild is None:
            return
        lg = await self._lg(guild)
        if not lg:
            return
        canal = _canal_do_evento(guild, lg, "message_delete")
        if not canal:
            return

        original = payload.cached_message
        if original is not None and original.author.bot:
            return

        e = discord.Embed(title="🗑️ Mensagem apagada", color=discord.Color.orange(),
                          timestamp=discord.utils.utcnow())
        onde = guild.get_channel(payload.channel_id)
        e.add_field(name="Canal", value=(onde.mention if onde else f"`{payload.channel_id}`"),
                    inline=True)
        if original is not None:
            e.add_field(name="Autor",
                        value=f"{original.author.mention} (`{original.author.id}`)",
                        inline=False)
            conteudo = (original.content or "").strip() or "*sem texto (anexo/embed)*"
            e.add_field(name="Conteúdo", value=conteudo[:1024], inline=False)
            if original.attachments:
                e.add_field(name="Anexos",
                            value="\n".join(a.filename for a in original.attachments)[:1024],
                            inline=False)
        else:
            e.add_field(name="Autor", value="*desconhecido (fora do cache)*", inline=False)
            e.add_field(name="Conteúdo", value="*conteúdo não disponível (mensagem antiga)*",
                        inline=False)
        await _enviar(canal, e)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        # Só interessa boost ou mudança de cargo. Sem esta checagem o listener
        # carregava a config a cada troca de apelido/avatar de qualquer membro.
        houve_boost = (before.premium_since is None) != (after.premium_since is None)
        antes = {r.id for r in before.roles}
        depois = {r.id for r in after.roles}
        if not houve_boost and antes == depois:
            return
        if after.bot:
            return

        lg = await self._lg(after.guild)
        if not lg:
            return

        # Boost / unboost.
        if before.premium_since is None and after.premium_since is not None:
            canal = _canal_do_evento(after.guild, lg, "boost")
            if canal:
                e = discord.Embed(title="🚀 Novo boost no servidor!",
                                  color=discord.Color.from_rgb(244, 67, 137),
                                  description=f"{after.mention} impulsionou o servidor!")
                await _enviar(canal, e)
        elif before.premium_since is not None and after.premium_since is None:
            canal = _canal_do_evento(after.guild, lg, "boost")
            if canal:
                e = discord.Embed(title="📉 Boost removido",
                                  color=discord.Color.dark_grey(),
                                  description=f"{after.mention} não impulsiona mais o servidor.")
                await _enviar(canal, e)

        # Mudança de cargos.
        if antes == depois:
            return
        canal = _canal_do_evento(after.guild, lg, "role_change")
        if not canal:
            return
        ganhou = [after.guild.get_role(rid) for rid in (depois - antes)]
        perdeu = [after.guild.get_role(rid) for rid in (antes - depois)]
        e = discord.Embed(title="🎭 Cargos atualizados", color=discord.Color.blurple(),
                          timestamp=discord.utils.utcnow())
        e.add_field(name="Membro", value=f"{after.mention} (`{after.id}`)", inline=False)
        if ganhou:
            e.add_field(name="Ganhou", value=" ".join(r.mention for r in ganhou if r) or "—",
                        inline=False)
        if perdeu:
            e.add_field(name="Perdeu", value=" ".join(r.mention for r in perdeu if r) or "—",
                        inline=False)
        await _enviar(canal, e)


async def setup(client: commands.Bot) -> None:
    await client.add_cog(Registros(client))
