# Aura

![bot image](img/AURA.png)

Bot de interação, atendimento e administração do **B.A.D**. Desenvolvido em Python com discord.py, painel web Flask e MongoDB.

---

### Funcionalidades

- Sistema de **provas** para Co-Líder com aprovação do dono via DM
- **Painel web** de administração (Dashboard, Provas, Tickets, Status do Clã)
- **MongoDB** para persistência de dados (provas, tickets)
- Dropdowns persistentes (painéis de atendimento)
- Transcrição e salvamento de histórico de tickets em `.md`
- Context menus (clique direito) para usuários
- Sistema de Autorole com exceção para banidos
- Sincronização com Clash of Clans API (cargos, verificação de membros)
- Status de clã em canais de voz (atualização automática)

---

### Comandos

**Context Menu (Clique Direito)**
- Usuario Avatar
- Usuario Info
- Usuario Banner
- Usuario Abraço

**Comandos de Barra (`/`)**

| Grupo | Comandos |
|-------|----------|
| **Owner** | `/owner say`, `/owner listar`, `/owner sair`, `/owner bot-name`, `/owner bot-avatar` |
| **Bot** | `/bot ping`, `/bot info`, `/bot help` |
| **Usuário** | `/usuario avatar`, `/usuario info`, `/usuario abraçar`, `/usuario banner`, `/usuario atacar`, `/usuario carinho`, `/usuario cafuné`, `/usuario afk` |
| **Servidor** | `/servidor icone`, `/servidor banner`, `/servidor splash`, `/servidor info` |
| **Admin** | `/admin banir`, `/admin desbanir`, `/admin kick` |
| **Chat** | `/chat deletar`, `/chat limpar`, `/chat criar`, `/chat info` |
| **Canal** | `/canal deletar`, `/canal criar`, `/canal info` |
| **Cargo** | `/cargo adicionar`, `/cargo remover`, `/cargo trocar`, `/cargo info` |
| **Painel** | `/painel suporte` |
| **Atendimento** | `/atendimento encerrar`, `/atendimento adicionar`, `/atendimento remover`, `/atendimento importar-transcricoes` |
| **Prova** | `/iniciar-prova` |
| **Clã** | `/clash setup`, `/clash registrar`, `/clash aprovar`, `/clash negar` |
| **Status** | `/setup-status`, `/force-update` |

---

### Painel Web

O bot sobe um painel administrativo em `http://ip:2501`.

| Rota | Descrição |
|------|-----------|
| `/` | Dashboard com stats e gráfico de aprovação |
| `/provas` | Histórico completo de provas |
| `/tickets` | Tickets de atendimento |
| `/clan` | Status do clã no Clash of Clans |

---

### Instalação (Render.com)

1. Faça fork do repositório para o GitHub
2. Crie um **Web Service** no Render conectado ao repositório
3. **Start Command:** `python main.py`
4. Adicione as variáveis de ambiente no painel do Render
5. Faça deploy

---

### Variáveis de Ambiente (.env)

| Variável | Descrição |
|----------|-----------|
| `DISCORD_TOKEN` | Token do bot Discord |
| `DONO_ID` / `OWNER_ID` | ID do dono do bot |
| `COC_EMAIL` / `COC_PASSWORD` | Credenciais da API Clash of Clans |
| `CLAN_TAG` | Tag do clã (ex: #ABC123) |
| `CANAL_REGISTRO_ID` | Canal de registro do autorole |
| `CARGO_MEMBRO_ID` | Cargo de membro (autorole) |
| `CARGO_BANIDO_ID` | Cargo de banido (exceção autorole) |
| `id_cargo_atendente` | Cargo de atendente de tickets |
| `id_canal_suporte` | Canal onde os tickets são criados |
| `id_categoria_staff` | Categoria para tickets |
| `id_servidor_bh` / `id_servidor_tribunal` | IDs dos servidores |
| `id_canal_logs_bh` / `id_canal_logs_tri` | Canais de log dos tickets |
| `id_canal_avaliacao` | Canal de avaliações |
| `REGISTRATION_CHANNEL_ID` | Canal de registro do Clash |
| `LOG_CHANNEL_ID` | Canal de logs do Clash |
| `APPROVAL_LOG_CHANNEL_ID` | Canal de aprovações do Clash |
| `COC_MEMBER_ROLE_ID` / `COC_ELDER_ROLE_ID` / `COC_COLEADER_ROLE_ID` | Cargos sincronizados CoC |
| `KICK_MESSAGE` | Mensagem enviada ao expulsar |
| `WEB_PANEL_PASSWORD` | Senha do painel web |
| `MONGO_URI` | URI de conexão MongoDB |
