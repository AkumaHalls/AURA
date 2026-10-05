"""
AURA · Assistente Unificado de Registros e Administração
--------------------------------------------------------
Schema central de configuração POR SERVIDOR.

Substitui as variáveis de ambiente / .env que antes Holdsapenas com um servidor.
Cada guild tem seu próprio documento na coleção `guild_configs`, e os cogs leem
a configuração daqui em vez de leer IDs hard-coded.

Nada neste módulo acessa a rede: é só schema + defaults + cache em memória.
A persistência fica em `mongo_db`.
"""

from __future__ import annotations

import copy
import os
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple

# --------------------------------------------------------------------------
# Constantes
# --------------------------------------------------------------------------

#: Perfis de servidor disponíveis. O perfil muda os *defaults sugeridos*
#: no painel (categorias de ticket, nomes, etc) mas nunca impede
#: configuração manual — o AURA não é preso a um único jogo.
PERFIS = ("generico", "coc", "arma3")

#: Ações possíveis para um filtro de moderação.
ACOES_MODERACAO = ("nada", "apagar", "avisar", "timeout", "banir")

#: Como o filtro de links deve se comportar.
MODOS_LINK = ("desativado", "bloquear_tudo", "bloquear_convites", "lista_branca")

#: Severidade de um termo bloqueado — usada na escalada automática.
SEVERIDADES = ("baixa", "media", "alta")

#: Todos os módulos que o painel consegue ligar/desligar por servidor.
MODULOS = (
    "tickets",
    "moderacao",
    "autorole",
    "boas_vindas",
    "provas",
    "logs",
    "contador",
    "games",
)


# --------------------------------------------------------------------------
# Defaults
# --------------------------------------------------------------------------

DEFAULT_TICKET_CATEGORIES: List[Dict[str, Any]] = [
    {
        "key": "outros",
        "label": "Outros Assuntos",
        "emoji": "❔",
        "description": "Seu assunto não está na lista? Sem problemas, conte pra gente.",
        "prompt": "Descreva em detalhes o motivo do seu contato.",
        "staff_role_id": None,
    },
]

DEFAULT_TICKETS: Dict[str, Any] = {
    "enabled": False,
    "panel_channel_id": None,
    "support_channel_id": None,
    "staff_role_id": None,
    "category_id": None,
    "log_channel_id": None,
    "transcript_channel_id": None,
    "panel_title": "Central de Atendimento",
    "panel_description": (
        "Bem-vindo ao suporte! Selecione o motivo do seu contato abaixo "
        "e abra um ticket. Nossa equipe responderá em breve."
    ),
    "panel_color": "#5865F2",
    "panel_image_url": None,
    "categories": DEFAULT_TICKET_CATEGORIES,
    "max_open_per_user": 1,
    "auto_close_days": 0,
    "close_delay_seconds": 5,
    "ticket_name_format": "{emoji}┃{username}-{user_id}",
    "welcome_message": (
        "Oiiie {user}, **tudo bem?**\n\n"
        "Seja muito bem-vindo(a) ao atendimento do **{guild}**!\n"
        "Um {staff} já foi chamado e vai te atender em instantes."
    ),
    "message_template": (
        "Novo ticket de **{tipo}**\n"
        "Membro: {user}\n"
        "Aberto: {opened_at}"
    ),
    "close_button_label": "Fechar Ticket",
    "rating_enabled": True,
    "rating_question": "Como foi seu atendimento?",
}

DEFAULT_MODERATION: Dict[str, Any] = {
    "enabled": False,
    "log_channel_id": None,
    "punish_channel_id": None,
    "ignored_channels": [],
    "ignored_roles": [],
    "words": {
        "enabled": True,
        "action": "apagar",
        "terms": [],
        "message": "Palavra proibida detectada. Leia as regras do servidor.",
    },
    "links": {
        "enabled": True,
        "mode": "bloquear_convites",
        "allowed_domains": [],
        "action": "apagar",
        "message": "Links não são permitidos neste canal.",
    },
    "invites": {
        "enabled": True,
        "action": "apagar",
        "message": "Convites de servidores não são permitidos aqui.",
    },
    "caps": {
        "enabled": False,
        "min_chars": 12,
        "percent": 70,
        "action": "apagar",
        "message": "Evite escrever tudo em caixa alta.",
    },
    "flood": {
        "enabled": True,
        "max_messages": 6,
        "window_seconds": 8,
        "action": "apagar",
        "message": "Você está enviando mensagens muito rápido. Faça uma pausa.",
    },
    "duplicate": {
        "enabled": True,
        "max_repeats": 3,
        "window_seconds": 30,
        "action": "apagar",
        "message": "Mensagem repetida demais.",
    },
    "mentions": {
        "enabled": True,
        "max_user_mentions": 6,
        "max_role_mentions": 2,
        "action": "apagar",
        "message": "Você mencionou pessoas demais nessa mensagem.",
    },
    "zerospace": {
        "enabled": True,
        "min_chars": 12,
        "action": "apagar",
        "message": "Mensagem com caracteres invisíveis.",
    },
    "escalation": {
        "enabled": True,
        "steps": [
            {"after": 1, "action": "avisar"},
            {"after": 3, "action": "timeout", "seconds": 300},
            {"after": 5, "action": "timeout", "seconds": 3600},
            {"after": 8, "action": "banir"},
        ],
        "dm_user": True,
        "exempt_roles": [],
    },
}

