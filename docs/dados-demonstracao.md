# Dados fictícios para testar o portal

Na pasta que contém `manage.py`, com o portal atualizado e as migrações aplicadas:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py criar_dados_demo
.\iniciar-portal.cmd
```

O comando mostra as senhas geradas no terminal. Guarde-as: uma nova execução não troca nem mostra novamente as senhas existentes. Para recuperar acesso, use `manage.py changepassword demo.lucas` com o Python da virtualenv.

São criados:

- **Técnicos:** `demo.lucas` (Suporte Especializado - N2), `demo.ana` (Infraestrutura e Redes) e `demo.bruno` (Sistemas).
- **Solicitantes:** `demo.marina` (Financeiro), `demo.pedro` (Comercial) e `demo.julia` (RH).
- **Três equipes** com prefixo `[DEMO]`, sem alterar as regras de encaminhamento existentes.
- **Doze chamados** com prefixo `[DEMO]`, distribuídos entre as equipes: abertos, em andamento, resolvidos e fechados; prioridades variadas; prazos vencidos, próximos e futuros; nove comentários fictícios.

Entre com seu administrador atual para ver todos os chamados. Entre como técnico para explorar Minha fila e respostas prontas; os solicitantes veem seus próprios chamados. As contas criadas não são administradoras.

Os exemplos usam e-mails `@example.invalid` e não disparam e-mails nem notificações durante a criação. O processador de alertas poderá gerar notificações internas posteriormente para os chamados elegíveis. Não são concedidas conquistas nem criados eventos de resolução retroativos.

Execute em sua instalação local de testes. O comando exige `DEBUG=True`. Ele adiciona registros ao banco configurado e registra as criações na auditoria; não apaga o banco nem substitui usuários, senhas ou chamados existentes. Se um login reservado já tiver outro e-mail, a operação é recusada integralmente. Repetir o comando não duplica os exemplos que continuam com o mesmo título e solicitante. Não há comando de remoção; para uma demonstração descartável, use uma cópia separada do portal e do banco.
