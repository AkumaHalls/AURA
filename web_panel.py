"""
AURA · Painel web
-----------------
Painel de administration multiseridor, no estilo Loritta.

Segurança:
    - a senha nunca é comparada em texto puro. Use WEB_PANEL_PASSWORD_HASH
        (hash gerado pelo werkzeug). Sem hash, o AURA gera um no primeiro boot
        e imprime a senha na stdout do container.
    - secret_key vem do .env, então reiniciar não derruba as sessões.
    - toda rota que mexe em configuração exige login e grava auditoria.

Por que dá para editar o Discord daqui: o bot registra o próprio cliente em
`core.runtime`, e o painel usa essa ponte para ler canais, cargos e publicar
embedes. Não há API key do Discord para configurar.
"""

from __future__ import annotations

import os
import re
import threading
import time
from copy import deepcopy
from typing import Any, Dict, List, Optional

from flask import (
    Flask,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from jinja2 import TemplateNotFound
from werkzeug.security import check_password_hash, generate_password_hash

# O painel também roda standalone (`python web_panel.py`), então precisa do .env.
try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass

import mongo_db
from core import runtime
from core import settings as st
from core.placeholders import DOC as PLACEHOLDER_DOC
from core.placeholders import preview as preview_placeholder

# --------------------------------------------------------------------------
# Configuração do app
# --------------------------------------------------------------------------

app = Flask(__name__, template_folder="templates")

SECRET_KEY = os.getenv("WEB_PANEL_SECRET_KEY") or os.urandom(32).hex()
app.secret_key = SECRET_KEY
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=60 * 60 * 12,
    MAX_CONTENT_LENGTH=2 * 1024 * 1024,
    JSON_SORT_KEYS=False,
)

PASSWORD_HASH = (os.getenv("WEB_PANEL_PASSWORD_HASH") or "").strip()
SENHA_TEMP = None

#: Módulos e o que o painel mostra em cada página.
MODULOS_PAINEL = [
    {"key": "tickets", "label": "Tickets", "icone": "🎫",
        "descricao": "Categorias, painel e canais de atendimento"},
    {"key": "moderacao", "label": "Moderação", "icone": "🛡️",
        "descricao": "Filtros, ações e punições automáticas"},
    {"key": "autorole", "label": "Liberação", "icone": "🎟️",
        "descricao": "Liberação de acesso por palavra-chave"},
    {"key": "boas_vindas", "label": "Boas-vindas", "icone": "👋",
        "descricao": "Mensagens de entrada e saída"},
    {"key": "provas", "label": "Provas", "icone": "📝",
        "descricao": "Exame de qualificação e aprovações"},
    {"key": "logs", "label": "Logs", "icone": "📜",
        "descricao": "Registro de entradas, saídas e moderação"},
    {"key": "contador", "label": "Contador", "icone": "👥",
        "descricao": "Contador de membros automático"},
    {"key": "games", "label": "Jogos", "icone": "🎮",
        "descricao": "Clash of Clans e Arma 3"},
]

ACOES = list(st.ACOES_MODERACAO)
MODOS_LINK = list(st.MODOS_LINK)
SEVERIDADES = list(st.SEVERIDADES)
PERFIS = list(st.PERFIS)


# --------------------------------------------------------------------------
# Senha
# --------------------------------------------------------------------------

def _garantir_senha() -> Optional[str]:
    """
    Garante que exista um hash no .env. Se não houver, cria uma senha
    temporária, mostra no log e devolve o valor (para o painel avisar).
    """
    global SENHA_TEMP, PASSWORD_HASH
    caminho = os.path.join(os.path.dirname(__file__), ".env")

    if PASSWORD_HASH:
        return None

    senha_plana = os.getenv("WEB_PANEL_PASSWORD")
    if senha_plana:
        PASSWORD_HASH = generate_password_hash(senha_plana)
        _anexar_ao_env(caminho, "WEB_PANEL_PASSWORD_HASH", PASSWORD_HASH)
        print("[painel] Senha convertida em hash. Pode remover WEB_PANEL_PASSWORD do .env.")
        return None

    senha_plana = "aura-" + os.urandom(6).hex()
    SENHA_TEMP = senha_plana
    PASSWORD_HASH = generate_password_hash(senha_plana)
    _anexar_ao_env(caminho, "WEB_PANEL_PASSWORD_HASH", PASSWORD_HASH)
    print("\n" + "=" * 62)
    print("  SENHA DO PAINEL GERADA (primeiro boot)")
    print(f"  {senha_plana}")
    print("  Já foi salva em .env como WEB_PANEL_PASSWORD_HASH.")
    print("  Anote agora — ela não aparece de novo.")
    print("=" * 62 + "\n")
    return senha_plana


def _anexar_ao_env(caminho: str, chave: str, valor: str) -> None:
    """Adiciona ou substitui uma chave no .env, sem apagar o resto."""
    try:
        linhas = []
        substituido = False
        if os.path.exists(caminho):
            with open(caminho, encoding="utf-8") as fh:
                for linha in fh:
                    if linha.strip().startswith(f"{chave}="):
                        linhas.append(f"{chave}={valor}\n")
                        substituido = True
                    else:
                        linhas.append(linha)
        if not substituido:
            if linhas and not linhas[-1].endswith("\n"):
                linhas[-1] += "\n"
            linhas.append(f"{chave}={valor}\n")
        with open(caminho, "w", encoding="utf-8") as fh:
            fh.writelines(linhas)
    except OSError as exc:
        print(f"[painel] Não consegui gravar {chave} no .env: {exc}")


