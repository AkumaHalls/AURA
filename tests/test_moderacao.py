"""Testes offline dos filtros de moderação (sem Discord e sem Mongo)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017/aura_teste")

from core import settings as st
from cogs import moderacao as M


def cfg_moderacao(**over):
    cfg = st.default_config(1, "Servidor de Teste")
    cfg["moderation"]["enabled"] = True
    cfg["moderation"]["words"].update({
        "enabled": True,
        "terms": [
            {"term": "idiota", "mode": "palavra", "severity": "media"},
            {"term": "merda", "mode": "palavra", "severity": "alta"},
            {"term": r"\b\d{3,}\b", "mode": "regex", "severity": "baixa"},
        ],
    })
    cfg["moderation"]["links"].update({
        "enabled": True, "mode": "lista_branca",
        "allowed_domains": ["discord.com", "meusite.com"],
    })
    cfg["moderation"]["caps"].update({"enabled": True, "percent": 70, "min_chars": 12})
    cfg["moderation"]["zerospace"].update({"enabled": True, "min_chars": 12})
    cfg["moderation"].update(over)
    return cfg


def eq(nome, obtido, esperado):
    ok = obtido == esperado
    print(f"{'ok  ' if ok else 'FALHA'} {nome}")
    if not ok:
        print(f"      esperado={esperado!r}\n      obtido  ={obtido!r}")
    return ok


def main():
    falhas = 0
    cfg = cfg_moderacao()

    # ---- palavras proibidas ----
    falhas += not eq("palavra exata", M.checar_palavras("você é um idiota", cfg).detalhe, "idiota")
    falhas += not eq("case/acentos ignorados", M.checar_palavras("Que IDIOTA!", cfg).detalhe, "idiota")
    falhas += not eq("não casa dentro de palavra",
                     M.checar_palavras("meu idiotalismo", cfg), None)
    falhas += not eq("regex", M.checar_palavras("código 12345", cfg).detalhe, r"\b\d{3,}\b")
    falhas += not eq("palavra limpa passa", M.checar_palavras("bom dia pessoal", cfg), None)

    # zerospace: burlando filtro
    invis = "".join(M.INVISIBLE[:2] * 3)
    falhas += not eq("zerospace detecta", bool(M.checar_zerospace("voce" + invis + "e um idiota aqui", cfg["moderation"]["zerospace"])), True)

    # ---- links / lista branca ----
    lk = cfg["moderation"]["links"]
    falhas += not eq("domínio na whitelist passa", M.checar_links("olha https://meusite.com/x", lk), None)
    falhas += not eq("subdomínio da whitelist passa", M.checar_links("https://www.discord.com/app", lk), None)
    falhas += not eq("domínio fora é bloqueado", M.checar_links("https://spam.com", lk).filtro, "link")
    falhas += not eq("invite bloqueado em modo lista branca",
                     M.checar_links("discord.gg/abc123", lk).filtro, "link")

    modo_convites = {"mode": "bloquear_convites", "allowed_domains": []}
    falhas += not eq("convite bloqueado", bool(M.checar_links("discord.gg/abc", modo_convites)), True)
    falhas += not eq("link comum passa em modo convites",
                     M.checar_links("https://google.com", modo_convites), None)
    modo_tudo = {"mode": "bloquear_tudo", "allowed_domains": []}
    falhas += not eq("bloquear_tudo barra link comum",
                     bool(M.checar_links("https://google.com", modo_tudo)), True)

    # ---- caps ----
    cp = cfg["moderation"]["caps"]
    falhas += not eq("caps detectado", bool(M.checar_caps("AAAAAAAAAAAAA MEU DEUS", cp)), True)
    falhas += not eq("frase normal não é caps", M.checar_caps("Tudo bem com você hoje?", cp), None)
    falhas += not eq("texto curto ignorado", M.checar_caps("AAAA", cp), None)

    # ---- flood / duplicatas ----
    M._track.clear(); M._dup_track.clear()
    for _ in range(4):
        v = M.checar_flood(1, 2, janela=8, limite=4)
    falhas += not eq("flood no limite", v, None)
    v = M.checar_flood(1, 2, janela=8, limite=4)
    falhas += not eq("flood dispara", v.filtro if v else None, "flood")
    falhas += not eq("flood isolado por usuário", M.checar_flood(1, 99, 8, 4), None)

    M._dup_track.clear()
    for _ in range(3):
        v = M.checar_duplicata(1, 3, "spam spam", janela=30, limite=3)
    falhas += not eq("duplicata no limite", v, None)
    v = M.checar_duplicata(1, 3, "spam spam", janela=30, limite=3)
    falhas += not eq("duplicata dispara", v.filtro if v else None, "duplicada")

    # ---- escalada ----
    esc = {"enabled": True, "steps": [
        {"after": 3, "action": "timeout", "seconds": 600},
        {"after": 6, "action": "banir"},
    ]}
    falhas += not eq("escalada antes do gatilho", M.Moderacao._passo_escalada(esc, 1), None)
    falhas += not eq("escalada no 1º gatilho",
                     M.Moderacao._passo_escalada(esc, 3)["action"], "timeout")
    falhas += not eq("escalada no 2º gatilho",
                     M.Moderacao._passo_escalada(esc, 7)["action"], "banir")

    # ---- normalização de invisíveis ----
    falhas += not eq("remove invisíveis", M.strip_invisible("a" + M.INVISIBLE[0] + "b"), "ab")
    falhas += not eq("normaliza acentos", M.normalize_text("ÍDÍOTA"), "idiota")

    print()
    print("FALHAS:", falhas)
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())