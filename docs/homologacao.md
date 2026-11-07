# Homologação: preparação e publicação

## Estado e custos

Esta entrega prepara Docker, Gunicorn e Caddy para um servidor Linux. Não contrata
VPS, domínio, SMTP ou serviços externos e não publica um site automaticamente.
Sem servidor/domínio/acesso ao provedor, OAuth público e entrega real de e-mail
continuam pendentes. Não usar dados reais antes de concluir as verificações abaixo.

O conjunto usa SQLite persistente, um worker web síncrono e um processo de alertas, adequado apenas a uma
homologação de baixo volume, sem garantia de capacidade/concorrência de produção.
Docker Engine e Compose V2 devem estar disponíveis no servidor. Uma VPS com IP público,
disco persistente e portas TCP 80/443 liberadas é um caminho compatível; dimensionar
recursos e custos com o provedor antes da contratação. O servidor pode ser dedicado
a esta homologação, evitando conflito com outros serviços nas mesmas portas.

## Publicar depois de obter infraestrutura

1. Criar servidor Linux e configurar acesso administrativo seguro no provedor.
2. Criar um subdomínio de homologação apontando para o IP público (registro A;
   só publicar AAAA se IPv6 estiver configurado). Não reutilizar dados de produção.
3. Instalar Docker/Compose e clonar a revisão aprovada da main no servidor.
4. Copiar `deploy/.env.example` para `.env.homologacao` na raiz do checkout,
   aplicar permissão 0600 e preencher domínio e chave nova. Gerar a chave com
   `python -c "import secrets; print(secrets.token_urlsafe(64))"` no servidor.
   Não enviar chaves por chat ou commit. Variáveis com `$` devem ser protegidas
   por aspas simples no arquivo dotenv para evitar interpolação do Compose.
5. Se houver conflito com a rede 172.30.89.0/24, alterar subnet e IP do proxy juntos.
   O IP do proxy é usado para confiar somente nele ao encaminhar o IP do cliente.
6. Executar da raiz:

   ```bash
   docker compose --env-file .env.homologacao -f deploy/compose.yml config --quiet
   docker compose --env-file .env.homologacao -f deploy/compose.yml up -d --build --wait
   docker compose --env-file .env.homologacao -f deploy/compose.yml exec app python manage.py createsuperuser
   ```

O Caddy solicita e renova HTTPS automaticamente para o domínio público; exige
DNS correto, acesso de saída à autoridade certificadora e entrada nas portas 80/443.
Persistir seus volumes de certificados/configuração. Apenas o proxy publica portas;
Gunicorn, banco e uploads ficam internos. Não publicar a porta 8000 da aplicação.
O IP real recebido pelo Caddy substitui X-Real-IP; o Django só aceita esse cabeçalho
da origem configurada. Não conectar contêineres não confiáveis a essa rede.

O aplicativo usa usuário sem privilégios, filesystem somente leitura e volumes
separados para dados privados e estáticos. Migrações, checks e collectstatic rodam
na inicialização. Faça backup antes de atualizar e acompanhe erros de startup.
O healthcheck verifica uma resposta funcional de login, não somente um PID/porta.
No build da nuvem, a CA do proxy é fornecida por segredo BuildKit; nunca é copiada
para a imagem. Em Linux comum usa-se o bundle do host; BUILD_CA_BUNDLE pode indicar
um bundle corporativo aprovado. Nunca desative TLS para contornar falhas.

O serviço `alertas_sla` inicia após o app ficar saudável e verifica os prazos a cada minuto. Veja [Alertas de SLA](alertas-sla.md). Pare esse serviço junto do app antes de backup, migração ou restauração.

## Google OAuth

- Criar cliente OAuth separado para homologação e cadastrar o callback HTTPS:
  `https://SEU_DOMINIO/accounts/google/login/callback/`.
- Configurar consentimento e usuários de teste no Google Cloud.
- No Django Admin, ajustar o Site ID 1 para o domínio e cadastrar SocialApp Google
  associado a esse site. Entrar com a conta local administrativa antes dessa etapa.
- O cadastro público está fechado: cadastrar usuários autorizados e vincular as
  contas Google em sessão autenticada. Não reabrir cadastro para contornar isso.
- Validar login de conta vinculada, bloqueio de conta desconhecida e de usuário
  desativado. Nunca colocar Client Secret no Git nem no exemplo de ambiente.

## E-mail

