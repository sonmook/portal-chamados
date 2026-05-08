# 🎧 Portal de Chamados - Suporte de TI

![Django](https://img.shields.io/badge/Django-092E20?style=for-the-badge&logo=django&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Bootstrap](https://img.shields.io/badge/Bootstrap-563D7C?style=for-the-badge&logo=bootstrap&logoColor=white)
![Chart.js](https://img.shields.io/badge/Chart.js-FF6384?style=for-the-badge&logo=chartdotjs&logoColor=white)

Um sistema completo de Helpdesk e Gestão de Tickets de TI desenvolvido em **Python (Django)**. O projeto foi desenhado para otimizar o fluxo de atendimento de suporte, oferecendo controle rigoroso de SLA, métricas de produtividade em tempo real e autenticação facilitada para ambientes corporativos.

---

## ✨ Principais Funcionalidades

### 📊 Dashboard e Métricas (Para a Equipe de TI)
* **Tempo Médio de Resolução (TMR):** Cálculo automático da média de horas levadas para fechar tickets.
* **Controle de SLA Inteligente:** Prazos (SLA) calculados dinamicamente com base na prioridade do chamado (Crítica, Alta, Normal, Baixa), **pulando finais de semana automaticamente**.
* **Gráficos em Tempo Real:** Visualização da distribuição de tickets por categoria (Software, Hardware, Rede, etc.) e saúde geral do SLA utilizando Chart.js.
* **Ranking de Produtividade:** Gamificação amigável mostrando a quantidade de tickets resolvidos por cada membro da equipe.

### 🔒 Autenticação e Segurança
* **Google SSO (Single Sign-On):** Login com "um clique" utilizando contas corporativas do Google.
* **Auto-Connect:** Vinculação automática de e-mails do Google com usuários previamente cadastrados manualmente.
* **Gestão de Níveis de Acesso:** Separação estrita entre `Cliente` (Apenas visualiza e abre chamados), `Técnico de TI` (Acesso ao Dashboard e resolução) e `Administrador` (Gestor de usuários).

### 🎫 Gestão de Tickets
* **Fila de Chamados:** Listagem responsiva com filtros combinados (Busca por texto + Status + Categoria).
* **Ticket Locking:** Mecanismo de "Assumir Chamado", garantindo que apenas o técnico responsável possa enviar respostas e encerrar o ticket.
* **Histórico Interativo:** Timeline de comentários estilo "chat" entre o usuário e o técnico, com suporte a anexo de prints/arquivos.
* **Encerramento Documentado:** Obrigatoriedade de informar a solução do problema ao fechar um ticket, gerando base de conhecimento.

---

## 🛠️ Tecnologias Utilizadas

* **Back-end:** Python, Django
* **Front-end:** HTML5, CSS3, Bootstrap 5, Ícones do Bootstrap
* **Visualização de Dados:** Chart.js
* **Banco de Dados:** SQLite (Fácil migração para PostgreSQL/MySQL)
* **Autenticação:** Django Allauth (Google OAuth2)

---

## 🚀 Como rodar o projeto localmente

Siga o passo a passo abaixo para clonar e rodar a aplicação na sua máquina:

### 1. Clone o repositório
```bash
git clone [https://github.com/sonmook/portal-chamados.git](https://github.com/sonmook/portal-chamados.git)
cd portal-chamados
