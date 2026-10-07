"""
AURA · Clash of Clans
---------------------
Integração com a API do Clash of Clans, configurada POR SERVIDOR.

O que este módulo faz:
    /clash vincular   liga uma tag de clã a este servidor do Discord
    /clash verificar  confere se cada membro do clã tem o cargo certo aqui
    /clash status     mostra a configuração deste servidor

Credenciais vêm do .env (COC_EMAIL / COC_PASSWORD), porque são sensíveis e
compartilhadas. O que é específico de cada servidor — tag do clã, canais,
cargos e mensagem de remoção — vem da config no painel web.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, List, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

import mongo_db
from core import runtime
from core import settings as st

COC_EMAIL = os.getenv("COC_EMAIL")
COC_PASSWORD = os.getenv("COC_PASSWORD")

#: Cargo no Clash -> chave na config. A API usa nomes próprios por cargo.
CARGOS_COC = {
    "member": "member",
    "admin": "elder",
    "elder": "elder",
    "coleader": "coleader",
    "co-leader": "coleader",
    "leader": "coleader",
}

_client = None


async def _coc():
    """Cliente do Clash of Clans, criado uma vez e reaproveitado."""
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
        runtime.log("ERRO", f"Clash: login falhou: {exc}", "clash")
        _client = None
    return _client


async def _fechar_coc():
    global _client
    if _client is not None:
        try:
            await _client.logout()
        except Exception:
            pass
        _client = None


def _pronto(cfg: Dict[str, Any]) -> tuple:
    coc = ((cfg.get("games") or {}).get("coc")) or {}
    faltando = []
    if not coc.get("clan_tag"):
        faltando.append("tag do clã")
    if not coc.get("registration_channel_id"):
        faltando.append("canal de registro")
    if not any((coc.get("roles") or {}).values()):
        faltando.append("cargos do clã")
    return (not faltando), ", ".join(faltando), coc


def _extrair_membros(resposta) -> List[Any]:
    """
    O coc.py muda o formato entre versões: `get_clan_members` pode devolver o
    objeto Clan, um dict de membros ou uma lista. Aqui vira sempre uma lista de
    objetos com `.name`, para o resto do código não precisar saber.
    """
    if resposta is None:
        return []
    if isinstance(resposta, dict):
        return list(resposta.values())
    membros = getattr(resposta, "members", None)
    if isinstance(membros, dict):
        return list(membros.values())
    if isinstance(membros, (list, tuple)):
        return list(membros)
    if isinstance(resposta, (list, tuple)):
        return list(resposta)
    return []


def _patente(membro) -> str:
    """Chave de cargo do clã (member/elder/coleader) a partir do objeto da API."""
    papel = getattr(getattr(membro, "role", None), "in_game_name", None)
    if not papel:
        papel = getattr(membro, "role", None)
        papel = getattr(papel, "name", None) if papel else None
    return CARGOS_COC.get(str(papel or "member").lower(), "member")


class ClashLogManager(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client

    async def cog_unload(self):
        await _fechar_coc()
        if self.verify_members.is_running():
            self.verify_members.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        if not (COC_EMAIL and COC_PASSWORD):
            runtime.log("AVISO", "Clash: sem COC_EMAIL/COC_PASSWORD, módulo inativo", "clash")
            return
        if not self.verify_members.is_running():
            self.verify_members.start()

    # ------------------------------------------------------------------
    # Sincronização de cargos
    # ------------------------------------------------------------------

    async def _servidores_com_clash(self) -> List[tuple]:
        """(guild, config_coc) de todos os servidores com o módulo ligado."""
        achados = []
        for guild in self.client.guilds:
            try:
                cfg = await st.get_config_cached(guild.id, guild_name=guild.name)
            except Exception:
                continue
            if not st.module_enabled(cfg, "games"):
                continue
            _, _, coc = _pronto(cfg)
            if coc.get("clan_tag"):
                achados.append((guild, coc))
        return achados

    async def verificar_um(self, guild: discord.Guild, coc: Dict[str, Any]) -> Dict[str, int]:
        """Confere os membros do clã contra os cargos configurados. """
        stats = {"ok": 0, "atualizados": 0, "removidos": 0, "erros": 0}
        api = await _coc()
        if api is None:
            stats["erros"] = -1
            return stats

        cargo_member = guild.get_role((coc.get("roles") or {}).get("member")) \
            if (coc.get("roles") or {}).get("member") else None
        cargo_elder = guild.get_role((coc.get("roles") or {}).get("elder")) \
            if (coc.get("roles") or {}).get("elder") else None
        cargo_coleader = guild.get_role((coc.get("roles") or {}).get("coleader")) \
            if (coc.get("roles") or {}).get("coleader") else None
        mapa_cargos = {"member": cargo_member, "elder": cargo_elder,
                       "coleader": cargo_coleader}
        cargos_validos = [c for c in mapa_cargos.values() if c is not None]

        try:
            membros = _extrair_membros(await api.get_clan_members(coc["clan_tag"]))
        except Exception as exc:
            runtime.log("ERRO", f"Clash: não consegui ler o clã {coc['clan_tag']}: {exc}",
                        "clash")
            stats["erros"] += 1
            return stats

        if not membros:
            runtime.log("AVISO", f"Clash: {coc['clan_tag']} devolveu zero membros. "
                                 f"Nenhuma alteração feita.", "clash")
            return stats

        nomes = {}
        for m in membros:
            nome = (getattr(m, "name", "") or "").lower()
            if not nome:
                continue
            chave = _patente(m)
            cargo = mapa_cargos.get(chave) or cargo_member
            nomes[nome] = cargo
            stats["ok"] += 1

            alvo = discord.utils.find(
                lambda x: (x.name or "").lower() == nome or
                          (x.nick or "").lower() == nome,
                guild.members)
            if alvo is None:
                alvo = discord.utils.find(
                    lambda x: (x.global_name or "").lower() == nome, guild.members)

            if alvo is None:
                stats["erros"] += 1
                continue

            if cargo is None:
                continue
            if discord.utils.get(alvo.roles, id=cargo.id) is None:
                try:
                    await alvo.add_roles(cargo, reason=f"AURA Clash: cargo {chave}")
                    stats["atualizados"] += 1
                except discord.Forbidden:
                    stats["erros"] += 1

            # Tira cargos do clã que a pessoa não tem mais.
            for outro in cargos_validos:
                if outro.id != cargo.id and discord.utils.get(alvo.roles, id=outro.id):
                    try:
                        await alvo.remove_roles(outro, reason="AURA Clash: cargo desatualizado")
                        stats["atualizados"] += 1
                    except discord.Forbidden:
                        stats["erros"] += 1

        # Quem tem cargo de clã mas saiu do clã.
        for membro in guild.members:
            if not any(discord.utils.get(membro.roles, id=c.id) for c in cargos_validos):
                continue
            if (membro.name or "").lower() in nomes:
                continue
            if guild.owner_id == membro.id:
                continue
            if not any(discord.utils.get(membro.roles, id=c.id)
                       for c in cargos_validos if c.name and
                       any(r.name.lower() in ("staff", "mod", "admin", "owner", "administrador")
                           for r in membro.roles)):
                for cargo in cargos_validos:
                    if discord.utils.get(membro.roles, id=cargo.id):
                        try:
                            await membro.remove_roles(cargo, reason="AURA Clash: saiu do clã")
                            stats["removidos"] += 1
                            await _avisar_remocao(membro, guild, coc)
                        except discord.Forbidden:
                            stats["erros"] += 1

        mongo_db.registrar_auditoria(
            guild.id, guild.name, "clash_verificado", "games", None,
            f"ok={stats['ok']} atualizados={stats['atualizados']} "
            f"removidos={stats['removidos']}",
        )
        return stats

    @tasks.loop(hours=1)
    async def verify_members(self):
        await self.client.wait_until_ready()
        if not (COC_EMAIL and COC_PASSWORD):
            return
        for guild, coc in await self._servidores_com_clash():
            try:
                await self.verificar_um(guild, coc)
            except Exception as exc:
                runtime.log("ERRO", f"Clash: verificação falhou em {guild.name}: {exc}",
                            "clash")

    @verify_members.before_loop
    async def _antes_do_loop(self):
        await self.client.wait_until_ready()
        await asyncio.sleep(30)

    # ------------------------------------------------------------------
    # Comandos
    # ------------------------------------------------------------------

    clash = app_commands.Group(name="clash", description="Integração com Clash of Clans.", guild_only=True)

    @clash.command(name="status", description="Mostra a configuração do Clash neste servidor.")
    @app_commands.guild_only()
    async def clash_status(self, interaction: discord.Interaction):
        guild = interaction.guild
        cfg = await st.get_config_cached(guild.id, guild_name=guild.name)
        pronto, falta, coc = _pronto(cfg)

        e = discord.Embed(
            title=f"⚔️ Clash of Clans · {guild.name}",
            color=discord.Color.green() if pronto else discord.Color.orange(),
        )
        e.add_field(name="Estado",
                    value="✅ configurado" if pronto else f"⚠️ falta: {falta}",
                    inline=False)
        e.add_field(name="Clã", value=f"`{coc.get('clan_tag') or '—'}`", inline=True)
        e.add_field(name="Verificação", value=f"a cada {coc.get('verify_hours', 1)}h", inline=True)
        for chave, rotulo in (("member", "Membro"), ("elder", "Elder/Admin"),
                              ("coleader", "Líder")):
            rid = (coc.get("roles") or {}).get(chave)
            cargo = guild.get_role(rid) if rid else None
            e.add_field(name=rotulo, value=cargo.mention if cargo else "—", inline=True)
        e.add_field(
            name="Credenciais da API",
            value="definidas no .env" if (COC_EMAIL and COC_PASSWORD)
                  else "⚠️ faltam COC_EMAIL/COC_PASSWORD no .env",
            inline=False,
        )
        e.set_footer(text="AURA · ajuste no painel web")
        await interaction.response.send_message(embed=e, ephemeral=True)

    @clash.command(name="verificar", description="Confere os membros do clã agora.")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_roles=True)
    async def clash_verificar(self, interaction: discord.Interaction):
        guild = interaction.guild
        cfg = await st.get_config_cached(guild.id, guild_name=guild.name)
        if not st.module_enabled(cfg, "games"):
            return await interaction.response.send_message(
                "❌ Módulo de jogos desligado aqui.", ephemeral=True)
        pronto, falta, coc = _pronto(cfg)
        if not pronto:
            return await interaction.response.send_message(
                f"❌ Falta configurar: {falta}. Use o painel web.", ephemeral=True)
        if not (COC_EMAIL and COC_PASSWORD):
            return await interaction.response.send_message(
                "❌ Sem COC_EMAIL/COC_PASSWORD no .env.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        stats = await self.verificar_um(guild, coc)
        if stats.get("erros") == -1:
            return await interaction.followup.send(
                "❌ Não consegui falar com a API do Clash. See os logs.", ephemeral=True)
        await interaction.followup.send(
            f"✅ Verificação concluída.\n"
            f"Membros no clã: **{stats['ok']}**\n"
            f"Cargos ajustados: **{stats['atualizados']}**\n"
            f"Cargos removidos: **{stats['removidos']}**\n"
            f"Problemas: **{stats['erros']}**", ephemeral=True)

    @clash.command(name="membros", description="Lista os membros do clã e o cargo de cada um.")
    @app_commands.guild_only()
    async def clash_membros(self, interaction: discord.Interaction):
        cfg = await st.get_config_cached(interaction.guild.id,
                                         guild_name=interaction.guild.name)
        pronto, falta, coc = _pronto(cfg)
        if not pronto:
            return await interaction.response.send_message(
                f"❌ Falta configurar: {falta}.", ephemeral=True)

        api = await _coc()
        if api is None:
            return await interaction.response.send_message(
                "❌ Sem credenciais da API do Clash no .env.", ephemeral=True)

        await interaction.response.defer()
        try:
            membros = _extrair_membros(await api.get_clan_members(coc["clan_tag"]))
        except Exception as exc:
            return await interaction.followup.send(f"❌ Falha na API: {exc}")

        linhas = []
        for m in membros[:40]:
            papel = (getattr(getattr(m, "role", None), "in_game_name", "") or "?")
            linhas.append(f"**{getattr(m, 'name', '?')}** — {papel}")
        await interaction.followup.send(embed=discord.Embed(
            title=f"👥 Membros de {coc['clan_tag']}",
            description="\n".join(linhas) or "clã vazio",
            color=discord.Color.gold(),
        ))


async def _avisar_remocao(membro: discord.Member, guild: discord.Guild,
                          coc: Dict[str, Any]):
    texto = coc.get("kick_message") or "Você foi removido do cargo do clã."
    try:
        dm = await membro.create_dm()
        await dm.send(f"{texto}\n\nServidor: **{guild.name}**")
    except discord.Forbidden:
        pass

    if coc.get("log_channel_id"):
        canal = guild.get_channel(coc["log_channel_id"])
        if canal is not None:
            try:
                await canal.send(f"⚠️ {membro.mention} perdeu o cargo do clã "
                                 f"({texto})")
            except discord.Forbidden:
                pass


async def setup(client: commands.Bot) -> None:
    await client.add_cog(ClashLogManager(client))