DEFAULT_AUTOROLE: Dict[str, Any] = {
    "enabled": False,
    "channel_id": None,
    "keyword": "liberar",
    "give_role_id": None,
    "deny_role_id": None,
    "delete_message": True,
    "delete_delay_seconds": 10,
    "welcome_message": "✅ Acesso liberado, {user}! Seja bem-vindo(a).",
    "log_channel_id": None,
}

DEFAULT_BOAS_VINDAS: Dict[str, Any] = {
    "enabled": False,
    "channel_id": None,
    "message": "Bem-vindo(a) ao **{guild}**, {user}!",
    "leave_message": "{user} saiu do servidor. Já我们是 {members} membros.",
    "send_dm": False,
    "dm_message": "Bem-vindo(a) ao **{guild}**!",
    "log_channel_id": None,
}

DEFAULT_PROVAS: Dict[str, Any] = {
    "enabled": False,
    "bank_name": "B.A.D",
    "title": "Exame de Qualificação",
    "require_approval": True,
    "approval_role_id": None,
    "notify_channel_id": None,
    "backup_channel_id": None,
    "time_per_question": 120,
    "pass_score": 7,
    "cooldown_days": 3,
    "shuffle_answers": True,
}

DEFAULT_LOGS: Dict[str, Any] = {
    "enabled": True,
    "join_channel_id": None,
    "leave_channel_id": None,
    "message_channel_id": None,
    "mod_channel_id": None,
    "boost_channel_id": None,
    "log_join": True,
    "log_leave": True,
    "log_boost": True,
    "log_message_delete": True,
    "log_role_change": False,
}

DEFAULT_CONTADOR: Dict[str, Any] = {
    "enabled": False,
    "channel_id": None,
    "channel_name": "👥 Membros: {count}",
    "category_name": "Status do Servidor",
}

DEFAULT_GAMES: Dict[str, Any] = {
    "coc": {
        "enabled": False,
        "clan_tag": None,
        "registration_channel_id": None,
        "log_channel_id": None,
        "approval_channel_id": None,
        "verify_hours": 1,
        "kick_message": "Você foi removido do servidor por não fazer mais parte do clã.",
        "roles": {"member": None, "elder": None, "coleader": None},
        "status_channel_ids": {},
    },
    "arma3": {
        "enabled": False,
        "whitelist_channel_id": None,
        "log_channel_id": None,
        "role_player": None,
        "role_whitelisted": None,
        "role_vip": None,
        "auto_tag_on_join": None,
        "sync_tags_on_message": False,
        "messages": {},
    },
}


def default_config(guild_id: str, guild_name: str = "", guild_icon: str = None) -> Dict[str, Any]:
    """Configuração-base de um servidor novo: tudo desligado, sem IDs herdados."""
    return {
        "guild_id": str(guild_id),
        "guild_name": guild_name,
        "guild_icon": guild_icon,
        "profile": "generico",
        "prefix": "-br",
        "locale": "pt-BR",
        "owner_ids": [],
        "modules": {name: False for name in MODULOS},
        "tickets": copy.deepcopy(DEFAULT_TICKETS),
        "moderation": copy.deepcopy(DEFAULT_MODERATION),
        "autorole": copy.deepcopy(DEFAULT_AUTOROLE),
        "boas_vindas": copy.deepcopy(DEFAULT_BOAS_VINDAS),
        "provas": copy.deepcopy(DEFAULT_PROVAS),
        "logs": copy.deepcopy(DEFAULT_LOGS),
        "contador": copy.deepcopy(DEFAULT_CONTADOR),
        "games": copy.deepcopy(DEFAULT_GAMES),
        "created_at": time.time(),
        "updated_at": time.time(),
        "updated_by": None,
    }


# --------------------------------------------------------------------------
# Presets por perfil de servidor
# --------------------------------------------------------------------------

