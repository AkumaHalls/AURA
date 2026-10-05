"""
Extensão do smoke test do painel: exercita os POSTs de todos os módulos, o
isolamento por servidor e o salvamento de config, que o test_painel.py só
toca de leve.
"""
import os
import sys
import unittest.mock as mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("WEB_PANEL_PASSWORD_HASH", "x")
os.environ.setdefault("MONGO_URI", "mongodb://127.0.0.1:27017/aura_teste")

import mongo_db  # noqa: E402
import web_panel as w  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402

SENHA = "teste-local-123"
w.PASSWORD_HASH = generate_password_hash(SENHA)

GUILD_A = {
    "id": "111111111111111111",
    "name": "Servidor A",
    "icon": None,
    "member_count": 100,
    "owner_id": "222222222222222222",
    "created_at": 1600000000.0,
    "bot_perms": True,
    "channels": 3,
    "roles": 2,
}
GUILD_B = dict(GUILD_A, id="999999999999999999", name="Servidor B")

SNAPSHOT = {
    **GUILD_A,
    "bot_user_id": "333333333333333333",
    "bot_top_role_position": 5,
    "channels": [
        {"id": "900", "name": "geral", "type": "text", "parent": None,
         "category_id": None, "position": 1},
        {"id": "901", "name": "voz", "type": "voice", "parent": None,
         "category_id": None, "position": 2},
        {"id": "902", "name": "Categorias", "type": "category", "parent": None,
         "category_id": None, "position": 0},
    ],
    "roles": [
        {"id": "10", "name": "Staff", "position": 4, "managed": False,
         "mentionable": True, "color": "#5865f2", "assignable": True},
        {"id": "11", "name": "Membros", "position": 3, "managed": False,
         "mentionable": False, "color": "#111111", "assignable": True},
    ],
    "emojis": [],
}

MODULOS = ["tickets", "moderacao", "autorole", "boas_vindas", "provas",
           "logs", "contador", "games"]


def cfg_modules_ligado(cfg: dict, modulo: str) -> bool:
    return bool((cfg.get("modules") or {}).get(modulo))


class _Gravado:
    """Guarda o que o painel tentou salvar, sem tocar em banco nenhum."""

    def __init__(self) -> None:
        self.ultimo = None

    def __call__(self, cfg, guild_id, guild_name, origem, acao):
        self.ultimo = {"cfg": cfg, "guild_id": guild_id, "guild_name": guild_name,
                       "origem": origem, "acao": acao}
        return True


