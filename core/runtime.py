"""
AURA · Runtime / Ponte Bot <-> Painel
-------------------------------------
O painel web roda numa thread do mesmo processo do bot. Isso permite usar o
cliente do discord.py de verdade dentro do Flask: os seletores de canal e
cargo no painel mostram os canais/cargos REAIS do servidor, em vez de pedir
para digitar ID no escuro.

Também concentra o estado volátil (uptime, ping, latência, métricas) e o
sinal de "sincronizar comandos", que antes era um arquivo `sync_signal.txt`
varrido por polling a cada 5 segundos.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import os
import threading
import time
from typing import Any, Dict, List, Optional

_client: Any = None
_loop: Optional[asyncio.AbstractEventLoop] = None
_lock = threading.Lock()

#: Evento disparado quando o painel pede re-sync dos slash commands.
_sync_event: Optional[asyncio.Event] = None

#: Estado colhido pelo bot a cada few segundos (usado no dashboard).
bot_status: Dict[str, Any] = {
    "online": False,
    "bot_id": None,
    "bot_name": None,
    "bot_avatar": None,
    "guild_count": 0,
    "user_count": 0,
    "ping_ms": 0,
    "uptime_seconds": 0,
    "cog_count": 0,
    "command_count": 0,
    "memory_mb": 0,
    "cpu_percent": 0,
    "started_at": None,
    "error": None,
}

#: Últimas mensagens de log do bot, para o painel mostrar o que está acontecendo.
_log_buffer: List[Dict[str, Any]] = []
LOG_BUFFER_SIZE = 400


# --------------------------------------------------------------------------
# Registro do cliente
# --------------------------------------------------------------------------

def register_client(client: Any, loop: asyncio.AbstractEventLoop = None) -> None:
    global _client, _loop, _sync_event
    if loop is None:
        loop = getattr(client, "loop", None)
    with _lock:
        _client = client
        _loop = loop
        try:
            _sync_event = asyncio.Event()
        except RuntimeError:
            _sync_event = None
    bot_status["online"] = True
    bot_status["started_at"] = time.time()


def unregister_client() -> None:
    global _client, _loop
    with _lock:
        _client = None
        _loop = None
    bot_status["online"] = False


def get_client() -> Any:
    return _client


def get_loop() -> Optional[asyncio.AbstractEventLoop]:
    return _loop


def is_ready() -> bool:
    c = _client
    return bool(c and not c.is_closed() and getattr(c, "is_ready", lambda: False)())


# --------------------------------------------------------------------------
# Executar corrotinas do bot a partir da thread do Flask
# --------------------------------------------------------------------------

def run_coro(coro, timeout: float = 12.0):
    """
    Executa uma corrotina a partir de outra thread e devolve o resultado.

    Se o bot ja tem loop, usa o loop dele. Se ainda nao conectou (painel aberto
    antes do bot subir), roda num loop descartavel, assim o painel continua
    salvando configuracao mesmo com o Discord fora do ar. Dentro do loop do bot
    devolve None, para nao travar a event loop esperando por ela mesma.
    """
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None

    loop = _loop
    if loop is None or loop.is_closed():
        if running is not None:
            return None
        try:
            return asyncio.run(asyncio.wait_for(coro, timeout))
        except Exception as exc:
            log("ERRO", f"falha ao rodar tarefa fora do bot: {exc}", source="painel")
            return None

    if running is loop:
        return None
    fut = asyncio.run_coroutine_threadsafe(coro, loop)
    try:
        return fut.result(timeout=timeout)
    except (asyncio.TimeoutError, concurrent.futures.CancelledError, concurrent.futures.TimeoutError):
        return None
    except Exception:
        import traceback
        log("ERRO", traceback.format_exc(limit=3), source="painel")
        return None


# --------------------------------------------------------------------------
# Sinal de sincronização de comandos
# --------------------------------------------------------------------------

def request_command_sync() -> bool:
    """Chamado pelo painel: pede re-sync dos slash commands."""
    ev = _sync_event
    if ev is None:
        return False
    loop = _loop
    if loop is None or loop.is_closed():
        return False
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if running is loop:
        ev.set()
        return True
    loop.call_soon_threadsafe(ev.set)
    return True


async def wait_sync_request(timeout: float = 5.0) -> bool:
    """Consumido pelo bot no setup_hook."""
    global _sync_event
    if _sync_event is None:
        try:
            _sync_event = asyncio.Event()
        except RuntimeError:
            return False
    try:
        await asyncio.wait_for(_sync_event.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        return False
    _sync_event.clear()
    return True


# --------------------------------------------------------------------------
# Log buffer
# --------------------------------------------------------------------------

def log(level: str, message: str, source: str = "bot") -> None:
    _log_buffer.append({
        "ts": time.time(),
        "level": str(level).upper()[:10],
        "message": str(message)[:1000],
        "source": source,
    })
    if len(_log_buffer) > LOG_BUFFER_SIZE:
        del _log_buffer[: len(_log_buffer) - LOG_BUFFER_SIZE]


def get_logs(limit: int = 120, level: str = None) -> List[Dict[str, Any]]:
    items = _log_buffer[-limit:]
    if level and level.lower() != "all":
        items = [i for i in items if i["level"] == level.upper()]
    return list(reversed(items))


def clear_logs() -> None:
    _log_buffer.clear()


# --------------------------------------------------------------------------
# Métricas
# --------------------------------------------------------------------------

def update_status() -> Dict[str, Any]:
    """Reamostra as métricas do bot. Chamado pelo próprio bot a cada 30s."""
    c = _client
    if c is None:
        bot_status["online"] = False
        return bot_status

    try:
        me = c.user
        bot_status["bot_id"] = me.id
        bot_status["bot_name"] = me.name
        bot_status["bot_avatar"] = str(me.display_avatar.url) if me.display_avatar else None
        bot_status["guild_count"] = len(c.guilds)
        bot_status["user_count"] = sum(g.member_count or 0 for g in c.guilds)
        bot_status["ping_ms"] = round(c.latency * 1000)
        bot_status["cog_count"] = len(c.cogs)
        bot_status["command_count"] = len(c.tree.get_commands())
        started = bot_status.get("started_at") or time.time()
        bot_status["uptime_seconds"] = int(time.time() - started)
        bot_status["online"] = not c.is_closed()

        try:
            import psutil
            proc = psutil.Process(os.getpid())
            bot_status["memory_mb"] = round(proc.memory_info().rss / (1024 * 1024), 1)
            bot_status["cpu_percent"] = round(proc.cpu_percent(interval=None), 1)
        except Exception:
            pass
    except Exception as exc:  # pragma: no cover
        bot_status["error"] = str(exc)
    return bot_status


# --------------------------------------------------------------------------
# Snapshots do Discord para o painel
# --------------------------------------------------------------------------

def guild_summary(guild: Any) -> Dict[str, Any]:
    return {
        "id": str(guild.id),
        "name": guild.name,
        "icon": str(guild.icon.url) if guild.icon else None,
        "member_count": guild.member_count or 0,
        "owner_id": str(guild.owner_id) if guild.owner_id else None,
        "created_at": guild.created_at.timestamp() if guild.created_at else None,
        "bot_perms": guild.me.guild_permissions.administrator if guild.me else False,
        "channels": len(guild.channels),
        "roles": len(guild.roles),
    }


def list_guild_summaries() -> List[Dict[str, Any]]:
    c = _client
    if c is None:
        return []
    return [guild_summary(g) for g in sorted(c.guilds, key=lambda g: g.name.lower())]


def channel_payload(ch: Any) -> Dict[str, Any]:
    return {
        "id": str(ch.id),
        "name": getattr(ch, "name", "?"),
        "type": ch.type.name if hasattr(ch.type, "name") else str(ch.type),
        "parent": str(ch.parent.name) if getattr(ch, "parent", None) else None,
        "category_id": str(ch.category_id) if getattr(ch, "category_id", None) else None,
        "position": getattr(ch, "position", 0),
    }


def role_payload(role: Any, bot_top_position: int = 999) -> Dict[str, Any]:
    return {
        "id": str(role.id),
        "name": role.name,
        "position": role.position,
        "managed": getattr(role, "managed", False),
        "mentionable": getattr(role, "mentionable", True),
        "color": f"#{role.color.value:06x}",
        "assignable": role.position < bot_top_position,
    }


def guild_snapshot(guild_id: Any) -> Optional[Dict[str, Any]]:
    """
    Tudo que o painel precisa para montar os seletores de um servidor.
    Roda dentro do loop do bot e devolve apenas dicionários serializáveis.
    """
    c = _client
    if c is None:
        return None
    guild = c.get_guild(int(guild_id)) if str(guild_id).isdigit() else None
    if guild is None:
        return None

    me = guild.me
    top_pos = me.top_role.position if me else 999

    channels = []
    for ch in guild.channels:
        channels.append(channel_payload(ch))

    return {
        **guild_summary(guild),
        "bot_user_id": str(guild.me.id) if guild.me else None,
        "bot_top_role_position": top_pos,
        "channels": sorted(channels, key=lambda x: (x["type"], x["position"])),
        "roles": sorted(
            (role_payload(r, top_pos) for r in guild.roles if not r.managed),
            key=lambda x: -x["position"],
        ),
        "emojis": [f"{e.name}:{e.id}" for e in list(guild.emojis)[:120]],
    }


# --------------------------------------------------------------------------
# Ações diretas do painel sobre o Discord
# --------------------------------------------------------------------------

async def _deploy_ticket_panel(guild_id: Any, channel_id: Any) -> Dict[str, Any]:
    """Publica o painel de tickets de um servidor, lendo a config atual."""
    from discord import Embed

    c = _client
    guild = c.get_guild(int(guild_id)) if str(guild_id).isdigit() else None
    if guild is None:
        return {"ok": False, "erro": "servidor não encontrado (o bot está nele?)"}
    channel = guild.get_channel(int(channel_id)) if str(channel_id).isdigit() else None
    if channel is None:
        return {"ok": False, "erro": "canal não encontrado nesse servidor"}
    if not hasattr(channel, "send"):
        return {"ok": False, "erro": "esse tipo de canal não aceita mensagens"}

    from core.settings import get_config_cached

    cfg = await get_config_cached(guild.id)
    tk = cfg.get("tickets") or {}
    categorias = tk.get("categories") or []
    if not categorias:
        return {"ok": False, "erro": "nenhuma categoria configurada"}

    cor = str(tk.get("panel_color") or "#f1c40f").lstrip("#")
    titulo = tk.get("panel_title") or f"🛡️ Central de Atendimento - {guild.name} 🛡️"
    descricao = tk.get("panel_description") or (
        "Bem-vindo à central de ajuda! Use o menu abaixo para selecionar o "
        "motivo do seu contato e abrir um ticket. Um líder ou co-líder irá te ajudar."
    )
    try:
        cobj = Embed(title=titulo, description=descricao, color=int(cor, 16))
    except ValueError:
        cobj = Embed(title=titulo, description=descricao)

    if tk.get("panel_image_url"):
        cobj.set_image(url=tk["panel_image_url"])
    elif guild.icon:
        cobj.set_image(url=guild.icon.url)
    cobj.set_footer(text=f"Atendimento do Clã {guild.name}")

    # Sem campo "Categorias": o próprio DropDown já mostra os tópicos com emoji
    # e descrição. Listar as duas vezes poluía o embed e ocupava a tela toda.
    cog = c.get_cog("Atendimento")
    if cog is None:
        return {"ok": False, "erro": "cog de tickets não carregado"}

    from cogs.atendimento import TicketPanelView

    try:
        cog.registrar_view(guild.id, categorias)
    except Exception as exc:
        return {"ok": False, "erro": f"não consegui registrar a view: {exc}"}

    apagados = await _remover_paineis_antigos(channel)
    try:
        msg = await channel.send(embed=cobj, view=TicketPanelView(guild.id, categorias))
    except Exception as exc:
        return {"ok": False, "erro": f"falha ao enviar: {exc}"}

    return {"ok": True, "channel_id": str(channel.id), "message_id": str(msg.id),
            "categorias": len(categorias), "removidos": apagados}


async def _remover_paineis_antigos(channel, limite: int = 5) -> int:
    """
    Apaga painéis de tickets antigos do canal.

    Sem isso o embed velho continua publicado junto com o novo, e a pessoa vê as
    duas versões — foi o que aconteceu quando o painel antigo continuou no canal
    depois da troca para DropDown.
    """
    import discord

    apagados = 0
    try:
        async for msg in channel.history(limit=30):
            if _client is None or msg.author.id != _client.user.id or not msg.embeds:
                continue
            titulo = msg.embeds[0].title or ""
            if "Central de Atendimento" in titulo or "Atendimento" in titulo:
                try:
                    await msg.delete()
                    apagados += 1
                except discord.Forbidden:
                    continue
                if apagados >= limite:
                    break
    except (discord.Forbidden, discord.HTTPException, AttributeError):
        pass
    return apagados


async def _send_preview(channel_id: Any, content: str) -> Dict[str, Any]:
    c = _client
    ch = c.get_channel(int(channel_id)) if str(channel_id).isdigit() else None
    if ch is None or not hasattr(ch, "send"):
        return {"ok": False, "erro": "Canal não encontrado"}
    if not content.strip():
        return {"ok": False, "erro": "mensagem vazia"}
    try:
        msg = await ch.send(content[:1900])
    except Exception as exc:
        return {"ok": False, "erro": f"falha ao enviar: {exc}"}
    return {"ok": True, "channel_id": str(ch.id), "message_id": str(msg.id)}


async def _sync_commands(guild_id: Any = None) -> Dict[str, Any]:
    c = _client
    try:
        if guild_id:
            guild = c.get_guild(int(guild_id))
            if guild is None:
                return {"ok": False, "erro": "Servidor não encontrado"}
            c.tree.clear_commands(guild=guild)
            n = await c.tree.sync(guild=guild)
            return {"ok": True, "detalhe": f"{len(n)} comandos publicados em {guild.name}"}

        total = 0
        for guild in c.guilds:
            try:
                c.tree.clear_commands(guild=guild)
                n = await c.tree.sync(guild=guild)
                total += len(n)
            except Exception:
                pass
        n = await c.tree.sync()
        return {"ok": True, "detalhe": f"{len(n)} comandos globais + {total} por servidor"}
    except Exception as exc:
        return {"ok": False, "erro": str(exc)}


async def _validate_config(guild_id: Any) -> Dict[str, Any]:
    """Confere, contra o servidor real, se os IDs configurados existem."""
    c = _client
    guild = c.get_guild(int(guild_id)) if str(guild_id).isdigit() else None
    if guild is None:
        return {"ok": False, "erro": "Servidor não encontrado (o bot está nele?)"}

    from core.settings import get_config_cached

    cfg = await get_config_cached(guild.id, force=True)
    problemas: List[str] = []

    def checar(campo: str, oid: Any) -> None:
        if not oid:
            return
        try:
            n = int(str(oid))
        except ValueError:
            problemas.append(f"{campo}: valor inválido ({oid})")
            return
        if guild.get_channel(n) is None and guild.get_role(n) is None:
            problemas.append(f"{campo}: ID {n} não existe neste servidor")

    for key in ("panel_channel_id", "support_channel_id", "category_id",
                "log_channel_id", "transcript_channel_id"):
        checar(f"tickets.{key}", cfg["tickets"].get(key))
    checar("tickets.staff_role_id", cfg["tickets"].get("staff_role_id"))
    for cat in cfg["tickets"].get("categories") or []:
        checar(f"ticket '{cat['label']}'.staff_role_id", cat.get("staff_role_id"))

    checar("moderation.log_channel_id", cfg["moderation"].get("log_channel_id"))
    checar("moderation.punish_channel_id", cfg["moderation"].get("punish_channel_id"))
    checar("autorole.channel_id", cfg["autorole"].get("channel_id"))
    checar("autorole.give_role_id", cfg["autorole"].get("give_role_id"))
    checar("autorole.deny_role_id", cfg["autorole"].get("deny_role_id"))
    checar("boas_vindas.channel_id", cfg["boas_vindas"].get("channel_id"))
    checar("provas.notify_channel_id", cfg["provas"].get("notify_channel_id"))
    checar("contador.channel_id", cfg["contador"].get("channel_id"))
    checar("games.coc.log_channel_id", cfg["games"]["coc"].get("log_channel_id"))
    checar("games.arma3.log_channel_id", cfg["games"]["arma3"].get("log_channel_id"))

    perms_faltando = []
    me = guild.me
    if me:
        g = me.guild_permissions
        precisa = [
            ("manage_threads", "Gerenciar Tópicos (tickets)"),
            ("manage_channels", "Gerenciar Canais"),
            ("manage_roles", "Gerenciar Cargos"),
            ("kick_members", "Expulsar Membros"),
            ("ban_members", "Banir Membros"),
            ("moderate_members", "Moderar Membros (timeout)"),
        ]
        for attr, nome in precisa:
            if not getattr(g, attr, False):
                perms_faltando.append(nome)

    return {
        "ok": not problemas and not perms_faltando,
        "problemas": problemas,
        "perms_faltando": perms_faltando,
    }
