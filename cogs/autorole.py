"""
AURA · Autorole
---------------
Liberação de acesso por palavra-chave, configurada POR SERVIDOR.

O painel define: canal de registro, palavra (padrão "liberar"), cargo a dar,
cargo que bloqueia e mensagem de boas-vindas. Antes valia um .env global, que
não funciona quando o AURA atende vários servidores.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict

import discord
from discord import app_commands
from discord.ext import commands

import mongo_db
from core import runtime
from core import settings as st
from core.placeholders import render


def _config_pronta(ar: Dict[str, Any]) -> bool:
    return bool(ar.get("channel_id") and ar.get("give_role_id"))


class Autorole(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self):
        runtime.log("INFO", "Autorole carregado (config por servidor)", "autorole")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return

        guild = message.guild
        try:
            cfg = await st.get_config_cached(guild.id, guild_name=guild.name)
        except Exception as exc:
            runtime.log("ERRO", f"autorole: config: {exc}", "autorole")
            return

        if not st.module_enabled(cfg, "autorole"):
            return

        ar = cfg.get("autorole") or {}
        if not ar.get("enabled") or not _config_pronta(ar):
            return

        if message.channel.id != ar.get("channel_id"):
            return

        palavra = (ar.get("keyword") or "liberar").strip().lower()
        if message.content.strip().lower() != palavra:
            return

        membro = message.author
        cargo_bloqueio = ar.get("deny_role_id")
        cargo_entrada = ar.get("give_role_id")

        try:
            if cargo_bloqueio and discord.utils.get(membro.roles, id=cargo_bloqueio):
                await message.add_reaction("❌")
                await message.reply(
                    "Você está bloqueado e não pode ser liberado. Fale com a administração.",
                    delete_after=30)
                return

            if cargo_entrada and discord.utils.get(membro.roles, id=cargo_entrada):
                await message.add_reaction("👍")
                await message.reply("Você já está liberado.", delete_after=15)
                return

            cargo = guild.get_role(cargo_entrada) if cargo_entrada else None
            if cargo is None:
                await message.add_reaction("⚠️")
                runtime.log("ERRO", f"cargo de entrada {cargo_entrada} não existe em "
                                     f"{guild.name}", "autorole")
                return

            await membro.add_roles(cargo, reason=f"AURA autorole: {palavra}")
            await message.add_reaction("✅")

            texto = render(
                ar.get("welcome_message") or "Bem-vindo ao servidor!",
                user=membro, member=membro, guild=guild, channel=message.channel,
            )
            if texto:
                await message.channel.send(texto[:2000])

            if ar.get("delete_message"):
                atraso = min(120, int(ar.get("delete_delay_seconds") or 0))
                await asyncio.sleep(atraso)
                try:
                    await message.delete()
                except discord.NotFound:
                    pass

            try:
                mongo_db.registrar_auditoria(
                    guild.id, guild.name, "autorole_concedido", "autorole", membro,
                    f"cargo {cargo.id}")
            except Exception:
                pass

        except discord.Forbidden:
            await message.add_reaction("⚠️")
            runtime.log("ERRO", f"sem permissão para dar cargo em {guild.name}", "autorole")
        except discord.HTTPException as exc:
            runtime.log("ERRO", f"autorole falhou em {guild.name}: {exc}", "autorole")

    ar = app_commands.Group(name="autorole", description="Liberação de acesso.")

    @ar.command(name="status", description="Mostra a configuração de autorole aqui.")
    @commands.guild_only()
    async def ar_status(self, interaction: discord.Interaction):
        guild = interaction.guild
        cfg = await st.get_config_cached(guild.id, guild_name=guild.name)
        mod = cfg.get("autorole") or {}
        ativo = st.module_enabled(cfg, "autorole") and mod.get("enabled") and _config_pronta(mod)

        e = discord.Embed(
            title=f"🎫 Liberação de acesso · {guild.name}",
            color=discord.Color.green() if ativo else discord.Color.orange(),
        )
        e.add_field(name="Estado",
                    value="✅ funcionando" if ativo else "⚠️ não configurado",
                    inline=False)
        canal = guild.get_channel(mod.get("channel_id")) if mod.get("channel_id") else None
        e.add_field(name="Canal", value=canal.mention if canal else "—", inline=True)
        cargo = guild.get_role(mod.get("give_role_id")) if mod.get("give_role_id") else None
        e.add_field(name="Cargo dado", value=cargo.mention if cargo else "—", inline=True)
        bloqueio = guild.get_role(mod.get("deny_role_id")) if mod.get("deny_role_id") else None
        e.add_field(name="Cargo bloqueado", value=bloqueio.mention if bloqueio else "—", inline=True)
        e.add_field(name="Palavra", value=f"`{mod.get('keyword') or 'liberar'}`", inline=True)
        e.set_footer(text="AURA · configure no painel web")
        await interaction.response.send_message(embed=e, ephemeral=True)

    @ar.command(name="liberar", description="Libera um membro manualmente.")
    @commands.guild_only()
    @app_commands.describe(membro="Quem liberar")
    @commands.has_permissions(manage_roles=True)
    async def ar_liberar(self, interaction: discord.Interaction, membro: discord.Member):
        cfg = await st.get_config_cached(interaction.guild.id,
                                         guild_name=interaction.guild.name)
        ar = cfg.get("autorole") or {}
        cargo_id = ar.get("give_role_id")
        cargo = interaction.guild.get_role(cargo_id) if cargo_id else None
        if cargo is None:
            return await interaction.response.send_message(
                "❌ Nenhum cargo de entrada configurado no painel.", ephemeral=True)
        try:
            await membro.add_roles(cargo, reason=f"AURA: liberado por {interaction.user}")
        except discord.Forbidden:
            return await interaction.response.send_message(
                "❌ Sem permissão para dar esse cargo.", ephemeral=True)
        await interaction.response.send_message(
            f"✅ {membro.mention} recebeu {cargo.mention}.", ephemeral=True)

    @ar.command(name="revogar", description="Remove o cargo de um membro.")
    @commands.guild_only()
    @app_commands.describe(membro="Quem revogar")
    @commands.has_permissions(manage_roles=True)
    async def ar_revogar(self, interaction: discord.Interaction, membro: discord.Member):
        cfg = await st.get_config_cached(interaction.guild.id,
                                         guild_name=interaction.guild.name)
        ar = cfg.get("autorole") or {}
        cargo_id = ar.get("give_role_id")
        cargo = interaction.guild.get_role(cargo_id) if cargo_id else None
        if cargo is None:
            return await interaction.response.send_message(
                "❌ Nenhum cargo de entrada configurado.", ephemeral=True)
        try:
            await membro.remove_roles(cargo, reason=f"AURA: revogado por {interaction.user}")
        except discord.Forbidden:
            return await interaction.response.send_message(
                "❌ Sem permissão.", ephemeral=True)
        await interaction.response.send_message(
            f"✅ {membro.mention} perdeu {cargo.mention}.", ephemeral=True)


async def setup(client: commands.Bot) -> None:
    await client.add_cog(Autorole(client))