_garantir_senha()


# --------------------------------------------------------------------------
# Autenticação
# --------------------------------------------------------------------------

def _logado() -> bool:
    return bool(session.get("painel_ok"))


@app.context_processor
def _injetar_globais():
    """Variáveis disponíveis em todos os templates."""
    return {
        "bot": runtime.update_status(),
        "todos_servidores": _servidores(),
    }


@app.before_request
def _exigir_login():
    rotas_livres = {"login", "health", "static"}
    if request.endpoint in rotas_livres:
        return None
    if not _logado():
        return redirect(url_for("login", next=request.full_path))
    return None


@app.after_request
def _cabecalhos(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "SAMEORIGIN"
    resp.headers["Referrer-Policy"] = "same-origin"
    return resp


@app.template_filter("datahora")
def _filtro_datahora(valor) -> str:
    """Epoch (float) ou ISO string vira 'dd/mm/aaaa HH:MM'."""
    from datetime import datetime as _dt

    if valor in (None, ""):
        return "—"
    try:
        if isinstance(valor, (int, float)):
            dt = _dt.fromtimestamp(float(valor))
        else:
            dt = _dt.fromisoformat(str(valor))
        return dt.strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError):
        return "—"


def _guild_atual() -> Optional[Dict[str, Any]]:
    """Só o resumo do servidor da requisição, para a barra lateral."""
    atual = _servidor_atual()
    return atual["guild"] if atual else None


def _destino_seguro(bruto: str) -> str:
    """Aceita apenas caminhos internos, para não virar redirecionador aberto."""
    if not bruto:
        return url_for("dashboard")
    bruto = bruto.split("?", 1)[0]
    if not bruto.startswith("/") or bruto.startswith("//") or "\\" in bruto:
        return url_for("dashboard")
    return bruto


@app.route("/login", methods=["GET", "POST"])
def login():
    erro = None
    destino = _destino_seguro(request.args.get("next") or request.form.get("next") or "")

    if request.method == "POST":
        senha = request.form.get("password", "")
        if PASSWORD_HASH and check_password_hash(PASSWORD_HASH, senha):
            session.clear()
            session["painel_ok"] = True
            session.permanent = True
            session["desde"] = time.time()
            mongo_db.registrar_auditoria(None, None, "login", "painel", None, "acesso ao painel")
            return redirect(destino)
        erro = "Senha incorreta."

    return render_template("login.html", erro=erro, next=destino, senha_temp=SENHA_TEMP)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/health")
def health():
    return {"ok": True, "bot": runtime.is_ready()}, 200


# --------------------------------------------------------------------------
# Helpers de servidor
# --------------------------------------------------------------------------

def _servidores() -> List[Dict[str, Any]]:
    """Servidores do bot, com a config e o resumo prontos."""
    lista = []
    for guild in runtime.list_guild_summaries():
        try:
            cfg = st.get_cached(guild["id"])
        except Exception:
            cfg = None
        lista.append({"guild": guild, "cfg": cfg})
    return lista


def _servidor_atual() -> Dict[str, Any]:
    """
    Descobre de qual servidor o painel está falando.
    Prioridade: ?guild= na URL, sessão, primeiro servidor do bot.
    """
    alvo = None
    pedido = request.values.get("guild")
    if pedido:
        alvo = pedido
    elif session.get("guild"):
        alvo = session["guild"]

    for item in _servidores():
        if str(item["guild"]["id"]) == str(alvo):
            return item

    if alvo and alvo.isdigit() and not _servidores():
        return {"guild": {"id": alvo, "name": f"Servidor {alvo}", "icon": None,
                            "members": 0},
                "cfg": None}

    return _servidores()[0] if _servidores() else None


def _salvar_cfg(cfg: Dict[str, Any], guild_id: str, guild_name: str,
                autor: str, acao: str) -> bool:
    cfg["guild_id"] = str(guild_id)
    cfg["guild_name"] = guild_name
    ok = bool(runtime.run_coro(st.save_config(cfg, autor=autor)))
    if ok:
        st.invalidate(str(guild_id))
        mongo_db.registrar_auditoria(guild_id, guild_name, acao, "painel",
                                        autor, "")
        _recarregar_views(str(guild_id))
    return ok


def _recarregar_views(guild_id: str):
    """Avisa os cogs para recarregar as views após uma mudança de config."""
    client = runtime.get_client()
    if client is None:
        return
    cog = client.get_cog("Atendimento")
    if cog is None:
        return
    try:
        cfg = st.get_cached(guild_id)
        categorias = (cfg.get("tickets") or {}).get("categories") or []
        cog.registrar_view(int(guild_id), categorias)
    except Exception as exc:
        runtime.log("AVISO", f"não consegui recarregar o painel de tickets: {exc}", "painel")


def _pedir_bool(chave: str, padrao: bool = False) -> bool:
    v = request.form.get(chave)
    if v is None:
        return padrao
    return v.lower() in ("1", "true", "on", "sim", "true")