PRESET_TICKET_CATEGORIES: Dict[str, List[Dict[str, Any]]] = {
    "generico": [
        {"key": "suporte", "label": "Suporte", "emoji": "🛟",
         "description": "Dúvida geral ou problema técnico.",
         "prompt": "Descreva o que está acontecendo.",
         "staff_role_id": None},
        {"key": "denuncia", "label": "Denunciar um Membro", "emoji": "🚨",
         "description": "Relate uma infração cometida por um membro.",
         "prompt": "Descreva o que aconteceu e envie prints como prova.",
         "staff_role_id": None},
        {"key": "apelo", "label": "Apelar de uma Punição", "emoji": "⚖️",
         "description": "Conteste uma punição aplicada.",
         "prompt": "Informe seu ID, o motivo da punição e por que ela deve ser revista.",
         "staff_role_id": None},
        {"key": "sugestao", "label": "Sugestão", "emoji": "💡",
         "description": "Ideias para melhorar o servidor.",
         "prompt": "Escreva sua sugestão com o máximo de detalhe possível.",
         "staff_role_id": None},
        {"key": "outros", "label": "Outro Assunto", "emoji": "❔",
         "description": "Qualquer outra coisa.",
         "prompt": "Descreva em detalhes o motivo do contato.",
         "staff_role_id": None},
    ],
    "coc": [
        {"key": "regras_cla", "label": "Dúvidas sobre Regras do Clã", "emoji": "📜",
         "description": "Dúvidas sobre as regras do clã.",
         "prompt": "Descreva sua dúvida sobre as regras do clã.",
         "staff_role_id": None},
        {"key": "guerras_cwl", "label": "Guerras ou CWL", "emoji": "⚔️",
         "description": "Ajuda com Guerra de Clãs ou Liga de Guerra.",
         "prompt": "Detalhe sua dúvida sobre a guerra e envie um print da base inimiga, se houver.",
         "staff_role_id": None},
        {"key": "doacoes", "label": "Problemas com Doações", "emoji": "🛡️",
         "description": "Tropas erradas, falta de doação, etc.",
         "prompt": "Informe qual o problema com as doações (tropas erradas, falta de doação...).",
         "staff_role_id": None},
        {"key": "denuncia", "label": "Denunciar um Membro", "emoji": "🚨",
         "description": "Relate uma infração Cometida por um membro.",
         "prompt": "Descreva o que aconteceu e envie prints como prova.",
         "staff_role_id": None},
        {"key": "apelo_ban", "label": "Apelar de um Banimento", "emoji": "🔨",
         "description": "Conteste uma punição aplicada no clã.",
         "prompt": "Informe sua TAG de jogador, o motivo do ban e por que a punição deve ser revista.",
         "staff_role_id": None},
        {"key": "sugestao", "label": "Sugestões para o Clã", "emoji": "💡",
         "description": "Ideias para melhorar o clã.",
         "prompt": "Escreva sua sugestão da forma mais detalhada possível.",
         "staff_role_id": None},
        {"key": "recrutamento", "label": "Recrutamento", "emoji": "📈",
         "description": "Tenha interesse em recrutar alguém.",
         "prompt": "Conte como funciona o recrutamento e para quem você quer recrutar.",
         "staff_role_id": None},
        {"key": "outros", "label": "Outros Assuntos", "emoji": "❔",
         "description": "Qualquer outra dúvida.",
         "prompt": "Descreva em detalhes o motivo do contato.",
         "staff_role_id": None},
    ],
    "arma3": [
        {"key": "recrutamento", "label": "Recrutamento de Jogador", "emoji": "🎖️",
         "description": "Quero entrar para a unidade.",
         "prompt": "Informe sua idade, sua região/fuso horário e sua disponibilidade.",
         "staff_role_id": None},
        {"key": "whitelist", "label": "Dúvida sobre Whitelist", "emoji": "📋",
         "description": "Preciso de ajuda com a whitelist.",
         "prompt": "Informe sua Tag/Steam ID e em qual etapa da whitelist você está.",
         "staff_role_id": None},
        {"key": "treinamento", "label": "Treinamento e Mentoria", "emoji": "🎓",
         "description": "Quero aprender com um membro experiente.",
         "prompt": "Descreva o que você quer aprender e sua experiência atual.",
         "staff_role_id": None},
        {"key": "reportar", "label": "Reportar Jogador", "emoji": "🚨",
         "description": "Comunique uma quebra de regra.",
         "prompt": "Descreva o que aconteceu, onde e quando, e envie provas.",
         "staff_role_id": None},
        {"key": "evento", "label": "Eventos e Operações", "emoji": "🗓️",
         "description": "Participar de eventos e operações.",
         "prompt": "Qual evento você quer participar e por quê?",
         "staff_role_id": None},
        {"key": "duvida_jogo", "label": "Dúvida sobre o Jogo", "emoji": "🎮",
         "description": "Dúvidas sobre mods, servers e mecânicas.",
         "prompt": "Descreva sua dúvida sobre o Arma 3.",
         "staff_role_id": None},
        {"key": "outros", "label": "Outros Assuntos", "emoji": "❔",
         "description": "Qualquer outro assunto.",
         "prompt": "Descreva em detalhes o motivo do contato.",
         "staff_role_id": None},
    ],
}


def preset_config(profile: str) -> Optional[Dict[str, Any]]:
    """
    Gera a config-base de um perfil (clonável a partir do painel).

    Devolve `None` para perfil desconhecido: o painel trata isso como "não
    faça nada", em vez de gravar uma config padrão por cima da que existe.
    """
    if profile not in PRESET_TICKET_CATEGORIES:
        return None
    cfg = default_config("0")
    cfg["profile"] = profile
    cfg["tickets"]["categories"] = copy.deepcopy(PRESET_TICKET_CATEGORIES[profile])
    return cfg