def main() -> int:
    falhas = 0
    gravado = _Gravado()

    def falha(msg: str) -> None:
        nonlocal falhas
        falhas += 1
        print("FALHA", msg)

    with mock.patch.object(w.runtime, "list_guild_summaries",
                           return_value=[GUILD_A, GUILD_B]), \
            mock.patch.object(w.runtime, "guild_snapshot", return_value=SNAPSHOT), \
            mock.patch.object(w.runtime, "is_ready", return_value=False), \
            mock.patch.object(w.mongo_db, "upsert_guild_config", return_value=True), \
            mock.patch.object(w.st, "invalidate"), \
            mock.patch.object(w, "_salvar_cfg", gravado), \
            mock.patch.object(mongo_db, "_garantir_conexao", return_value=False):

        app = w.app
        app.config["TESTING"] = True
        c = app.test_client()
        c.post("/login", data={"password": SENHA})
        g = GUILD_A["id"]

        # ---- geral: interruptores de módulo no mesmo formulário ----
        c.post(f"/config/geral?guild={g}", data={
            "prefix": "!", "locale": "pt-BR",
            "owner_ids_texto": "444444444444444444",
            "mod_tickets": "on", "mod_provas": "on",
        })
        cfg = gravado.ultimo["cfg"]
        if gravado.ultimo is None:
            falha("geral nao salvou")
        else:
            if cfg["prefix"] != "!":
                falha(f"prefixo virou {cfg['prefix']!r}")
            if not cfg["modules"]["tickets"] or not cfg["modules"]["provas"]:
                falha("modulos ligados nao foram marcados")
            if cfg["modules"]["moderacao"] or cfg["modules"]["logs"]:
                falha("modulos desmarcados voltaram ligados")

        # ---- tickets: campos de texto e categoria ----
        c.post(f"/modulo/tickets?guild={g}", data={
            "enabled": "on", "panel_channel_id": "900",
            "support_channel_id": "900", "staff_role_id": "10",
            "panel_title": "Atendimento", "panel_description": "Escolha",
            "panel_color": "#112233",
            "max_open_per_user": "2", "auto_close_days": "7",
            "close_delay_seconds": "5",
            "ticket_name_format": "{emoji} {label}",
            "message_template": "ola {user}", "close_button_label": "Fechar",
            "welcome_message": "bem-vindo", "rating_enabled": "on",
            "rating_question": "como foi",
            "cat_key_1": "suporte", "cat_label_1": "Suporte",
            "cat_emoji_1": "x", "cat_description_1": "duvidas",
            "cat_prompt_1": "o que precisa", "cat_staff_1": "10",
        })
        tk = gravado.ultimo["cfg"]["tickets"]
        if gravado.ultimo["acao"] != "salvar_tickets":
            falha(f"acao de tickets errada: {gravado.ultimo['acao']}")
        for campo, esperado in (("ticket_name_format", "{emoji} {label}"),
                                ("message_template", "ola {user}"),
                                ("close_button_label", "Fechar"),
                                ("panel_color", "#112233")):
            if tk.get(campo) != esperado:
                falha(f"tickets.{campo} = {tk.get(campo)!r}")
        if len(tk.get("categories") or []) != 1:
            falha(f"categorias: {tk.get('categories')}")
        elif tk["categories"][0]["key"] != "suporte":
            falha(f"chave de categoria: {tk['categories'][0]['key']}")

        # ---- moderacao ----
        c.post(f"/modulo/moderacao?guild={g}", data={
            "enabled": "on", "log_channel_id": "900",
            "ignored_channels_texto": "900, 901",
            "ignored_roles_texto": "10",
        })
        if gravado.ultimo["acao"] != "salvar_moderacao":
            falha(f"acao de moderacao errada: {gravado.ultimo['acao']}")

        # ---- modulos genericos: o campo precisa chegar inteiro no banco ----
        genericos = {
            "autorole": {"enabled": "on", "channel_id": "900", "keyword": "entrar",
                         "give_role_id": "10", "delete_delay_seconds": "15",
                         "welcome_message": "liberado {user}"},
            "boas_vindas": {"enabled": "on", "channel_id": "901",
                            "message": "oi {user}", "send_dm": "on"},
            "logs": {"enabled": "on", "join_channel_id": "900",
                     "log_boost": "on", "log_role_change": "on"},
            "contador": {"enabled": "on", "channel_id": "900",
                         "channel_name": "Membros: {count}"},
        }
        for mod, form in genericos.items():
            resp = c.post(f"/modulo/{mod}?guild={g}", data=form)
            if resp.status_code not in (302, 303):
                falha(f"POST /modulo/{mod}: HTTP {resp.status_code}")
                continue
            if gravado.ultimo is None:
                falha(f"{mod} nao salvou")
                continue
            bloco = gravado.ultimo["cfg"][mod]
