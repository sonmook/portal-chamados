# Histórico de atualizações

## v1.7.0 — Central de Administração

- Detalhes de auditoria com resumo alinhado e alterações em blocos: comparação Antes/Depois ou indicação única de campo alterado sem valores armazenados.

- Auditoria nativa do portal, com filtros por período/responsável/ID/tipo/ação/origem, paginação e detalhes protegidos. Sem edição ou exclusão, preservando o histórico existente.

- Retorno das telas de gestão unificado no caminho Administração; removidos links antigos duplicados de volta a equipes, conquistas, regras e gerenciamento de usuários.

- Acesso único Administração no cabeçalho substitui Gerenciar Usuários e Gerenciar Equipes.
- Central com Usuários, Equipes, Encaminhamento, Conquistas e Auditoria, reutilizando as telas existentes.
- Acesso exclusivo para administradores, verificado no servidor; permissões de técnicos e coordenadores preservadas.
- Navegação destaca Administração nas telas de gestão e mantém Conquistas para a coleção pessoal.
- Caminho de retorno à central nas telas administrativas. Auditoria continua somente consultável.
- Sem migração, nova dependência ou alteração de dados. Notas em `docs/releases/v1.7.0.md`.

## v1.6.0 — Alertas de SLA e filtros de prazo

- Publicação permite registrar a v1.5.0 histórica (notificações) antes da versão atual, sem mover tags existentes ou atribuir Latest à versão histórica.

- Avisos de prazo próximo (até 1 hora) e vencido ao responsável; sem responsável, os coordenadores recebem os avisos de prazo e de fila sem dono.
- Processamento periódico por comando Django, com serviço automático no Docker; não depende de abrir páginas.
- Deduplicação por prazo, situação e destinatário; leitura não reinicia avisos. Novo ciclo de atribuição permite novo aviso de chamado sem responsável.
- Filtros de prazo combinam com Minha fila, busca, equipes e paginação, respeitando permissões atuais e excluindo finalizados.
- Migração 0024 amplia os tipos de notificação e adiciona índice de status/prazo; preserva dados e não cria avisos durante a migração.
- Backup com aplicação e processo de alertas parados; validação de restauração inclui os novos tipos.
- Sem nova dependência. Operação e atualização em `docs/alertas-sla.md` e `docs/releases/v1.6.0.md`.

## v1.5.0 — Notificações no portal

- Sino com contador pessoal e central paginada, com filtro de não lidas.
- Avisos transacionais de atribuição, resposta, transferência de equipe e resolução; sem avisos sobre a própria ação ou duplicação por evento/destinatário.
- Abrir um aviso marca como lido e leva ao chamado; marcação individual ou em lote protegida por POST e CSRF.
- Acesso atual ao chamado é revalidado na listagem, no contador e na leitura. Avisos de chamados sem acesso deixam de aparecer.
- Migração 0023 adiciona a tabela sem alertas retroativos. Backup/restauração inclui avisos e estado de leitura.
- Sem nova dependência; notas em `docs/releases/v1.5.0.md`.

## v1.4.0 — Catálogo de conquistas e perfil completo

- Catálogo com 12 conquistas predefinidas, individuais e de equipe, com marcos de resoluções e atendimento dentro do SLA; criação manual desabilitada.
- Oito ilustrações SVG originais; coleção compacta com ícone e nome e painel de detalhes por mouse, foco ou toque, sem expandir os cards.
- Meu Perfil separado de Editar perfil, com dados profissionais, equipes e coleção completa de medalhas discretas na lateral.
- Aparência não concede medalhas; alterações de meta e retomadas usam prévia assinada e confirmação explícita. Configurações e medalhas existentes preservadas.
- Migrações 0021 e 0022 adicionam planos, níveis e oito novas conquistas. As novas contagens começam na atualização, sem premiação retroativa.
- Documentação e capturas atualizadas; publicação permite recuperar a v1.3.0 no commit histórico e publicar a versão atual após validar cada commit.
- Notas e atualização em `docs/releases/v1.4.0.md`. A tag só passa a existir após a execução bem-sucedida da ação de publicação.

## v1.3.0 — Conquistas

- Medalhas com fitas, cores e ícones individuais; coleção pessoal, mensagens de incentivo e seletor administrativo com oito símbolos. Migração 0020 preserva o histórico e aplica os ícones iniciais às medalhas existentes.