def _pedir_int(chave: str, padrao=None):
    v = request.form.get(chave, "").strip()
    if not v:
        return padrao
    try:
        return int(v)
    except ValueError:
        return padrao


def _pedir_lista(chave: str) -> List[int]:
    """Aceita repetição do campo e texto com vírgulas/espaços."""
    cru = list(request.form.getlist(chave) or [])
    cru += request.form.getlist(f"{chave}_texto") or []
    saida = []
    for item in cru:
        for parte in re.split(r"[\s,;\n]+", str(item)):
            parte = parte.strip()
            if parte.isdigit():
                saida.append(int(parte))
    return sorted(set(saida))


# --------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------

@app.route("/")
def dashboard():
    atual = _servidor_atual()
    if atual is None:
        return render_template("sem_servidor.html", modulos=MODULOS_PAINEL)

    guild = atual["guild"]
    gid = guild["id"]
    cfg = atual["cfg"] or st.default_config(gid, guild["name"], guild.get("icon"))

    if atual["cfg"] is None:
        # Primeira visita: grava a config padrão para o painel passar a listar.
        runtime.run_coro(st.save_config(cfg, autor="painel"))
        st.put_cache(cfg)
        atual["cfg"] = cfg

    stats = mongo_db.stats_dashboard(gid)
    series = mongo_db.series_dias(gid, dias=14)
    status = st.build_status(cfg)
    mod = mongo_db.status()

    contexto = {
        "modulos": MODULOS_PAINEL,
        "status_modulos": status,
        "stats": stats,
        "series": series,
        "db": mod,
        "bot": runtime.update_status(),
        "pronto": st.tickets_ready(cfg),
        "moderacao_ok": st.moderation_ready(cfg),
        "owner_ids": cfg.get("owner_ids") or [],
    }
    return render_template("dashboard.html", guild=guild, cfg=cfg, **contexto)


@app.route("/servidor", methods=["POST"])
def trocar_servidor():
    alvo = request.form.get("guild", "").strip()
    if alvo:
        session["guild"] = alvo
        st.invalidate(alvo)
    return redirect(_destino_seguro(request.form.get("volta") or ""))


def _rota_do_referrer() -> str:
    ref = request.referrer or ""
    if "/modulo/" in ref:
        return "modulo"
    return "dashboard"


@app.route("/config/<chave>", methods=["POST"])
def salvar_basico(chave: str):
    atual = _servidor_atual()
    if atual is None:
        abort(404)
    guild = atual["guild"]
    cfg = deepcopy(atual["cfg"] or st.default_config(guild["id"], guild["name"]))

    if chave == "preset":
        perfil = request.form.get("perfil", "generico")
        novo = st.preset_config(perfil)
        if novo is None:
            flash(f"❌ Perfil '{perfil}' não existe. Nada foi alterado.", "erro")
            return redirect(url_for("config_geral", guild=guild["id"]))
        novo["guild_id"] = cfg.get("guild_id")
        novo["guild_name"] = cfg.get("guild_name")
        novo["guild_icon"] = cfg.get("guild_icon")
        novo["owner_ids"] = cfg.get("owner_ids", [])
        novo["modules"] = cfg.get("modules", {})
        novo["prefix"] = cfg.get("prefix", "-br")
        novo["locale"] = cfg.get("locale", "pt-BR")
        if _salvar_cfg(novo, guild["id"], guild["name"], "painel", f"preset_{perfil}"):
            flash(f"✅ Perfil {perfil} aplicado. Revise os canais antes de salvar.",
                    "ok")
        else:
            flash("❌ Não consegui aplicar o perfil.", "erro")
        return redirect(url_for("modulo", modulo="tickets", guild=guild["id"]))

    if chave == "geral":
        cfg["profile"] = request.form.get("profile", cfg.get("profile", "generico"))
        cfg["prefix"] = request.form.get("prefix", cfg.get("prefix", "-br"))[:16]
        cfg["locale"] = request.form.get("locale", cfg.get("locale", "pt-BR"))[:16]
        cfg["owner_ids"] = _pedir_lista("owner_ids")

    # Os interruptores de módulo ficam no mesmo formulário da página geral,
    # então são lidos sempre que vierem — tanto em "geral" quanto em "modulos".
    if any(f"mod_{mod['key']}" in request.form for mod in MODULOS_PAINEL):
        for mod in MODULOS_PAINEL:
            cfg["modules"][mod["key"]] = _pedir_bool(
                f"mod_{mod['key']}", bool(cfg["modules"].get(mod["key"])))

    if _salvar_cfg(cfg, guild["id"], guild["name"], "painel", f"salvar_{chave}"):
        flash("✅ Configuração salva.", "ok")
    else:
        flash("❌ Não consegui salvar. O MongoDB está acessível?", "erro")
    return redirect(url_for(_rota_do_referrer(), guild=guild["id"]))


# --------------------------------------------------------------------------
# Páginas dos módulos
# --------------------------------------------------------------------------

