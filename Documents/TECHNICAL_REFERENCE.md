# Technical Reference

## Arquivos centrais
- [`app.py`](/Users/camilagoulartlima/Documents/surfspot-finder/Demo/app.py)
- [`persistent_cache.py`](/Users/camilagoulartlima/Documents/surfspot-finder/Demo/persistent_cache.py)
- [`surf_metadata.py`](/Users/camilagoulartlima/Documents/surfspot-finder/Demo/surf_metadata.py)
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

### `GET /api/location-autocomplete`
Responsavel por:
- receber `q`;
- consultar o Google Places Autocomplete;
- retornar sugestoes normalizadas para o campo de busca.

## Principais funcoes em `app.py`
### `safe_get`
Wrapper HTTP com retry simples para chamadas externas.
Tambem reexecuta timeouts curtos antes de falhar definitivamente.

### `cache_get` e `cache_set`
Leitura e escrita do cache em memoria com TTL.

### `layered_cache_get` e `layered_cache_set`
Combinam cache em memoria com cache persistente em disco para reaproveitar dados entre reinicios do app.
Os namespaces de busca e descoberta de praias sao versionados para evitar reaproveitar resultados antigos apos mudancas de heuristica.

### `find_candidate_beaches`
Descobre praias dinamicamente ao redor da origem via Google Places, remove duplicatas e filtra pelo raio final.
Se o Google nao retornar praias, a busca fica sem candidatos.

### `clamp_radius_km`
Garante que a busca respeite o intervalo suportado pela interface e pelo Google Places, hoje entre `30` e `50 km`.

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

### `swell_quality_score`
Pontua quanto a direcao do swell atual combina com o swell preferido do spot, quando esse metadata existe.

### `evaluate_beach`
Combina dados externos e regras de score para uma praia.
Quando apenas uma API externa falha, a funcao ainda aproveita os dados parciais disponiveis em vez de zerar toda a praia.
O score total agora combina `wave_score`, `swell_score` e `wind_score`.

### `resolve_origin`
Resolve a origem da busca:
- coordenadas recebidas do navegador; ou
- texto livre geocodificado pela Google.

## Configuracao tecnica relevante
- `app.py` e `mcp_server/config.py` carregam `.env` usando caminho absoluto da pasta `Demo`.
- Isso evita falhas quando o servidor e iniciado fora do diretorio da aplicacao.
- Quando `python-dotenv` nao esta disponivel, `env_loader.py` carrega manualmente as variaveis do arquivo `.env`.
- `mcp_server/config.py` aceita override do endpoint `GOOGLE_PLACES_NEARBY_BASE_URL`.
- `mcp_server/config.py` aceita override do endpoint `GOOGLE_PLACES_AUTOCOMPLETE_BASE_URL`.
- `persistent_cache.py` grava o cache persistente em `Demo/.cache/surfspot_cache.json`.

### `build_beach_rankings`
Aplica filtro por distancia, avalia praias e ordena o ranking final.
Resultados dinamicos sem sinal util da Marine API sao removidos do ranking para reduzir spots que nao representam mar aberto.
Para reduzir latencia, a funcao limita a avaliacao externa aos candidatos mais proximos antes de ordenar o top final.

### `build_rankings_with_radius_fallback`
Executa o ranking no raio pedido e, quando nao encontra praia surfavel, tenta novamente com raios maiores predefinidos.

## Principais classes do `mcp_server`
### `GoogleGeocodingClient`
Responsavel por:
- chamar a Geocoding API;
- tratar status e erros do Google;
- retornar o primeiro resultado relevante.

### `GooglePlacesClient`
Responsavel por:
- chamar o endpoint `places:searchNearby`;
- chamar o endpoint `places:autocomplete`;
- limitar o raio ao maximo aceito pela API;
- solicitar apenas os campos necessarios via `X-Goog-FieldMask`;
- retornar praias proximas para a camada de servico.

### `GoogleLocationService`
Responsavel por:
- encapsular a logica de geocoding e reverse geocoding;
- encapsular a descoberta de praias via Google Places;
- normalizar payloads para o contrato interno do app e do MCP;
- enriquecer spots conhecidos com metadata local de swell.

### `GoogleLocationService.find_nearby_beaches(lat, lon, radius_km)`
Entrada:
- `lat: number`
- `lon: number`
- `radius_km: number`

Saida:
- lista de praias com `name`, `region`, `lat`, `lon`, `place_id`, `notes` e `source`

Observacao:
- o Google Nearby Search aceita raio maximo de 50 km por chamada, entao o servico faz clamp automatico.

### `GoogleLocationService.autocomplete_places(query)`
Entrada:
- `query: string`

Saida:
- lista de sugestoes com `value`, `label`, `meta` e `place_id`

## Metadata auxiliar de surf
### `surf_metadata.py`
Responsavel por:
- canonicalizar nomes de praia para deduplicacao;
- manter uma lista curta de spots conhecidos com `preferred_swell_label` e `preferred_swell_degrees`, com cobertura expandida para praias mais comuns de SC e RS;
- aplicar esse metadata sem voltar a depender de um dataset completo de praias.

### URLs de mapa da praia vencedora
- `build_beach_map_embed_url(beach)` usa `place_id` quando a praia veio do Google Places e cai para coordenadas quando esse identificador nao existe.
- `build_beach_google_maps_url(beach)` usa `query_place_id` para abrir o Google Maps diretamente no spot vencedor quando possivel.

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
- o autocomplete do campo `location_query` agora consome o endpoint interno `/api/location-autocomplete`.

## Funcionalidades atuais
- busca por localizacao digitada;
- busca por localizacao atual;
- descoberta dinamica de praias por coordenadas e raio com Google Places como fonte principal;
- reverse geocoding interno;
- ranking de praias por score;
- destaque da melhor praia;
- tabela de resultados com wave score e wind score;
- cache em memoria;
- testes unitarios para fluxo principal e servico de localizacao.
