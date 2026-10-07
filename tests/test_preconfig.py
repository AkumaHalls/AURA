"""
Testa a pre-configuração por perfil.

Cobre o que importa:
  - aplica o preset de categorias do perfil;
  - liga os módulos pedidos;
  - moderação fica sem punição automática (só avisa e apaga);
  - preenche canais/cargos que encontra e **relata** o que faltou, sem inventar;
  - roda de novo sem apagar o que já estava ajustado.
"""
import os
import sys
import unittest.mock as mk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FALHAS = 0
GID = "1362076878458065037"


def checa(condicao, msg):
    global FALHAS
    if condicao:
        print("ok  ", msg)
    else:
        FALHAS += 1
        print("FALHA", msg)


class Canal:
    def __init__(self, cid, nome):
        self.id = cid
        self.name = nome


class Cargo:
    def __init__(self, rid, nome):
        self.id = rid
        self.name = nome


class GuildFalso:
    def __init__(self):
        self.name = "BAD - Bravos ANJOS DEFENSORES"
        self.text_channels = [
            Canal(900, "📋 painel-de-tickets"),
            Canal(901, "#suporte"),
            Canal(902, "📃 registro-de-membros"),
            Canal(903, "log-geral"),
            Canal(904, "boas-vindas"),
            Canal(905, "membros"),
        ]
        self.roles = [
            Cargo(1, "Bot"), Cargo(2, "Membro"), Cargo(3, "Atendente"),
            Cargo(4, "Elder"), Cargo(5, "CoLider"), Cargo(6, "Dono"),
        ]


ENV = {
    "OWNER_ID": "260912891782365196",
    "CLAN_TAG": "#U0L9VGYV",
    "id_canal_suporte": "901",
    "id_cargo_atendente": "3",
    "ID_CANAL_TRANSCRICOES": "777",
    "LOG_CHANNEL_ID": "903",
    "CANAL_REGISTRO_ID": "902",
    "APPROVAL_LOG_CHANNEL_ID": "903",
    "COC_MEMBER_ROLE_ID": "2",
    "COC_ELDER_ROLE_ID": "4",
    "COC_COLEADER_ROLE_ID": "5",
}