@app.route("/config/geral")
def config_geral():
    atual = _servidor_atual()
    if atual is None:
        abort(404)
    guild = atual["guild"]
    cfg = atual["cfg"] or st.default_config(guild["id"], guild["name"], guild.get("icon"))
    snap = runtime.guild_snapshot(guild["id"]) or {}
    return render_template("geral.html", modulos=MODULOS_PAINEL, guild=guild, cfg=cfg,
                            perfis=PERFIS, status_modulos=st.build_status(cfg),
                            snap=snap,
                            owner_ids_texto=" ".join(cfg.get("owner_ids") or []))


@app.route("/modulo/<modulo>")
def modulo(modulo: str):
    atual = _servidor_atual()
    if atual is None:
        abort(404)

    guild = atual["guild"]
    cfg = atual["cfg"] or st.default_config(guild["id"], guild["name"], guild.get("icon"))
    meta = next((m for m in MODULOS_PAINEL if m["key"] == modulo), None)
    if meta is None:
        abort(404)

    canal = runtime.get_client() is not None
    contexto = {
        "modulos": MODULOS_PAINEL,
        "meta": meta,
        "cfg": cfg,
        "guild": guild,
        "status_modulos": st.build_status(cfg),
        "acoes": ACOES,
        "modos_link": MODOS_LINK,
        "severidades": SEVERIDADES,
        "canal": canal,
        "canais": runtime.guild_snapshot(guild["id"]) or {},
        "placeholders": PLACEHOLDER_DOC,
        "pronto": st.tickets_ready(cfg),
        "moderacao_ok": st.moderation_ready(cfg),
    }
    try:
        return render_template("modulo_pagina.html", **contexto)
    except TemplateNotFound:
        return render_template("erro.html", guild=guild, codigo=500,
                                mensagem=f"A página do módulo '{modulo}' não existe."), 500


# ---------- tickets ----------

@app.route("/modulo/tickets", methods=["POST"])
def salvar_tickets():
    atual = _servidor_atual()
    if atual is None:
        abort(404)
    guild = atual["guild"]
    cfg = deepcopy(atual["cfg"] or st.default_config(guild["id"], guild["name"]))
    tk = dict(cfg.get("tickets") or {})

    tk["enabled"] = _pedir_bool("enabled", tk.get("enabled", False))
    tk["panel_channel_id"] = _pedir_int("panel_channel_id", tk.get("panel_channel_id"))
    tk["support_channel_id"] = _pedir_int("support_channel_id", tk.get("support_channel_id"))
    tk["staff_role_id"] = _pedir_int("staff_role_id", tk.get("staff_role_id"))
    tk["category_id"] = _pedir_int("category_id", tk.get("category_id"))
    tk["log_channel_id"] = _pedir_int("log_channel_id", tk.get("log_channel_id"))
    tk["transcript_channel_id"] = _pedir_int("transcript_channel_id",
                                            tk.get("transcript_channel_id"))
    tk["panel_title"] = request.form.get("panel_title", "")[:200]
    tk["panel_description"] = request.form.get("panel_description", "")[:2000]
    tk["panel_image_url"] = request.form.get("panel_image_url", "")[:500] or None
    tk["max_open_per_user"] = _pedir_int("max_open_per_user", tk.get("max_open_per_user")) or 0
    tk["auto_close_days"] = _pedir_int("auto_close_days", tk.get("auto_close_days")) or 0
    tk["close_delay_seconds"] = _pedir_int("close_delay_seconds",
                                            tk.get("close_delay_seconds")) or 0
    tk["welcome_message"] = request.form.get("welcome_message", "")[:2000]
    tk["ticket_name_format"] = request.form.get(
        "ticket_name_format", tk.get("ticket_name_format", "{emoji} {label} · {user}"))[:120]
    tk["message_template"] = request.form.get(
        "message_template", tk.get("message_template", ""))[:2000]
    tk["close_button_label"] = request.form.get(
        "close_button_label", tk.get("close_button_label", "Fechar ticket"))[:80]
    tk["rating_enabled"] = _pedir_bool("rating_enabled", tk.get("rating_enabled", True))
    tk["rating_question"] = request.form.get("rating_question", "")[:500]

    cor = request.form.get("panel_color", "#5865F2").strip()
    if not cor.startswith("#") or len(cor) not in (4, 7):
        cor = "#5865F2"
    tk["panel_color"] = cor

    # Categorias: o formulário manda N linhas com o mesmo prefixo.
    categorias = []
    for chave, valor in request.form.items():
        if not chave.startswith("cat_key_"):
            continue
        idx = chave.rsplit("_", 1)[-1]
        label = request.form.get(f"cat_label_{idx}", "").strip()
        if not label:
            continue
        categorias.append({
            "key": valor.strip(),
            "label": label,
            "emoji": request.form.get(f"cat_emoji_{idx}", "🎫").strip() or "🎫",
            "description": request.form.get(f"cat_description_{idx}", "")[:1500],
            "prompt": request.form.get(f"cat_prompt_{idx}", "")[:1500],
            "staff_role_id": _pedir_int(f"cat_staff_{idx}") or None,
        })

    if categorias:
        vistos, unicas = set(), []
        for c in categorias:
            chave = re.sub(r"[^a-z0-9_]", "", c["key"].lower()) or "categoria"
            if chave in vistos:
                continue
            vistos.add(chave)
            c["key"] = chave
            unicas.append(c)
        tk["categories"] = unicas
    else:
        flash("Nenhuma categoria preenchida: as categorias atuais foram mantidas.", "erro")
    cfg["tickets"] = tk
    cfg["modules"]["tickets"] = tk["enabled"]

    if _salvar_cfg(cfg, guild["id"], guild["name"], "painel", "salvar_tickets"):
        pronto, falta = st.tickets_ready(cfg)
        if pronto:
            flash("✅ Tickets salvos.", "ok")
        else:
            flash(f"⚠️ Salvo, mas falta: {falta}.", "erro")
    else:
        flash("❌ Falha ao salvar.", "erro")
    return redirect(url_for("modulo", modulo="tickets", guild=guild["id"]))


