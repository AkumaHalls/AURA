"""
Verifica que todo View registrado com `add_view` é persistente.

O Discord exige `custom_id` em cada item e `timeout=None` na view. Se não for
assim, `add_view` levanta ValueError na hora do load e o cog inteiro não sobe —
e o erro só aparece no log do container, muito depois do deploy. Estes testes
rodam sem Discord: só instanciam as views e passam pelas mesmas regras.
"""
import asyncio
import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import discord  # noqa: E402

FALHAS = 0


def checa(condicao, msg):
    global FALHAS
    if condicao:
        print("ok  ", msg)
    else:
        FALHAS += 1
        print("FALHA", msg)


def checa_view(view, nome):
    """Repete o que a lib faz ao registrar uma view, sem precisar do bot."""
    checa(view.timeout is None, f"{nome}: timeout é None")
    for item in view.children:
        checa(bool(item.custom_id) is True,
              f"{nome}: item {item.label!r} tem custom_id")
        checa(item.style is not None, f"{nome}: item {item.label!r} tem style")


def main() -> int:
    from cogs import atendimento, moderacao

    # ---- moderação: a view que quebrou o cog no deploy ----
    checa_view(moderacao.ConfigModView(), "ConfigModView")

    # ---- atendimento: views de ticket ----
    for nome, obj in vars(atendimento).items():
        if not inspect.isclass(obj) or not issubclass(obj, discord.ui.View):
            continue
        if obj.__module__ != atendimento.__name__:
            continue
        if obj is discord.ui.View:
            continue
        # Views internas de botão não são registradas com add_view.
        if getattr(obj, "__aura_persistente__", False):
            checa_view(obj(), nome)

    # ---- varredura: nenhuma view persistente sem custom_id ----
    for modulo in (atendimento, moderacao):
        for nome, obj in vars(modulo).items():
            if not inspect.isclass(obj) or not issubclass(obj, discord.ui.View):
                continue
            if obj.__module__ != modulo.__name__:
                continue
            try:
                inst = obj()
            except TypeError:
                continue  # exige argumentos; coberto por outro teste
            persistente = inst.timeout is None
            tem_custom = all(bool(i.custom_id) for i in inst.children)
            if persistente and inst.children:
                checa(tem_custom,
                      f"{modulo.__name__}.{nome}: view persistente sem custom_id nos itens")

    # ---- toda cog_listeners que chama registrar_views precisa de await ----
    source = inspect.getsource(atendimento)
    checa("await self.registrar_views_iniciais()" in source,
          "atendimento: on_ready espera a corrotina das views")
    checa("self.registrar_views_iniciais()" not in source.split("cog_load")[1].split("@commands.Cog.listener")[0],
          "atendimento: cog_load nao chama a corrotina sem await")

    # ---- funcoes de listener declaradas como async ----
    for modulo in (atendimento, moderacao):
        for nome, obj in vars(modulo).items():
            if nome.startswith("on_") and inspect.isfunction(obj):
                checa(inspect.iscoroutinefunction(obj),
                      f"{modulo.__name__}.{nome} e async")

    print()
    print("views persistentes: tudo certo" if FALHAS == 0
          else f"views persistentes: {FALHAS} falha(s)")
    return 1 if FALHAS else 0


if __name__ == "__main__":
    sys.exit(main())