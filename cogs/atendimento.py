"""
AURA · Tickets
--------------
Atendimento configurável POR SERVIDOR. Nada aqui é fixo em Clash of Clans:
o painel define as categorias (nome, emoji, descrição, mensagem de abertura e
cargo extra de staff), e o bot monta o painel e cria as threads a partir disso.

Fluxo:
    /painel enviar        publica o painel de categorias no canal
    botão/select          cria a thread privada, salva no Mongo
    /atendimento atender  um staff assume o ticket
    botão Fechar          gera a transcrição, salva e opcionalmente avalia

Threads são nomeadas `ticket-<user_id>-<n>`; o ID do Mongo fica guardado na
thread em `topic` e no documento, então não dependemos de parsing de nome.
"""

from __future__ import annotations

import asyncio
import re
from io import BytesIO
from typing import Any, Dict, List, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

import mongo_db
from core import runtime
from core import settings as st
from core.placeholders import render

#: Painéis publicados, para o /painel remover o anterior sem duplicar.
_painel_ids: Dict[str, int] = {}
_views_registradas: Dict[str, "TicketPanelView"] = {}

CATEGORIA_RE = re.compile(r"^ticket-\d{15,25}-\d+$")


def _canal_do_ticket(thread: discord.Thread) -> Optional[str]:
    """Extrai o ID do Mongo do topoico da thread."""
    topico = (thread.topic or "").strip()
    if topico.startswith("aura-ticket:"):
        return topico.split(":", 1)[1].strip() or None
    return None


def _nome_da_thread(user: discord.Member, numero: int) -> str:
    base = re.sub(r"[^a-z0-9\-]", "", user.name.lower().replace(" ", "-"))[:24] or "user"
    return f"ticket-{user.id}-{numero}"


# ==========================================================================
# Painel de categorias
# ==========================================================================