# --------------------------------------------------------------------------
# Cache em memória
# --------------------------------------------------------------------------
# Os cogs são acionados a cada mensagem; ir ao MongoDB sempre seria caro.
# O cache é invalidado quando o painel salva (via `invalidate`) e tem um
# TTL curto como rede de segurança para quando o bot roda em processo
# separado do painel.

_cache: Dict[str, Dict[str, Any]] = {}
_cache_at: Dict[str, float] = {}
CACHE_TTL = 300.0  # 5 minutos


def invalidate(guild_id: Optional[str] = None) -> None:
    """Limpa o cache. Com guild_id, só o servidor affected; sem, limpa tudo."""
    if guild_id is None:
        _cache.clear()
        _cache_at.clear()
        return
    _cache.pop(str(guild_id), None)
    _cache_at.pop(str(guild_id), None)


def put_cache(config: Dict[str, Any]) -> None:
    gid = str(config.get("guild_id"))
    _cache[gid] = config
    _cache_at[gid] = time.time()


def get_cached(guild_id: str) -> Optional[Dict[str, Any]]:
    gid = str(guild_id)
    ts = _cache_at.get(gid)
    if ts is None:
        return None
    if time.time() - ts > CACHE_TTL:
        invalidate(gid)
        return None
    return _cache.get(gid)


def cached_guild_ids() -> List[str]:
    return list(_cache.keys())


# --------------------------------------------------------------------------
# Loader assíncrono (usado pelos cogs)
# --------------------------------------------------------------------------

async def get_config_cached(guild_id, force: bool = False,
                            guild_name: str = "", guild_icon: str = None) -> Dict[str, Any]:
    """
    Devolve a configuração normalizada de um servidor, usando o cache quando possível.

    É a função que os cogs chamam em `on_message` e afins — por isso vai no
    cache e só toca o MongoDB quando o cache não existe ou expirou.
    """
    gid = str(guild_id)

    if not force:
        cached = get_cached(gid)
        if cached is not None:
            return cached

    import mongo_db

    raw = mongo_db.get_guild_config_raw(gid)
    if raw is None:
        cfg = default_config(gid, guild_name, guild_icon)
    else:
        cfg = normalize(raw, gid, raw.get("guild_name") or guild_name,
                        raw.get("guild_icon") or guild_icon)

    put_cache(cfg)
    return cfg


async def get_many_configs(guild_ids) -> Dict[str, Dict[str, Any]]:
    """Carrega várias configs de uma vez (usado pelo painel e pelo on_ready)."""
    out: Dict[str, Dict[str, Any]] = {}
    for gid in guild_ids:
        out[str(gid)] = await get_config_cached(gid)
    return out


async def save_config(cfg: Dict[str, Any], autor: str = "painel") -> bool:
    """Persiste a config e invalida o cache do servidor."""
    import mongo_db

    gid = str(cfg.get("guild_id"))
    ok = mongo_db.upsert_guild_config(gid, cfg, updated_by=autor)
    invalidate(gid)
    return ok


# --------------------------------------------------------------------------
# Normalização / validação
# --------------------------------------------------------------------------

#: Limite de categorias num select do Discord.
MAX_TICKET_CATEGORIES = 25


def _as_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    if value is None or value == "":
        return default
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in ("1", "true", "on", "sim", "yes", "y")


def _as_choice(value: Any, choices, default):
    if value in choices:
        return value
    if isinstance(value, str):
        low = value.strip().lower()
        for c in choices:
            if c.lower() == low:
                return c
    return default


_SLUG_RE = re.compile(r"[^a-z0-9_]+")


def slugify(text: str, fallback: str = "cat") -> str:
    slug = _SLUG_RE.sub("_", (text or "").strip().lower()).strip("_")
    return slug[:32] or fallback


def normalize_categories(categories: Any) -> List[Dict[str, Any]]:
    """Garante que cada categoria tenha key/label/emoji/prompt válidos e únicos."""
    if not isinstance(categories, list):
        return copy.deepcopy(DEFAULT_TICKET_CATEGORIES)

    out: List[Dict[str, Any]] = []
    seen: set = set()

    for item in categories[:MAX_TICKET_CATEGORIES]:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()[:100]
        if not label:
            continue
        key = slugify(str(item.get("key") or label), f"cat{len(out) + 1}")
        while key in seen:
            key = f"{key}_{len(seen)}"
        seen.add(key)

        out.append({
            "key": key,
            "label": label,
            "emoji": (str(item.get("emoji") or "❔").strip() or "❔")[:8],
            "description": str(item.get("description") or "").strip()[:1500],
            "prompt": str(item.get("prompt") or "").strip()[:1500],
            "staff_role_id": _as_int(item.get("staff_role_id")),
        })

    if not out:
        return copy.deepcopy(DEFAULT_TICKET_CATEGORIES)
    return out


