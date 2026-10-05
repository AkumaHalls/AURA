"""
Procura nomes de variável que não existem no módulo.

O bug real: `COOC_PASSWORD` em vez de `COC_PASSWORD`. Como o comentário do
arquivo citava "COC_EMAIL / COOC_PASSWORD", o nome errado aparecia como
substring de um trecho correto e passava despercebido numa leitura apressada.
Aqui a checagem é mecânica: compila o arquivo e passa o namespace para o
`NameError` de quem lê.
"""
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
    import cogs.clashlog_manager as cm
    import cogs.status_cla as sc

    # As duas cogs leem as mesmas duas variaveis do ambiente.
    for modulo, nome in ((cm, "clashlog_manager"), (sc, "status_cla")):
        tem_email = hasattr(modulo, "COC_EMAIL")
        tem_senha = hasattr(modulo, "COC_PASSWORD")
        checa(tem_email, f"{nome}: define COC_EMAIL")
        checa(tem_senha, f"{nome}: define COC_PASSWORD")

        # Todo uso de nome COOC_* e um erro: a variavel nao existe.
        with open(modulo.__file__, encoding="utf-8") as fh:
            fonte = fh.read()
        import re
        errados = sorted(set(re.findall(r"\bCOOC_[A-Z_]+", fonte)))
        checa(not errados,
              f"{nome}: sem variavel COOC_* (encontradas: {errados or 'nenhuma'})")

    # As duas passam a usar a mesma variavel do ambiente, sem divergir.
    checa(cm.COC_PASSWORD == sc.COC_PASSWORD,
          "as duas cogs leem a mesma senha")

    print()
    print("variaveis de ambiente: tudo certo" if FALHAS == 0
          else f"variaveis de ambiente: {FALHAS} falha(s)")
    return 1 if FALHAS else 0


if __name__ == "__main__":
    sys.exit(main())