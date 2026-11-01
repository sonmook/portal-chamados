# Histórico de atualizações

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
