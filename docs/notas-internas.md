# Notas internas da TI

A v1.14.0 permite registrar colaboração técnica no mesmo chamado, usando um formulário separado de **Adicionar Resposta**. Notas internas e seus anexos têm acesso restrito no servidor e não são enviados como resposta ao solicitante.

## Quem pode consultar e registrar

| Acesso atual | Consultar notas/anexos | Registrar nota |
| --- | --- | --- |
| Solicitante sem papel técnico na equipe | Não | Não |
| Técnico ativo e integrante da equipe ativa do chamado | Sim | Sim, enquanto o chamado estiver ativo |
| Coordenador ativo dessa equipe | Sim | Sim, enquanto o chamado estiver ativo |
| Administrador ativo | Sim | Sim, enquanto chamado e equipe estiverem ativos |
| Técnico de outra equipe, sem acesso interno atual | Não | Não |

Ser solicitante ou autor de uma nota, por si só, não concede acesso interno. Uma pessoa que também é técnico ativo da equipe conserva essa permissão técnica nos próprios chamados. O Django Admin usa a mesma regra de consulta e não permite editar/excluir comentários ou converter sua classificação.

As notas acompanham o chamado: a transferência libera o histórico interno à equipe de destino e revoga o acesso da equipe anterior, salvo se o usuário também tiver permissão na equipe atual ou for administrador. Remoção de vínculo, rebaixamento ou desativação revogam o acesso conforme a situação atual, inclusive quando o usuário continua vendo a conversa pública como solicitante. Equipes inativas não concedem acesso interno aos integrantes; administradores ainda podem consultar o histórico.

## Uso

Nos detalhes de um chamado ativo, abra **Adicionar nota interna · TI**, escreva o texto e, opcionalmente, anexe PNG, JPEG ou PDF de até 10 MB. O formulário distingue o público da mensagem antes de salvar. As notas aparecem no histórico técnico com identificação **Nota interna · TI**, cor própria e link de anexo privado. Não há conversão para resposta pública, edição ou exclusão no portal.

Para solicitantes sem acesso interno, texto, autor/data da nota, marcador e link do anexo não são renderizados. O download direto também revalida o acesso, mesmo quando o ID do comentário é conhecido. O detalhe e as páginas de erro desse fluxo usam `no-store`; os anexos mantêm os cabeçalhos privados existentes.

Texto vazio e arquivo inválido retornam ao formulário com o texto preservado e sem gravação. Arquivos precisam ser selecionados novamente após erro. O formulário inclui CSRF e versões de situação/atribuição; uma tela anterior a mudanças do atendimento retorna HTTP 409 e pede atualização. O servidor determina autor, chamado e classificação interna; campos enviados pelo navegador não alteram essa classificação. A operação registra nota, auditoria e aviso na mesma transação.

## Conversa pública, SLA e avisos

Uma nota interna não altera situação, espera, vencimento, ciclo de atendimento ou última interação da conversa pública. Não retoma automaticamente uma espera pelo solicitante. A resposta pública continua usando **Adicionar Resposta**, com as regras existentes de responsável/solicitante. A busca da fila continua pesquisando número/título/descrição, sem incluir textos de notas.

O aviso interno vai ao técnico responsável elegível, excluindo o autor e o solicitante. Sem responsável elegível, usa coordenadores ativos; sem coordenação, administradores ativos. O autor não recebe seu próprio aviso. Não se gera uma segunda notificação de resposta pública, nem se copia texto ou nome de arquivo para o aviso. O aviso é único por nota/destinatário.

A central, o sino e as ações de leitura também verificam o acesso interno atual. Avisos anteriores ficam ocultos depois de perder a permissão e não são marcados como lidos por ações sobre avisos públicos. A auditoria administrativa registra a classificação e que texto/anexo foram informados, sem copiar o conteúdo ou o nome do arquivo.

## Atualização e verificação

1. Pare portal, alertas e demais escritores; faça backup de banco e uploads.
2. Atualize o código aprovado e aplique `python manage.py migrate` (**0029_notas_internas**).
3. Execute `python scripts/validar_atualizacao.py`; em produção, colete estáticos e reinicie os serviços.
4. No Windows, use o Python da venv e o inicializador habitual.

A migração mantém todos os comentários anteriores públicos (`interna=False`), preservando texto, autoria, data, anexos e notificações/leituras. Não cria notas ou avisos retroativos. O backup completo inclui a classificação e os arquivos; a homologação testa acesso técnico, recusa ao solicitante e preservação após restauração.

Não há nova dependência. Código anterior não conhece a classificação e pode exibir notas como comentários comuns: após usar notas internas, não execute uma versão antiga contra esse banco. Uma recuperação para versão anterior exige backup compatível, anterior às notas.