def normalize_terms(terms: Any) -> List[Dict[str, Any]]:
    """Normaliza a lista de termos proibidos. Cada item vira um 'ban word'."""
    if isinstance(terms, str):
        terms = [t for t in re.split(r"[\n,;]+", terms) if t.strip()]
    if not isinstance(terms, list):
        return []

    out: List[Dict[str, Any]] = []
    seen: set = set()

    for item in terms[:500]:
        if isinstance(item, str):
            item = {"term": item, "mode": "palavra", "severity": "media"}
        if not isinstance(item, dict):
            continue
        term = str(item.get("term") or "").strip()[:100]
        if not term:
            continue
        mode = _as_choice(item.get("mode"), ("palavra", "regex", "contem"), "palavra")
        severity = _as_choice(item.get("severity"), SEVERIDADES, "media")
        key = f"{mode}:{term.lower()}"
        if key in seen:
            continue
        seen.add(key)
        if mode == "regex":
            try:
                re.compile(term)
            except re.error:
                mode = "contem"  # regex inválida não pode derrubar o filtro
        out.append({"term": term, "mode": mode, "severity": severity})

    return out


def _norm_action(value: Any, default: str = "apagar") -> str:
    return _as_choice(value, ACOES_MODERACAO, default)


def normalize_moderation(mod: Any) -> Dict[str, Any]:
    mod = dict(mod or {})
    d = copy.deepcopy(DEFAULT_MODERATION)

    mod["enabled"] = _as_bool(mod.get("enabled"), False)
    mod["log_channel_id"] = _as_int(mod.get("log_channel_id"))
    mod["punish_channel_id"] = _as_int(mod.get("punish_channel_id"))
    mod["ignored_channels"] = [
        c for c in (_as_int(x) for x in mod.get("ignored_channels") or []) if c
    ]
    mod["ignored_roles"] = [
        r for r in (_as_int(x) for x in mod.get("ignored_roles") or []) if r
    ]

    words = dict(mod.get("words") or {})
    words["enabled"] = _as_bool(words.get("enabled"), True)
    words["action"] = _norm_action(words.get("action"))
    words["terms"] = normalize_terms(words.get("terms"))
    words["message"] = str(words.get("message") or d["words"]["message"])[:500]
    mod["words"] = words

    links = dict(mod.get("links") or {})
    links["enabled"] = _as_bool(links.get("enabled"), True)
    links["mode"] = _as_choice(links.get("mode"), MODOS_LINK, "bloquear_convites")
    links["action"] = _norm_action(links.get("action"))
    links["allowed_domains"] = [
        str(x).strip().lower().lstrip("@.")
        for x in (links.get("allowed_domains") or [])
        if str(x).strip()
    ][:200]
    links["message"] = str(links.get("message") or d["links"]["message"])[:500]
    mod["links"] = links

    invites = dict(mod.get("invites") or {})
    invites["enabled"] = _as_bool(invites.get("enabled"), True)
    invites["action"] = _norm_action(invites.get("action"))
    invites["message"] = str(invites.get("message") or d["invites"]["message"])[:500]
    mod["invites"] = invites

    caps = dict(mod.get("caps") or {})
    caps["enabled"] = _as_bool(caps.get("enabled"), False)
    caps["min_chars"] = max(4, _as_int(caps.get("min_chars")) or 12)
    caps["percent"] = min(100, max(10, _as_int(caps.get("percent")) or 70))
    caps["action"] = _norm_action(caps.get("action"))
    caps["message"] = str(caps.get("message") or d["caps"]["message"])[:500]
    mod["caps"] = caps

    flood = dict(mod.get("flood") or {})
    flood["enabled"] = _as_bool(flood.get("enabled"), True)
    flood["max_messages"] = max(2, _as_int(flood.get("max_messages")) or 6)
    flood["window_seconds"] = max(2, _as_int(flood.get("window_seconds")) or 8)
    flood["action"] = _norm_action(flood.get("action"))
    flood["message"] = str(flood.get("message") or d["flood"]["message"])[:500]
    mod["flood"] = flood

    dup = dict(mod.get("duplicate") or {})
    dup["enabled"] = _as_bool(dup.get("enabled"), True)
    dup["max_repeats"] = max(2, _as_int(dup.get("max_repeats")) or 3)
    dup["window_seconds"] = max(2, _as_int(dup.get("window_seconds")) or 30)
    dup["action"] = _norm_action(dup.get("action"))
    dup["message"] = str(dup.get("message") or d["duplicate"]["message"])[:500]
    mod["duplicate"] = dup

    mentions = dict(mod.get("mentions") or {})
    mentions["enabled"] = _as_bool(mentions.get("enabled"), True)
    mentions["max_user_mentions"] = max(1, _as_int(mentions.get("max_user_mentions")) or 6)
    mentions["max_role_mentions"] = max(0, _as_int(mentions.get("max_role_mentions")) or 2)
    mentions["action"] = _norm_action(mentions.get("action"))
    mentions["message"] = str(mentions.get("message") or d["mentions"]["message"])[:500]
    mod["mentions"] = mentions

    zs = dict(mod.get("zerospace") or {})
    zs["enabled"] = _as_bool(zs.get("enabled"), True)
    zs["min_chars"] = max(4, _as_int(zs.get("min_chars")) or 12)
    zs["action"] = _norm_action(zs.get("action"))
    zs["message"] = str(zs.get("message") or d["zerospace"]["message"])[:500]
    mod["zerospace"] = zs

    esc = dict(mod.get("escalation") or {})
    steps = []
    for step in esc.get("steps") or []:
        if not isinstance(step, dict):
            continue
        after = _as_int(step.get("after"))
        action = _as_choice(step.get("action"), ACOES_MODERACAO, "avisar")
        if after is None or after < 1:
            continue
        steps.append({
            "after": after,
            "action": action,
            "seconds": _as_int(step.get("seconds")) or 300,
        })
    steps.sort(key=lambda s: s["after"])
    esc["steps"] = steps[:20]
    esc["enabled"] = _as_bool(esc.get("enabled"), True)
    esc["dm_user"] = _as_bool(esc.get("dm_user"), True)
    esc["exempt_roles"] = [
        r for r in (_as_int(x) for x in esc.get("exempt_roles") or []) if r
    ]
    mod["escalation"] = esc

    return mod


