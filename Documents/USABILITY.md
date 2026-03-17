# Usability

## Objetivo da experiencia
Permitir que uma pessoa encontre rapidamente praias de surf proximas e bem avaliadas sem precisar conhecer previamente os municipios ou spots cadastrados.

## Fluxos principais do usuario
### 1. Buscar digitando uma localizacao
- O usuario digita cidade, bairro, praia ou endereco.
- Escolhe raio maximo.
- Escolhe quantidade de resultados.
- Escolhe nivel do surfista.
- Clica em `Find beaches`.

### 2. Buscar com `Use my location`
- O usuario clica em `Use my location`.
- O navegador pede permissao de localizacao.
- O sistema resolve o endereco atual.
- A busca e enviada automaticamente.

## Comportamentos de interface
- A origem nao depende mais de uma lista fixa.
- O conjunto de praias pode ser descoberto dinamicamente ao redor da origem e do raio escolhidos.
- A descoberta dinamica prioriza praias com perfil mais costeiro e reduz resultados de lago, rio e canal quando a intencao e surf.
- Spots dinamicos sem leitura util de ondas na Marine API deixam de aparecer no ranking final.
- Leituras muito fracas de onda tambem sao descartadas para reduzir praias nao surfaveis de agua interna.
- O campo de localizacao aceita texto livre.
- O campo de localizacao oferece autocomplete inline com contexto completo, como cidade, estado e pais.
- A interface permite alternar unidades entre `Metric / Universal` e `American` para distancia, onda, vento e temperatura.
- O campo `Surfer Level` oferece um botao informativo explicando os perfis e como eles influenciam o ranking.
- A interface mostra o local resolvido no resumo da busca.
- O resumo tambem mostra a origem do dado:
  - `manual`
  - `browser`
- A interface adota uma direcao visual inspirada no Surfguru:
  - hero com azul marinho forte e destaque laranja;
  - tipografia condensada para titulos;
  - destaque da melhor praia em um card principal;
  - ranking completo em tabela dentro de um painel editorial.

## Feedback e estados
### Estado inicial
- Exibe uma mensagem convidando o usuario a digitar uma localizacao ou usar a localizacao atual.

### Estado de carregamento da geolocalizacao
- Exibe mensagem de status no formulario.
- Desabilita o botao temporariamente enquanto o browser e o reverse geocoding executam.

### Estado de carregamento da busca
- Exibe uma tela de carregamento sobre a pagina durante a pesquisa.
- Bloqueia novas interacoes enquanto praias e previsoes estao sendo carregadas.
- Usa mensagens diferentes para busca manual e busca por localizacao atual.

### Estados de erro
- Campo vazio: pede para informar uma localizacao ou usar a localizacao atual.
- Permissao negada: orienta o usuario a digitar a localizacao manualmente.
- Localizacao indisponivel ou timeout: orienta retry ou fallback manual.
- Google sem resposta: exibe erro amigavel sem quebrar a pagina.

### Estado de sucesso
- Exibe local selecionado, raio, perfil e quantidade de resultados.
- Quando nao ha praia surfavel no raio inicial, o sistema pode ampliar automaticamente a busca e avisar isso em um banner.
- Mostra a melhor praia em destaque com score em estrelas e resumo rapido de condicoes.
- Agrupa `Snapshot` e `Weather` dentro do proprio card vencedor para concentrar a leitura principal.
- No `Waves`, destaca onda, periodo e direcao do swell.
- No `Weather`, destaca temperatura, clima com icone, vento e direcao do vento com seta.
- Mostra um quadro lateral com mapa da praia vencedora em um zoom mais distante para dar contexto geografico.
- Mostra o score com estrelas de 0 a 5 no ranking, incluindo estrelas vazias para indicar progresso visual, sem exibir o numero bruto.
- Mostra legenda da escala de estrelas no topo do ranking com leitura orientada a surf, como `Difficult`, `Limited`, `Surfable`, `Good Window` e `Worth It`.
- Mostra cards laterais com metricas e chips de leitura.
- Na coluna `Wave` do ranking, explicita `Height`, `Period` e `Direction` antes dos valores para facilitar a leitura.
- Mostra a tabela ranqueada em uma secao separada.

## Boas praticas de usabilidade adotadas
- fallback manual quando a geolocalizacao falha;
- mensagens claras e proximas da acao do usuario;
- resumo da origem usada na busca;
- interface responsiva para desktop e mobile;
- campo livre para reduzir friccao de uso;
- hierarquia visual mais forte entre busca, melhor resultado e ranking;
- score com leitura visual mais imediata, sem depender apenas do numero bruto;
- leitura mais rapida das condicoes principais antes de entrar na tabela.

## Limitacoes de UX atuais
- ainda nao existe autocomplete de localizacao;
- a descoberta dinamica depende de conectividade com Overpass e pode variar conforme a cobertura do OpenStreetMap.
