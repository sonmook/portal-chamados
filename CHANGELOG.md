# Histórico de atualizações

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
