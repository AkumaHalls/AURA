"""
Confere que a página geral realmente manda os interruptores de módulo com o
nome que o handler procura. É o tipo de bug que só aparece no navegador: o
formulário renderiza, o POST responde 302, e nada muda no banco.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from web_panel import MODULOS_PAINEL  # noqa: E402

FALHAS = 0


def checa(condicao, msg):
    global FALHAS
    if condicao:
        print("ok  ", msg)
    else:
        FALHAS += 1
        print("FALHA", msg)


def main() -> int:
    with open(os.path.join(RAIZ, "templates", "geral.html"), encoding="utf-8") as fh:
        html = fh.read()

    action = re.search(r'action="\{\{ url_for\(\'salvar_basico\', chave=\'(\w+)\'', html)
    checa(action is not None, "formulário geral aponta para salvar_basico")
    if action:
        checa(action.group(1) == "geral", "geral posta em chave='geral'")

    # O nome do campo é montado no loop, então conferimos o template do nome
    # e não 8 literais.
    checa('name="mod_{{ s.key }}"' in html,
          "geral monta o campo mod_<chave> dentro do loop")
    checa("{% for s in modulos %}" in html or "{% for s in" in html,
          "geral itera a lista de módulos do painel")
    for mod in MODULOS_PAINEL:
        chave = mod["key"]
        achou = re.search(rf'id="mod_\{{\{{ s\.key \}}\}}[^>]*', html)
        if achou:
            break
    checa(bool(achou), "geral liga o interruptor ao id do checkbox")

    # As forms de módulo precisam apontar para um módulo que existe.
    for destino in set(re.findall(r"url_for\('modulo/(\w+)'", html)):
        checa(destino in {m["key"] for m in MODULOS_PAINEL},
              f"geral nao aponta para modulo inexistente ({destino})")

    # Todo módulo do painel tem parcial.
    for mod in MODULOS_PAINEL:
        chave = mod["key"]
        parcial = os.path.join(RAIZ, "templates", "modulos", f"{chave}.html")
        checa(os.path.exists(parcial), f"parcial {chave}.html existe")

    # Os parciales não usam `extends`: são include, não página.
    for mod in MODULOS_PAINEL:
        caminho = os.path.join(RAIZ, "templates", "modulos", f"{mod['key']}.html")
        with open(caminho, encoding="utf-8") as fh:
            corpo = fh.read()
        checa("{% extends" not in corpo,
              f"{mod['key']}.html nao usa extends (e include, nao pagina)")

    print()
    print("templates: tudo certo" if FALHAS == 0 else f"templates: {FALHAS} falha(s)")
    return 1 if FALHAS else 0


if __name__ == "__main__":
    sys.exit(main())