# Capturas do sistema

## Organização atual

As imagens do README principal ficam em [`v1.15.0/`](v1.15.0/), com a identidade
Nexaltri, metadados e hashes em `capturas.json`. O script `scripts/validar_visual.py`
gera um novo artefato com banco temporário e dados fictícios; as imagens aprovadas
são copiadas para a pasta da versão. Artefatos de CI expiram, mas as cópias
versionadas no Git permanecem disponíveis.

A [evolução visual](../evolucao-visual.md) organiza as etapas, as notas e todas as
capturas anteriores. Os arquivos PNG desta pasta raiz são históricos e não devem
ser substituídos por telas atuais. [`historico/inventario.json`](historico/inventario.json)
registra origem, data de integração e hashes; as cópias em `historico/` recuperam
revisões que haviam sido sobrescritas antes desta organização.

## Registro original das capturas da v1.1.0

As dez capturas então utilizadas no README foram renovadas em Chromium em 03/11/2026,
a partir da revisão `4fb8f0b`, identificada pela tag `v1.1.0`, em instância local
isolada. Incluem a marca refinada, os ícones de navegação e a versão no cabeçalho.
Viewport de 1440 × 1000, com captura da página inteira quando necessário.

Todos os usuários, e-mails, chamados e comentários são fictícios. Os endereços
usam o domínio reservado `example.invalid`. Nenhum banco, cookie, senha ou arquivo
de configuração da demonstração acompanha as imagens. As páginas foram exibidas
em português e no fuso America/Sao_Paulo por configuração local da demonstração.

| Arquivo | Tela |
| --- | --- |
| `login.png` | Login local, sem configuração OAuth |
| `dashboard.png` | Indicadores e distribuição de chamados |
| `chamados.png` | Fila, estados, prioridades e responsáveis |
| `atendimento.png` | Histórico e formulário vistos pelo técnico responsável |
| `resolucao.png` | Solução registrada e chamado concluído |
| `usuarios.png` | Administração das contas de demonstração |
| `redistribuicao.png` | Formulário preenchido, sem confirmar a transferência |
| `pendencias-tecnico.png` | Aviso de chamados pendentes na edição do técnico |
| `equipes.png` | Equipes, coordenação, integrantes e pendências |
| `encaminhamento.png` | Regras por categoria e equipe de destino |

Para atualizar, use banco e contas de demonstração separados dos dados reais,
capture as rotas correspondentes com os recursos visuais carregados e revise
cada imagem antes de adicioná-la à nova pasta de versão. Não exponha informações de usuários
ou credenciais. Alterações nas imagens seguem o mesmo fluxo de branch e PR.

## Conquistas da v1.3.0

As capturas `conquistas.png`, `gestao-conquistas.png` e `editor-conquista.png`
ilustram as medalhas e a seleção visual de ícones em uma demonstração isolada.
As regras iniciais usam metas de 1/20/20/20; a meta coletiva nas capturas foi
ajustada para 2 apenas para demonstrar uma medalha desbloqueada. O histórico
anterior e a data de início da contagem são preservados na migração 0020.


## Relatório de performance administrativo

A captura `indicadores-administracao.png` mostra o relatório de Administração →
Indicadores com o visual integrado ao Portal de TI, implementado na revisão
`3056455`. Registrada em Chromium com viewport de 1280 × 900 e captura da página
inteira, em 14/11/2026, usando banco isolado e dados fictícios de validação.
A demonstração usa o fuso UTC, indicado no cabeçalho do relatório.
Os oito chamados e a conta de teste servem apenas para ilustrar a interface.
A imagem inclui resumo, SLA, categorias, equipes, rankings e detalhamento das
resoluções; nenhum banco, cookie ou credencial acompanha a captura.