# ---------- moderação ----------

@app.route("/modulo/moderacao", methods=["POST"])
def salvar_moderacao():
    atual = _servidor_atual()
    if atual is None:
        abort(404)
    guild = atual["guild"]
    cfg = deepcopy(atual["cfg"] or st.default_config(guild["id"], guild["name"]))
    md = dict(cfg.get("moderation") or {})

    md["enabled"] = _pedir_bool("enabled", md.get("enabled", False))
    md["log_channel_id"] = _pedir_int("log_channel_id", md.get("log_channel_id"))
    md["punish_channel_id"] = _pedir_int("punish_channel_id", md.get("punish_channel_id"))
    md["ignored_channels"] = _pedir_lista("ignored_channels")
    md["ignored_roles"] = _pedir_lista("ignored_roles")

    # Palavras proibidas
    termos = []
    for chave, valor in request.form.items():
        if not chave.startswith("termo_"):
            continue
        idx = chave.rsplit("_", 1)[-1]
        palavra = valor.strip()
        if not palavra:
            continue
        termos.append({
            "term": palavra,
            "mode": request.form.get(f"modo_{idx}", "palavra"),
            "severity": request.form.get(f"sev_{idx}", "media"),
        })
    palavras = dict(md.get("words") or {})
    if termos:
        palavras["terms"] = termos
    palavras["enabled"] = _pedir_bool("words_enabled", palavras.get("enabled", False))
    palavras["action"] = request.form.get("words_action", "apagar")
    palavras["message"] = request.form.get("words_message", "")[:500]
    md["words"] = palavras

    # Links
    links = dict(md.get("links") or {})
    links["enabled"] = _pedir_bool("links_enabled", links.get("enabled", False))
    links["mode"] = request.form.get("links_mode", "bloquear_convites")
    links["allowed_domains"] = [
        d.strip().lower().lstrip(".")
        for d in re.split(r"[\s,;\n]+", request.form.get("links_dominios", ""))
        if d.strip()
    ]
    links["action"] = request.form.get("links_action", "apagar")
    md["links"] = links

    convites = dict(md.get("invites") or {})
    convites["enabled"] = _pedir_bool("invites_enabled", convites.get("enabled", False))
    convites["action"] = request.form.get("invites_action", "apagar")
    convites["message"] = request.form.get("invites_message", "")[:500]
    md["invites"] = convites

    def _filtro(chave, padrao):
        d = dict(md.get(chave) or {})
        d["enabled"] = _pedir_bool(f"{chave}_enabled", d.get("enabled", False))
        d["action"] = request.form.get(f"{chave}_action", "apagar")
        for campo, pad in (("min_chars", 12), ("percent", 70),
                            ("window_seconds", 8), ("max_messages", 6),
                            ("max_repeats", 3), ("max_user_mentions", 6),
                            ("max_role_mentions", 2)):
            if campo in d:
                d[campo] = _pedir_int(f"{chave}_{campo}", pad) or pad
        return d

    md["caps"] = _filtro("caps", None)
    md["zerospace"] = _filtro("zerospace", None)
    md["flood"] = _filtro("flood", None)
    md["duplicate"] = _filtro("duplicate", None)
    md["mentions"] = _filtro("mentions", None)

    esc = dict(md.get("escalation") or {})
    esc["enabled"] = _pedir_bool("escalation_enabled", esc.get("enabled", False))
    esc["dm_user"] = _pedir_bool("escalation_dm", esc.get("dm_user", True))
    esc["exempt_roles"] = _pedir_lista("escalation_exempt_roles")

    passos = []
    for chave, valor in request.form.items():
        if not chave.startswith("esc_after_"):
            continue
        idx = chave.rsplit("_", 1)[-1]
        acao = request.form.get(f"esc_action_{idx}", "").strip()
        if not acao:
            continue
        passo = {"after": _pedir_int(f"esc_after_{idx}", 1) or 1, "action": acao}
        segundos = _pedir_int(f"esc_seconds_{idx}")
        if segundos:
            passo["seconds"] = segundos
        passos.append(passo)
    passos.sort(key=lambda p: p["after"])
    if passos:
        esc["steps"] = passos[:10]
    md["escalation"] = esc

    cfg["moderation"] = md
    cfg["modules"]["moderacao"] = md["enabled"]

    if _salvar_cfg(cfg, guild["id"], guild["name"], "painel", "salvar_moderacao"):
        flash("✅ Moderação salva.", "ok")
    else:
        flash("❌ Falha ao salvar.", "erro")
    return redirect(url_for("modulo", modulo="moderacao", guild=guild["id"]))


# ---------- liberação, boas-vindas, logs, contador, provas ----------