- Catálogo inicial de quatro conquistas individuais e por equipe, com progresso, vitrine no perfil e aviso no encerramento.
- Gestão de nomes, descrições, metas e concessões pelo administrador; reavaliação explícita ao salvar regras ativas.
- Resoluções elegíveis registradas uma única vez por chamado, sem contagem de histórico, transferências ou chamados próprios.
- Medalhas preservam critérios e nomes do momento da concessão. Auditoria, controle de versão e isolamento por equipe.
- Migração 0019 cria o catálogo e inicia a contagem sem alterar os chamados existentes. Notas em `docs/releases/v1.3.0.md`.

## v1.2.0 — Meu Perfil e enquadramento da foto

- Enquadramento da foto com prévia circular, arraste por mouse/toque, controles de posição e zoom (100–300%) e centralização. Fonte normalizada preservada para ajustes posteriores; migração 0018 mantém o enquadramento central dos perfis existentes.

- Foto, nome, sobrenome, cargo, departamento e ramal editáveis pelo próprio usuário; conta, permissões e equipes protegidas.
- Fotos normalizadas em PNG sem metadados, com limites de tamanho/dimensões e acesso autenticado; avatar no cabeçalho e nas mensagens, com iniciais como fallback.
- Alterações auditadas sem conteúdo pessoal, controle de versão e limpeza de arquivos após confirmação da gravação.
- Migração 0017 cria perfis; backups verificam as fotos sem perder compatibilidade com cópias antigas. Pillow adicionado ao lockfile com hashes.
- Versão do código atualizada para 1.2.0 no portal e no login. Notas em `docs/releases/v1.2.0.md`; publicação oficial pela ação **Publicar versão** após o merge na main.

## v1.1.0 — Equipes, encaminhamento e identidade visual

- Versão centralizada em `VERSION` e exibida no portal e no login.
- Marca refinada com chamado preenchido e headset separado; favicons em 16px e 32px para melhor leitura em abas.
- Identidade própria do Portal de TI: símbolo de chamado com headset, favicon e ícones consistentes, incluindo Gerenciar Equipes.
- Consolida atendimento por equipes, encaminhamento por categoria, última interação e refinamento visual descritos abaixo.
- Notas em `docs/releases/v1.1.0.md`; tag e Release são publicadas pela ação **Publicar versão**, na main, após a validação. O registro neste arquivo não significa que a tag já foi publicada.

## Preparação da v1.1.0 — Refinamento visual

- Navegação e estilos compartilhados entre atendimento e administração, com página ativa e menu móvel.
- Painel de filtros separado do título, tabelas com rolagem acessível e histórico adaptado a telas pequenas.
- Cores, espaçamentos, foco de teclado, rótulos e controles de senha refinados; textos ajustados para português brasileiro.
- Auditoria e capturas fictícias em `docs/auditoria-visual.md`. Sem migrações de banco de dados.

## Preparação da v1.1.0 — Encaminhamento automático por categoria

- Regras administráveis em Gerenciar Equipes, com destinos iniciais para Rede, Acessos, Hardware, Software e Outros.
- Novos chamados do portal e do Django Admin seguem a regra aplicável; destinos inativos ou sem técnico ativo e regras ausentes/desativadas usam a triagem. Não atribui técnico automaticamente.
- Configuração e decisões auditadas, com controle de versão das regras. Migração 0016 não reclassifica chamados nem recria equipes renomeadas.
- Chamados existentes e transferências manuais preservados; nenhuma tag de release publicada.

## Preparação da v1.1.0 — Atendimento por equipes

- Chamados vinculados a equipes; novos registros entram na triagem N1. Migração 0015 preserva o histórico e inclui técnicos ativos já responsáveis na equipe inicial.
- Filas, detalhes, comentários, anexos, indicadores e Django Admin respeitam o escopo de acesso por equipe, mantendo o acesso do solicitante aos próprios chamados.
- Coordenadores distribuem na origem e transferem para equipes ativas, com responsável opcional, motivo e auditoria; administradores têm visão geral.
- Versão de atribuição protege contra edição antiga. Remoção de responsáveis com pendências e desativação de equipes com chamados ativos são bloqueadas; triagem permanece ativa.
- Filtros por equipe e contagem de pendências na gestão; nenhuma tag de release publicada.

## 2026-11-03 — Idioma padrão em português do Brasil

- Definido pt-br como idioma padrão do Django, corrigindo a duração da última interação e demais mensagens traduzíveis do framework. O fuso horário permanece inalterado.
- Regressão valida a exibição de “1 dia, 23 horas atrás” na fila com o idioma padrão real da aplicação.

