"""
Testa o fluxo de tickets: dropdown no painel, orientação antes de criar,
botão de atender persistente e avaliação na hora de fechar.

O ponto mais importante é o `delete_after`: o botão de atender sumia em 15
segundos e o admin não conseguia assumir o ticket. Aqui isso não pode voltar.
"""
import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FALHAS = 0


def checa(condicao, msg):
    global FALHAS
    if condicao:
        print("ok  ", msg)
    else:
        FALHAS += 1
        print("FALHA", msg)


def main() -> int:
    import cogs.atendimento as at

    src_abrir = inspect.getsource(at.abrir_ticket)

    # ---- painel: um dropdown, não botões ----
    view = at.TicketPanelView(1, [{"key": "a", "label": "A", "emoji": "1"},
                                  {"key": "b", "label": "B", "emoji": "2"}])
    selects = [c for c in view.children if isinstance(c, at.discord.ui.Select)]
    buttons = [c for c in view.children if isinstance(c, at.discord.ui.Button)]
    checa(len(selects) == 1, f"painel tem 1 dropdown (veio {len(selects)})")
    checa(not buttons, f"painel não usa botões por categoria (veio {len(buttons)})")
    checa(len(selects[0].options) == 2, "dropdown lista as categorias")

    # o placeholder antigo é parte do que o usuario pediu de volta
    checa("tópico" in (selects[0].placeholder or ""),
          f"placeholder antigo preservado ({selects[0].placeholder!r})")

    # limite do discord: no maximo 25 opcoes
    cheio = at.TicketPanelView(1, [{"key": f"k{i}", "label": f"L{i}"}
                                    for i in range(40)])
    s2 = [c for c in cheio.children if isinstance(c, at.discord.ui.Select)]
    checa(len(s2) == 1 and len(s2[0].options) <= 25,
          f"respeita o limite de 25 opcoes (veio {len(s2[0].options)})")

    # ---- orientacao antes de criar ----
    checa(hasattr(at, "CreateTicketView"), "existe a view do botao Abrir Ticket")
    checa(hasattr(at, "mostrar_orientacao"), "existe a etapa de orientacao")
    checa("CreateTicketView" in inspect.getsource(at.mostrar_orientacao),
          "a orientacao oferece o botao de abrir")

    # ---- a view do ticket e persistente e SEM delete_after ----
    checa(hasattr(at, "TicketAdminView"), "existe a view do ticket")
    checa(not hasattr(at, "StaffTicketView"),
          "a view duplicada do staff foi removida")

    # os botoes reais da view: instancia e le os filhos
    inst = at.TicketAdminView(1)
    labels = [c.label for c in inst.children]
    checa("Atender" in labels, f"botao Atender existe (veio {labels})")
    checa("Fechar" in labels, "botao Fechar existe")
    checa("Salvar transcrição" in labels, "botao de transcricao continua")
    checa(all(not c.disabled for c in inst.children),
          "os botoes comecam habilitados")

    # o bug principal: nada de delete_after na criacao do ticket
    checa("delete_after=15" not in src_abrir,
          "a view do ticket NAO e enviada com delete_after=15")
    checa("view_ticket" in src_abrir, "a view persistente e enviada")
    checa("StaffTicketView" not in src_abrir, "nao manda mais a view que sumia")

    # ---- saudacao antiga de volta ----
    checa("tudo bem" in src_abrir, "volta a saudacao 'tudo bem'")
    checa("bem-vindo" in src_abrir, "volta a saudacao de bem-vindo")
    checa("máximo de detalhes" in src_abrir, "pede detalhe do caso")

    # ---- embed do ticket com os campos antigos ----
    checa("Atendido por" in inspect.getsource(at.TicketAdminView.assumir),
          "o embed ganha 'Atendido por' quando alguem assume")
    checa("Em Atendimento" in inspect.getsource(at.TicketAdminView.assumir),
          "o botao vira 'Em Atendimento'")

    # ---- avaliacao preservada ----
    checa(hasattr(at, "RatingView"), "a avaliacao continua existindo")
    check = inspect.getsource(at._fechar_ticket)
    checa("RatingView" in check, "a avaliacao e enviada ao fechar")
    checa("rating_enabled" in check, "a avaliacao respeita a config do painel")

    # ---- o bug que matava todas as mensagens do ticket ----
    # `Thread.edit()` nao aceita topic e estourava TypeError DEPOIS de criar a
    # thread: embed, botao de atender e saudacao nunca eram enviados.
    src_tid = inspect.getsource(at._canal_do_ticket)
    checa("ticket_por_thread" in src_tid,
          "o _id do ticket e buscado pela thread (topico nao funciona)")
    checa("aura-ticket:" in src_tid, "ainda da para ler o topico dos tickets antigos")

    # a chamada do topico tem que estar dentro de um try que nao engula o resto
    linha_topic = [l for l in src_abrir.split("\n") if "thread.edit(" in l]
    checa(bool(linha_topic), "a chamada de topico existe")
    bloco = src_abrir[src_abrir.find("thread.edit(") - 400:src_abrir.find("thread.edit(")]
    checa("try:" in bloco, "gravar o topico esta protegido por try")
    checa("TypeError" in src_abrir,
          "TypeError do discord.py e tratado explicitamente")

    # e o _id precisa chegar a ser resolvido por banco
    checa(hasattr(at.mongo_db, "ticket_por_thread"),
          "existe a busca de ticket por thread no mongo")

    # a busca tem que respeitar o servidor, senao o botao de atender pode
    # abrir o ticket do clã errado
    src_busca = inspect.getsource(at.mongo_db.ticket_por_thread)
    checa("guild_id" in src_busca, "a busca por thread filtra por servidor")
    checa("ts" in src_busca, "a busca devolve o ticket mais recente")
    checa("_id" in src_busca, "a busca devolve o _id do mongo")

    # ---- painel do web: mesmo embed limpo ----
    from core import runtime as rt
    src_rt = inspect.getsource(rt._deploy_ticket_panel)
    checa('add_field(name="Categorias"' not in src_rt
          and "cobj.add_field" not in src_rt,
          "o painel publicado pelo painel web nao lista as categorias")
    checa("Central de Atendimento" in src_rt, "usa o titulo do modelo antigo")
    checa("set_image" in src_rt, "usa o icone do servidor como imagem")
    checa("_remover_paineis_antigos" in src_rt,
          "apaga o painel antigo antes de publicar o novo")

    print()
    print("tickets: tudo certo" if FALHAS == 0 else f"tickets: {FALHAS} falha(s)")
    return 1 if FALHAS else 0


if __name__ == "__main__":
    sys.exit(main())