# AURA

Bot de Discord multiserver com painel web de configuração, no estilo
painel-por-servidor: cada servidor tem a sua configuração, salva no MongoDB,
editada pelo navegador.

- **Painel Flask** na porta `2501`, com login por senha.
- **Um banco de perguntas, filtros, tickets e logs por servidor.**
- **Bot e painel no mesmo processo**: o painel fala com o Discord através do
  cliente que já está rodando, então não existe token da API exposto no navegador.
- **Módulos ligáveis por servidor**: Tickets, Moderação, Autorole,
  Boas-vindas, Provas, Logs, Contador e Jogos.

---

## Índice

- [O que precisa](#o-que-precisa)
- [Rodando localmente](#rodando-localmente)
- [Com Docker](#com-docker)
- [No Portainer](#no-portainer)
- [Variáveis de ambiente](#variáveis-de-ambiente)
- [Como o painel funciona](#como-o-painel-funciona)
- [Módulos](#módulos)
- [Banco de dados](#banco-de-dados)
- [Segurança](#segurança)
- [Testes](#testes)
- [Estrutura do projeto](#estrutura-do-projeto)

---

## O que precisa

- Python 3.11 ou mais novo (testado no 3.12).
- Um bot no [Discord Developer Portal](https://discord.com/developers/applications),
  com o token e as permissões de **Administrator** marcadas, e o bot convidado
  para o servidor.
- Um MongoDB acessível. Pode ser local, um VPS ou o serviço do Compose.

Permissões que o AURA usa, para o caso de você preferir uma lista menor em vez
de Administrator: Manage Channels, Manage Threads, Manage Roles, Manage Messages,
Send Messages, Embed Links, Read Message History, Moderate Members e Use
Application Commands.

---

## Rodando localmente

```bash
git clone https://github.com/SEU_USUARIO/AURA.git
cd AURA

python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS

pip install -r requirements.txt

cp .env.example .env            # Windows: copy .env.example .env
```

Abra o `.env` e preencha pelo menos:

```env
DISCORD_TOKEN=seu_token
MONGO_URI=mongodb://localhost:27017
OWNER_ID=seu_id_do_discord
```

Gere a senha do painel:

```bash
python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('SUA_SENHA'))"
```

Cole o resultado em `WEB_PANEL_PASSWORD_HASH`. Se deixar em branco na primeira
subida, o AURA sorteia uma senha, imprime no console **uma única vez** e grava o
hash sozinho.

```bash
python main.py
```

O painel sobe em `http://localhost:2501` assim que o bot conectar no Discord.
No console você deve ver o bot online, os servidores e `MongoDB conectado`.

---

## Com Docker

```bash
cp .env.example .env
# preencha o .env
docker compose up -d --build
docker compose logs -f bot
```

Isso sobe dois containers:

| Container   | Função                                   | Porta        |
|-------------|------------------------------------------|--------------|
| `aura-bot`  | Bot do Discord e painel web              | `127.0.0.1:2501` |
| `aura-mongo`| MongoDB                                  | só rede interna |

O Mongo não é publicado para fora de propósito. Para acessar o painel de
outra máquina, use túnel SSH:

```bash
ssh -L 2501:127.0.0.1:2501 usuario@seu_servidor
```

ou um proxy com HTTPS na frente. Evite expor a porta crua na internet.

Volumes persistidos: `mongo-dados` (banco) e `aura-dados` (bancos de perguntas).

Parar e remover mantendo os dados:

```bash
docker compose down
```

---

## No Portainer

1. **Stacks → Add stack → Repository**, apontando para o repositório, ou
   **Web editor** colando o conteúdo do `docker-compose.yml`.
2. Se usar repositório, copie o `docker-compose.yml` da raiz.
3. Em **Environment variables**, cadastre as variáveis do `.env` do projeto.
   No Portainer não existe `.env`, então cada chave vira uma variável do stack.
4. Clique em **Deploy the stack**.

Para um deploy simples (sem banco gerenciado pelo stack), use **Containers →
Add container** com:

- **Image**: o registry onde você publicou a imagem, ou
  `ghcr.io/SEU_USUARIO/aura:latest`
- **Command**: `python main.py`
- **Port**: `2501`
- **Volumes**: um volume montado em `/app/dados` (bancos de perguntas)
- **Env**: as variáveis do `.env`
- **Restart policy**: `unless-stopped`

Depois, conecte um proxy (Traefik, Caddy ou nginx) com HTTPS para o painel.

---

## Variáveis de ambiente

O `.env` guarda **só credenciais**. A configuração de cada servidor vive no
MongoDB e se edita pelo painel.

| Variável | Obrigatória | Para quê |
|---|---|---|
| `DISCORD_TOKEN` | sim | Login do bot |
| `MONGO_URI` | recomendado | String de conexão do MongoDB |
| `MONGO_DB_NAME` | não | Nome do banco (padrão `aura_bot`) |
| `OWNER_ID` | recomendado | Donos do AURA, separados por vírgula |
| `TEST_GUILD_ID` | não | Sync instantâneo de comandos neste servidor |
| `WEB_PANEL_PASSWORD_HASH` | não | Senha do painel. Gerada no primeiro boot se vazio |
| `WEB_PANEL_SECRET_KEY` | recomendado | Assinatura dos cookies de sessão |
| `WEB_PANEL_HOST` / `WEB_PANEL_PORT` | não | Endereço do painel (padrão `0.0.0.0:2501`) |
| `COC_EMAIL` / `COC_PASSWORD` | não | API do Clash of Clans |
| `AURA_DATA_DIR` | não | Onde ficam os `provas_<id>.json` |
| `TZ` | não | Fuso horário (padrão `America/Sao_Paulo`) |

### Configuração antiga

O AURA de servidor único usava IDs no `.env` (`id_canal_suporte`,
`CANAL_REGISTRO_ID`, `CLAN_TAG`, e afins). Essas variáveis **não são lidas em
tempo de execução**. Elas servem como ponto de partida para a importação única,
feita em **Configurações → Migrar do .env antigo**.

O bot também tenta isso sozinho, uma vez, assim que entra no ar: ele usa
`TEST_GUILD_ID` ou `id_servidor_tribunal` do `.env`; se não houver nenhum dos
dois, importa para o primeiro servidor onde ele está. A importação acontece
**antes** de carregar as configurações dos servidores, senão o cache ficaria com
os valores padrão e o painel não mostraria o que foi importado.

A migração **não sobrescreve** uma configuração que já existe, a não ser que você
marque a caixa, e **não copia senha nem token** para o banco. Depois de migrar,
apague as variáveis antigas do `.env`.

---

## Como o painel funciona

```
navegador ──HTTP──> Flask (web_panel.py) ──runtime.run_coro──> cliente do bot
                              │                                        │
                              └──> MongoDB (mongo_db.py) <────────────┘
```

O Flask roda em uma thread e não conhece o Discord. Quem faz a ponte é
`core/runtime.py`: ele registra o cliente do bot e executa as ações pedidas pelo
painel dentro do loop do asyncio. O painel só recebe dicionários simples.

Fluxo de uma mudança:

1. Você envia o formulário.
2. `_salvar_cfg()` normaliza a config e grava no MongoDB.
3. `runtime.invalidate_config()` derruba o cache.
4. Se o módulo for do tipo bot, `runtime.call_action()` avisa o cog, que recria
   a view persistente do painel de tickets daquele servidor.

---

## Módulos

Cada módulo é ligado e desligado por servidor, em **Configurações → Geral**.

| Módulo | O que faz |
|---|---|
| **Tickets** | Categorias livres, painel com botões, threads privadas, transcrição e avaliação |
| **Moderação** | Anti-link, anti-convite, flood, duplicatas, caixa alta, menções, zerospace, escalada |
| **Autorole** | Cargos por palavra-chave, com negação e log |
| **Boas-vindas** | Mensagem de entrada e saída, com contagem |
| **Provas** | Questionário por DM, com aprovação, tempo por pergunta, nota e cooldown |
| **Logs** | Alterações de configuração e eventos selecionados |
| **Contador** | Contagem de mensagens e comandos |
| **Jogos** | Clash of Clans: cargos por patente e status do clã |

### Tickets

As categorias não são fixas: você cria quantas quiser, com nome, emoji,
descrição, mensagem de abertura e cargo de atendimento próprio. Cada thread
privada carrega o ID do ticket no tópico (`aura-ticket:<id>`), o que faz o
bot reconhecer a própria thread e o painel navegar entre elas.

### Provas

Cada servidor tem seu banco em `provas_<guild_id>.json`. O `provas.json` da
raiz serve apenas de semente de leitura — escrever uma pergunta nova sempre vai
para o arquivo do servidor, para não misturar os questionários.

No Docker, o volume `aura-dados` começa vazio, então esse `provas.json` da
imagem é copiado para lá no primeiro start. Sem essa cópia o bot subiria sem
pergunta nenhuma.

Aprovação pendente sobrevive a reinício: quando o bot volta, ele reenvia o pedido
aos aprovadores. O que já estava com a DM aberta é apagado, porque o botão morreu
com o processo e o membro precisa pedir a prova de novo.

Com `require_approval` ligado, o AURA manda as perguntas selecionadas por DM
para o cargo de aprovador. Aprovado, o membro recebe o botão de começar.

---

## Banco de dados

Uma coleção por servidor lógico, todas com `guild_id`:

| Coleção | Guarda |
|---|---|
| `configs` | Configuração completa de cada servidor |
| `tickets` | Tickets, status, avaliação e transcrição |
| `feedbacks` | Notas de atendimento |
| `provas_resultados` | Tentativas, acertos e cooldown |
| `provas_aprovacoes` | Aprovações pendentes |
| `modlog` | Punições automáticas e manuais |
| `auditoria` | Quem mudou o quê, e quando |
| `migracoes` | Registro das importações do `.env` |

Os índices são criados no boot. Sem MongoDB o bot sobe, mas todo o painel fica
somente leitura e os módulos de dados ficam desligados.

---

## Segurança

- **O `.env` nunca é versionado.** Está no `.gitignore` e no `.dockerignore`.
- **Troque o `DISCORD_TOKEN`**, a senha do MongoDB e a senha do painel se
  eles já ficaram expostos em algum commit, log ou imagem.
- **Use TLS no MongoDB** e nunca deixe um Mongo público sem autenticação.
- **Publique o painel atrás de HTTPS.** Ele autentica com senha e cookie de
  sessão; sem TLS, a senha trafega em claro.
- **`WEB_PANEL_SECRET_KEY` fixa:** sem ele, toda reinicialização invalida as
  sessões abertas.
- O painel **não expõe o token do Discord** nem chama a API do Discord
  diretamente; ele só conversa com o processo do bot.

---

## Testes

Rodam sem Discord e sem MongoDB de verdade, com dublês:

```bash
.venv\Scripts\python.exe -X utf8 tests\test_moderacao.py
.venv\Scripts\python.exe -X utf8 tests\test_painel.py
.venv\Scripts\python.exe -X utf8 tests\test_chamadas_db.py
.venv\Scripts\python.exe -X utf8 tests\test_migracao_env.py
```

O `test_chamadas_db.py` confere por análise estática que todo cog chama
`mongo_db` com os nomes de parâmetro certos, que é a classe de erro que mais
esconde em bot multiserver.

---

## Estrutura do projeto

```
AURA/
├── main.py               Entrada: cogs, runtime, painel
├── web_panel.py          Flask: páginas, formulários e ações
├── mongo_db.py           Persistência, isolada por guild_id
├── core/
│   ├── settings.py       Schema, normalização, presets
│   ├── runtime.py        Ponte Flask <-> Discord
│   └── placeholders.py   Mensagens com variáveis
├── cogs/
│   ├── atendimento.py    Tickets
│   ├── moderacao.py      Filtros e punições
│   ├── sistema_prova.py  Questionário por DM
│   ├── autorole.py       Cargos por palavra-chave
│   ├── clashlog_manager.py  Clash of Clans
│   ├── status_cla.py     Status do clã por voz
│   ├── admin.py          Comandos administrativos
│   ├── misc.py           Utilidades
│   └── owner.py          Comandos do dono
├── templates/            HTML do painel (Jinja2)
├── tests/                Testes offline
├── Dockerfile
├── docker-compose.yml
└── .env.example
```