## 2026-11-03 — Última interação e fila por inatividade

- Comentários e soluções registram a última interação do chamado na mesma transação; salvamentos administrativos não sobrescrevem essa informação.
- Fila mostra data e tempo desde a última interação e permite ordenar por interações recentes ou por chamados ativos sem interação há mais tempo, preservando filtros e paginação.
- Migração 0012 preenche o histórico com datas já registradas de abertura, comentários e encerramento, sem criar auditoria retroativa.

## Preparação da v1.1.0 — Cadastro de equipes

- Área Gerenciar Equipes no menu administrativo, com pesquisa, paginação, cadastro, integrantes, coordenadores e ativação/desativação.
- Migração 0013 cria as seis equipes aprovadas, incluindo Suporte Especializado — N2, sem atribuir usuários ou chamados automaticamente.
- Coordenadores devem ser integrantes; seleção restrita a técnicos ativos, alterações auditadas e proteção contra sobrescrita de edição antiga.
- Django Admin disponível para consulta. Vínculo de chamados, filas e permissões por equipe ficam para a próxima etapa; nenhuma tag de release publicada.

## 2026-11-03 — Consultas do dashboard

- Indicadores e categorias agrupados em uma agregação; tempo médio de resolução calculado no banco, preservando o fallback para a última atualização.
- Ranking agrupado por técnico, incluindo integrantes sem resoluções, e solicitantes carregados junto dos cinco chamados recentes.
- Testes verificam filtros, permissões, resultados e cinco consultas por página mesmo após ampliar equipe e volume de chamados. Nenhuma mudança de interface ou migração.

## 2026-11-03 — Redistribuição administrativa de chamados

- Administradores podem transferir chamados ativos para técnicos ativos com motivo obrigatório, registrando responsáveis anterior/novo e ator na auditoria.
- Telas de transferência desatualizadas não sobrescrevem outra atribuição; falha no registro de auditoria reverte a transferência.
- Desativação e retirada do papel de técnico são bloqueadas com pendências; edição de colaboradores mostra links para redistribuição. Chamados concluídos preservam seus responsáveis.
- Campo técnico somente leitura no Django Admin; recuperação de chamados de técnicos inativos disponível no portal.

## 2026-11-03 — Limitação de tentativas no Django Admin

- Login administrativo agora compartilha com o portal o limite por conta/IP e por IP, sem renovar a cota ao alternar as rotas.
- Preservados CSRF, formulário e permissões padrão do Django Admin; respostas 429 incluem Retry-After e não são cacheadas.
- Testes cobrem expiração, contadores compartilhados, cabeçalhos de IP forjados, login válido e recusa de contas sem acesso.
- MFA permanece pendente; documentados os requisitos para proteger também sessões iniciadas no portal/Google e recuperação de acesso.

## 2026-11-02 — Completude dos anexos nos backups

- Criação, verificação e restauração agora cruzam referências de anexos de chamados e comentários com os arquivos copiados, além dos hashes e integridade SQLite.
- Backups incompletos são recusados; uma instalação sem anexos continua aceitando raiz de uploads inexistente. Cópias parciais de criação são removidas sem alterar a origem.
- Testes de regressão cobrem anexos ausentes, manifesto coerente mas incompleto, restauração e referências inválidas.

## 2026-11-01 — Preparação portátil de homologação

- Docker com Gunicorn sem privilégios e filesystem somente leitura; Caddy com HTTPS e volumes separados. Nenhum serviço externo contratado.
- IP real do cliente aceito somente de proxies explicitamente configurados.
- Variáveis SMTP e rejeição de configuração TLS/SSL conflitante.
- Backup/restauração de SQLite, uploads e auditoria para destino novo, com manifesto de hashes e validação de integridade. Exige escritores parados.
- Teste isolado Docker/HTTPS/restauração executado com sucesso e incorporado ao CI; documentação de domínio, OAuth, SMTP e cópias externas privadas.
- Dependências de execução incluem Gunicorn; lockfile e auditoria atualizados.
- 78 testes Django; OAuth/SMTP e HTTPS públicos aguardam infraestrutura e credenciais do operador.


## 2026-11-01 — Instalação reproduzível, CI e perfil de produção

