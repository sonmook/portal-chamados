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
git clone https://github.com/sonmook/portal-chamados.git
cd portal-chamados
```


## Controles de acesso e anexos

Novas contas são cadastradas por administradores em `/novo-usuario/` ou no Django Admin.
O cadastro público via senha e via Google está fechado. Contas sociais já vinculadas
continuam usando o login existente; cadastrar uma conta local não a vincula automaticamente
à conta Google. A vinculação deve seguir um fluxo autenticado e verificado; não habilite
cadastro público para contornar essa etapa.

Anexos novos aceitam PNG, JPEG e PDF de até 10 MB. Extensão e assinatura básica são
verificadas nas três entradas (abertura, comentário e resolução), inclusive nos formulários
do admin por validação de modelo. Isso não constitui análise antivírus nem decodificação
completa do conteúdo. Os arquivos são entregues como download binário, sem cache compartilhado.
Solicitantes acessam anexos de seus chamados; equipe técnica acessa os chamados da fila.

**Implantação:** mantenha `MEDIA_ROOT` privado. Não configure alias público de `/media/`,
bucket público ou servidor estático apontando para uploads. Os downloads passam pelas rotas
`/chamado/<id>/anexo/` e `/chamado/<id>/comentario/<id>/anexo/` com autorização.
Arquivos antigos permanecem no armazenamento e também passam por essas rotas; não são
revalidados ou removidos automaticamente. Links antigos de `/media/` deixam de funcionar.
Configure no proxy um limite de corpo compatível com 10 MB por arquivo mais o formulário,
e políticas de armazenamento/antivírus conforme a implantação.

Após atualizar, execute `python manage.py migrate` (migração 0009 de validadores) e
`python manage.py test helpdesk`. Ativar/bloquear usuários agora exige POST com CSRF;
integrações que faziam GET nessa rota devem ser atualizadas.


## Login e administração

Execute a migração 0010 antes de usar o login local. O limite de `/contas/login/`
conta todos os POSTs que passam pelo CSRF (incluindo os bem-sucedidos): 10 por
conta/IP e 50 por IP em janelas fixas de 15 minutos. Contadores ficam no banco,
com chaves hash, e registros expirados são limpos nas próximas tentativas.
Um bloqueio retorna 429 com Retry-After; a virada de janela permite novas tentativas.
Nomes de conta são normalizados para contagem; o login mantém o comportamento Django.
Não se confia em X-Forwarded-For. Atrás de proxy, configure REMOTE_ADDR no servidor
com uma origem confiável; caso contrário todos os clientes podem compartilhar o limite.
Esse limite cobre o login local do portal, não /admin/ ou o fluxo OAuth/Allauth.
O servidor deve complementar a proteção contra tráfego abusivo e ataques distribuídos.

Edição de contas preserva pelo menos um administrador ativo com acesso ao admin
(is_active/is_staff/is_superuser). No Django Admin é necessário rebaixar um
administrador antes de excluí-lo. Operações SQL/ORM diretas continuam sendo de
responsabilidade do operador. Alterações pelas telas usam transações e bloqueios
de administradores; SQLite não oferece bloqueio de linha e pode rejeitar escritas
concorrentes. Testes de concorrência na infraestrutura de produção ainda são necessários.


## Preservação de histórico e auditoria

A migração 0011 protege usuários referenciados como solicitantes, técnicos,
responsáveis pelo encerramento, autores de comentários ou atores da auditoria.
Excluir essas contas retorna proteção de relacionamento; prefira desativá-las.
Nenhum dado histórico é removido ou anonimizado automaticamente. A política de
retenção e eventual anonimização deve ser definida antes de executar processos
específicos para esse fim, considerando a preservação dos vínculos.

O Django Admin não permite excluir chamados ou comentários, alterar chamados
Resolvidos/Fechados nem editar comentários. Status e encerramento são controlados
pelo fluxo de atendimento, não pelos campos do admin. Comentários novos são
adicionados pelo portal. Chamados com comentários também têm exclusão protegida
no relacionamento do modelo.

Superusuários podem consultar os registros de auditoria no Django Admin, sem
botões de criação, edição ou exclusão. Cada evento inclui data, ator, origem
(portal/admin/sistema), objeto e alterações. Status, IDs de responsáveis, papéis,
ativação e datas têm valores antes/depois. Nomes, e-mail, senha, descrição,
comentários e caminhos de anexos são registrados apenas como campo alterado;
nem senhas nem hashes são armazenados nessa trilha. Mudanças de grupos e
permissões diretas dos usuários registram os IDs envolvidos.

A coleta começa após a migração, sem reconstruir eventos anteriores. Alterações
fora de requisições identificadas pelo middleware ficam com ator vazio e origem
sistema. Isso não constitui log imutável contra administradores do banco:
SQL direto, QuerySet.update/bulk_create e mudanças externas não passam pelos
signals. A atribuição condicional de chamados tem registro explícito na view.
As rotas de alteração do portal e o admin usam transações para preservar a
consistência do registro e da alteração. Integrações futuras devem também usar
transações e registrar atualizações em lote explicitamente. Operações de terminal
fora de transação não oferecem a mesma atomicidade.

Backups devem abranger banco, uploads privados e trilha de auditoria juntos.
Não foram realizados nesta etapa testes de restauração, concorrência real em
produção ou retenção em armazenamento externo protegido contra adulteração.
