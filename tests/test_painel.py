"""
Smoke test do painel: sobe o Flask com o bot desconectado e o Mongo inacessivel,
forca login e visita todas as rotas. Serve para pegar erro de template, nome de
funcao e variavel faltando sem precisar de Discord.
"""
import os
import sys
import unittest.mock as mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("WEB_PANEL_PASSWORD_HASH", "x")
os.environ.setdefault("MONGO_URI", "mongodb://127.0.0.1:27017/aura_teste")

import web_panel as w  # noqa: E402
import mongo_db  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402

SENHA = "teste-local-123"
w.PASSWORD_HASH = generate_password_hash(SENHA)

# Guilda falso: o painel só precisa dos campos do resumo.
GUILDE = {
    "id": "111111111111111111",
    "name": "Servidor de Teste",
    "icon": None,
    "member_count": 1234,
    "owner_id": "222222222222222222",
    "created_at": 1600000000.0,
    "bot_perms": True,
    "channels": 12,
    "roles": 8,
}

SNAPSHOT = {
    **GUILDE,
    "bot_user_id": "333333333333333333",
    "bot_top_role_position": 5,
    "channels": [
        {"id": "900", "name": "geral", "type": "text", "parent": None,
         "category_id": None, "position": 1},
        {"id": "901", "name": "voz", "type": "voice", "parent": None,
         "category_id": None, "position": 2},
        {"id": "902", "name": "Categorias", "type": "category", "parent": None,
         "category_id": None, "position": 0},
        {"id": "903", "name": "tickets", "type": "text", "parent": "Categorias",
         "category_id": "902", "position": 3},
    ],
    "roles": [
        {"id": "10", "name": "Staff", "position": 4, "managed": False,
         "mentionable": True, "color": "#5865f2", "assignable": True},
        {"id": "11", "name": "Membros", "position": 3, "managed": False,
         "mentionable": False, "color": "#111111", "assignable": True},
        {"id": "12", "name": "Bot", "position": 5, "managed": True,
         "mentionable": False, "color": "#222222", "assignable": False},
    ],
    "emojis": [],
}

ROTAS = [
    "/",
    "/config/geral",
    "/modulo/tickets",
    "/modulo/moderacao",
    "/modulo/autorole",
    "/modulo/boas_vindas",
    "/modulo/provas",
    "/modulo/logs",
    "/modulo/contador",
    "/modulo/games",
    "/modulo/games?jogo=arma3",
    "/tickets",
    "/tickets?status=aberto",
    "/modlog",
    "/infrações",
    "/logs",
    "/provas",
]


def main() -> int:
    falhas = 0
    with mock.patch.object(w.runtime, "list_guild_summaries", return_value=[GUILDE]), \
            mock.patch.object(w.runtime, "guild_snapshot", return_value=SNAPSHOT), \
            mock.patch.object(w.runtime, "is_ready", return_value=False), \
            mock.patch.object(mongo_db, "_garantir_conexao", return_value=False):
        app = w.app
        app.config["TESTING"] = True
        cliente = app.test_client()

        # Login
        r = cliente.get("/login")
        if r.status_code != 200:
            print("FALHA /login", r.status_code)
            falhas += 1
        r = cliente.post("/login", data={"password": SENHA})
        if r.status_code not in (302, 303):
            print("FALHA no login", r.status_code)
            falhas += 1

        for rota in ROTAS:
            url = rota if "?" in rota or rota == "/" else rota + f"?guild={GUILDE['id']}"
            try:
                resp = cliente.get(url)
            except Exception as exc:  # noqa: BLE001
                print(f"FALHA {url}: {exc.__class__.__name__}: {exc}")
                falhas += 1
                continue
            if resp.status_code != 200:
                print(f"FALHA {url}: HTTP {resp.status_code}")
                falhas += 1

        # Módulo inexistente
        resp = cliente.get(f"/modulo/inexistente?guild={GUILDE['id']}")
        if resp.status_code != 404:
            print(f"FALHA /modulo/inexistente: HTTP {resp.status_code}")
            falhas += 1

        # Redirect aberto não pode passar
        resp = cliente.post("/login", data={"password": SENHA,
                                           "next": "https://evil.example.com"})
        if "evil.example.com" in (resp.headers.get("Location") or ""):
            print("FALHA: open redirect permitido no login")
            falhas += 1

        # Precisa de login
        anon = app.test_client()
        resp = anon.get("/tickets")
        if resp.status_code not in (302, 303) or "/login" not in (resp.headers.get("Location") or ""):
            print(f"FALHA: rota protegida sem login-devolveu {resp.status_code}")
            falhas += 1

        # Salvar configuração (sem Mongo: deve avisar e não quebrar)
        form = {
            "prefix": "?",
            "locale": "pt-BR",
            "owner_ids_texto": "444444444444444444",
            "mod_tickets": "on",
            "mod_moderacao": "on",
        }
        resp = cliente.post(f"/config/geral?guild={GUILDE['id']}", data=form)
        if resp.status_code not in (302, 303):
            print(f"FALHA salvar geral: HTTP {resp.status_code}")
            falhas += 1

    print()
    print("painel: tudo certo" if falhas == 0 else f"painel: {falhas} falha(s)")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())