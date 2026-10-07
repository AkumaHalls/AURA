"""
AURA · Placeholders
-------------------
Permite que o dono do servidor escreva mensagens configuráveis no painel
usando variáveis no estilo `{user}`, `{guild}`, `{ticket}`...

É a mesma ideia do sistema de placeholders da Loritta, Needed para que uma
mensagem de ticket / boas-vindas / punição sirva para Clash of Clans,
Arma 3 ou qualquer outro servidor sem editar código.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict

PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z0-9_]+)(?::([^}]*))?\}")

#: Variáveis que não dependem de contexto (só do servidor).
GUILD_VARS = ("guild", "guild_name", "guild_id", "member_count")

#: Documentação mostrada no painel para o usuário não adivinhar.
DOC: Dict[str, str] = {
    "{user}": "Menção do membro (@nome)",
    "{username}": "Nome do membro sem menção",
    "{user_tag}": "Nome#1234",
    "{user_id}": "ID numérico do membro",
    "{user_avatar}": "URL do avatar do membro",
    "{user_created}": "Data de criação da conta",
    "{user_joined}": "Data de entrada no servidor",
    "{guild}": "Nome do servidor",
    "{guild_id}": "ID do servidor",
    "{member_count}": "Número de membros",
    "{channel}": "Nome do canal",
    "{channel_id}": "ID do canal",
    "{ticket}": "Nome/ID do ticket",
    "{tipo}": "Categoria do ticket",
    "{staff}": "Menção do cargo de atendente",
    "{motivo}": "Motivo informado",
    "{motivo_link}": "Motivo com quebra de linha",
    "{hora}": "Hora atual",
    "{data}": "Data atual",
    "{datetime}": "Data e hora atuais",
    "{timestamp}": "Data/hora em formato unix (para <t:...>)",
    "{emojis}": "Emoji padrão do servidor",
}

ALL_VARS = tuple(DOC.keys())


def _ts(dt: datetime) -> int:
    return int(dt.timestamp())


def render(
    template: str,
    *,
    user: Any = None,
    guild: Any = None,
    channel: Any = None,
    extra: Dict[str, Any] = None,
    member: Any = None,
    default: str = "",
) -> str:
    """
    Substitui os placeholders de `template`.

    `user` e `member` são objetos discord.Member / discord.User. `guild` é
    discord.Guild. Tudo é opcional: qualquer placeholder sem contexto vira
    `default`.
    """
    if not template:
        return ""

    if member is None:
        member = user

    def _resolve(name: str, arg: str = None) -> str:
        key = name.lower()
        val: Any = None

        if key == "user":
            val = getattr(user, "mention", None)
        elif key == "username":
            val = getattr(user, "display_name", None) or getattr(user, "name", None)
        elif key == "user_tag":
            name_ = getattr(user, "display_name", None) or getattr(user, "name", None)
            disc = getattr(user, "discriminator", None)
            val = f"{name_}#{disc}" if name_ and disc and disc != "0" else name_
        elif key == "user_id":
            val = getattr(user, "id", None)
        elif key == "user_avatar":
            av = getattr(user, "display_avatar", None)
            val = getattr(av, "url", None)
        elif key == "user_created":
            created = getattr(user, "created_at", None)
            val = f"<t:{_ts(created)}:R>" if created else None
        elif key == "user_joined":
            joined = getattr(member, "joined_at", None)
            val = f"<t:{_ts(joined)}:R>" if joined else None
        elif key == "guild":
            val = getattr(guild, "name", None)
        elif key == "guild_id":
            val = getattr(guild, "id", None)
        elif key == "member_count":
            count = getattr(guild, "member_count", None)
            val = count if count is not None else (len(getattr(guild, "members", [])) or None)
        elif key == "members":
            count = getattr(guild, "member_count", None)
            val = count if count is not None else (len(getattr(guild, "members", [])) or None)
        elif key == "channel":
            val = getattr(channel, "name", None)
        elif key == "channel_id":
            val = getattr(channel, "id", None)
        elif key == "emojis":
            em = getattr(guild, "emojis", None)
            val = str(em[0]) if em and len(em) else None

        now = datetime.now()
        if key == "hora":
            val = now.strftime("%H:%M")
        elif key == "data":
            val = now.strftime("%d/%m/%Y")
        elif key == "datetime":
            val = now.strftime("%d/%m/%Y às %H:%M")
        elif key == "timestamp":
            val = _ts(now)

        if val is None and extra:
            val = extra.get(name) or extra.get(key)

        if val is None or val == "":
            return default

        val = str(val)
        if arg:
            if arg == "upper":
                val = val.upper()
            elif arg == "lower":
                val = val.lower()
            elif arg == "link":
                if user is not None:
                    name_ = getattr(user, "display_name", None) or getattr(user, "name", "membro")
                    val = f"[{name_}]({getattr(user, 'mention', '')})"
            elif arg.isdigit():
                try:
                    val = val[: int(arg)]
                except ValueError:
                    pass
        return val

    return PLACEHOLDER_RE.sub(lambda m: _resolve(m.group(1), m.group(2)), template)


def used_placeholders(text: str):
    """Lista os placeholders presentes em um texto (para validar no painel)."""
    if not text:
        return []
    return sorted({m.group(0) for m in PLACEHOLDER_RE.finditer(text)})


def unknown_placeholders(text: str):
    """Placeholders escritos pelo usuário que não existem no catálogo."""
    known = {v.strip("{}") for v in ALL_VARS}
    return [
        m.group(0)
        for m in PLACEHOLDER_RE.finditer(text or "")
        if m.group(1).lower() not in known
    ]


def highlight(text: str, user=None, guild=None, channel=None, extra=None) -> str:
    """
    Versão para o painel: mostra o texto com os placeholders já substituídos,
    mostrando `{{user}}` quando não há contexto real.
    """
    if not text:
        return ""
    return PLACEHOLDER_RE.sub(
        lambda m: f"[{_safe(render(m.group(0), user=user, guild=guild, channel=channel, extra=extra, default='')) or m.group(0)}]",
        text,
    )


def _safe(val: str) -> str:
    return val or ""


def preview(text: str) -> str:
    """
    Prévia sem contexto: resolve o que der para resolver com placeholders
    'de sistema' (datas) e deixa os demais visíveis entre chaves.
    """
    if not text:
        return ""
    now = datetime.now()
    fixos = {
        "hora": now.strftime("%H:%M"),
        "data": now.strftime("%d/%m/%Y"),
        "datetime": now.strftime("%d/%m/%Y às %H:%M"),
        "timestamp": _ts(now),
    }

    def _sub(m: "re.Match[str]") -> str:
        name = m.group(1).lower()
        if name in fixos:
            return fixos[name]
        return m.group(0)

    return PLACEHOLDER_RE.sub(_sub, text)