def main() -> int:
    from core import preconfig as pc
    from core import settings as st

    guild = GuildFalso()

    with mk.patch.dict(os.environ, {**ENV, "TEST_GUILD_ID": GID}, clear=False):
        cfg, falta = pc.montar(GID, guild.name, None, "coc", guild=guild)

    # ---- perfil e preset ----
    checa(cfg["profile"] == "coc", "perfil coc aplicado")
    cats = cfg["tickets"]["categories"]
    chaves = [c["key"] for c in cats]
    checa(len(cats) == 8, f"preset coc trouxe 8 categorias (veio {len(cats)})")
    checa("guerras_cwl" in chaves, "categoria de guerra/CWL presente")
    checa("doacoes" in chaves, "categoria de doações presente")
    checa("outros" in chaves, "categoria 'outros' presente (sempre tem uma)")

    # ---- módulos ----
    mods = cfg["modules"]
    ligados = [k for k, v in mods.items() if v]
    checa(len(ligados) == 8, f"todos os 8 módulos ligados (veio {len(ligados)})")

    # ---- moderação sem punição automática ----
    mod = cfg["moderation"]
    checa(mod["enabled"] is True, "moderação ligada")
    acoes = {mod[f]["action"] for f in ("words", "links", "invites", "caps",
                                        "flood", "duplicate", "mentions",
                                        "zerospace")}
    checa(acoes == {"apagar"}, f"todo filtro só apaga (veio {acoes})")
    passos = mod["escalation"]["steps"]
    checa(all(p["action"] == "avisar" for p in passos),
          f"escalada só avisa, sem timeout/ban (veio {[p['action'] for p in passos]})")
    checa(mod["punish_channel_id"] is None, "sem canal de punição")

    # ---- canais e cargos preenchidos ----
    detectar = pc.detectar_canais(guild)
    tk = cfg["tickets"]
    checa(tk["enabled"] is True, "tickets ligado")
    checa(tk["support_channel_id"] == 901, "canal de suporte preenchido")
    checa(tk["panel_channel_id"] == 900, "canal do painel detectado pelo nome")
    checa(tk["staff_role_id"] == 3, "cargo de atendente detectado")
    checa(tk["transcript_channel_id"] == 777, "canal de transcrições veio do env")
    checa(cfg["logs"]["join_channel_id"] == 903, "log de entrada preenchido")
    checa(cfg["boas_vindas"]["channel_id"] == 904, "canal de boas-vindas detectado")
    checa(cfg["contador"]["channel_id"] == 905, "canal do contador detectado")
    checa(cfg["autorole"]["give_role_id"] == 2, "cargo de membro detectado")
    checa(cfg["provas"]["approval_role_id"] == 6, "cargo aprovador detectado")
    checa(cfg["owner_ids"] == ["260912891782365196"], "dono do env registrado")

    # ---- clash ----
    coc = cfg["games"]["coc"]
    checa(coc["enabled"] is True, "módulo clash ligado")
    checa(coc["clan_tag"] == "#U0L9VGYV", "tag do clã preenchida")
    checa(coc["roles"]["elder"] == 4 and coc["roles"]["coleader"] == 5,
          "cargos elder/coleader preenchidos")

    # ---- pendências honestas ----
    checa(any("Status do Clã" in f or "status do Status" in f.lower() for f in falta),
          f"pendência cita os canais de voz do status ({falta})")
    checa(isinstance(falta, list) and all(isinstance(f, str) for f in falta),
          "pendências são listas de texto legíveis")

    # ---- perfil generico ----
    with mk.patch.dict(os.environ, ENV, clear=False):
        cfg2, _ = pc.montar("999", "KOTH", None, "generico", guild=guild)
    chaves2 = [c["key"] for c in cfg2["tickets"]["categories"]]
    checa(cfg2["profile"] == "generico", "perfil generico aplicado")
    checa("suporte" in chaves2 and "denuncia" in chaves2,
          f"preset generico traz suporte/denúncia ({chaves2})")
    checa("guerras_cwl" not in chaves2, "preset generico não tem categoria de guerra")

    # ---- perfil desconhecido cai no generico, não quebra ----
    with mk.patch.dict(os.environ, ENV, clear=False):
        cfg3, _ = pc.montar("999", "X", None, "perfil_que_nao_existe", guild=guild)
    checa(cfg3["profile"] == "generico", "perfil desconhecido cai no generico")

    # ---- .env é do servidor do Clash e não pode vazar para outro ----
    KOTH = "810674050581659668"
    with mk.patch.dict(os.environ, {**ENV, "TEST_GUILD_ID": GID}, clear=False):
        cfg5, falta5 = pc.montar(KOTH, "KOTH", None, "generico", guild=guild)

    checa((cfg5["games"].get("coc") or {}).get("clan_tag") is None,
          "servidor que não é do Clash não recebe o CLAN_TAG")
    checa((cfg5["games"].get("coc") or {}).get("enabled") is not True,
          "módulo clash fica desligado no KOTH")
    checa(cfg5["games"]["coc"].get("registration_channel_id") is None,
          "canal de registro do Clash não vaza para o KOTH")
    checa(not any("Status do Clã" in f for f in falta5),
          f"Status do Clã não vira pendência no KOTH ({falta5})")
    # o ID de transcrição do .env (777) não pode aparecer em outro servidor
    checa(cfg5["tickets"].get("transcript_channel_id") != 777,
          "canal de transcrições do .env não vaza para o KOTH")
    checa(cfg5["tickets"].get("transcript_channel_id") is None,
          "KOTH fica sem transcrição (ninguém achou pelo nome)")

    # e o dono do .env pode ser global, isso é intencional
    checa(cfg5["owner_ids"] == ["260912891782365196"],
          "dono do .env continua valendo em todos os servidores")

    # ---- só um módulo, se pedir ----
    with mk.patch.dict(os.environ, {**ENV, "TEST_GUILD_ID": GID}, clear=False):
        cfg4, _ = pc.montar(GID, guild.name, None, "coc", guild=guild,
                            modulos=("tickets", "logs"))
    l4 = [k for k, v in cfg4["modules"].items() if v]
    checa(sorted(l4) == ["logs", "tickets"], f"respeita lista de módulos ({l4})")

    # ---- normalização: nada de campo perdido ou string solta ----
    for nome, c in (("coc", cfg), ("generico", cfg2), ("fallback", cfg3),
                    ("parcial", cfg4)):
        checa(isinstance(c.get("tickets", {}).get("max_open_per_user"), int),
              f"{nome}: max_open_per_user continua inteiro")
        checa(isinstance(c.get("modules"), dict) and len(c["modules"]) == 8,
              f"{nome}: os 8 módulos presentes na config")

    # ---- reserva exclusiva: um canal não serve dois papéis ----
    usados = [v for v in detectar.values() if v in (900, 901, 902, 903, 904, 905)]
    checa(len(usados) == len(set(usados)),
          f"nenhum canal detectdo em dois papéis ({usados})")
    checa(detectar.get("games_registro") == 902,
          "registro do Clash ficou com o canal de registro, não com o contador")
    checa(detectar.get("contador") == 905, "contador ficou com o canal certo")

    # ---- perfil escolhido sozinho por servidor ----
    with mk.patch.dict(os.environ, {**ENV, "TEST_GUILD_ID": GID}, clear=False):
        checa(pc.perfil_padrao_para(GID) == "coc",
              "servidor do Clash ganha perfil coc automaticamente")
        checa(pc.perfil_padrao_para("810674050581659668") == "generico",
              "outro servidor ganha perfil generico automaticamente")
    sem_clash = {k: v for k, v in ENV.items() if k != "TEST_GUILD_ID"}
    # Isola tambem as envs reais herdadas do ambiente (ex.: container com
    # secrets.env apontando para o servidor do Clash), senao o "sem env do
    # Clash" passa a depender da maquina que roda o teste.
    for nome in pc.ENV_GUILDS_COC:
        sem_clash[nome] = ""
    with mk.patch.dict(os.environ, sem_clash, clear=False):
        checa(pc.perfil_padrao_para(GID) == "generico",
              "sem o env do Clash, cai no generico em vez de adivinhar")

    print()
    print("pre-configuração: tudo certo" if FALHAS == 0
          else f"pre-configuração: {FALHAS} falha(s)")
    return 1 if FALHAS else 0


if __name__ == "__main__":
    sys.exit(main())