Preencher DJANGO_EMAIL_HOST, PORT, HOST_USER, HOST_PASSWORD e DEFAULT_FROM_EMAIL
com os valores do provedor. Usar STARTTLS (USE_TLS=1/USE_SSL=0, tipicamente 587) ou
SSL (USE_TLS=0/USE_SSL=1, tipicamente 465), nunca ambos. A senha é informada somente
no servidor/gerenciador de segredos. Recriar app após alterar ambiente.

Executar `python manage.py sendtestemail EMAIL_DO_OPERADOR` dentro do serviço app,
com endereço autorizado pelo operador. Confirmar recebimento na caixa e em spam;
sucesso do comando comprova aceitação pelo SMTP, não entrega final. Validar também
recuperação de senha pelo domínio HTTPS. Sem SMTP configurado, o perfil não envia
mensagens para console nem considera o envio validado.

## Backup e restauração

**Parar todos os escritores**, inclusive jobs e outros processos que acessem esses
volumes. O comando exige confirmação explícita: ele não detecta todos os escritores.
Manter o proxy em manutenção ou interromper acesso durante a janela. Não há backup
online coerente de banco + arquivos enquanto uploads mudam.

Exemplo com o app e o processo de alertas parados e nenhuma outra instância escrevendo:

```bash
docker compose --env-file .env.homologacao -f deploy/compose.yml stop alertas_sla app
docker compose --env-file .env.homologacao -f deploy/compose.yml run --rm --no-deps --entrypoint python app manage.py backup_homologacao /data/backups/ID_NOVO --confirmar-escritores-parados
docker compose --env-file .env.homologacao -f deploy/compose.yml up -d app alertas_sla
```

A cópia inclui SQLite (com usuários, chamados, comentários e auditoria), uploads e
manifesto SHA-256; verifica integridade SQLite e chaves estrangeiras. O comando
recusa sobrescrita, links simbólicos e destino dentro dos uploads. A restauração
recusa arquivos ausentes/adicionais ou hashes divergentes e usa diretório novo.

Na criação, verificação e restauração, as referências de anexos dos chamados e
comentários no snapshot SQLite também são comparadas com os uploads copiados.
Um anexo referenciado mas ausente impede a operação, mesmo que o manifesto de
hashes seja coerente. Uma raiz de uploads inexistente só é aceita quando o banco
não referencia anexos. Se houver falha na criação, a cópia parcial é removida;
o banco e os uploads de origem são preservados. Corrija a montagem ou recupere os
arquivos ausentes antes de repetir; não apague referências para contornar o erro.
Essa validação não revalida o conteúdo dos anexos antigos nem autentica o manifesto.

Para restaurar:

```bash
docker compose --env-file .env.homologacao -f deploy/compose.yml run --rm --no-deps --entrypoint python app manage.py backup_homologacao /data/restauracao-ID --restaurar /data/backups/ID_NOVO
```

Isso não substitui o banco em uso. Configurar uma instância isolada apontando para
`/data/restauracao-ID/db.sqlite3` e `/data/restauracao-ID/media`, verificar integridade,
usuários, chamados, comentários, auditoria e anexos antes de qualquer corte.

Backups no mesmo volume são apenas uma cópia local: exportar para destino externo
privado e criptografado, com retenção e teste periódico. Eles contêm dados pessoais
e podem conter Client Secret OAuth no banco. Nunca versionar, publicar ou colocar
em imagem Docker. Guardar também revisão do código e segredos da implantação em
armazenamento seguro separado (não são incluídos automaticamente no backup).
SHA-256 detecta corrupção, mas não autentica um manifesto adulterado; restaurar
somente de uma origem confiável. Não apagar a origem ao testar restauração.

## Teste automatizado local/CI

`python scripts/test_homologacao.py` exige Linux com Docker/Compose no socket local.
Cria projeto e volumes exclusivos, usa somente 127.0.0.1 nas portas 18080/18443,
verifica HTTPS com a CA local do Caddy (sem modo insecure), login e estáticos,
bloqueio de mídia pública, backup e restauração de fixtures em destino separado.
Remove apenas seus contêineres/volumes ao finalizar. Não executar em um servidor
sem conferir disponibilidade dessas portas/rede e recursos para o build.

Esse teste não provisiona um domínio público, não valida ACME público, OAuth real,
entrega SMTP ou capacidade sob carga. A suíte Django cobre autorização de anexos
e o fluxo de atendimento; o teste Docker complementa a inicialização e restauração.

Antes de usar dados reais, concluir no domínio público: certificado válido,
redirecionamento HTTPS, login/OAuth, acesso autorizado e bloqueio anônimo dos anexos,
envio/recebimento de e-mail, recuperação de senha e restauração isolada de um backup.
