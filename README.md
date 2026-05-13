# 🎧 Portal de Chamados - Suporte de TI

![Django](https://img.shields.io/badge/Django-092E20?style=for-the-badge&logo=django&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Bootstrap](https://img.shields.io/badge/Bootstrap-563D7C?style=for-the-badge&logo=bootstrap&logoColor=white)
![Chart.js](https://img.shields.io/badge/Chart.js-FF6384?style=for-the-badge&logo=chartdotjs&logoColor=white)

Um sistema completo de Helpdesk e Gestão de Tickets de TI desenvolvido em **Python (Django)**. O projeto foi desenhado para otimizar o fluxo de atendimento de suporte, oferecendo controle rigoroso de SLA, métricas de produtividade em tempo real e autenticação facilitada para ambientes corporativos.

---

## ✨ Principais Funcionalidades

### 📊 Dashboard e Métricas (Para a Equipe de TI)
<img width="1360" height="931" alt="Tela_Dashboard" src="https://github.com/user-attachments/assets/a7128337-8fea-40c3-bf59-b6d249db50d4" />

* **Tempo Médio de Resolução (TMR):** Cálculo automático da média de horas levadas para fechar tickets.
* **Controle de SLA Inteligente:** Prazos (SLA) calculados dinamicamente com base na prioridade do chamado (Crítica, Alta, Normal, Baixa), **pulando finais de semana automaticamente**.
* **Gráficos em Tempo Real:** Visualização da distribuição de tickets por categoria (Software, Hardware, Rede, etc.) e saúde geral do SLA utilizando Chart.js.
* **Ranking de Produtividade:** Gamificação amigável mostrando a quantidade de tickets resolvidos por cada membro da equipe.

### 🎫 Gestão de Tickets
<img width="1430" height="435" alt="Tela_Chamados" src="https://github.com/user-attachments/assets/39aaebc6-20fe-4879-9bdd-299101277954" />

* **Fila de Chamados:** Listagem responsiva com filtros combinados (Busca por texto + Status + Categoria).
* **Ticket Locking:** Mecanismo de "Assumir Chamado", garantindo que apenas o técnico responsável possa enviar respostas e encerrar o ticket.
* **Histórico Interativo:** Timeline de comentários estilo "chat" entre o usuário e o técnico, com suporte a anexo de prints/arquivos.
* **Encerramento Documentado:** Obrigatoriedade de informar a solução do problema ao fechar um ticket, gerando base de conhecimento.

### 💬 Interação e Resolução de Chamados
<img width="1505" height="881" alt="Chamado_Resolvido" src="https://github.com/user-attachments/assets/9c45ef59-494d-4ef4-a2b0-dae7b230d6c5" />

* **Histórico Interativo:** Timeline de comentários estilo "chat" entre o usuário solicitante e o técnico responsável.
* **Barra de Progresso Visual:** Identificação clara e com cores (via Bootstrap) do status atual e do técnico atribuído.
* **Encerramento Documentado:** Obrigatoriedade de informar a solução do problema ao fechar um ticket. Uma vez resolvido, o chamado é bloqueado para novas interações, garantindo a integridade da base de conhecimento (auditoria).

### 👥 Gerenciamento de Usuários (Admin)
<img width="1476" height="692" alt="image" src="https://github.com/user-attachments/assets/18906f85-f551-44cd-8085-fd4a940d3def" />

* **Controle de Acessos:** Separação estrita entre `Cliente` (Apenas visualiza e abre chamados), `Técnico de TI` (Acesso ao Dashboard e resolução) e `Administrador` (Gestor de usuários).
* **Busca Inteligente:** Barra de pesquisa com filtros avançados para encontrar rapidamente colaboradores por nome, e-mail ou username.
* **Ativação e Bloqueio:** Interface ágil para ativar ou revogar o acesso de funcionários ao sistema com um único clique.
* **Identificação Automática:** Captura e exibição automática do e-mail corporativo sincronizado com o Google.

### 🔒 Autenticação e Segurança
<img width="1908" height="935" alt="image" src="https://github.com/user-attachments/assets/981005fc-88a1-4ef7-90ad-167fd414d247" />

* **Google SSO (Single Sign-On):** Login com "um clique" utilizando contas corporativas do Google.
* **Auto-Connect:** Vinculação automática de e-mails do Google com usuários previamente cadastrados manualmente, evitando duplicidade de contas.
* **Proteção de Rotas:** Bloqueio de acesso não autorizado a páginas administrativas e restrição de visualização de tickets.

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