@app.route("/modulo/<modulo>", methods=["POST"])
def salvar_generico(modulo: str):
    atual = _servidor_atual()
    if atual is None:
        abort(404)
    if modulo not in {m["key"] for m in MODULOS_PAINEL}:
        abort(404)

    guild = atual["guild"]
    cfg = deepcopy(atual["cfg"] or st.default_config(guild["id"], guild["name"]))
    bloco = dict(cfg.get(modulo) or {})

    for chave in list(bloco.keys()):
        if chave == "enabled":
            bloco[chave] = _pedir_bool("enabled", bloco.get("enabled", False))
        elif chave.endswith("_channel_id"):
            bloco[chave] = _pedir_int(chave, bloco.get(chave))
        elif chave.endswith("_role_id"):
            bloco[chave] = _pedir_int(chave, bloco.get(chave))
        elif chave.endswith(("days", "seconds", "question", "questions", "score",
                                "chars", "minutes", "count", "total", "segundos")):
            bloco[chave] = _pedir_int(chave, bloco.get(chave))
        elif isinstance(bloco[chave], bool):
            bloco[chave] = _pedir_bool(chave, bloco.get(chave, False))
        elif isinstance(bloco[chave], str) or bloco[chave] is None:
            if chave in request.form:
                bruto = request.form.get(chave, "")
                bloco[chave] = bruto[:4000]
            elif bloco[chave] is None and chave.endswith("_message"):
                bloco[chave] = request.form.get(chave, "")[:4000]
        elif isinstance(bloco[chave], dict) and bloco[chave] and \
                all(isinstance(v, (int, type(None))) for v in bloco[chave].values()):
            bloco[chave] = {k: _pedir_int(f"status_{chave}_{k}") for k in bloco[chave]}

    if modulo == "autorole":
        bloco["keyword"] = request.form.get("keyword", bloco.get("keyword"))[:60]

    cfg[modulo] = bloco
    cfg["modules"][modulo] = bool(bloco.get("enabled"))

    if _salvar_cfg(cfg, guild["id"], guild["name"], "painel", f"salvar_{modulo}"):
        flash(f"✅ {meta_nome(modulo)} salvo.", "ok")
    else:
        flash("❌ Falha ao salvar.", "erro")
    return redirect(url_for("modulo", modulo=modulo, guild=guild["id"]))


def meta_nome(chave: str) -> str:
    m = next((x for x in MODULOS_PAINEL if x["key"] == chave), None)
    return m["label"] if m else chave


# ---------- jogos ----------

@app.route("/modulo/games", methods=["POST"])
def salvar_games():
    atual = _servidor_atual()
    if atual is None:
        abort(404)
    guild = atual["guild"]
    cfg = deepcopy(atual["cfg"] or st.default_config(guild["id"], guild["name"]))
    games = dict(cfg.get("games") or {})

    jogo = request.form.get("jogo", "coc")
    if jogo not in ("coc", "arma3"):
        abort(400)
    bloco = dict(games.get(jogo) or {})

    bloco["enabled"] = _pedir_bool("enabled", bloco.get("enabled", False))

    # Canais e cargos: ids do formulário.
    for chave in list(bloco.keys()):
        if chave.endswith("_channel_id") or chave.endswith("_role_id"):
            bloco[chave] = _pedir_int(chave, bloco.get(chave))

    if jogo == "coc":
        # `clan_tag` e `kick_message` são texto: o laço de ids não os pegaria.
        bloco["clan_tag"] = request.form.get("clan_tag", bloco.get("clan_tag") or "")
        bloco["verify_hours"] = _pedir_int("verify_hours", bloco.get("verify_hours")) or 1
        bloco["kick_message"] = request.form.get(
            "kick_message", bloco.get("kick_message") or "")[:500]
        roles = dict(bloco.get("roles") or {})
        for cargo in ("member", "elder", "coleader"):
            roles[cargo] = _pedir_int(f"role_{cargo}", roles.get(cargo))
        bloco["roles"] = roles

        canais = {}
        for chave in request.form:
            if not chave.startswith("status_"):
                continue
            sub = chave[len("status_"):]
            if "_" in sub or not sub:
                continue
            vid = _pedir_int(chave)
            if vid:
                canais[sub] = vid
        if canais:
            bloco["status_channel_ids"] = canais

    else:  # arma3
        bloco["auto_tag_on_join"] = _pedir_int("auto_tag_on_join",
                                                bloco.get("auto_tag_on_join"))
        bloco["sync_tags_on_message"] = _pedir_bool("sync_tags_on_message",
                                                    bloco.get("sync_tags_on_message", False))

    games[jogo] = bloco
    cfg["games"] = games
    cfg["modules"]["games"] = any(bool((games.get(j) or {}).get("enabled"))
                                    for j in ("coc", "arma3"))

    if _salvar_cfg(cfg, guild["id"], guild["name"], "painel", f"salvar_games_{jogo}"):
        flash(f"✅ {meta_nome('games')} salvo.", "ok")
    else:
        flash("❌ Falha ao salvar.", "erro")
    return redirect(url_for("modulo", modulo="games", guild=guild["id"]))


# --------------------------------------------------------------------------
# Ações que falam com o Discord
# --------------------------------------------------------------------------