- Python 3.12 registrado e dependências diretas/lockfile com hashes versionados.
- Django atualizado para 6.0.9 e sqlparse para 0.6.1; auditoria do lockfile final sem vulnerabilidades conhecidas reportadas. IDs anteriores documentados em docs/dependencias.md.
- Workflow GitHub Actions com testes, checks, migrações pendentes, produção, estáticos e auditoria de dependências semanal.
- Removida chave fixa do código atual; desenvolvimento usa chave local ignorada e produção exige configuração explícita, HTTPS e cookies seguros.
- Uploads e banco não podem ficar nos estáticos públicos pelo perfil de produção. HSTS em subdomínios/preload não é habilitado automaticamente.
- Configurações Allauth obsoletas substituídas.
- 67 testes aprovados; instalação validada em venv vazio com hashes. Sem implantação pública ou validação de infraestrutura/OAuth real.


## 2026-11-01 — Correção de autoria Git

- Configurada a identidade oficial sonmook (e-mail noreply do GitHub) para novos commits neste repositório.
- Corrigidos autor e committer dos quatro commits publicados nesta sessão, preservando suas árvores de arquivos e datas.
- Identificadores anteriores passam a corresponder a: 0afd790 → 39bd724; 3900bda → bbd7aae; f610cd2 → 2fa45df; 50a9c2c → cab0215.
- Referências aos identificadores anteriores nas entradas históricas foram mantidas como registro da publicação original.


## 2026-11-01 — Preservação de histórico e auditoria

- Exclusão de usuários com vínculos de atendimento/auditoria agora é protegida; desativação preserva os dados.
- Chamados e comentários não podem ser excluídos no Django Admin; chamados finalizados e comentários existentes não podem ser alterados por essa interface.
- Trilha de alterações com data, ator, origem, status, responsáveis e dados administrativos; conteúdo pessoal e senhas não são armazenados na trilha.
- Consulta da auditoria restrita a superusuários e somente leitura no admin.
- Registros de criação/edição/exclusão dos modelos acompanhados e de grupos/permissões de usuários; atualizações condicionais da atribuição têm registro explícito.
- Corrigida duplicação de registros de modelos no admin introduzida no commit anterior, que impedia a inicialização.
- Adicionadas 14 regressões de histórico/auditoria; suíte completa com 62 testes.
- Migração necessária: 0011_preservar_historico_auditoria. Sem reconstrução retroativa de eventos.


## 2026-11-01 — Autenticação, administração e SLA

- Cadastro administrativo aplica os validadores de senha com os dados do usuário.
- Proteção contra desativação/rebaixamento do último administrador ativo na aplicação e no Django Admin; exclusão de administradores ativos é bloqueada no admin.
- Login local limitado no banco: 10 POSTs por conta/IP e 50 por IP em janelas fixas de 15 minutos; resposta 429 com Retry-After.
- Login local renderiza mesmo sem configuração Google.
- SLA histórico compara encerramento ao prazo (igualdade conta dentro); Fechado é terminal nas métricas, ranking e interface.
- Registros sem datas são identificados sem classificação inventada; TMR legado usa data de atualização como fallback.
- 48 testes aprovados. Migração necessária: 0010_limitar_login.


## 2026-11-01 — Anexos privados e acesso restrito

- Downloads de anexos agora verificam o acesso ao chamado e são entregues como arquivos para baixar, sem cache compartilhado.
- Removida a exposição direta de uploads pela rota de mídia em desenvolvimento.
- Uploads de abertura, comentário e resolução limitados a PNG, JPEG e PDF de até 10 MB, com verificação básica de assinatura.
- Adicionado link privado para o anexo inicial do chamado e feedback de erros nos formulários de chamados.
- Fechado o cadastro público local e social; administradores continuam cadastrando usuários. Contas Google já vinculadas mantêm seu fluxo de login.
- Ativação e bloqueio de usuários passam a exigir POST e CSRF.
- Adicionadas 15 verificações de segurança, totalizando 33 testes aprovados.
- Migração necessária: `python manage.py migrate` (0009_validar_anexos).
- Implantação: manter MEDIA_ROOT privado, sem alias público no servidor ou bucket. A validação básica de assinatura não substitui antivírus. OAuth real e infraestrutura de produção não foram retestados.

## 2026-11-01 — Permissões e encerramento de chamados

- Restringido acesso dos clientes aos próprios chamados.
- Ações de atendimento protegidas por permissões no servidor.
- Encerramento exige técnico responsável e solução preenchida.
- Bloqueadas novas interações em chamados finalizados e encerramento por alteração direta de status.
- Ações de assumir e devolver usam POST com CSRF; atribuição usa atualização condicional.
- Adicionados 18 testes de regressão, todos aprovados.
- Integrado à main no commit `0afd790`.
