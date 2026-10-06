"""
Reproduz o bug "Atender mostra 'bot não responde'" (botão tk:assumir).

Causa raiz: a view de dentro do ticket (TicketAdminView) NUNCA era registrada
com `client.add_view`. O painel de categorias era registrado, mas os botões de
dentro do ticket não. Depois de qualquer restart do bot (todo deploy em Docker),
os botões de tickets antigos não têm handler registrado: a Discord manda o
INTERACTION_CREATE, o discord.py não acha view nenhuma e devolve silenciosamente
— sem `interaction.response`, o cliente mostra "o bot não responde".

Além disso:
- o callback fazia leitura de histórico e escrita no Mongo ANTES do
  `interaction.response.defer()`, estourando a janela de 3s de ack mesmo com o
  bot online;
- a desativação do botão usava `view.get_item(...)`, que não existe no
  discord.py — o botão nunca travava, e o "Em Atendimento" nunca aparecia;
- os callbacks dependiam de `self.guild_id`, impossibilitando uma única view
  persistente compartilhada atender vários servidores sem vazar config
  (multi-server).
"""
import asyncio
import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import discord  # noqa: E402
import cogs.atendimento as at  # noqa: E402

FALHAS = 0


def checa(condicao, msg):
    global FALHAS
    if condicao:
        print("ok  ", msg)
    else:
        FALHAS += 1
        print("FALHA", msg)


def main() -> int:
    src_assumir = inspect.getsource(at.TicketAdminView.assumir)

    # ---- 1. views de dentro do ticket registradas de forma persistente ----
    src_init = inspect.getsource(at.Atendimento.registrar_view_admin_persistente)
    checa("add_view(TicketAdminView" in src_init,
          "on_ready registra a view 'Atender/Fechar' com add_view")
    checa("add_view(RatingView" in src_init,
          "on_ready registra a view de avaliação com add_view")

    # reprodução comportamental: no 'restart', o store de views volta vazio e o
    # clique em tk:assumir não tinha nada registrado (a resposta nunca vinha)
    bot = discord.Client(intents=discord.Intents.default())
    cog = at.Atendimento(bot)
    asyncio.run(cog.registrar_views_iniciais())
    store = bot._connection._view_store
    key_assumir = (2, "tk:assumir")  # 2 = botão (component_type da API)
    key_rate = (2, "tk:rate:1")
    checa(key_assumir in (store._views.get(None) or {}),
          "depois do on_ready, tk:assumir volta a ter handler persistente")
    checa(key_rate in (store._views.get(None) or {}),
          "depois do on_ready, a avaliação volta a ter handler persistente")

    # ---- 2. defer antes de trabalho pesado (histórico + banco) ----
    pos_defer = src_assumir.find("response.defer()")
    pos_dono = src_assumir.find("_dono_do_ticket")
    pos_mongo = src_assumir.find("mongo_db.")
    pos_cfg = src_assumir.find("get_config_cached(")
    checa(pos_defer != -1 and pos_dono != -1 and pos_defer < pos_dono,
          "defer vem antes de ler o histórico do ticket (janela de 3s)")
    checa(pos_defer != -1 and pos_mongo != -1 and pos_defer < pos_mongo,
          "defer vem antes de tocar no MongoDB (janela de 3s)")
    checa(pos_defer != -1 and pos_cfg != -1 and pos_defer < pos_cfg,
          "defer vem antes de carregar a config")

    # ---- 3. sem get_item; desabilita o botão pelo custom_id ----
    checa("get_item" not in src_assumir,
          "não usa view.get_item (método inexistente no discord.py)")
    checa('item.custom_id == "tk:assumir"' in src_assumir
          and "item.disabled = True" in src_assumir,
          "o botão Atender é travado procurando pelo custom_id")

    # ---- 4. multi-server: callbacks usam o servidor da interação ----
    checa("_gid_do_interaction(interaction, self.guild_id)" in src_assumir,
          "assumir deriva o servidor da interação, não do self.guild_id")
    checa("gid, interaction.guild.name" in src_assumir,
          "a auditoria usa o servidor da interação")
    checa("_gid_do_interaction(interaction, self.guild_id)"
          in inspect.getsource(at.TicketAdminView.fechar),
          "o botão Fechar também deriva o servidor da interação")

    # ---- 5. avaliação: ticket e servidor vêm da thread/interação ----
    src_rating = inspect.getsource(at.RatingButton.callback)
    checa("_canal_do_ticket" in src_rating,
          "a avaliação acha o ticket pela thread (funciona pós-restart)")
    checa("_gid_do_interaction(interaction, self.guild_id)" in src_rating,
          "a avaliação usa o servidor da interação")
    checa("tk:rate:" in inspect.getsource(at.RatingButton.__init__)
          and "tk:{guild_id}:rate" not in inspect.getsource(at.RatingButton.__init__),
          "o custom_id da avaliação é global (serve todos os servidores)")

    # ---- 6. as views são persistentes e constroem sem argumentos ----
    checa(at.TicketAdminView().timeout is None,
          "TicketAdminView é persistente e constrói para o add_view compartilhado")
    checa(at.RatingView().timeout is None,
          "RatingView é persistente e constrói para o add_view compartilhado")

    print()
    print("ticket persistente: tudo certo" if FALHAS == 0
          else f"ticket persistente: {FALHAS} falha(s)")
    return 1 if FALHAS else 0


if __name__ == "__main__":
    sys.exit(main())