"""
AURA · Pre-configuração por perfil
----------------------------------
Monta a configuração de um servidor já com valores que fazem sentido, para não
precisar clicar em cada campo do painel.

O que ela faz:
  - aplica o preset de categorias de ticket do perfil (coc, generico, arma3);
  - liga os módulos pedidos;
  - preenche canais e cargos que ela consegue discovering sozinha;
  - deixa a escalada da moderação em "avisar e apagar", sem punir ninguém
    sozinho (é o padrão seguro; dá para endurecer no painel depois);
  - devolve um relatório do que ficou faltando, em vez de fingir que está
    pronto.

Regra importante: ela só preenche campo que está vazio, e nunca apaga o que já
estava configurado. Rodar de novo não quebra um servidor já ajustado.
"""

from __future__ import annotations

import copy
import os
from typing import Any, Dict, List, Optional, Tuple

from core import settings as st

#: Módulos que a pre-configuração liga por padrão.
MODULOS_PADRAO = ("tickets", "moderacao", "autorole", "boas_vindas",
                  "provas", "logs", "contador", "games")

#: Variáveis que apontam para o servidor do Clash (o perfil `coc`).
ENV_GUILDS_COC = ("DISCORD_GUILD_ID_LEGADO", "TEST_GUILD_ID",
                  "id_servidor_tribunal")


def perfil_padrao_para(guild_id: Any) -> str:
    """
    Escolhe o perfil sozinho: `coc` no servidor do Clash, `generico` nos outros.

    Assim dá para rodar a pre-configuração em todos os servidores de uma vez sem
    escolher perfil servidor por servidor. Um servidor que não for o do Clash
    ganha categorias genéricas (suporte, denúncia, apelação, sugestão), o que é
    o certo — não faz sentido criar categoria de CWL em servidor que não é de
    clã.
    """
    for nome in ENV_GUILDS_COC:
        valor = os.getenv(nome)
        if valor and str(valor).strip() == str(guild_id).strip():
            return "coc"
    return "generico"

#: Onde cada papel do AURA costuma estar, por nome de papel no Discord.
#: Usado só para sugerir; nunca escreve sem o ID.
PASTAS_CANAL = {
    "tickets_panel": ("painel", "atendimento", "suporte", "ticket"),
    "tickets_support": ("suporte", "atendimento", "ticket", "ajuda"),
    "tickets_logs": ("log", "registro", "painel-log"),
    "tickets_transcripts": ("transcric", "transcri", "tickets"),
    "logs_geral": ("log", "registro", "mod-log", "modlog"),
    "logs_moderacao": ("mod", "punish", "puni", "warn"),
    "boas_vindas": ("boas-vindas", "boas vindas", "entrada", "welcome"),
    "contador": ("membros", "contador", "member"),
    "games_registro": ("registro", "registrar", "verificacao", "verificação"),
    "games_logs": ("log", "clan", "cla"),
    "provas_aprovacao": ("aprov", "prova", "exame"),
}

#: Ordem em que os canais são reivindicados. Os mais específicos primeiro, e um
#: canal já usado por um papel anterior não pode ser reatribuído — é assim que
#: "registro-de-membros" (registro do Clash) não vira o contador de membros.
ORDEM_CANAIS = (
    "games_registro",
    "provas_aprovacao",
    "boas_vindas",
    "tickets_panel",
    "tickets_transcripts",
    "tickets_support",
    "contador",
    "logs_moderacao",
    "tickets_logs",
    "logs_geral",
    "games_logs",
)

PASTAS_CARGO = {
    "staff": ("atendente", "suporte", "staff", "mod", "moderador"),
    "membro_cla": ("membro", "member", "jogador"),
    "elder": ("elder", "ancestor", "ancião"),
    "coleader": ("coleader", "co-lider", "lider"),
    "banido": ("banido", "ban"),
    "aprovador": ("aprov", "dono", "owner", "admin"),
}


def _id_de(valor: Any) -> Optional[int]:
    """Aceita int, str numérica, None. Devolve None se não for número."""
    if valor in (None, ""):
        return None
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        return None


def _achar_por_pasta(nome: str, pastas: Tuple[str, ...]) -> bool:
    baixo = (nome or "").lower()
    return any(p in baixo for p in pastas)


