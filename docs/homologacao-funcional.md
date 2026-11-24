# Homologação funcional da v1.17.2

[Resultado aprovado em 24/11/2026, com capturas e uma observação de interface](relatorios/homologacao-v1.17.2-2026-11-24.md).

O comando `scripts/validar_fluxo_atendimento.py` complementa os testes Django, a validação visual e a homologação Docker/HTTPS. Executa os formulários reais no Chromium com CSRF e sessões independentes: um solicitante, outro solicitante sem acesso, um técnico coordenador da equipe inicial, um técnico da equipe de destino e uma administradora.

Todas as contas, chamados e arquivos são fictícios. Banco, uploads e backup são criados em diretório temporário exclusivo. O roteiro não lê nem modifica o banco da instalação.

## Cobertura do roteiro

| Código | Cenário e verificação |
| --- | --- |
| HF-01 | Solicitante abre chamado com PNG; regra de encaminhamento, prazo e download do anexo conferidos. |
| HF-02 | Outro solicitante recebe 404 no chamado/anexo e 403 no Excel administrativo. |
| HF-03 | Técnico assume pelo formulário; responsável muda e prazo é preservado. |
| HF-04 | Resposta pública aparece ao solicitante e gera notificação. |
| HF-05 | Nota e PNG internos aparecem somente à TI; solicitante recebe 404 no arquivo e não recebe aviso privado. |
| HF-06 | Espera por solicitante e resposta do cliente retomam atendimento sem mudar o prazo. |
| HF-07 | Coordenador transfere entre equipes; SLA é preservado, técnico anterior perde acesso e destino recebe o histórico autorizado. |
| HF-08 | Primeiro encerramento salva solução, autor, equipe e ciclo. |
| HF-09 | Solicitante abre aviso e reabre com justificativa; nova contagem de ciclo e histórico anterior conferidos. |
| HF-10 | Segundo encerramento mantém as duas resoluções e os autores históricos. |
| HF-11 | Administradora aplica filtros e confere um chamado, duas resoluções, 100% de SLA e nenhum ativo. |
| HF-12 | Downloads reais de CSV e Excel conferidos: filtros, ciclos, título, equipe e autor; resumo Excel concilia números. |
| HF-13 | Auditoria acessível à administradora e nenhuma exceção JavaScript nas páginas do fluxo. |
| HF-14 | Backup/restauração com todas as tabelas logicamente idênticas, arquivos privados idênticos e banco de origem preservado. |
| HF-15 | Nova instância sobre a cópia restaurada: login, histórico, anexos autorizados, nota oculta ao cliente e indicadores/Excel novamente conferidos. |

O job também valida os **dois arquivos Excel baixados no navegador** com o Open XML SDK da Microsoft, além da checagem do modelo e de outra exportação no job `excel`.

## Executar

Com as dependências do projeto instaladas em ambiente de desenvolvimento:

```sh
python -m pip install playwright==1.62.0
python -m playwright install --with-deps chromium
python scripts/validar_fluxo_atendimento.py
```

Use o Python da venv. Playwright e Chromium são ferramentas de teste; o portal não depende deles para executar. A verificação exige disponibilidade dos recursos CDN já usados pelas páginas, com TLS validado. A CI instala essas ferramentas somente no job visual.

As evidências ficam em `artifacts/homologacao-funcional/`: relatório `resultados.json` com versão, commit e resultados por cenário; capturas com hashes; CSV e dois Excel. Esse diretório é ignorado pelo Git. O artefato `nexaltri-visual` da CI reúne essas evidências e as capturas responsivas por 14 dias. Uma falha interrompe o roteiro e produz resultado parcial e capturas de diagnóstico quando o navegador já iniciou.

## Interpretação dos resultados

Uma execução aprovada comprova o cenário descrito com dados fictícios, na revisão identificada pelo relatório. O teste usa navegador, servidor Django e armazenamento SQLite reais, em processo isolado; não usa `force_login` nem POST direto para simular as ações dos formulários.

A restauração é comparada antes de fazer login na cópia, pois o login cria sessões e avisos administrativos próprios da nova navegação. Depois, a cópia restaurada é aberta pelo navegador com os perfis autorizados.

SMTP externo, Google OAuth real, domínio público e capacidade sob carga não fazem parte deste roteiro. Os avisos validados são as notificações internas do portal. A leitura e a validação Open XML complementam os testes do Excel; não representam automação do aplicativo Microsoft Excel.

[Homologação Docker/HTTPS e implantação](homologacao.md) · [Validação completa Linux/Windows](validacao-atualizacoes.md).