@app.route("/acao/sync-comandos", methods=["POST"])
def acao_sync_comandos():
    pedido = runtime.request_command_sync()
    flash("🔄 O bot vai ressincronizar os comandos em instantes." if pedido
            else "⚠️ O bot ainda não está pronto para sincronizar.", "ok" if pedido else "erro")
    return redirect(url_for("dashboard", guild=request.form.get("guild")))


@app.route("/acao/publicar-painel", methods=["POST"])
def acao_publicar_painel():
    guild_id = request.form.get("guild", "").strip()
    canal_id = request.form.get("panel_channel_id", "").strip()
    atual = _servidor_atual()
    nome = atual["guild"]["name"] if atual else "?"

    if not (guild_id.isdigit() and canal_id.isdigit()):
        flash("❌ Escolha o canal do painel antes de publicar.", "erro")
        return redirect(url_for("modulo", modulo="tickets", guild=guild_id))

    resultado = runtime.run_coro(runtime._deploy_ticket_panel(int(guild_id), int(canal_id)))
    if resultado and resultado.get("ok"):
        flash(f"✅ Painel publicado com {resultado.get('categorias', 0)} categoria(s).", "ok")
    else:
        motivo = (resultado or {}).get("erro", "o bot não respondeu")
        flash(f"❌ Não consegui publicar: {motivo}", "erro")
    return redirect(url_for("modulo", modulo="tickets", guild=guild_id))


@app.route("/acao/testar-mensagem", methods=["POST"])
def acao_testar_mensagem():
    canal_id = request.form.get("test_channel_id", "").strip()
    texto = request.form.get("test_texto", "")
    guild_id = request.form.get("guild", "").strip()

    if not canal_id.isdigit():
        flash("❌ Escolha um canal para o teste.", "erro")
    else:
        resultado = runtime.run_coro(runtime._send_preview(int(canal_id), texto))
        if resultado and resultado.get("ok"):
            flash("✅ Mensagem enviada. Confira no canal.", "ok")
        else:
            flash(f"❌ Falha: {(resultado or {}).get('erro', 'sem resposta')}", "erro")
    return redirect(url_for("modulo", modulo=modulo_da_referrer(), guild=guild_id))


def modulo_da_referrer() -> str:
    ref = request.referrer or ""
    if "/modulo/" in ref:
        return ref.split("/modulo/")[1].split("?")[0].split("/")[0]
    return "tickets"


@app.route("/acao/validar", methods=["POST"])
def acao_validar():
    atual = _servidor_atual()
    if atual is None:
        abort(404)
    guild_id = atual["guild"]["id"]
    resultado = runtime.run_coro(runtime._validate_config(str(guild_id)))
    if resultado and resultado.get("ok"):
        flash("✅ Tudo certo: canais e cargos existem no Discord.", "ok")
    else:
        problemas = (resultado or {}).get("problemas") or ["o bot não respondeu"]
        flash("⚠️ " + "; ".join(problemas[:6]), "erro")
    return redirect(url_for("modulo", modulo=modulo_da_referrer(), guild=guild_id))


@app.route("/acao/sincronizar-view", methods=["POST"])
def acao_sincronizar_view():
    atual = _servidor_atual()
    if atual is None:
        abort(404)
    _recarregar_views(str(atual["guild"]["id"]))
    flash("🔄 Painel de tickets recarregado.", "ok")
    return redirect(url_for("modulo", modulo="tickets", guild=atual["guild"]["id"]))


@app.route("/acao/migrar-env", methods=["POST"])
def acao_migrar_env():
    forcar = _pedir_bool("forcar", False)
    avisos = mongo_db.migrar_config_antiga(forcar=forcar)
    for aviso in avisos:
        flash(aviso, "ok" if "importada" in aviso or "já tem" in aviso else "erro")
    return redirect(url_for("dashboard"))


# --------------------------------------------------------------------------
# Dados: tickets, modlog, logs
# --------------------------------------------------------------------------

@app.route("/tickets")
def tickets():
    atual = _servidor_atual()
    if atual is None:
        abort(404)
    gid = atual["guild"]["id"]

    status = request.args.get("status", "")
    busca = request.args.get("busca", "").strip()
    pagina = max(1, int(request.args.get("pagina", 1) or 1))
    por_pagina = 25

    itens = mongo_db.listar_tickets(
        guild_id=gid, status=status or None, busca=busca or None,
        limite=por_pagina, offset=(pagina - 1) * por_pagina)
    contagem = mongo_db.contar_tickets(gid)

    return render_template("tickets.html", modulos=MODULOS_PAINEL,
                            guild=atual["guild"], tickets=itens,
                            contagem=contagem, status=status, busca=busca,
                            pagina=pagina, por_pagina=por_pagina)


@app.route("/ticket/<ticket_id>")
def ticket(ticket_id: str):
    atual = _servidor_atual()
    if atual is None:
        abort(404)
    dado = mongo_db.get_ticket(ticket_id)
    # Um ID de outro servidor não pode ser aberto trocando o servidor no painel.
    if dado is None or str(dado.get("guild_id")) != str(atual["guild"]["id"]):
        abort(404)
    return render_template("ticket.html", guild=atual["guild"], ticket=dado)