def normalize_tickets(tk: Any) -> Dict[str, Any]:
    tk = dict(tk or {})
    d = copy.deepcopy(DEFAULT_TICKETS)

    tk["enabled"] = _as_bool(tk.get("enabled"), False)
    for key in (
        "panel_channel_id", "support_channel_id", "staff_role_id",
        "category_id", "log_channel_id", "transcript_channel_id",
    ):
        tk[key] = _as_int(tk.get(key))

    tk["panel_title"] = str(tk.get("panel_title") or d["panel_title"])[:120]
    tk["panel_description"] = str(tk.get("panel_description") or d["panel_description"])[:4000]
    tk["panel_color"] = _norm_color(tk.get("panel_color"), d["panel_color"])
    tk["panel_image_url"] = (str(tk.get("panel_image_url") or "").strip()[:500] or None)
    tk["categories"] = normalize_categories(tk.get("categories"))
    tk["max_open_per_user"] = max(1, min(10, _as_int(tk.get("max_open_per_user")) or 1))
    tk["auto_close_days"] = max(0, min(90, _as_int(tk.get("auto_close_days")) or 0))
    tk["close_delay_seconds"] = max(0, min(60, _as_int(tk.get("close_delay_seconds")) or 5))
    tk["ticket_name_format"] = str(tk.get("ticket_name_format") or d["ticket_name_format"])[:100]
    tk["welcome_message"] = str(tk.get("welcome_message") or d["welcome_message"])[:4000]
    tk["message_template"] = str(tk.get("message_template") or d["message_template"])[:4000]
    tk["close_button_label"] = str(tk.get("close_button_label") or d["close_button_label"])[:40]
    tk["rating_enabled"] = _as_bool(tk.get("rating_enabled"), True)
    tk["rating_question"] = str(tk.get("rating_question") or d["rating_question"])[:300]
    return tk


def _norm_color(value: Any, default: str) -> str:
    if not value:
        return default
    val = str(value).strip()
    val = val.lstrip("#")
    if re.fullmatch(r"[0-9a-fA-F]{6}", val):
        return "#" + val.upper()
    return default


def normalize_autorole(a: Any) -> Dict[str, Any]:
    a = dict(a or {})
    d = copy.deepcopy(DEFAULT_AUTOROLE)
    a["enabled"] = _as_bool(a.get("enabled"), False)
    for key in ("channel_id", "give_role_id", "deny_role_id", "log_channel_id"):
        a[key] = _as_int(a.get(key))
    a["keyword"] = str(a.get("keyword") or d["keyword"])[:60]
    a["delete_message"] = _as_bool(a.get("delete_message"), True)
    a["delete_delay_seconds"] = max(0, min(300, _as_int(a.get("delete_delay_seconds")) or 10))
    a["welcome_message"] = str(a.get("welcome_message") or d["welcome_message"])[:2000]
    return a


def normalize_boas_vindas(b: Any) -> Dict[str, Any]:
    b = dict(b or {})
    d = copy.deepcopy(DEFAULT_BOAS_VINDAS)
    b["enabled"] = _as_bool(b.get("enabled"), False)
    for key in ("channel_id", "log_channel_id"):
        b[key] = _as_int(b.get(key))
    b["message"] = str(b.get("message") or d["message"])[:2000]
    b["leave_message"] = str(b.get("leave_message") or d["leave_message"])[:2000]
    b["send_dm"] = _as_bool(b.get("send_dm"), False)
    b["dm_message"] = str(b.get("dm_message") or d["dm_message"])[:2000]
    return b


