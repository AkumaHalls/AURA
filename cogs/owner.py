"""
AURA · Dono e informações do bot
------------------------------
Comandos globais do AURA: falar em massa, listar servidores, sincronizar
comandos e informações de sistema.

A autorização usa `OWNER_ID` do .env mais os `owner_ids` registrados em cada
servidor pelo painel — assim dá para adicionar um dono sem reiniciar o bot.
"""

from __future__ import annotations

import asyncio
import os
import platform
import time
from typing import List

import discord
import psutil
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from core import runtime
from core import settings as st

load_dotenv()

PROC = psutil.Process(os.getpid())
INICIO = time.time()

_mensagem_erro = (
    "<:ew:969703224825225266> Não consegui fazer isso. "
    "Confira se você está no canal certo e se tem permissão."
)


def getdonoid() -> int:
    try:
        return int(os.getenv("OWNER_ID") or os.getenv("DONO_ID"))
    except (TypeError, ValueError):
        return None


def getmensagemerro() -> str:
    return _mensagem_erro


def _dono_do_env() -> int:
    return getdonoid()


class Owner(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client

    async def _eh_dono(self, interaction: discord.Interaction) -> bool:
        if await self.client.is_owner(interaction.user):
            return True
        if st.eh_dono(interaction.user.id):
            return True
        if interaction.guild is None:
            return False
        try:
            cfg = await st.get_config_cached(interaction.guild.id,
                                             guild_name=interaction.guild.name)
        except Exception:
            return False
        return st.eh_dono(interaction.user.id, cfg)

    async def _recusar(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.send_message(_mensagem_erro, ephemeral=True)

    # ------------------------------------------------------------------
    # /owner
    # ------------------------------------------------------------------

    owner = app_commands.Group(name="owner", description="Comandos do dono do AURA.")

    @owner.command(name="listar", description="Lista os servidores onde o AURA está.")
    async def listar(self, interaction: discord.Interaction):
        if not await self._eh_dono(interaction):
            return await self._recusar(interaction)

        guilds = self.client.guilds
        if not guilds:
            return await interaction.response.send_message("O AURA não está em nenhum servidor.",
                                                           ephemeral=True)

        testes = {int(v) for v in {os.getenv("TEST_GUILD_ID", "")} if str(v).isdigit()}
        linhas = []
        for g in guilds[:25]:
            prefixo = "⭐ " if g.id in testes else "• "
            linhas.append(f"{prefixo}**{g.name}** · `{g.id}` · "
                          f"{g.member_count or 0} membros")
        texto = "\n".join(linhas)
        if len(guilds) > 25:
            texto += f"\n…e mais {len(guilds) - 25}"

        await interaction.response.send_message(embed=discord.Embed(
            title=f"🌐 AURA em {len(guilds)} servidor(es)",
            description=texto,
            color=discord.Color.blurple(),
        ), ephemeral=True)

    @owner.command(name="falar", description="Envia uma mensagem num servidor.")
    @app_commands.describe(servidor_id="ID do servidor", texto="O que enviar")
    async def falar(self, interaction: discord.Interaction, servidor_id: str, texto: str):
        if not await self._eh_dono(interaction):
            return await self._recusar(interaction)
        guild = self.client.get_guild(int(servidor_id)) if servidor_id.isdigit() else None
        if guild is None:
            return await interaction.response.send_message("Servidor não encontrado.",
                                                           ephemeral=True)
        canais = [c for c in guild.text_channels
                  if c.permissions_for(guild.me).send_messages]
        if not canais:
            return await interaction.response.send_message(
                "O bot não pode enviar mensagens em nenhum canal desse servidor.",
                ephemeral=True)
        canal = canais[0]
        await canal.send(texto[:1900])
        await interaction.response.send_message(
            f"Enviado em #{canal.name} ({guild.name}).", ephemeral=True)

    @owner.command(name="sair", description="Faz o AURA sair de um servidor.")
    @app_commands.describe(servidor_id="ID do servidor")
    async def sair(self, interaction: discord.Interaction, servidor_id: str):
        if not await self._eh_dono(interaction):
            return await self._recusar(interaction)
        guild = self.client.get_guild(int(servidor_id)) if servidor_id.isdigit() else None
        if guild is None:
            return await interaction.response.send_message("Servidor não encontrado.",
                                                           ephemeral=True)
        nome = guild.name
        try:
            import mongo_db
            mongo_db.delete_guild_config(guild.id)
        except Exception:
            pass
        await guild.leave()
        await interaction.response.send_message(f"Saiu de **{nome}**.", ephemeral=True)

    @owner.command(name="preconfig", description="Pre-configura os módulos com o padrão do perfil.")
    @app_commands.describe(
        perfil="'auto' escolhe coc no servidor do Clash e generico nos outros",
        modulos="Módulos separados por vírgula (vazio = todos)",
        alcance="Servidor atual, ou 'todos' para configuring todos")
    async def preconfig(self, interaction: discord.Interaction,
                        perfil: str = "auto", modulos: str = "",
                        alcance: str = "atual"):
        if not await self._eh_dono(interaction):
            return await self._recusar(interaction)

        from core import preconfig as pc

        if perfil not in st.PERFIS and perfil != "auto":
            return await interaction.response.send_message(
                f"Perfil '{perfil}' não existe. Use: {', '.join(st.PERFIS)} ou auto.",
                ephemeral=True)

        mods = tuple(m.strip() for m in modulos.split(",") if m.strip()) \
            if modulos.strip() else pc.MODULOS_PADRAO
        desconhecidos = [m for m in mods if m not in st.MODULOS]
        if desconhecidos:
            return await interaction.response.send_message(
                f"Módulo desconhecido: {', '.join(desconhecidos)}.\n"
                f" existent: {', '.join(st.MODULOS)}", ephemeral=True)

        if alcance.strip().lower() in ("todos", "all", "*"):
            alvos = list(self.client.guilds)
        elif interaction.guild is not None:
            alvos = [interaction.guild]
        else:
            return await interaction.response.send_message(
                "Usa esse comando dentro de um servidor, ou passe alcance: todos.",
                ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        linhas, total_falta = [], 0
        for guild in alvos:
            perfil_guild = pc.perfil_padrao_para(guild.id) if perfil == "auto" \
                else perfil
            try:
                ok, cfg, falta = await asyncio.to_thread(
                    pc.aplicar, guild.id, guild.name,
                    str(guild.icon or "") or None, perfil_guild, guild=guild,
                    modulos=mods)
            except Exception as exc:
                linhas.append(f"❌ **{guild.name}** — erro: {exc}")
                continue
            if not ok:
                linhas.append(f"❌ **{guild.name}** — não consegui gravar no Mongo")
                continue
            ligados = [k for k, v in (cfg.get("modules") or {}).items() if v]
            total_falta += len(falta)
            resumo = f"✅ **{guild.name}** · perfil `{perfil_guild}` · " \
                     f"{len(ligados)} módulos"
            if falta:
                resumo += "\n" + "\n".join(f"   • falta: {f}" for f in falta)
            linhas.append(resumo)

        e = discord.Embed(title="⚙️ Pre-configuração aplicada", color=discord.Color.green())
        e.description = "\n".join(linhas) or "nenhum servidor encontrado"
        e.add_field(name="Punição automática",
                    value="desligada (só avisa e apaga)", inline=True)
        e.add_field(name="Pendências no total",
                    value=str(total_falta) or "0", inline=True)
        e.set_footer(text="Ajuste o resto no painel web (Configurações gerais).")
        await interaction.followup.send(embed=e, ephemeral=True)

    @owner.command(name="sync", description="Ressincroniza os comandos do AURA.")
    async def sync_cmd(self, interaction: discord.Interaction):
        if not await self._eh_dono(interaction):
            return await self._recusar(interaction)
        await interaction.response.defer(ephemeral=True)
        cmds = [c.name for c in self.client.tree.get_commands()]
        await self.client.tree.sync()
        await interaction.followup.send(
            f"✅ {len(cmds)} comandos sincronizados.\n" + ", ".join(sorted(cmds)),
            ephemeral=True)

    @owner.command(name="nome", description="Muda o nome de exibição do bot.")
    @app_commands.describe(novo="Novo nome")
    async def nome(self, interaction: discord.Interaction, novo: str):
        if not await self._eh_dono(interaction):
            return await self._recusar(interaction)
        await self.client.user.edit(name=novo[:80])
        await interaction.response.send_message(f"Agora sou **{novo}**.", ephemeral=True)

    @owner.command(name="avatar", description="Muda o avatar do bot por URL.")
    @app_commands.describe(url="URL de uma imagem")
    async def avatar(self, interaction: discord.Interaction, url: str):
        if not await self._eh_dono(interaction):
            return await self._recusar(interaction)
        if not url.startswith("http"):
            return await interaction.response.send_message("Precisa ser uma URL http(s).",
                                                           ephemeral=True)
        try:
            dados = await _baixar(url)
            await self.client.user.edit(avatar=dados)
            await interaction.response.send_message("Avatar atualizado.", ephemeral=True)
        except Exception as exc:
            await interaction.response.send_message(f"Falhou: {exc}", ephemeral=True)

    # ------------------------------------------------------------------
    # /bot
    # ------------------------------------------------------------------

    bot = app_commands.Group(name="bot", description="Informações do AURA.")

    @bot.command(name="ping", description="Latência do AURA.")
    async def ping(self, interaction: discord.Interaction):
        latencia = round(self.client.latency * 1000)
        await interaction.response.send_message(
            f"🏓 **{latencia}ms** · {len(self.client.guilds)} servidor(es) · "
            f"{len(self.client.tree.get_commands())} comandos", ephemeral=True)

    @bot.command(name="info", description="Detalhes do AURA e do servidor.")
    @commands.guild_only()
    async def info(self, interaction: discord.Interaction):
        guild = interaction.guild
        cfg = await st.get_config_cached(guild.id, guild_name=guild.name)

        uso_cpu = psutil.cpu_percent(interval=0.2)
        memoria = PROC.memory_info().rss / (1024 * 1024)
        segundos = int(time.time() - INICIO)

        e = discord.Embed(
            title="🤖 AURA",
            color=discord.Color.blurple(),
        )
        e.add_field(name="Versão", value="2.1 · multiserver", inline=True)
        e.add_field(name="Python", value=platform.python_version(), inline=True)
        e.add_field(name="discord.py", value=discord.__version__, inline=True)
        e.add_field(name="Latência", value=f"{round(self.client.latency * 1000)}ms", inline=True)
        e.add_field(name="Memória", value=f"{memoria:.0f} MB", inline=True)
        e.add_field(name="CPU", value=f"{uso_cpu:.0f}%", inline=True)
        e.add_field(name="Online há", value=f"{segundos // 3600}h {(segundos % 3600) // 60}m",
                    inline=True)
        e.add_field(name="Servidores", value=str(len(self.client.guilds)), inline=True)

        status = st.build_status(cfg)
        ligados = [s["label"] for s in status if s.get("ativo")]
        e.add_field(name="Módulos aqui",
                    value=", ".join(ligados) if ligados else "nenhum ligado",
                    inline=False)
        e.set_footer(text=f"{guild.name} · prefixo {cfg.get('prefix')}")
        if self.client.user.display_avatar:
            e.set_thumbnail(url=self.client.user.display_avatar.url)

        await interaction.response.send_message(embed=e, ephemeral=True)

    @bot.command(name="modulos", description="Módulos ativos e o que falta em cada um.")
    @commands.guild_only()
    async def modulos(self, interaction: discord.Interaction):
        guild = interaction.guild
        cfg = await st.get_config_cached(guild.id, guild_name=guild.name)
        status = st.build_status(cfg)

        linhas = []
        for s in status:
            marca = {True: "🟢", False: "⚪"}[bool(s.get("ativo"))]
            extra = s.get("detalhe") or ("pronto" if s.get("pronto") else "")
            linhas.append(f"{marca} **{s['label']}** — {extra}")

        await interaction.response.send_message(embed=discord.Embed(
            title=f"🧩 Módulos · {guild.name}",
            description="\n".join(linhas),
            color=discord.Color.blurple(),
        ), ephemeral=True)


async def _baixar(url: str) -> bytes:
    import aiohttp
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as sess:
        async with sess.get(url) as resp:
            resp.raise_for_status()
            return await resp.read()


async def setup(client: commands.Bot) -> None:
    await client.add_cog(Owner(client))