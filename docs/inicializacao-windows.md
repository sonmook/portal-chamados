# Iniciar o portal no Windows

Com o ambiente preparado, um comando mantém portal e alertas de SLA no mesmo terminal:

```powershell
.\iniciar-portal.cmd
```

Abra **http://127.0.0.1:8000/**. O terminal mostra as mensagens dos dois serviços. Para encerrar ambos, pressione **Ctrl+C** e aguarde a mensagem de encerramento. Se o Windows pedir confirmação para finalizar o arquivo em lotes, confirme com **S**.

O comando usa o Python da `.venv` do próprio projeto e encontra a pasta a partir da localização do arquivo. Não precisa ativar o ambiente. Para chamá-lo de outra pasta, use o caminho completo com `&` e aspas:

```powershell
& "C:\Meu projeto\portal-chamados\iniciar-portal.cmd"
```

Encerre os antigos terminais de `runserver` e `processar_alertas_sla` antes de usar o inicializador. Mantenha somente esse terminal aberto durante o uso. Para carregar alterações do Git, pare com Ctrl+C e inicie novamente.

## Preparar uma máquina pela primeira vez

Instale Python **3.12** e Git. Na pasta que contém `manage.py`, execute um comando por vez e pare se ocorrer erro:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser
.\iniciar-portal.cmd
```

`createsuperuser` só é necessário se o banco ainda não tiver uma conta administrativa. O Git traz o código; usuários, chamados e fotos de outra instalação exigem backup/restauração. O lockfile corrigido já inclui `tzdata`; não é necessário instalar esse pacote separadamente.

## Atualizar uma instalação existente

Pare pelo Ctrl+C, faça backup de banco e uploads e atualize a main aprovada. Com o portal e os alertas parados:

```powershell
git switch main
git pull origin main
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\iniciar-portal.cmd
```

Não recrie a conta administrativa nem remova o banco para atualizar.

## Verificações e erros

- **Ambiente:** exige Python 3.12 na `.venv` deste projeto e configuração de desenvolvimento com DEBUG ativo. Não inicia uma implantação de produção.
- **Dependências:** verifica Django e executa `pip check` e o check do projeto. Se houver falha, apresenta o próximo comando necessário; não instala pacotes automaticamente.
- **Migrações:** verifica se o banco está atualizado. Se houver pendências, pede backup e `manage.py migrate`; não aplica alterações silenciosamente.
- **Porta:** se a porta estiver ocupada, encerre a instância antiga ou use `--porta 8001`. O endereço exibido acompanhará a porta escolhida.
- **Duplicação:** a trava `.portal-local.lock` impede dois inicializadores na mesma pasta, mesmo com portas diferentes. Ela é liberada ao encerrar, inclusive se o processo for interrompido. O arquivo permanece ignorado pelo Git; não precisa apagá-lo.
- **Falha de serviço:** se portal ou alertas encerrarem, o inicializador para o outro e termina com erro. Confira a mensagem no terminal antes de reiniciar. Ele só encerra os processos que criou.

Para verificar a preparação sem iniciar serviços:

```powershell
.\iniciar-portal.cmd --verificar
```

Para usar outra porta:

```powershell
.\iniciar-portal.cmd --porta 8001
```

O portal só escuta em `127.0.0.1`. A URL é para essa máquina; o comando não publica o sistema na rede. O Docker mantém a inicialização de seus serviços pelo Compose.
