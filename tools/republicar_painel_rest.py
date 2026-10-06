"""
Republica o painel de tickets via REST (sem gateway).

O Discord nao deixa abrir uma segunda sessao de gateway com o mesmo token, entao
um cliente extra nao conecta. A API HTTP funciona, e como a view do painel ja
esta registrada no processo do bot (registrar_views_iniciais no on_ready), basta
enviar o DropDown com o mesmo custom_id para o bot responder.

Antes de publicar, apaga os paineis antigos do bot no canal, com a mesma regra de
_deploy_ticket_panel.

Uso: python tools/republicar_painel_rest.py <guild_id> <canal_id>
"""
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mongo_db  # noqa: E402

API = "https://discord.com/api/v10"
TEXTO_ANTIGO = ("Bem-vindo à central de ajuda! Use o menu abaixo para selecionar "
                "o motivo do seu contato e abrir um ticket. "
                "Um líder ou co-líder irá te ajudar.")


def _req(metodo, caminho, token, **kw):
    r = requests.request(metodo, f"{API}{caminho}", headers={"Authorization": f"Bot {token}"},
                         timeout=30, **kw)
    return r


def main() -> int:
    if len(sys.argv) < 3:
        print("uso: python tools/republicar_painel_rest.py <guild_id> <canal_id>")
        return 2
    guild_id, canal_id = sys.argv[1], sys.argv[2]
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("ERRO: DISCORD_TOKEN nao encontrado")
        return 1

    mongo_db.conectar()
    cfg = next((d for d in mongo_db.list_all_guild_configs() if str(d["guild_id"]) == str(guild_id)), None)
    if cfg is None:
        print("ERRO: servidor sem configuracao")
        return 1
    tk = cfg.get("tickets") or {}
    cats = [c for c in (tk.get("categories") or []) if c.get("key") and c.get("label")][:25]
    if not cats:
        print("ERRO: nenhuma categoria configurada")
        return 1

    guild = _req("GET", f"/guilds/{guild_id}", token)
    if guild.status_code != 200:
        print("ERRO guild:", guild.status_code, guild.text[:200])
        return 1
    guild = guild.json()
    nome = guild.get("name") or "?"
    meu_id = _req("GET", "/users/@me", token).json().get("id")

    # apaga paineis antigos do proprio bot
    apagados = 0
    for m in _req("GET", f"/channels/{canal_id}/messages?limit=30", token).json():
        autor = (m.get("author") or {}).get("id")
        embeds = m.get("embeds") or []
        if autor != meu_id or not embeds:
            continue
        titulo = embeds[0].get("title") or ""
        if "Central de Atendimento" in titulo or "Atendimento" in titulo:
            d = _req("DELETE", f"/channels/{canal_id}/messages/{m['id']}", token)
            print(f"  apagado painel antigo {m['id']} -> {d.status_code}")
            apagados += 1

    embed = {
        "title": tk.get("panel_title") or f"🛡️ Central de Atendimento - {nome} 🛡️",
        "description": tk.get("panel_description") or TEXTO_ANTIGO,
        "color": int(str(tk.get("panel_color") or "#f1c40f").lstrip("#"), 16),
        "footer": {"text": f"Atendimento do Clã {nome}"},
    }
    icone = guild.get("icon")
    if tk.get("panel_image_url"):
        embed["image"] = {"url": tk["panel_image_url"]}
    elif icone:
        embed["image"] = {"url": f"https://cdn.discordapp.com/icons/{guild_id}/{icone}.png?size=512"}

    componente = {
        "type": 1,
        "components": [
            {
                "type": 3,
                "custom_id": f"tk:{int(guild_id)}:select",
                "placeholder": "Selecione um tópico para o suporte...",
                "min_values": 1,
                "max_values": 1,
                "options": [
                    {
                        "label": (c.get("label") or "Ticket")[:100],
                        "value": str(c.get("key")),
                        "description": (c.get("description") or "")[:100],
                        "emoji": {"name": c.get("emoji")} if c.get("emoji") else None,
                    }
                    for c in cats
                ],
            }
        ],
    }
    payload = {"embeds": [embed], "components": [componente]}
    resp = _req("POST", f"/channels/{canal_id}/messages", token, json=payload)
    if resp.status_code not in (200, 201):
        print("ERRO ao publicar:", resp.status_code, resp.text[:400])
        return 1

    msg = resp.json()
    print(f"{nome}: painel publicado em {msg['id']} com {len(cats)} categoria(s)")
    print(f"  paineis antigos apagados: {apagados}")
    print(f"  embed tem campo 'Categorias': {bool((msg['embeds'][0]).get('fields'))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())