class TicketPanelView(discord.ui.View):
    """Botões (e menu) gerados a partir das categorias configuradas no painel."""

    def __init__(self, guild_id: int, categorias: List[Dict[str, Any]]):
        super().__init__(timeout=None)
        self.guild_id = int(guild_id)
        self.categorias = categorias or []
        self._montar()

    # ---------- construção ----------

    def _montar(self):
        self.clear_items()

        if len(self.categorias) <= 20:
            for i, cat in enumerate(self.categorias[:20]):
                self.add_item(TicketButton(self.guild_id, cat, row=i // 5))
        else:
            # Acima de 20 botões o Discord estoura o limite de 25 componentes,
            # então o menu assume sozinho.
            self.add_item(TicketSelect(self.guild_id, self.categorias[:25], row=4))

    def recarregar(self, categorias: List[Dict[str, Any]]):
        self.categorias = categorias or []
        self._montar()

    async def abrir(self, interaction: discord.Interaction, key: str):
        await abrir_ticket(interaction, key, self.guild_id)


class TicketButton(discord.ui.Button):
    def __init__(self, guild_id: int, categoria: Dict[str, Any], row: int = 0):
        super().__init__(
            style=discord.ButtonStyle.primary,
            label=(categoria.get("label") or "Ticket")[:80],
            emoji=categoria.get("emoji") or None,
            row=row,
            custom_id=f"tk:{guild_id}:{categoria.get('key')}",
        )
        self.guild_id = int(guild_id)
        self.key = categoria.get("key")

    async def callback(self, interaction: discord.Interaction):
        view = getattr(self, "_view", None)
        gid = getattr(view, "guild_id", None) or self.guild_id
        await abrir_ticket(interaction, self.key, gid)


class TicketSelect(discord.ui.Select):
    def __init__(self, guild_id: int, categorias: List[Dict[str, Any]], row: int = 4):
        opcoes = [
            discord.SelectOption(
                label=(c.get("label") or "Ticket")[:100],
                value=str(c.get("key")),
                description=(c.get("description") or "")[:100] or None,
                emoji=c.get("emoji") or None,
            )
            for c in categorias[:25]
        ]
        super().__init__(
            placeholder="Escolha o assunto do seu ticket…",
            custom_id=f"tk:{guild_id}:select",
            options=opcoes,
            row=row,
            min_values=1,
            max_values=1,
        )
        self.guild_id = int(guild_id)

    async def callback(self, interaction: discord.Interaction):
        view = getattr(self, "_view", None)
        gid = getattr(view, "guild_id", None) or self.guild_id
        await abrir_ticket(interaction, self.values[0], gid)


# ==========================================================================
# Views dentro do ticket
# ==========================================================================

class TicketAdminView(discord.ui.View):
    """Botões que o solicitante vê: fechar ou cancelar."""

    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = int(guild_id)

    @discord.ui.button(label="Fechar ticket", style=discord.ButtonStyle.danger,
                       custom_id="tk:fechar")
    async def fechar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _fechar_ticket(interaction, self.guild_id, interaction.user)

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary,
                       custom_id="tk:cancelar")
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _cancelar_ticket(interaction)


class StaffTicketView(discord.ui.View):
    """Botões que o staff vê: assumir, transcrição, fechar."""

    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = int(guild_id)

    @discord.ui.button(label="Assumir", style=discord.ButtonStyle.success,
                       custom_id="tk:assumir")
    async def assumir(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = await st.get_config_cached(self.guild_id,
                                         guild_name=interaction.guild.name)
        if not await _pode_atender(interaction.user, cfg):
            return _erro(interaction, "Só a equipe de atendimento pode assumir este ticket.")

        ticket_id = _canal_do_ticket(interaction.channel)
        if not ticket_id:
            return _erro(interaction, "Este ticket não está registrado no banco.")

        if interaction.user.id == await _dono_do_ticket(interaction.channel):
            return _msg(interaction, "Você já está atendendo este ticket.",
                        ephemeral=True)

        ok = mongo_db.atualizar_ticket_status(
            ticket_id, "atendendo", str(interaction.user))
        mongo_db.registrar_auditoria(
            self.guild_id, interaction.guild.name, "ticket_atendido", "tickets",
            str(interaction.user), f"assumiu o ticket {ticket_id}",
        )
        await _msg(
            interaction,
            f"✅ {interaction.user.mention} assumiu este atendimento."
            + ("" if ok else "\n⚠️ Não consegui salvar o status no banco."),
        )

    @discord.ui.button(label="Salvar transcrição", style=discord.ButtonStyle.primary,
                       custom_id="tk:transcricao")
    async def transcricao(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = await st.get_config_cached(self.guild_id,
                                         guild_name=interaction.guild.name)
        if not await _pode_atender(interaction.user, cfg):
            return _erro(interaction, "Só a equipe de atendimento pode salvar a transcrição.")

        await interaction.response.defer(ephemeral=True)
        texto = await _montar_transcricao(interaction.channel)
        ticket_id = _canal_do_ticket(interaction.channel)
        mensagens = texto.count("\n") if texto else 0
        ok = mongo_db.salvar_transcricao(ticket_id, texto,
                                         atendente=str(interaction.user),
                                         mensagem_count=mensagens)
        mongo_db.registrar_auditoria(
            self.guild_id, interaction.guild.name, "ticket_transcricao", "tickets",
            str(interaction.user), ticket_id,
        )
        await interaction.followup.send(
            "📄 Transcrição salva no painel." if ok else "⚠️ Falha ao salvar a transcrição.",
            ephemeral=True,
        )

    @discord.ui.button(label="Fechar", style=discord.ButtonStyle.danger,
                       custom_id="tk:staff_fechar")
    async def fechar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _fechar_ticket(interaction, self.guild_id, interaction.user)


class RatingView(discord.ui.View):
    """Avaliação de 1 a 5, enviada quando o ticket é fechado."""

    def __init__(self, guild_id: int, ticket_id: str):
        super().__init__(timeout=None)
        self.guild_id = int(guild_id)
        self.ticket_id = ticket_id
        for nota in range(1, 6):
            self.add_item(RatingButton(guild_id, ticket_id, nota))

    def disable(self):
        for item in self.children:
            item.disabled = True


class RatingButton(discord.ui.Button):
    def __init__(self, guild_id: int, ticket_id: str, nota: int):
        super().__init__(
            style=discord.ButtonStyle.success if nota >= 4 else discord.ButtonStyle.secondary,
            label=f"{nota} ⭐",
            custom_id=f"tk:{guild_id}:rate:{nota}",
            row=0,
        )
        self.guild_id = int(guild_id)
        self.ticket_id = ticket_id
        self.nota = nota

    async def callback(self, interaction: discord.Interaction):
        mongo_db.salvar_feedback(self.ticket_id, str(interaction.user.id), self.nota)
        mongo_db.registrar_auditoria(
            self.guild_id, interaction.guild.name, "ticket_avaliado", "tickets",
            str(interaction.user), f"{self.nota}/5",
        )
        for item in self._view.children:
            item.disabled = True
        await interaction.response.edit_message(
            content=f"Obrigado pela avaliação: **{self.nota}/5** ⭐", view=self._view)


# ==========================================================================
# Regras de acesso
# ==========================================================================

async def _pode_atender(member: discord.Member, cfg: Dict[str, Any]) -> bool:
    if member.guild_permissions.administrator or member.guild_permissions.manage_channels:
        return True
    cargos = {cfg.get("tickets", {}).get("staff_role_id")}
    for cat in cfg.get("tickets", {}).get("categories") or []:
        cargos.add(cat.get("staff_role_id"))
    cargos.discard(None)
    return bool({r.id for r in member.roles}.intersection(cargos))


def _eh_staff(member: discord.Member, guild: discord.Guild) -> bool:
    if member.guild_permissions.administrator or member.guild_permissions.manage_channels:
        return True
    return any(r.name.lower() in ("staff", "atendente", "suporte", "mod", "moderador")
               for r in member.roles)


async def _dono_do_ticket(thread: discord.Thread) -> Optional[int]:
    """
    Descobre o ID de quem abriu o ticket olhando o embed inicial.
    `Thread.history` é um iterador assíncrono, então só dá para percorrer
    com `async for`, e sem inverter a ordem.
    """
    try:
        async for msg in thread.history(limit=30):
            if msg.author.id != thread.guild.me.id:
                continue
            for embed in msg.embeds or []:
                for field in embed.fields:
                    if field.name != "Membro":
                        continue
                    digitos = re.search(r"\d{15,25}", field.value or "")
                    if digitos:
                        return int(digitos.group())
            if msg.embeds:
                break
    except (discord.Forbidden, discord.HTTPException, AttributeError):
        pass
    return None


# ==========================================================================
# Ações
# ==========================================================================

async def abrir_ticket(interaction: discord.Interaction, key: str, guild_id: int = None):
    guild = interaction.guild
    gid = int(guild_id or guild.id)

    cfg = await st.get_config_cached(gid, guild_name=guild.name)
    if not st.module_enabled(cfg, "tickets"):
        return _erro(interaction, "O módulo de tickets está **desligado** neste servidor. "
                                  "Ligue em **{0} → Tickets** no painel.".format(guild.name))

    pronto, falta = st.tickets_ready(cfg)
    if not pronto:
        return _erro(interaction, f"O módulo de tickets não está pronto: falta {falta}. "
                                  "Configure em **{0} → Tickets** no painel.".format(guild.name))

    tk = cfg["tickets"]
    cat = next((c for c in tk["categories"] if c.get("key") == key), None)
    if cat is None:
        return _erro(interaction, "Essa categoria não existe mais. "
                                  "Use o painel atualizado do servidor.")

    suporte = guild.get_channel(tk["support_channel_id"])
    if suporte is None or not isinstance(suporte, discord.TextChannel):
        return _erro(interaction, "O canal de suporte configurado não existe mais.")

    if interaction.user.bot:
        return _erro(interaction, "Bots não abrem tickets.")

    max_abertos = int(tk.get("max_open_per_user") or 0)
    abertos = mongo_db.tickets_abertos_por_usuario(gid, interaction.user.id)
    if max_abertos and abertos >= max_abertos:
        return _erro(interaction, f"Você já tem **{abertos}** ticket(s) aberto(s). "
                                  f"O limite deste servidor é {max_abertos}.")

    numero = mongo_db.contar_tickets(gid).get("total", 0) + 1
    nome = _nome_da_thread(interaction.user, numero)

    # Reaproveita uma thread do mesmo usuário que ainda esteja aberta.
    for th in suporte.threads:
        if th.name == nome and not th.archived:
            return _msg(interaction, f"Você já tem um ticket aberto: {th.mention}",
                        ephemeral=True)

    try:
        thread = await suporte.create_thread(
            name=nome, type=discord.ChannelType.private_thread,
            reason=f"AURA ticket: {cat.get('label')}")
    except discord.Forbidden:
        return _erro(interaction, "Não tenho permissão para criar threads aqui.")
    except discord.HTTPException as exc:
        runtime.log("ERRO", f"Falha ao criar thread: {exc}", "tickets")
        return _erro(interaction, "Não consegui criar o ticket agora. Tente de novo.")

    # Thread privada: sem isso o membro não consegue nem ver o canal.
    try:
        await thread.add_user(interaction.user)
    except (discord.Forbidden, discord.HTTPException) as exc:
        runtime.log("ERRO", f"Falha ao adicionar membro na thread: {exc}", "tickets")
        await _erro(interaction, "Criei o ticket, mas não consegui te adicionar nele. "
                                 "Abra o painel de novo em instantes.")
        return

    ticket_id = mongo_db.salvar_ticket(
        interaction.user.id, interaction.user.name, cat.get("label"),
        "aberto", guild_id=gid, guild_name=guild.name,
        ticket_id=str(thread.id), channel_name=thread.name,
        categoria_key=cat.get("key"),
        avatar=str(interaction.user.display_avatar.url),
    )

    if ticket_id:
        try:
            await thread.edit(topic=f"aura-ticket:{ticket_id}")
        except discord.Forbidden:
            pass

    mencao_staff = ""
    if tk.get("staff_role_id"):
        mencao_staff = f"<@&{tk['staff_role_id']}>"
    elif guild.owner_id:
        mencao_staff = f"<@{guild.owner_id}>"

    embed = discord.Embed(
        title=f"{cat.get('emoji') or '🎫'} {cat.get('label')}",
        color=discord.Color(int(str(tk.get("panel_color") or "#2b6cb0").lstrip("#"), 16)),
    )
    if cat.get("description"):
        embed.description = cat["description"][:4000]
    embed.add_field(name="Membro", value=f"{interaction.user.mention}\n`{interaction.user.id}`",
                    inline=True)
    embed.add_field(name="Servidor", value=guild.name, inline=True)
    embed.set_footer(text=f"AURA · ticket #{numero} · {guild.name}")
    if interaction.user.display_avatar:
        embed.set_thumbnail(url=interaction.user.display_avatar.url)

    view_ticket = TicketAdminView(gid)
    view_staff = StaffTicketView(gid)
    if mencao_staff:
        await thread.send(mencao_staff, delete_after=8)

    await thread.send(embed=embed, view=view_ticket)
    await thread.send(view=view_staff, delete_after=15)

    texto = render(
        tk.get("welcome_message") or "Olá! Um staff já vai te atender por aqui. Descreva seu problema.",
        user=interaction.user, member=interaction.user, guild=guild, channel=thread,
        extra={"tipo": cat.get("label"), "motivo": cat.get("description") or ""},
    )
    await thread.send(texto[:2000])

    if cat.get("prompt"):
        await thread.send(f"```\n{cat['prompt'][:1800]}\n```")

    runtime.log(
        "INFO",
        f"[{guild.name}] ticket de {interaction.user} · {cat.get('label')}",
        "tickets",
    )
    mongo_db.registrar_auditoria(gid, guild.name, "ticket_aberto", "tickets",
                                 interaction.user, cat.get("label"))

    await _msg(interaction, f"✅ Ticket aberto: {thread.mention}", ephemeral=True)


def _erro(interaction: discord.Interaction, texto: str):
    if interaction.response.is_done():
        return interaction.followup.send(texto, ephemeral=True)
    return interaction.response.send_message(texto, ephemeral=True)


def _msg(interaction: discord.Interaction, texto: str, ephemeral: bool = True):
    if interaction.response.is_done():
        return interaction.followup.send(texto, ephemeral=ephemeral)
    return interaction.response.send_message(texto, ephemeral=ephemeral)


async def _montar_transcricao(thread: discord.Thread, limite: int = 200) -> str:
    linhas = [f"# Transcrição · {thread.name}", ""]
    try:
        async for msg in thread.history(limit=limite, oldest_first=True):
            stamp = msg.created_at.strftime("%d/%m %H:%M")
            quem = msg.author.display_name
            if msg.author.id == thread.guild.owner_id:
                quem += " (dono)"
            elif _eh_staff(msg.author, thread.guild):
                quem += " (staff)"
            conteudo = msg.content or "(sem texto)"
            if msg.embeds:
                conteudo += " " + " ".join(
                    f"[embed: {e.title or 'sem título'}]" for e in msg.embeds)
            linhas.append(f"**{stamp} · {quem}**\n{conteudo}\n")
    except discord.Forbidden:
        linhas.append("_não consegui ler o histórico_")
    return "\n".join(linhas)[:180_000]


async def _fechar_ticket(interaction: discord.Interaction, guild_id: int,
                         quem: discord.Member):
    thread = interaction.channel
    guild = interaction.guild
    cfg = await st.get_config_cached(guild_id, guild_name=guild.name)
    tk = cfg["tickets"]

    dono_id = await _dono_do_ticket(thread)
    eh_dono_do_ticket = dono_id is not None and dono_id == interaction.user.id

    if not (eh_dono_do_ticket or await _pode_atender(interaction.user, cfg)):
        await _erro(interaction, "Só o dono do ticket ou um atendente pode fechar isso.")
        return

    await interaction.response.defer()
    ticket_id = _canal_do_ticket(thread)

    texto = await _montar_transcricao(thread)
    mongo_db.salvar_transcricao(ticket_id, texto, atendente=str(quem),
                                 mensagem_count=texto.count("\n"))
    mongo_db.atualizar_ticket_status(ticket_id, "fechado", atendente=str(quem),
                                     motivo="fechado por botão")

    cabecalho = ("🔒 Ticket fechado"
                 + (f" por {quem.mention}" if quem else "")
                 + f"\nTranscrição salva. Valorize o atendimento!")
    await thread.send(cabecalho)

    if tk.get("rating_enabled"):
        nota_view = RatingView(guild_id, ticket_id)
        await thread.send(
            render(tk.get("rating_question") or "Como foi o atendimento? Avalie de 1 a 5:",
                   user=interaction.user, guild=guild, channel=thread),
            view=nota_view,
        )

    aviso = render(
        tk.get("close_message") or "Este ticket foi fechado. Use o painel para abrir outro.",
        user=interaction.user, guild=guild, channel=thread,
    )
    if aviso:
        await thread.send(aviso)

    if tk.get("transcript_channel_id"):
        destino = guild.get_channel(tk["transcript_channel_id"])
        if destino is not None:
            try:
                buf = BytesIO(texto.encode("utf-8", "ignore"))
                await destino.send(
                    content=f"📄 Transcrição de {thread.mention}",
                    file=discord.File(buf, filename=f"aura-{thread.name}.txt"),
                )
            except discord.Forbidden:
                pass

    atraso = int(tk.get("close_delay_seconds") or 0)
    if atraso > 0:
        await asyncio.sleep(min(600, atraso))
    try:
        await thread.edit(archived=True, locked=True, name=f"fechado-{thread.name}")
    except discord.Forbidden:
        pass

    mongo_db.registrar_auditoria(guild_id, guild.name, "ticket_fechado", "tickets",
                                 quem, thread.name)
    runtime.log("INFO", f"[{guild.name}] ticket fechado por {quem}", "tickets")


async def _cancelar_ticket(interaction: discord.Interaction):
    await _erro(interaction, "Para encerrar, feche o ticket com o botão. "
                             "Um staff pode ajudar se algo travar.")


# ==========================================================================
# Cog
# ==========================================================================

class Atendimento(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client

    # ---------- ciclo de vida ----------

    async def cog_load(self):
        self.registrar_views_iniciais()

    @commands.Cog.listener()
    async def on_ready(self):
        await self.registrar_views_iniciais()

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        cfg = await st.get_config_cached(guild.id, guild_name=guild.name)
        self.registrar_view(guild.id, (cfg.get("tickets") or {}).get("categories") or [])

    async def registrar_views_iniciais(self):
        for guild in self.client.guilds:
            try:
                cfg = await st.get_config_cached(guild.id, guild_name=guild.name)
            except Exception:
                continue
            self.registrar_view(guild.id, (cfg.get("tickets") or {}).get("categories") or [])

    def registrar_view(self, guild_id: int, categorias: List[Dict[str, Any]]):
        """(Re)cria a view persistente do painel de um servidor."""
        gid = int(guild_id)
        anterior = _views_registradas.get(gid)
        if anterior is not None:
            try:
                self.client.remove_view(anterior)
            except Exception:
                pass
            anterior.categorias = []
            _views_registradas.pop(gid, None)

        cats = [c for c in (categorias or []) if c.get("key") and c.get("label")]
        if not cats:
            return
        view = TicketPanelView(gid, cats)
        self.client.add_view(view)
        _views_registradas[gid] = view

    async def recarregar_view(self, guild_id: int):
        cfg = await st.get_config_cached(guild_id)
        self.registrar_view(int(guild_id),
                            (cfg.get("tickets") or {}).get("categories") or [])

    # ---------- comandos ----------

    painel = app_commands.Group(name="painel", description="Painéis do AURA.")

    @painel.command(name="enviar", description="Publica o painel de tickets neste canal.")
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    async def painel_enviar(self, interaction: discord.Interaction):
        guild = interaction.guild
        cfg = await st.get_config_cached(guild.id, guild_name=guild.name)
        pronto, falta = st.tickets_ready(cfg)
        if not st.module_enabled(cfg, "tickets"):
            return await _erro(interaction, "Módulo de tickets desligado neste servidor.")
        if not pronto:
            return await _erro(interaction, f"Falta configurar: {falta}. Use o painel web.")

        tk = cfg["tickets"]
        cats = tk["categories"]

        view = TicketPanelView(guild.id, cats)
        self.registrar_view(guild.id, cats)

        cor = discord.Color(int(str(tk.get("panel_color") or "#2b6cb0").lstrip("#"), 16))
        embed = discord.Embed(
            title=tk.get("panel_title") or f"Atendimento · {guild.name}",
            description=(tk.get("panel_description")
                         or "Escolha abaixo o assunto do seu ticket. Um staff atende em breve."),
            color=cor,
        )
        if tk.get("panel_image_url"):
            embed.set_image(url=tk["panel_image_url"])
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        linhas = []
        for cat in cats:
            staff_txt = ""
            if cat.get("staff_role_id"):
                staff_txt = f"\n└ staff: <@&{cat['staff_role_id']}>"
            linhas.append(f"{cat.get('emoji') or '🎫'} **{cat.get('label')}**"
                          + (f" — {cat['description'][:120]}" if cat.get("description") else "")
                          + staff_txt)
        embed.add_field(name="Categorias", value="\n".join(linhas)[:4000] or "—", inline=False)
        embed.set_footer(text=f"AURA · {len(cats)} categoria(s) · {guild.name}")

        await interaction.response.send_message(embed=embed, view=view)
        _painel_ids[guild.id] = interaction.channel.id
        runtime.log("INFO", f"[{guild.name}] painel de tickets publicado em "
                            f"#{interaction.channel}", "tickets")

    @painel.command(name="remover", description="Apaga o embed de painel deste canal.")
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    async def painel_remover(self, interaction: discord.Interaction):
        apagados = 0
        async for msg in interaction.channel.history(limit=30):
            if msg.author.id == self.client.user.id and msg.embeds and \
                    msg.embeds[0].title and "Atendimento" in msg.embeds[0].title:
                await msg.delete()
                apagados += 1
                if apagados >= 1:
                    break
        _painel_ids.pop(interaction.guild.id, None)
        await interaction.response.send_message(
            f"🗑️ {apagados} painel(is) removido(s).", ephemeral=True)

    @painel.command(name="atualizar", description="Reposta o painel com a config atual.")
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    async def painel_atualizar(self, interaction: discord.Interaction):
        await self.recarregar_view(interaction.guild.id)
        cfg = await st.get_config_cached(interaction.guild.id,
                                         guild_name=interaction.guild.name)
        await interaction.response.send_message(
            "🔄 Painel atualizado com as categorias atuais do painel web.\n"
            f"Categorias: **{len(cfg['tickets']['categories'])}**.\n"
            "Use `/painel remover` e `/painel enviar` para republish.", ephemeral=True)

    atendimento = app_commands.Group(name="atendimento", description="Gestão de tickets.")

    @atendimento.command(name="fechar", description="Fecha um ticket por ID de thread.")
    @commands.guild_only()
    @app_commands.describe(canal="O ticket (thread) a fechar")
    async def atendimento_fechar(self, interaction: discord.Interaction,
                                  canal: discord.Thread):
        await _fechar_ticket(interaction, interaction.guild.id, interaction.user)

    @atendimento.command(name="assumir", description="Marca o ticket como atendido por você.")
    @commands.guild_only()
    async def atendimento_assumir(self, interaction: discord.Interaction):
        if not isinstance(interaction.channel, discord.Thread):
            return await _erro(interaction, "Rode este comando dentro do ticket.")
        ticket_id = _canal_do_ticket(interaction.channel)
        mongo_db.atualizar_ticket_status(ticket_id, "atendendo", str(interaction.user))
        await interaction.response.send_message(
            f"✅ Ticket marcado como seu.", ephemeral=True)

    @atendimento.command(name="listar", description="Lista os tickets deste servidor.")
    @commands.guild_only()
    @app_commands.describe(limite="Quantos listar (padrão 10)")
    async def atendimento_listar(self, interaction: discord.Interaction, limite: int = 10):
        itens = mongo_db.listar_tickets(guild_id=interaction.guild.id,
                                         limite=max(1, min(50, limite)))
        if not itens:
            return await _erro(interaction, "Nenhum ticket registrado aqui ainda.")
        linhas = []
        for t in itens:
            status = t.get("status", "?")
            marca = {"aberto": "🟢", "atendendo": "🟡", "fechado": "⚪"}.get(status, "⚫")
            linhas.append(f"{marca} **{t.get('tipo')}** · {t.get('user_name')} "
                          f"· {status} · <t:{int(t.get('ts', 0))}:R>")
        embed = discord.Embed(
            title=f"🎫 Tickets · {interaction.guild.name}",
            description="\n".join(linhas)[:3800],
            color=discord.Color.blurple(),
        )
        contagem = mongo_db.contar_tickets(interaction.guild.id)
        embed.set_footer(text=f"abertos: {contagem.get('aberto', 0)} · "
                              f"atendendo: {contagem.get('atendendo', 0)} · "
                              f"fechados: {contagem.get('fechado', 0)}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @atendimento.command(name="abrir", description="Abre um ticket para um membro (staff).")
    @commands.guild_only()
    @app_commands.describe(membro="Para quem é o ticket", assunto="Palavra que identifica a categoria")
    @commands.has_permissions(manage_channels=True)
    async def atendimento_abrir(self, interaction: discord.Interaction,
                                membro: discord.Member, assunto: str = None):
        cfg = await st.get_config_cached(interaction.guild.id,
                                         guild_name=interaction.guild.name)
        pronto, falta = st.tickets_ready(cfg)
        if not pronto:
            return await _erro(interaction, f"Falta configurar: {falta}.")

        cats = cfg["tickets"]["categories"]
        chave = cats[0]["key"]
        if assunto:
            achada = next((c for c in cats if assunto.lower() in c["label"].lower()), None)
            if achada:
                chave = achada["key"]

        sup_id = cfg["tickets"].get("support_channel_id")
        suporte = interaction.guild.get_channel(sup_id) if sup_id else None
        if suporte is None or not isinstance(suporte, discord.TextChannel):
            return await _erro(interaction, "Canal de suporte não configurado.")

        numero = mongo_db.contar_tickets(interaction.guild.id).get("total", 0) + 1
        nome = _nome_da_thread(membro, numero)
        try:
            thread = await suporte.create_thread(
                name=nome, type=discord.ChannelType.private_thread,
                reason=f"AURA ticket aberto por {interaction.user}")
        except discord.HTTPException as exc:
            return await _erro(interaction, f"Não consegui criar a thread: {exc}")

        ticket_id = mongo_db.salvar_ticket(
            membro.id, membro.name, next(c["label"] for c in cats if c["key"] == chave),
            "aberto", guild_id=interaction.guild.id, guild_name=interaction.guild.name,
            ticket_id=str(thread.id), channel_name=thread.name, categoria_key=chave,
            avatar=str(membro.display_avatar.url),
        )
        if ticket_id:
            await thread.edit(topic=f"aura-ticket:{ticket_id}")

        embed = discord.Embed(
            title=f"{next(c['emoji'] for c in cats if c['key'] == chave)} "
                  f"{next(c['label'] for c in cats if c['key'] == chave)}",
            description=f"Ticket aberto por **{interaction.user.mention}** para {membro.mention}.",
            color=discord.Color.blurple(),
        )
        # O campo "Membro" é como o AURA descobre o dono do ticket depois.
        embed.add_field(name="Membro", value=f"{membro.mention} · `{membro.id}`")
        try:
            await thread.add_user(membro)
        except discord.HTTPException:
            pass
        await thread.send(embed=embed, view=TicketAdminView(interaction.guild.id))
        await thread.send(view=StaffTicketView(interaction.guild.id), delete_after=15)
        await interaction.response.send_message(f"✅ Ticket criado: {thread.mention}", ephemeral=True)

    @atendimento.command(name="importar", description="Importa threads antigas como tickets fechados.")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def atendimento_importar(self, interaction: discord.Interaction):
        cfg = await st.get_config_cached(interaction.guild.id,
                                         guild_name=interaction.guild.name)
        sup_id = cfg["tickets"].get("support_channel_id")
        suporte = interaction.guild.get_channel(sup_id) if sup_id else None
        if suporte is None or not isinstance(suporte, discord.TextChannel):
            return await _erro(interaction, "Canal de suporte não configurado.")

        await interaction.response.defer(ephemeral=True)
        importadas = 0
        for th in suporte.threads:
            if not CATEGORIA_RE.match(th.name or ""):
                continue
            if mongo_db.ticket_aberto_do_usuario(interaction.guild.id, _user_do_ticket(th.name)):
                continue
            mongo_db.salvar_ticket(
                _user_do_ticket(th.name), f"usuário {_user_do_ticket(th.name)}",
                "Importado", "fechado", atendente="Importado automaticamente",
                guild_id=interaction.guild.id, guild_name=interaction.guild.name,
                channel_name=th.name,
            )
            importadas += 1

        await interaction.followup.send(
            f"✅ {importadas} thread(s) antiga(s) importada(s).", ephemeral=True)

    @atendimento.command(name="stats", description="Números de tickets deste servidor.")
    @commands.guild_only()
    async def atendimento_stats(self, interaction: discord.Interaction):
        g = interaction.guild.id
        contagem = mongo_db.contar_tickets(g)
        feedback = mongo_db.media_feedback(g)
        embed = discord.Embed(title=f"📊 Tickets · {interaction.guild.name}",
                              color=discord.Color.green())
        embed.add_field(name="Total", value=str(contagem.get("total", 0)), inline=True)
        embed.add_field(name="Abertos", value=str(contagem.get("aberto", 0)), inline=True)
        embed.add_field(name="Atendendo", value=str(contagem.get("atendendo", 0)), inline=True)
        embed.add_field(name="Fechados", value=str(contagem.get("fechado", 0)), inline=True)
        nota = feedback.get("media") or 0
        embed.add_field(name="Avaliação",
                        value=f"{nota:.1f}/5 ⭐\n{feedback.get('total', 0)} resposta(s)",
                        inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)


def _user_do_ticket(nome: str) -> str:
    partes = (nome or "").split("-")
    return partes[1] if len(partes) >= 2 else "desconhecido"


async def setup(client: commands.Bot) -> None:
    await client.add_cog(Atendimento(client))