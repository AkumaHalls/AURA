# Changelog

Todas as mudanças relevantes deste projeto.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/), e o
projeto usa [SemVer](https://semver.org/lang/pt-BR/).

## [Não publicado]

### Corrigido

- Tickets: restaurado registro de views persistentes no on_ready (TicketAdminView/RatingView) com dd_view, evitando "bot não responde" após reinício.
- Tickets: defer() movido para o início de ssumir e _fechar_ticket, com respostas via ollowup (evita timeout de 3s).
- Tickets: travamento do botão "Atender" por custom_id (removido uso de iew.get_item).
- Tickets: callbacks derivam guild_id da interação (_gid_do_interaction) para suportar views compartilhadas multi-servidor.
- Avaliação: RatingButton com custom_id global e resolução correta de ticket/servidor.
- Correções menores de encoding e ajustes no embed do painel (thumbnail/footer).
- Adicionado teste 	ests/test_ticket_persistencia.py cobrindo persistência e comportamento pós-restart.


## [1.0.0] — 2026-10-05

### Adicionado

**Multiserver**

- Configuração por servidor no MongoDB, com cache e invalidação a partir do
  painel (`core/settings.py`, `core/runtime.py`).
- Seletor de servidor no painel, e todas as consultas filtradas por `guild_id`.
- Perfis de configuração (`generico`, `coc`, `arma3`) e importação única do
  `.env` legado, que não sobrescreve config existente nem copia segredos.

**Painel web**

- Flask na porta `2501`, servido pelo mesmo processo do bot.
- Login por senha com hash Werkzeug, sessão assinada e proteção contra open
  redirect.
- Dashboard com métricas por servidor, configuração geral, interruptores de
  módulo e páginas de dados (tickets, modlog, infrações, auditoria, provas).
- Formulário de tickets com categorias livres: nome, emoji, descrição, mensagem
  de abertura e cargo de atendimento por categoria.
- Formulários de todos os oito módulos, com validação de canal, cargo e ação.

**Módulos**

- Tickets com painel persistente por servidor, threads privadas, transcrição,
  avaliação e gestão de status.
- Moderação automática com anti-link, anti-convite, flood, duplicatas, caixa
  alta, menções, zerospace e escalada configurável.
- Provas por DM, com banco de perguntas por servidor, aprovação por cargo,
  tempo por pergunta, nota e cooldown.
- Autorole, boas-vindas, logs, contador de mensagens e integração com Clash of
  Clans (cargos por patente e status do clã).

**Operação**

- `Dockerfile` enxuto em etapa única, executando como usuário sem privilégio, com
  healthcheck em `/health`.
- `docker-compose.yml` com bot, MongoDB autenticado sem porta publicada e
  volumes para banco e bancos de perguntas.
- `README.md` com instalação local, Docker, Portainer e variáveis de ambiente.
- Suíte de testes offline (`tests/run_all.py`): config, templates, runtime,
  retomada de provas, moderação, painel, assinaturas do MongoDB e migração.
- Aprovação de prova pendente é reenviada aos aprovadores quando o bot volta,
  em vez de ficar travada no banco até o membro desistir.

### Corrigido

- Chaves de retorno do runtime padronizadas em `erro` e `detalhe`.
- `run_coro` passou a funcionar quando o painel grava antes do loop do bot
  existir, com `asyncio.run` como alternativa.
- Threads abertas pelo painel agora adicionam o solicitante à thread privada.
- Detecção do dono do ticket deixou de iterar `Thread.history` de forma
  inválida, e passou a olhar todos os embeds da mensagem.
- Aprovação de prova deixou de depender de `interaction.guild`, que é `None`
  quando o botão é clicado por DM.
- Criação de pergunta passou a gravar sempre no arquivo do servidor, e não no
  `provas.json` compartilhado.
- `cooldown_days` e `pass_score` zero voltaram a significar "zero", em vez de
  caírem no padrão por causa de um `or`.
- `get_clan_members` deixou de assumir uma lista: o formato do coc.py muda
  entre versões.
- Respostas de painel que passavam `Embed` como texto.
- A migração do `.env` passou a rodar antes de carregar as configs dos servidores,
  para o cache não ficar com o padrão e esconder o que foi importado.
- O banco de perguntas inicial (`provas.json`) é copiado da imagem para o volume
  no primeiro start, que antes ficava vazio e saía sem perguntas.

### Segurança

- `.env` removido do tracking e ignorado pelo Git e pelo Docker.
- `.env.example` sem nenhum segredo real.
- `MONGO_URI`, `WEB_PANEL_SECRET_KEY` e hashes de senha documentados como
  obrigatórios no Compose e no README.
- Token do Discord nunca sai do processo do bot para o navegador.

### Migração

- O `.env` legado deixou de ser lido em tempo de execução. As variáveis antigas
  servem só como origem para a importação em **Migrar do .env antigo**.
- **Pendências antes de ir para produção:** rotacionar `DISCORD_TOKEN`, senha do
  MongoDB e senha do painel, caso tenham ficado expostas; reescrever o histórico
  Git para remover segredos; publicar o painel atrás de HTTPS.

[Não publicado]: https://github.com/AkumaHalls/AURA/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/AkumaHalls/AURA/releases/tag/v1.0.0
