# Documentation Policy

## Objetivo
Garantir que a documentacao acompanhe o codigo e continue util para uso, manutencao e onboarding.

## Regra de manutencao
Sempre que houver alteracao no codigo da versao `Demo`, os arquivos desta pasta devem ser atualizados de forma correspondente.

## O que atualizar em cada tipo de mudanca
### Mudancas de arquitetura ou integracoes
Atualizar:
- [`INFRASTRUCTURE.md`](/Users/camilagoulartlima/Documents/surfspot-finder/Demo/Documents/INFRASTRUCTURE.md)
- [`TECHNICAL_REFERENCE.md`](/Users/camilagoulartlima/Documents/surfspot-finder/Demo/Documents/TECHNICAL_REFERENCE.md)

### Mudancas de setup, env vars, deploy ou dependencias
Atualizar:
- [`IMPLEMENTATION_AND_INSTALLATION.md`](/Users/camilagoulartlima/Documents/surfspot-finder/Demo/Documents/IMPLEMENTATION_AND_INSTALLATION.md)
- [`.env.example`](/Users/camilagoulartlima/Documents/surfspot-finder/Demo/.env.example) se aplicavel

### Mudancas de interface ou fluxo do usuario
Atualizar:
- [`USABILITY.md`](/Users/camilagoulartlima/Documents/surfspot-finder/Demo/Documents/USABILITY.md)
- [`TECHNICAL_REFERENCE.md`](/Users/camilagoulartlima/Documents/surfspot-finder/Demo/Documents/TECHNICAL_REFERENCE.md) se houver novo contrato tecnico

### Novos endpoints, classes, funcoes ou ferramentas MCP
Atualizar:
- [`TECHNICAL_REFERENCE.md`](/Users/camilagoulartlima/Documents/surfspot-finder/Demo/Documents/TECHNICAL_REFERENCE.md)
- [`INFRASTRUCTURE.md`](/Users/camilagoulartlima/Documents/surfspot-finder/Demo/Documents/INFRASTRUCTURE.md) se a mudanca afetar a arquitetura

## Padrao de escrita recomendado
- descrever responsabilidade antes de implementar detalhes;
- separar visao de produto, operacao e referencia tecnica;
- manter exemplos curtos e reais;
- evitar duplicar longos trechos entre arquivos;
- citar arquivos reais do projeto sempre que necessario.

## Compromisso futuro
De agora em diante, toda alteracao relevante no codigo desta base deve vir acompanhada da atualizacao destes arquivos de documentacao.
