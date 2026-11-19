# Identidade visual — Nexaltri

Desde a v1.15.0, o nome exibido é **Nexaltri** e o descritor é **Gestão de chamados e atendimento de TI**. Dois segmentos formam um N, com recorte diagonal e pontas arredondadas, representando conexão e encaminhamento. A proposta aprovada orienta as aplicações no produto.

![Marca Nexaltri](../helpdesk/static/helpdesk/brand/logo.svg)

## Arquivos e proporções

Em `helpdesk/static/helpdesk/brand/`:

- `simbolo.svg`: monograma turquesa, sem fundo.
- `logo.svg`: monograma e wordmark azul-marinho, para fundos claros.
- `logo-claro.svg`: monograma e wordmark branco, para fundos escuros.
- `favicon.svg`: monograma sobre base azul-marinho arredondada.
- `favicon-16.png`, `favicon-32.png`, `apple-touch-icon.png`: ícones em 16/32/180px.

O wordmark tem contornos vetoriais derivados da Manrope em peso 800 e espaçamento óptico próprio. Não depende de fonte instalada ou texto rasterizado. Preserve proporções e uma área livre de pelo menos um quarto da altura do símbolo. Não adicione sombras, efeitos ou cores de status ao logotipo. No cabeçalho, a imagem possui texto alternativo Nexaltri; imagens decorativas não repetem o nome.

## Paleta e contraste

| Papel | Cor |
| --- | --- |
| Marca e texto principal | `#101D37` |
| Ações principais e monograma | `#14B8A6` |
| Acento azul | `#638CFF` |
| Fundo gelo | `#F4F7FB` |
| Links, contornos e foco | `#0F766E` / `#087F76` |
| Azul funcional legível | `#365EC4` |
| Superfícies | `#FFFFFF` |
| Texto secundário | `#526179` |
| Bordas | `#DCE4EE` |

Turquesa claro usa texto azul-marinho nas ações principais. Links usam turquesa escuro; o azul funcional mantém contraste em textos/estados. Vermelho, verde e amarelo continuam com significado operacional, sempre acompanhados de texto. O check visual verifica contraste de pelo menos 4,5:1 nos botões principais renderizados.

## Tipografia e aplicações

**Manrope** em títulos e **Inter** na interface, com fallback para fontes do sistema. As famílias variáveis WOFF e licenças OFL estão em `helpdesk/static/helpdesk/fonts/`. O carregamento é local; não se consulta um provedor de fontes durante o acesso. O conjunto inclui os caracteres latinos do português; demais escritas usam fallback. A procedência e os blobs originais estão no README das fontes.

Navegação clara, marca compacta e seleção em turquesa suave. O login combina apresentação azul-marinho no desktop com formulário claro e marca compacta no celular. O Django Admin usa a mesma marca/fontes com folha própria, sem carregar Bootstrap sobre seus componentes. Ícones e CSS compartilhado recebem a versão na URL para atualizar o cache após o deploy.

Campos, rotas, permissões, conteúdo de chamados, notas e ciclos não foram alterados por esta entrega. Responsividade, foco visível e movimento reduzido são preservados. Bootstrap, ícones e Chart.js continuam usando recursos externos já existentes; fontes e marca locais não tornam todo o portal independente de rede.

## Validação visual

O job `visual` instala Playwright/Chromium somente no ambiente de teste. `scripts/validar_visual.py` cria **seu próprio banco SQLite temporário e usuários fictícios**, sem ler um banco de implantação. Exercita login e senha, navegação e telas principais em 1440px, 820px e 390px; verifica marca, imagens, fontes locais, erros JavaScript, contraste e ausência de overflow global. Tabelas podem manter rolagem interna.

Capturas e resultados ficam em `artifacts/nexaltri-visual/`, publicados no artefato homônimo da CI por 14 dias. As prévias incluem apenas dados fictícios. O script pode rodar em desenvolvimento com Playwright 1.62.0 e Chromium preparados; não é preciso instalá-los para usar o portal ou executar a validação comum da atualização.

As capturas aprovadas do README são preservadas em `docs/imagens/v1.15.0/`, com data, commit e hashes, independentemente da expiração do artefato da CI. A [evolução visual](evolucao-visual.md) reúne as imagens antigas e suas origens. Notas anteriores mantêm o nome histórico; novas notas usam Nexaltri. Repositório e comandos de inicialização conservam seus caminhos para compatibilidade com instalações existentes.
