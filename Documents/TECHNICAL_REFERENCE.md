# Technical Reference

## Arquivos centrais
- [`app.py`](/Users/camilagoulartlima/Documents/surfspot-finder/Demo/app.py)
- [`beach_source.py`](/Users/camilagoulartlima/Documents/surfspot-finder/Demo/beach_source.py)
- [`beaches_rs.py`](/Users/camilagoulartlima/Documents/surfspot-finder/Demo/beaches_rs.py)
- [`beaches_sc.py`](/Users/camilagoulartlima/Documents/surfspot-finder/Demo/beaches_sc.py)
- [`persistent_cache.py`](/Users/camilagoulartlima/Documents/surfspot-finder/Demo/persistent_cache.py)
- [`templates/index.html`](/Users/camilagoulartlima/Documents/surfspot-finder/Demo/templates/index.html)
- [`mcp_server/google_client.py`](/Users/camilagoulartlima/Documents/surfspot-finder/Demo/mcp_server/google_client.py)
- [`mcp_server/location_service.py`](/Users/camilagoulartlima/Documents/surfspot-finder/Demo/mcp_server/location_service.py)
- [`mcp_server/server.py`](/Users/camilagoulartlima/Documents/surfspot-finder/Demo/mcp_server/server.py)

## Principais rotas
### `GET/POST /`
Responsavel por:
- renderizar a home;
- receber filtros de busca;
- resolver a origem;
- montar o ranking final.

### `POST /api/reverse-geocode`
Responsavel por:
- receber `lat` e `lon`;
- resolver endereco amigavel via Google;
- retornar JSON para o frontend.

## Principais funcoes em `app.py`
### `safe_get`
Wrapper HTTP com retry simples para chamadas externas.

### `cache_get` e `cache_set`
Leitura e escrita do cache em memoria com TTL.

### `layered_cache_get` e `layered_cache_set`
Combinam cache em memoria com cache persistente em disco para reaproveitar dados entre reinicios do app.

### `find_candidate_beaches`
Descobre praias dinamicamente ao redor da origem, remove duplicatas e aplica fallback para datasets locais.
Quando o fallback local ja traz cobertura suficiente, evita a chamada dinamica para reduzir latencia.

### `haversine_km`
Calcula a distancia entre origem e praia.

### `get_marine_conditions`
Consulta dados de onda na Open-Meteo Marine API.

### `get_forecast_conditions`
Consulta dados de vento e clima na Open-Meteo Forecast API.

### `wind_quality_score`
Pontua a qualidade do vento para cada praia.

### `wave_quality_score`
Pontua a qualidade das ondas por perfil de surfista.

### `evaluate_beach`
Combina dados externos e regras de score para uma praia.

### `resolve_origin`
Resolve a origem da busca:
- coordenadas recebidas do navegador; ou
- texto livre geocodificado pela Google.

## Configuracao tecnica relevante
- `app.py` e `mcp_server/config.py` carregam `.env` usando caminho absoluto da pasta `Demo`.
- Isso evita falhas quando o servidor e iniciado fora do diretorio da aplicacao.
- Quando `python-dotenv` nao esta disponivel, `env_loader.py` carrega manualmente as variaveis do arquivo `.env`.
- `beach_source.py` aceita override do endpoint `OVERPASS_API_URL`.
- `persistent_cache.py` grava o cache persistente em `Demo/.cache/surfspot_cache.json`.

### `build_beach_rankings`
Aplica filtro por distancia, avalia praias e ordena o ranking final.
Resultados dinamicos sem sinal util da Marine API sao removidos do ranking para reduzir spots que nao representam mar aberto.
Para reduzir latencia, a funcao limita a avaliacao externa aos candidatos mais proximos antes de ordenar o top final.

### `build_rankings_with_radius_fallback`
Executa o ranking no raio pedido e, quando nao encontra praia surfavel, tenta novamente com raios maiores predefinidos.

## Principais funcoes em `beach_source.py`
### `discover_beaches`
Executa uma consulta na Overpass API para buscar praias por geolocalizacao e raio.
Aplica filtros heurísticos para priorizar praias com sinal costeiro ou de surf e reduzir praias de lago, rio ou canal.

### `BeachDiscoveryError`
Erro de integracao usado para acionar o fallback local sem quebrar o fluxo do usuario.

## Principais classes do `mcp_server`
### `GoogleGeocodingClient`
Responsavel por:
- chamar a Geocoding API;
- tratar status e erros do Google;
- retornar o primeiro resultado relevante.

### `GoogleLocationService`
Responsavel por:
- encapsular a logica de geocoding e reverse geocoding;
- normalizar payloads para o contrato interno do app e do MCP.

## Ferramentas MCP expostas
### `geocode_address(query)`
Entrada:
- `query: string`

Saida:
- `formatted_address`
- `lat`
- `lon`
- `place_id`

### `reverse_geocode(lat, lon)`
Entrada:
- `lat: number`
- `lon: number`

Saida:
- `formatted_address`
- `lat`
- `lon`
- `place_id`

## Campos principais do formulario
- `location_query`
- `origin_lat`
- `origin_lon`
- `origin_source`
- `resolved_location_label`
- `max_distance_km`
- `result_limit`
- `skill_level`

## Dados auxiliares de interface
- `SEARCH_SUGGESTIONS`: lista local estruturada com `value`, `label` e `meta`, usada no autocomplete inline do campo `location_query`.

## Funcionalidades atuais
- busca por localizacao digitada;
- busca por localizacao atual;
- descoberta dinamica de praias por coordenadas e raio;
- fallback para datasets locais de SC e RS quando a descoberta externa falha;
- reverse geocoding interno;
- ranking de praias por score;
- destaque da melhor praia;
- tabela de resultados com wave score e wind score;
- cache em memoria;
- testes unitarios para fluxo principal e servico de localizacao.