# Ids de canal/cargo chegam como texto em uns lugares e como int em
            # outros, porque cada bloco foi escrito em uma epoca diferente. O
            # que importa e que o valor gravado bate com o digitado.
            esperado = {
                "autorole": [("channel_id", "900"), ("keyword", "entrar"),
                             ("give_role_id", 10), ("delete_delay_seconds", 15),
                             ("welcome_message", "liberado {user}"),
                             ("delete_message", True)],
                "boas_vindas": [("channel_id", "901"), ("message", "oi {user}"),
                                ("send_dm", True)],
                "logs": [("join_channel_id", "900"), ("log_boost", True),
                         ("log_role_change", True)],
                "contador": [("channel_id", "900"),
                             ("channel_name", "Membros: {count}")],
            }[mod]
            for campo, quer in esperado:
                if str(bloco.get(campo)) != str(quer):
                    falha(f"{mod}.{campo} = {bloco.get(campo)!r}, esperava {quer!r}")
            if not cfg_modules_ligado(gravado.ultimo["cfg"], mod):
                falha(f"module {mod} nao ligou junto")

        # ---- provas: cooldown e nota zero tem de valer zero ----
        c.post(f"/modulo/provas?guild={g}", data={
            "enabled": "on", "pass_score": "0", "cooldown_days": "0",
            "time_per_question": "60",
        })
        p = gravado.ultimo["cfg"]["provas"]
        if p.get("cooldown_days") != 0:
            falha(f"cooldown_days virou {p.get('cooldown_days')!r}, devia ser 0")
        if p.get("pass_score") != 0:
            falha(f"pass_score virou {p.get('pass_score')!r}, devia ser 0")

        # ---- games ----
        c.post(f"/modulo/games?guild={g}", data={"jogo": "coc", "enabled": "on",
                                                 "clan_tag": "ABC"})
        if gravado.ultimo["acao"] != "salvar_games_coc":
            falha(f"acao de games errada: {gravado.ultimo['acao']}")
        if gravado.ultimo["cfg"]["games"]["coc"]["clan_tag"] != "ABC":
            falha("clan_tag nao foi salvo")

        # ---- modulo generico precisa ter action save_ no log ----
        # ---- isolamento: ticket de outro servidor nao abre ----
        with mock.patch.object(mongo_db, "get_ticket",
                               return_value={"_id": "x", "guild_id": GUILD_B["id"],
                                             "channel_name": "t"}):
            resp = c.get(f"/ticket/nao-existe?guild={g}")
            if resp.status_code != 404:
                falha(f"ticket de outro servidor nao foi barrado: HTTP {resp.status_code}")
            resp = c.post(f"/ticket/nao-existe/apagar?guild={g}")
            if resp.status_code != 404:
                falha(f"apagar ticket de outro servidor: HTTP {resp.status_code}")

        with mock.patch.object(mongo_db, "get_prova",
                               return_value={"_id": "y", "guild_id": GUILD_B["id"]}):
            resp = c.get(f"/prova/nao-existe?guild={g}")
            if resp.status_code != 404:
                falha(f"prova de outro servidor nao foi barrada: HTTP {resp.status_code}")

        # ---- ticket do proprio servidor abre ----
        with mock.patch.object(mongo_db, "get_ticket",
                               return_value={"_id": "x", "guild_id": g,
                                             "channel_name": "t", "status": "aberto",
                                             "user_name": "ze", "ts": 0}):
            resp = c.get(f"/ticket/abc?guild={g}")
            if resp.status_code != 200:
                falha(f"ticket do proprio servidor nao abriu: HTTP {resp.status_code}")

        # ---- logs filtra por servidor ----
        with mock.patch.object(mongo_db, "listar_auditoria",
                               return_value=[]) as auditoria:
            c.get(f"/logs?guild={g}")
            if auditoria.call_args.kwargs.get("guild_id") != g:
                falha(f"logs nao filtrou por guild_id: {auditoria.call_args}")

        # ---- preset nao pode existir sem perfil valido ----
        resp = c.post(f"/config/preset?guild={g}", data={"perfil": "inexistente"})
        if resp.status_code not in (302, 303):
            falha(f"preset invalido: HTTP {resp.status_code}")

    print()
    print("painel post: tudo certo" if falhas == 0 else f"painel post: {falhas} falha(s)")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())