def normalize_provas(p: Any) -> Dict[str, Any]:
    p = dict(p or {})
    d = copy.deepcopy(DEFAULT_PROVAS)
    p["enabled"] = _as_bool(p.get("enabled"), False)
    for key in ("approval_role_id", "notify_channel_id", "backup_channel_id"):
        p[key] = _as_int(p.get(key))
    p["bank_name"] = str(p.get("bank_name") or d["bank_name"])[:80]
    p["title"] = str(p.get("title") or d["title"])[:120]
    p["require_approval"] = _as_bool(p.get("require_approval"), True)
    p["time_per_question"] = max(15, min(900, _as_int(p.get("time_per_question")) or 120))
    # `or 7` / `or 3` aqui viravam 7/3 quando o painel mandava 0 de propósito
    # (passar com zero acertos, ou nenhuma espera entre tentativas).
    p["pass_score"] = max(0, _as_int(p.get("pass_score"), d["pass_score"]))
    p["cooldown_days"] = max(0, min(90, _as_int(p.get("cooldown_days"), d["cooldown_days"])))
    p["shuffle_answers"] = _as_bool(p.get("shuffle_answers"), True)
    return p


def normalize_logs(l: Any) -> Dict[str, Any]:
    l = dict(l or {})
    d = copy.deepcopy(DEFAULT_LOGS)
    l["enabled"] = _as_bool(l.get("enabled"), True)
    for key in ("join_channel_id", "leave_channel_id", "message_channel_id",
                "mod_channel_id", "boost_channel_id"):
        l[key] = _as_int(l.get(key))
    for key in ("log_join", "log_leave", "log_boost", "log_message_delete", "log_role_change"):
        l[key] = _as_bool(l.get(key), d[key])
    return l


def normalize_contador(c: Any) -> Dict[str, Any]:
    c = dict(c or {})
    d = copy.deepcopy(DEFAULT_CONTADOR)
    c["enabled"] = _as_bool(c.get("enabled"), False)
    c["channel_id"] = _as_int(c.get("channel_id"))
    c["channel_name"] = str(c.get("channel_name") or d["channel_name"])[:100]
    c["category_name"] = str(c.get("category_name") or d["category_name"])[:100]
    return c


def normalize_games(g: Any) -> Dict[str, Any]:
    g = dict(g or {})
    out = copy.deepcopy(DEFAULT_GAMES)

    coc = dict(g.get("coc") or {})
    coc["enabled"] = _as_bool(coc.get("enabled"), False)
    for key in ("registration_channel_id", "log_channel_id", "approval_channel_id"):
        coc[key] = _as_int(coc.get(key))
    coc["clan_tag"] = _norm_clan_tag(coc.get("clan_tag"))
    coc["verify_hours"] = max(1, min(168, _as_int(coc.get("verify_hours")) or 1))
    coc["kick_message"] = str(coc.get("kick_message") or DEFAULT_GAMES["coc"]["kick_message"])[:500]
    roles = dict(coc.get("roles") or {})
    for key in ("member", "elder", "coleader"):
        roles[key] = _as_int(roles.get(key))
    coc["roles"] = roles
    status = {}
    for k, v in (coc.get("status_channel_ids") or {}).items():
        iv = _as_int(v)
        if iv:
            status[str(k)[:32]] = iv
    coc["status_channel_ids"] = status
    out["coc"] = coc

    arma = dict(g.get("arma3") or {})
    arma["enabled"] = _as_bool(arma.get("enabled"), False)
    for key in ("whitelist_channel_id", "log_channel_id", "role_player",
                "role_whitelisted", "role_vip", "auto_tag_on_join"):
        arma[key] = _as_int(arma.get(key))
    arma["sync_tags_on_message"] = _as_bool(arma.get("sync_tags_on_message"), False)
    msgs = {}
    for k, v in (arma.get("messages") or {}).items():
        if str(v).strip():
            msgs[str(k)[:48]] = str(v)[:4000]
    arma["messages"] = msgs
    out["arma3"] = arma

    return out


def _norm_clan_tag(tag: Any) -> Optional[str]:
    if not tag:
        return None
    tag = str(tag).strip().upper().replace(" ", "")
    if not tag.startswith("#"):
        tag = "#" + tag
    body = tag[1:]
    if not body or not re.fullmatch(r"[A-Z0-9]{3,12}", body):
        return None
    return "#" + body


def normalize_modules(mods: Any) -> Dict[str, bool]:
    mods = dict(mods or {})
    return {name: _as_bool(mods.get(name), False) for name in MODULOS}


def normalize(config: Any, guild_id: str, guild_name: str = "", guild_icon: str = None) -> Dict[str, Any]:
    """
    Normaliza um documento vindo do Mongo (ou do form do painel) contra o schema.
    Campos desconhecidos são preservados para não perder dados de versões futuras.
    """
    raw = copy.deepcopy(config) if isinstance(config, dict) else {}
    base = default_config(guild_id, guild_name, guild_icon)

    out = dict(raw)
    out["guild_id"] = str(guild_id)
    out["guild_name"] = str(raw.get("guild_name") or guild_name or "")[:120]
    out["guild_icon"] = raw.get("guild_icon") or guild_icon
    out["profile"] = _as_choice(raw.get("profile"), PERFIS, "generico")
    out["prefix"] = str(raw.get("prefix") or base["prefix"])[:16]
    out["locale"] = str(raw.get("locale") or base["locale"])[:16]

    donos = raw.get("owner_ids")
    if not donos and os.getenv("OWNER_ID"):
        donos = [os.getenv("OWNER_ID")]
    out["owner_ids"] = sorted({
        str(d) for d in (donos or []) if str(d).strip().isdigit()
    })[:20]

    out["modules"] = normalize_modules(raw.get("modules"))

    out["tickets"] = normalize_tickets(raw.get("tickets"))
    out["moderation"] = normalize_moderation(raw.get("moderation"))
    out["autorole"] = normalize_autorole(raw.get("autorole"))
    out["boas_vindas"] = normalize_boas_vindas(raw.get("boas_vindas"))
    out["provas"] = normalize_provas(raw.get("provas"))
    out["logs"] = normalize_logs(raw.get("logs"))
    out["contador"] = normalize_contador(raw.get("contador"))
    out["games"] = normalize_games(raw.get("games"))

    out["created_at"] = raw.get("created_at") or base["created_at"]
    out["updated_at"] = raw.get("updated_at") or base["updated_at"]
    out["updated_by"] = raw.get("updated_by")

    return out


