"""
AURA · núcleo compartilhado
--------------------------
Ponto único de onde o resto do projeto importa as peças novas:

    core.settings       schema + cache da configuração por servidor
    core.placeholders   {user}, {guild}... em mensagens configuráveis
    core.runtime        ponte entre o bot e o painel web
"""

__all__ = ["settings", "placeholders", "runtime"]