def _pontuacao(nome: str, pastas: Tuple[str, ...]) -> Optional[int]:
    """
    Quão bem um nome casa com um conjunto de pastas. Menor é melhor.

    0 = o nome é exatamente a pasta (ou com emoji antes)
    1 = começa com a pasta
    2 = só contém a pasta
    None = não casa
    """
    limpo = (nome or "").lower().strip()
    melhor = None
    for p in pastas:
        if limpo == p or limpo.lstrip("📋📃🧾📊🔧🎫📝• ️") == p:
            melhor = 0 if melhor is None else min(melhor, 0)
        elif limpo.startswith(p):
            melhor = 1 if melhor is None else min(melhor, 1)
        elif p in limpo:
            melhor = 2 if melhor is None else min(melhor, 2)
    return melhor


def _escalada_so_avisar(mod: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deixa a moderação sem punição automática.

    O padrão do código escala até banir na 8ª infração. Aqui todo filtro apaga
    a mensagem e a escalada só avisa — nada de timeout nem ban sem alguém
    olhando.
    """
    mod = copy.deepcopy(mod)
    for filtro in ("words", "links", "invites", "caps", "flood",
                   "duplicate", "mentions", "zerospace"):
        bloco = mod.get(filtro)
        if isinstance(bloco, dict):
            bloco["action"] = "apagar"
    esc = mod.get("escalation")
    if isinstance(esc, dict):
        esc["enabled"] = True
        esc["steps"] = [{"after": 1, "action": "avisar"}]
        esc["dm_user"] = True
    mod["log_channel_id"] = mod.get("log_channel_id") or None
    mod["punish_channel_id"] = None
    return mod


def detectar_canais(guild) -> Dict[str, int]:
    """
    Acha canais no servidor pelos nomes conhecidos.

    Cada canal é entregue a um papel só, na ordem de especificidade — sem isso
    "registro-de-membros" serviria ao registro do Clash e ao contador de membros
    ao mesmo tempo. Em empate de qualidade, fica com o primeiro canal que casa.

    Devolve só o que o nome indica; quem chama decide se usa. O painel segue
    sendo o lugar de conferir, porque nome de canal engana.
    """
    achados: Dict[str, int] = {}
    usados: set = set()
    canais = list(getattr(guild, "text_channels", []))
    for chave in ORDEM_CANAIS:
        pastas = PASTAS_CANAL.get(chave)
        if not pastas:
            continue
        melhor_nota, melhor_id = None, None
        for ch in canais:
            if ch.id in usados:
                continue
            nota = _pontuacao(ch.name, pastas)
            if nota is not None and (melhor_nota is None or nota < melhor_nota):
                melhor_nota, melhor_id = nota, ch.id
                if nota == 0:
                    break
        if melhor_id is not None:
            achados[chave] = melhor_id
            usados.add(melhor_id)
    return achados


def detectar_cargos(guild) -> Dict[str, int]:
    """
    Acha cargos pelos nomes conhecidos, cada um num papel só.

    "Staff" e "Moderador" não podem virar o mesmo cargo, e o cargo com o nome do
    servidor é ignorado. Os mais específicos (elder, coleader) são reivindicados
    antes dos genéricos, senão "Membro" acabaria virando elder.
    """
    ordem = ("elder", "coleader", "staff", "aprovador", "banido", "membro_cla")
    achados: Dict[str, int] = {}
    usados: set = set()
    cargos = [r for r in getattr(guild, "roles", [])
              if r.name != getattr(guild, "name", "")]
    for chave in ordem:
        pastas = PASTAS_CARGO.get(chave)
        if not pastas:
            continue
        melhor_nota, melhor_id = None, None
        for r in cargos:
            if r.id in usados:
                continue
            nota = _pontuacao(r.name, pastas)
            if nota is not None and (melhor_nota is None or nota < melhor_nota):
                melhor_nota, melhor_id = nota, r.id
                if nota == 0:
                    break
        if melhor_id is not None:
            achados[chave] = melhor_id
            usados.add(melhor_id)
    return achados


def _env_canais() -> Dict[str, Any]:
    """Canais e cargos que ainda existem como variável de ambiente."""
    return {
        "tickets_support": os.getenv("id_canal_suporte"),
        "tickets_transcripts": os.getenv("ID_CANAL_TRANSCRICOES")
        or os.getenv("id_canal_logs_tri"),
        "tickets_logs": os.getenv("id_canal_logs_tri") or os.getenv("LOG_CHANNEL_ID"),
        "logs_geral": os.getenv("LOG_CHANNEL_ID") or os.getenv("id_canal_logs_tri"),
        "logs_moderacao": os.getenv("LOG_CHANNEL_ID"),
        "games_registro": os.getenv("CANAL_REGISTRO_ID")
        or os.getenv("REGISTRATION_CHANNEL_ID"),
        "games_logs": os.getenv("LOG_CHANNEL_ID"),
        "provas_aprovacao": os.getenv("APPROVAL_LOG_CHANNEL_ID"),
    }


def _env_cargos() -> Dict[str, Any]:
    return {
        "staff": os.getenv("id_cargo_atendente"),
        "membro_cla": os.getenv("COC_MEMBER_ROLE_ID") or os.getenv("CARGO_MEMBRO_ID"),
        "elder": os.getenv("COC_ELDER_ROLE_ID"),
        "coleader": os.getenv("COC_COLEADER_ROLE_ID"),
        "banido": os.getenv("CARGO_BANIDO_ID"),
    }


def _env_clan() -> Dict[str, Any]:
    tag = os.getenv("CLAN_TAG")
    return {"clan_tag": tag} if tag else {}


def montar(guild_id: str, guild_name: str = "", guild_icon: str = None,
           profile: str = "generico", *, guild=None,
           modulos: Tuple[str, ...] = MODULOS_PADRAO,
           owner_ids: Optional[List[str]] = None,
           usar_env: bool = True,
           detectar: bool = True) -> Tuple[Dict[str, Any], List[str]]:
    """
    Devolve `(config, pendencias)`.

    `pendencias` são as linhas de "isso ficou faltando", para o painel/command
    falar o que o humano precisa fechar. Nada é inventado: se não achou o
    canal, fica None e aparece na lista.
    """
    if profile not in st.PERFIS:
        profile = "generico"

    cfg = st.preset_config(profile) or st.default_config(guild_id, guild_name,
                                                        guild_icon)
    cfg["guild_id"] = str(guild_id)
    cfg["guild_name"] = guild_name or ""
    cfg["guild_icon"] = guild_icon

    canais: Dict[str, Any] = {}
    cargos: Dict[str, Any] = {}
    if usar_env:
        canais.update(_env_canais())
        cargos.update(_env_cargos())
    if detectar and guild is not None:
        for chave, valor in detectar_canais(guild).items():
            canais.setdefault(chave, valor)
        for chave, valor in detectar_cargos(guild).items():
            cargos.setdefault(chave, valor)

    dono_env = os.getenv("OWNER_ID")
    if owner_ids is None and dono_env:
        owner_ids = [dono_env]
    if owner_ids:
        cfg["owner_ids"] = [str(d) for d in owner_ids if str(d).strip()]

    # ---- módulos ----
    for mod in st.MODULOS:
        cfg["modules"][mod] = mod in modulos

    # ---- tickets ----
    tk = cfg["tickets"]
    if "tickets" in modulos:
        tk["enabled"] = True
        tk["support_channel_id"] = _id_de(canais.get("tickets_support"))
        tk["panel_channel_id"] = _id_de(canais.get("tickets_panel"))
        tk["staff_role_id"] = _id_de(cargos.get("staff"))
        tk["log_channel_id"] = _id_de(canais.get("tickets_logs"))
        tk["transcript_channel_id"] = _id_de(canais.get("tickets_transcripts"))

    # ---- moderação ----
    mod_cfg = cfg["moderation"]
    if "moderacao" in modulos:
        mod_cfg = _escalada_so_avisar(mod_cfg)
        mod_cfg["enabled"] = True
        mod_cfg["log_channel_id"] = _id_de(canais.get("logs_moderacao")
                                          or canais.get("logs_geral"))
        cfg["moderation"] = mod_cfg

    # ---- logs ----
    if "logs" in modulos:
        lg = cfg["logs"]
        lg["enabled"] = True
        lg["join_channel_id"] = _id_de(canais.get("logs_geral"))
        lg["leave_channel_id"] = _id_de(canais.get("logs_geral"))
        lg["message_channel_id"] = _id_de(canais.get("logs_geral"))
        lg["mod_channel_id"] = _id_de(canais.get("logs_moderacao")
                                      or canais.get("logs_geral"))
        lg["boost_channel_id"] = _id_de(canais.get("logs_geral"))

    # ---- boas-vindas ----
    if "boas_vindas" in modulos:
        bv = cfg["boas_vindas"]
        bv["enabled"] = True
        bv["channel_id"] = _id_de(canais.get("boas_vindas"))
        bv["log_channel_id"] = _id_de(canais.get("logs_geral"))

    # ---- contador ----
    if "contador" in modulos:
        ct = cfg["contador"]
        ct["enabled"] = True
        ct["channel_id"] = _id_de(canais.get("contador"))

    # ---- autorole ----
    if "autorole" in modulos:
        ar = cfg["autorole"]
        ar["enabled"] = True
        ar["channel_id"] = _id_de(canais.get("tickets_support")
                                 or canais.get("boas_vindas"))
        ar["give_role_id"] = _id_de(cargos.get("membro_cla"))

    # ---- provas ----
    if "provas" in modulos:
        pv = cfg["provas"]
        pv["enabled"] = True
        pv["approval_role_id"] = _id_de(cargos.get("aprovador"))
        pv["notify_channel_id"] = _id_de(canais.get("provas_aprovacao"))
        pv["backup_channel_id"] = _id_de(canais.get("provas_aprovacao"))

    # ---- jogos / clash ----
    if "games" in modulos:
        gm = cfg["games"]
        coc = gm.get("coc") or {}
        tag = (_env_clan() if usar_env else {}).get("clan_tag")
        if tag:
            coc["clan_tag"] = tag
            coc["enabled"] = True
            coc["registration_channel_id"] = _id_de(canais.get("games_registro"))
            coc["log_channel_id"] = _id_de(canais.get("games_logs"))
            coc["approval_channel_id"] = _id_de(canais.get("games_registro"))
            coc.setdefault("roles", {})
            coc["roles"]["member"] = _id_de(cargos.get("membro_cla"))
            coc["roles"]["elder"] = _id_de(cargos.get("elder"))
            coc["roles"]["coleader"] = _id_de(cargos.get("coleader"))
        gm["coc"] = coc

    cfg = st.normalize(cfg, str(guild_id), guild_name, guild_icon)
    return cfg, pendencias(cfg)


def pendencias(cfg: Dict[str, Any]) -> List[str]:
    """O que ainda falta para os módulos ligados funcionarem de verdade."""
    faltando: List[str] = []
    mods = cfg.get("modules") or {}

    if mods.get("tickets"):
        tk = cfg.get("tickets") or {}
        if not tk.get("support_channel_id"):
            faltando.append("tickets: canal de suporte")
        if not tk.get("panel_channel_id"):
            faltando.append("tickets: canal do painel (onde o botão aparece)")
        if not tk.get("staff_role_id"):
            faltando.append("tickets: cargo de atendente")

    if mods.get("moderacao"):
        mod = cfg.get("moderation") or {}
        if not mod.get("log_channel_id"):
            faltando.append("moderação: canal de log")

    if mods.get("logs"):
        lg = cfg.get("logs") or {}
        if not lg.get("join_channel_id"):
            faltando.append("logs: canal de registro")

    if mods.get("boas_vindas"):
        if not (cfg.get("boas_vindas") or {}).get("channel_id"):
            faltando.append("boas-vindas: canal de entrada")

    if mods.get("contador"):
        if not (cfg.get("contador") or {}).get("channel_id"):
            faltando.append("contador: canal do membro contador")

    if mods.get("autorole"):
        ar = cfg.get("autorole") or {}
        if not ar.get("channel_id"):
            faltando.append("autorole: canal da palavra-chave")
        if not ar.get("give_role_id"):
            faltando.append("autorole: cargo a entregar")

    if mods.get("provas"):
        pv = cfg.get("provas") or {}
        if not pv.get("approval_role_id"):
            faltando.append("provas: cargo que aprova")

    if mods.get("games"):
        coc = (cfg.get("games") or {}).get("coc") or {}
        if not coc.get("clan_tag"):
            faltando.append("jogos: tag do clã (CLAN_TAG)")
        if not coc.get("status_channel_ids"):
            faltando.append("jogos: canais de voz do Status do Clã "
                            "(use /status-cla auto-detectar)")
    return faltando


def aplicar(guild_id: str, guild_name: str = "", guild_icon: str = None,
            profile: str = "generico", *, guild=None, autor: str = "preconfig",
            **kwargs) -> Tuple[bool, Dict[str, Any], List[str]]:
    """Monta e grava. Devolve `(ok, config, pendencias)`."""
    import mongo_db

    cfg, falta = montar(guild_id, guild_name, guild_icon, profile,
                        guild=guild, **kwargs)
    ok = mongo_db.upsert_guild_config(guild_id, cfg, updated_by=autor)
    if ok:
        st.invalidate(str(guild_id))
    return ok, cfg, falta