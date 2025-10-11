# 🤖 Brix

![bot image](img/AURA.png)

Código em Python do Bot de interação e atendimento do **B.A.D** com suporte a Cogs.

Todos os comandos estão com comentários e explicados para fácil modificação. Os arquivos de dependências e de configuração para a Render estão adicionados ao repositório. Divirta-se! ✨

---

### **🚀 Especificações do Código**

* Dropdowns (Paineis);
* Suporte para paineis persistentes (não somem se o bot reiniciar);
* Salva o histórico do chat ao fechar um ticket;
* Suporte a **context\_menu** (comandos de clique direito) para algumas funções;
* Suporte a `.env` para gerenciar as variáveis de ambiente;
* **Código em cogs**, facilitando a adição de novas funções e updates;
* Vários comandos de interação para os usuários;
* Comando de avaliação de atendimento;
* Sistema de Autorole com exceção para cargos específicos.

---

### **📋 Lista dos Comandos**

<details>
<summary><strong>Clique para expandir a lista de comandos</strong></summary>

**Context Menu (Clique Direito)**
* 👤 Usuario Avatar
* ℹ️ Usuario Info
* 🖼️ Usuario Banner
* 🫂 Usuario Abraço

**Comandos de Barra (`/`)**

* `/owner say`
* `/owner listar`
* `/owner sair`
* `/owner bot-name`
* `/owner bot-avatar`
    ***
* `/bot ping`
* `/bot info`
* `/bot help`
    ***
* `/usuario avatar`
* `/usuario info`
* `/usuario abraçar`
* `/usuario banner`
* `/usuario atacar`
* `/usuario carinho`
* `/usuario cafuné`
* `/usuario afk`
    ***
* `/servidor icone`
* `/servidor banner`
* `/servidor splash`
* `/servidor info`
    ***
* `/admin banir`
* `/admin desbanir`
* `/admin kick`
    ***
* `/chat deletar`
* `/chat limpar`
* `/chat criar`
* `/chat info`
    ***
* `/canal deletar`
* `/canal limpar`
* `/canal criar`
* `/canal info`
    ***
* `/cargo adicionar`
* `/cargo remover`
* `/cargo trocar`
* `/cargo info`
    ***
* `/painel suporte-bh`
* `/painel servicos-bh`
* `/painel tribunal`
    ***
* `/atendimento fechar`
* `/atendimento encerrar`
* `/atendimento adicionar`
* `/atendimento remover`
* `/atendimento avaliar`
* `/atendimento entrevista`

</details>

---

### **🛠️ Instruções de Instalação**

#### **Hospedagem na Render (Recomendado)**

1.  Faça um "Fork" deste repositório para a sua conta do GitHub.
2.  Crie uma nova aplicação "Web Service" na [Render](https://render.com/).
3.  Conecte o repositório que você acabou de criar.
4.  Nas configurações, defina o **Start Command** como: `python main.py`
5.  Vá para a aba "Environment" e adicione todas as **Variáveis Exigidas** listadas abaixo.
6.  Clique em "Create Web Service" e aguarde o deploy.

#### **Rodando Localmente (Para testes)**

1.  Clone o repositório para a sua máquina.
2.  Renomeie o arquivo `exemplo.env` para `.env` e preencha as variáveis.
3.  Recomendo o uso do VSCode. Abra um terminal e instale as dependências com o comando:
    ```
    pip install -r requirements.txt
    ```
4.  Inicie o bot com:
    ```
    python main.py
    ```

---

### **🔑 Variáveis Exigidas (Environment Variables)**

Estas são as variáveis que você **precisa** configurar no painel da Render para que o bot funcione corretamente.

* `DISCORD_TOKEN` - O token de autenticação do seu bot.
* `DONO_ID` ou `OWNER_ID` - A sua ID de usuário do Discord.
* `CANAL_REGISTRO_ID` - ID do canal onde os membros se registram com a palavra "Liberar".
* `CARGO_MEMBRO_ID` - ID do cargo que será dado aos novos membros.
* `CARGO_BANIDO_ID` - ID do cargo de banido, que servirá como exceção para o autorole.
* `id_cargo_atendente` - ID do cargo que pode atender aos tickets de suporte.
* `id_canal_suporte` - ID do canal onde os tickets (tópicos/threads) serão criados.
* `id_servidor_tribunal` - ID do seu servidor do Discord.
* `id_canal_logs_tri` - ID do canal para onde os logs dos tickets serão enviados.
