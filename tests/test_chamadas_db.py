"""
Confere, por assinatura, se as chamadas de mongo_db feitas pelos cogs batem com
as funcoes reais do modulo. Erro de argumento aqui vira erro em producao.
"""
import ast
import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mongo_db  # noqa: E402

PASTA_COGS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cogs")


def collectar_chamadas(tree):
    """Dicionário nome_da_funcao -> lista de nós Call."""
    achados = {}

    def chave_de(arg):
        try:
            return ast.unparse(arg)
        except Exception:  # noqa: BLE001
            return "?"

    def visitar(node):
        for filho in ast.iter_child_nodes(node):
            if isinstance(filho, ast.Call):
                func = filho.func
                nome = None
                if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) \
                        and func.value.id == "mongo_db":
                    nome = func.attr
                elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Attribute) \
                        and isinstance(func.value.value, ast.Name) \
                        and func.value.value.id == "mongo_db" \
                        and hasattr(mongo_db, func.value.attr):
                    nome = f"{func.value.attr}.{func.attr}"
                if nome and hasattr(mongo_db, nome.split(".")[0]):
                    achados.setdefault(nome, []).append((chave_de, filho))
            visitar(filho)

    visitar(tree)
    return achados


def resolver(nome):
    """Segue `modulo.funcao` até achar a função real."""
    partes = nome.split(".")
    obj = mongo_db
    for p in partes:
        obj = getattr(obj, p, None)
        if obj is None:
            return None
    return obj


def checar_no_arquivo(caminho):
    with open(caminho, encoding="utf-8") as fh:
        fonte = fh.read()
    try:
        tree = ast.parse(fonte, filename=caminho)
    except SyntaxError as exc:
        return [f"{os.path.basename(caminho)}: erro de sintaxe na linha {exc.lineno}: {exc.msg}"]

    problemas = []
    for nome, chamadas in collectar_chamadas(tree).items():
        func = resolver(nome)
        if func is None or not callable(func):
            problemas.append(f"{os.path.basename(caminho)}: mongo_db.{nome} não existe")
            continue
        try:
            assinatura = inspect.signature(func)
        except (TypeError, ValueError):
            continue
        permite_extra = any(p.kind == inspect.Parameter.VAR_KEYWORD
                            for p in assinatura.parameters.values())

        for chave_de, call in chamadas:
            args = call.args
            kwargs = {k.arg: k.value for k in call.keywords if k.arg}
            nomes = set(kwargs)
            nome_curto = nome.split(".")[-1]
            try:
                assinatura.bind(*args, **kwargs)
            except TypeError as exc:
                if not permite_extra:
                    problemas.append(
                        f"{os.path.basename(caminho)}:{call.lineno}: "
                        f"mongo_db.{nome_curto}("
                        f"{', '.join(chave_de(a) for a in args)}"
                        f"{', ' if args and nomes else ''}"
                        f"{', '.join(sorted(nomes))}) -> {exc}"
                    )
                elif "unexpected keyword argument" in str(exc):
                    problemas.append(
                        f"{os.path.basename(caminho)}:{call.lineno}: "
                        f"mongo_db.{nome_curto} não aceita "
                        f"{', '.join(sorted(nomes - set(assinatura.parameters)))}"
                    )
    return problemas


def main() -> int:
    problemas = []
    arquivos = sorted(f for f in os.listdir(PASTA_COGS) if f.endswith(".py"))
    for nome in arquivos:
        problemas.extend(checar_no_arquivo(os.path.join(PASTA_COGS, nome)))

    if problemas:
        print(f"{len(problemas)} problema(s) de assinatura:\n")
        for p in problemas:
            print(" -", p)
        return 1

    print(f"assinaturas de mongo_db conferidas em {len(arquivos)} cog(s): tudo certo")
    return 0


if __name__ == "__main__":
    sys.exit(main())