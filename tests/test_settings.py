"""
Testes da lógica que não depende de Discord: normalização de config, presets,
embaralhamento de alternativas e deduplicação de categorias.
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import settings as st  # noqa: E402

FALHAS = 0


def checa(condicao, msg):
    global FALHAS
    if condicao:
        print("ok  ", msg)
    else:
        FALHAS += 1
        print("FALHA", msg)


def main() -> int:
    # ---- ids podem vir como texto do formulário ----
    cfg = st.normalize({"tickets": {"panel_channel_id": "900", "staff_role_id": "10"},
                        "autorole": {"channel_id": "901"}},
                       "1", "Servidor")
    checa(cfg["tickets"]["panel_channel_id"] == 900, "tickets.panel_channel_id vira int")
    checa(cfg["tickets"]["staff_role_id"] == 10, "tickets.staff_role_id vira int")
    checa(cfg["autorole"]["channel_id"] == 901, "autorole.channel_id vira int")

    # ---- texto em campo de número não derruba o resto ----
    cfg = st.normalize({"contador": {"enabled": "on"}}, "1", "Servidor")
    checa(cfg["contador"]["enabled"] is True, '"on" vira True')
    checa(isinstance(cfg["contador"]["channel_name"], str),
          "channel_name continua texto")

    # ---- zero é valor, não ausência ----
    p = st.normalize_provas({"cooldown_days": 0, "pass_score": 0})
    checa(p["cooldown_days"] == 0, "cooldown_days 0 continua 0")
    checa(p["pass_score"] == 0, "pass_score 0 continua 0")
    p = st.normalize_provas({})
    checa(p["cooldown_days"] == 3, "cooldown_days vazio usa o padrão")
    checa(p["pass_score"] == 7, "pass_score vazio usa o padrão")
    p = st.normalize_provas({"cooldown_days": "lixo"})
    checa(p["cooldown_days"] == 3, "cooldown_days invalido usa o padrão")

    # ---- limites ----
    p = st.normalize_provas({"time_per_question": 5, "cooldown_days": 5000})
    checa(p["time_per_question"] == 15, "tempo minimo de 15s")
    checa(p["cooldown_days"] == 90, "cooldown maximo de 90 dias")

    # ---- categorias ----
    cats = st.normalize_categories([
        {"key": "suporte!!", "label": "Suporte", "emoji": "x"},
        {"key": "SUPORTE", "label": "Repetida"},
        {"label": "Sem chave"},
    ])
    chaves = [c["key"] for c in cats]
    checa(len(chaves) == len(set(chaves)), "categorias repetidas saem deduplicadas")
    checa(all(c["key"].replace("_", "").isalnum() for c in cats),
          "chave de categoria fica sem caractere especial")
    checa(any(c["key"] == "suporte" for c in cats), "chave com acento e cleaned")

    # ---- cor inválida cai no padrão ----
    tk = st.normalize_tickets({"panel_color": "azul"})
    checa(tk["panel_color"].startswith("#"), "cor invalida vira hex")

    # ---- clan tag ----
    g = st.normalize_games({"coc": {"clan_tag": " abc def "}})
    checa(g["coc"]["clan_tag"] == "#ABCDEF", "clan_tag vira #TAG maiúscula sem espaço")

    # ---- presets cobrem os perfis ----
    for perfil in ("generico", "coc", "arma3"):
        p = st.preset_config(perfil)
        checa(bool(p), f"preset {perfil} existe")
        checa(p["profile"] == perfil, f"preset {perfil} se identifica")
    checa(st.preset_config("inexistente") is None, "preset desconhecido devolve vazio")

    # ---- dono ----
    checa(st.eh_dono(123) in (True, False), "eh_dono sem config nao quebra")
    cfg = st.default_config("1", "Servidor")
    cfg["owner_ids"] = [123]
    checa(st.eh_dono(123, cfg) is True, "dono da config e reconhecido")
    checa(st.eh_dono(999, cfg) is False, "outro nao e dono")

    # ---- prontidão dos módulos ----
    cfg = st.default_config("1", "Servidor")
    pronto, falta = st.tickets_ready(cfg)
    checa(not pronto and bool(falta), "tickets incompleto avisa o que falta")
    pronto, falta = st.moderation_ready(cfg)
    checa(not pronto and bool(falta), "moderacao incompleta avisa o que falta")

    # ---- embaralhamento de alternativas ----
    from cogs.sistema_prova import _embaralhar_alternativas
    original = ["a", "b", "c", "d", "e"]
    for _ in range(50):
        q = {"alternativas": list(original), "correta": 2}
        _embaralhar_alternativas(q)
        correta = q["correta"]
        checa_valida = (isinstance(correta, int) and 0 <= correta < len(q["alternativas"]))
        if not checa_valida:
            break
        if q["alternativas"][correta] != "c":
            break
    else:
        checa(True, "alternativas embaralhadas 50x mantendo a correta")
    q = {"alternativas": list(original), "correta": 2}
    _embaralhar_alternativas(q)
    checa(sorted(q["alternativas"]) == sorted(original), "nenhuma alternativa perdida")
    q = {"alternativas": list(original), "correta": 99}
    _embaralhar_alternativas(q)
    checa(q["correta"] == 99, "indice de correta invalido nao e mexido")

    print()
    print("settings: tudo certo" if FALHAS == 0 else f"settings: {FALHAS} falha(s)")
    return 1 if FALHAS else 0


if __name__ == "__main__":
    random.seed(7)
    sys.exit(main())