# --------------------------------------------------------------------------
# Utilidades de leitura (atalhos usados pelos cogs)
# --------------------------------------------------------------------------

def module_enabled(cfg: Dict[str, Any], module: str) -> bool:
    return bool((cfg.get("modules") or {}).get(module))


def dono_do_env() -> Optional[int]:
    """ID do dono global, vindo do .env. É sempre dono, em qualquer servidor."""
    for chave in ("OWNER_ID", "DONO_ID", "DISCORD_OWNER_ID"):
        bruto = os.getenv(chave)
        if bruto and str(bruto).strip().isdigit():
            return int(str(bruto).strip())
    return None


def eh_dono(user_id: Any, cfg: Dict[str, Any] = None) -> bool:
    """
    Dono global do .env ou dono registrado na config deste servidor.
    Usado por todos os comandos sensíveis, para não repetir a regra.
    """
    dono = dono_do_env()
    if dono and user_id is not None and int(user_id) == dono:
        return True
    if cfg is None or user_id is None:
        return False
    return int(user_id) in (cfg.get("owner_ids") or [])


def tickets_ready(cfg: Dict[str, Any]) -> Tuple[bool, str]:
    """Confere se o módulo de tickets tem o mínimo para funcionar."""
    tk = cfg.get("tickets") or {}
    faltando = []
    if not tk.get("support_channel_id"):
        faltando.append("canal de suporte")
    if not tk.get("staff_role_id"):
        faltando.append("cargo de atendente")
    if not (tk.get("categories") or []):
        faltando.append("categorias de ticket")
    return (not faltando), ", ".join(faltando)


def moderation_ready(cfg: Dict[str, Any]) -> Tuple[bool, str]:
    mod = cfg.get("moderation") or {}
    filtros = ("words", "links", "invites", "caps", "flood", "duplicate",
               "mentions", "zerospace")
    algum_ativo = any((mod.get(k) or {}).get("enabled") for k in filtros)
    if not algum_ativo:
        return False, "nenhum filtro ativo"
    if not mod.get("enabled"):
        return False, "módulo desligado"
    return True, ""


def build_status(cfg: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Resumo por módulo usado no painel para mostrar o que está pronto e o que falta.
    Cada item: {key, label, ativo, pronto, detalhe}
    """
    mod_nome = {
        "tickets": "Tickets",
        "moderacao": "Moderação",
        "autorole": "Autorole",
        "boas_vindas": "Boas-vindas",
        "provas": "Provas",
        "logs": "Logs",
        "contador": "Contador",
        "games": "Jogos",
    }
    status = []
    for key in MODULOS:
        ativo = module_enabled(cfg, key)
        pronto, detalhe = True, ""

        if key == "tickets":
            pronto, detalhe = tickets_ready(cfg)
        elif key == "moderation":
            pronto, detalhe = moderation_ready(cfg)
        elif key == "autorole":
            pronto = bool(cfg["autorole"].get("channel_id") and cfg["autorole"].get("give_role_id"))
            detalhe = "canal de registro + cargo a liberar"
        elif key == "boas_vindas":
            pronto = bool(cfg["boas_vindas"].get("channel_id"))
            detalhe = "canal de boas-vindas"
        elif key == "provas":
            pronto = True
            detalhe = "" if ativo else "módulo desligado"
        elif key == "logs":
            pronto = bool(cfg["logs"].get("mod_channel_id"))
            detalhe = "canal de moderação para registrar punições"
        elif key == "contador":
            pronto = bool(cfg["contador"].get("channel_id"))
            detalhe = "canal do contador"
        elif key == "games":
            jogos = [n for n in ("coc", "arma3") if cfg["games"].get(n, {}).get("enabled")]
            pronto = bool(jogos)
            detalhe = ", ".join(jogos) if jogos else "nenhum jogo habilitado"

        # Um módulo desligado nunca está "pronto" — evita mostrar o setup como concluído.
        if not ativo:
            pronto, detalhe = False, "módulo desligado"

        status.append({
            "key": key,
            "label": mod_nome[key],
            "ativo": ativo,
            "pronto": pronto,
            "detalhe": "" if pronto else detalhe,
        })
    return status