@app.route("/ticket/<ticket_id>/apagar", methods=["POST"])
def ticket_apagar(ticket_id: str):
    atual = _servidor_atual()
    if atual is None:
        abort(404)
    dado = mongo_db.get_ticket(ticket_id)
    if dado is None or str(dado.get("guild_id")) != str(atual["guild"]["id"]):
        abort(404)
    if mongo_db.deletar_ticket(ticket_id):
        flash("🗑️ Ticket removido.", "ok")
    else:
        flash("❌ Não consegui remover.", "erro")
    return redirect(url_for("tickets", guild=atual["guild"]["id"]))


@app.route("/modlog")
def modlog():
    atual = _servidor_atual()
    if atual is None:
        abort(404)
    gid = atual["guild"]["id"]

    acao = request.args.get("acao", "")
    busca = request.args.get("busca", "").strip()
    itens = mongo_db.listar_modlog(guild_id=gid, acao=acao or None, busca=busca or None,
                                    limite=200)
    stats = mongo_db.stats_moderacao(gid)
    top = mongo_db.top_infratores(gid, limite=10, dias=30)

    return render_template("modlog.html", modulos=MODULOS_PAINEL,
                            guild=atual["guild"], itens=itens, stats=stats,
                            top=top, acao=acao, busca=busca)


@app.route("/infrações")
def infracoes():
    atual = _servidor_atual()
    if atual is None:
        abort(404)
    gid = atual["guild"]["id"]

    busca = request.args.get("busca", "").strip()
    user_id = request.args.get("user_id", "").strip()
    itens = mongo_db.listar_infracoes(guild_id=gid, busca=busca or None,
                                        user_id=user_id or None, limite=200)
    stats = mongo_db.stats_moderacao(gid)
    top = mongo_db.top_infratores(gid, limite=10, dias=30)

    return render_template("infracoes.html", modulos=MODULOS_PAINEL,
                            guild=atual["guild"], itens=itens, stats=stats,
                            top=top, busca=busca, user_id=user_id)


@app.route("/logs")
def logs():
    atual = _servidor_atual()
    gid = atual["guild"]["id"] if atual else None
    return render_template("logs.html",
                            guild=atual["guild"] if atual else None,
                            escopo="servidor" if gid else "todos",
                            itens=mongo_db.listar_auditoria(guild_id=gid, limite=150),
                            bot_logs=runtime.get_logs(150))


@app.route("/provas")
def provas():
    atual = _servidor_atual()
    if atual is None:
        abort(404)
    gid = atual["guild"]["id"]

    resultado = request.args.get("resultado", "")
    busca = request.args.get("busca", "").strip()
    itens = mongo_db.listar_provas(guild_id=gid, resultado=resultado or None,
                                    busca=busca or None, limite=100)
    stats = mongo_db.stats_provas(gid)

    return render_template("provas.html", modulos=MODULOS_PAINEL,
                            guild=atual["guild"], provas=itens, stats=stats,
                            resultado=resultado, busca=busca)


@app.route("/prova/<prova_id>")
def prova(prova_id: str):
    atual = _servidor_atual()
    if atual is None:
        abort(404)
    dado = mongo_db.get_prova(prova_id)
    if dado is None or str(dado.get("guild_id")) != str(atual["guild"]["id"]):
        abort(404)
    return render_template("prova.html", guild=atual["guild"], prova=dado)


@app.route("/preview", methods=["POST"])
def preview():
    """Renderiza uma mensagem com os placeholders, sem enviar ao Discord."""
    texto = request.form.get("texto", "")
    guild = _servidor_atual()
    guild_obj = None
    if guild:
        client = runtime.get_client()
        if client is not None:
            guild_obj = client.get_guild(int(guild["guild"]["id"]))
    try:
        saida = preview_placeholder(texto, guild=guild_obj)
    except Exception as exc:
        saida = f"erro ao renderizar: {exc}"
    return {"html": saida, "original": texto}


# --------------------------------------------------------------------------
# Erros
# --------------------------------------------------------------------------

@app.errorhandler(404)
def _404(_e):
    if not _logado():
        return redirect(url_for("login"))
    return render_template("erro.html", modulos=MODULOS_PAINEL,
                            guild=_guild_atual(), codigo=404,
                            mensagem="Não encontrei esta página."), 404


@app.errorhandler(500)
def _500(_e):
    return render_template("erro.html", modulos=MODULOS_PAINEL,
                            guild=_guild_atual(), codigo=500,
                            mensagem="Erro interno. Veja os logs."), 500


@app.errorhandler(403)
def _403(_e):
    return render_template("erro.html", modulos=MODULOS_PAINEL,
                            guild=_guild_atual(), codigo=403,
                            mensagem="Você não tem permissão para isto."), 403


# --------------------------------------------------------------------------
# Boot
# --------------------------------------------------------------------------

def run_web_panel():
    host = os.getenv("WEB_PANEL_HOST", "0.0.0.0")
    porta = int(os.getenv("WEB_PANEL_PORT", "2501"))

    if not mongo_db.conectar():
        print("[painel] Aviso: sem MongoDB. As páginas de dados ficarão vazias.")

    print(f"[painel] http://{host}:{porta}  ·  bot "
            f"{'online' if runtime.is_ready() else 'conectando'}")
    app.run(host=host, port=porta, debug=False, use_reloader=False, threaded=True)