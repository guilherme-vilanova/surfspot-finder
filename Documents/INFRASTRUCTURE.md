# Infrastructure

## Visao geral
O SurfSpot Finder e uma aplicacao web em Flask que recomenda praias de surf a partir de uma origem escolhida pelo usuario. A aplicacao usa:
- frontend HTML/Jinja em [`templates/index.html`](/Users/camilagoulartlima/Documents/surfspot-finder/Demo/templates/index.html);
- backend Flask em [`app.py`](/Users/camilagoulartlima/Documents/surfspot-finder/Demo/app.py);
- descoberta dinamica de praias via Google Places na camada [`mcp_server/`](/Users/camilagoulartlima/Documents/surfspot-finder/Demo/mcp_server);
- metadata leve de surf em [`surf_metadata.py`](/Users/camilagoulartlima/Documents/surfspot-finder/Demo/surf_metadata.py) para enriquecer o ranking com swell preferido em spots conhecidos;
- camada de integracao Google e MCP em [`mcp_server/`](/Users/camilagoulartlima/Documents/surfspot-finder/Demo/mcp_server).

## Componentes principais
### 1. Flask app
Responsavel por:
- receber a busca do usuario;
- resolver a origem;
- consultar dados externos;
- calcular distancias e score;
- renderizar o ranking final.

### 2. Template web
Responsavel por:
- receber digitacao livre de localizacao;
- consultar autocomplete de localizacao em tempo real via endpoint interno;
- acionar `Use my location`;
- chamar o endpoint interno de reverse geocoding;
- disparar a busca automaticamente quando a geolocalizacao for obtida.

### 3. Descoberta de praias
Responsavel por:
- buscar praias em torno da origem e do raio escolhido usando Google Places Nearby Search;
- normalizar nome, regiao, coordenadas e notas basicas de cada praia encontrada.

### 4. Metadata de surf
Responsavel por:
- aplicar heuristicas de identidade para nomes equivalentes de praia;
- anexar metadata local de swell preferido para spots conhecidos;
- influenciar o ranking quando a direcao do swell combina com o spot.

### 5. Integracoes externas
- Google Geocoding API:
  - geocode de endereco digitado;
  - reverse geocode de latitude/longitude do navegador.
- Google Places API:
  - descoberta de praias proximas a partir de coordenadas e raio.
  - autocomplete de locais digitados no campo de busca.
- Open-Meteo Marine API:
  - altura, periodo e direcao de onda.
- Open-Meteo Forecast API:
  - vento, temperatura, precipitacao e weather code.

### 6. MCP server
Responsavel por:
- encapsular integracoes com Google;
- expor ferramentas reutilizaveis para geocoding;
- preparar a base para novas APIs no futuro.

## Fluxo de dados
### Busca manual
1. O usuario digita uma localizacao.
2. O Flask chama a camada `GoogleLocationService`.
3. O endereco e convertido em latitude/longitude.
4. O backend descobre praias proximas dentro do raio escolhido.
5. As praias dentro do raio sao avaliadas com dados da Open-Meteo.
6. O ranking e ordenado e renderizado.

### Busca por localizacao atual
1. O navegador usa `navigator.geolocation`.
2. O frontend envia coordenadas para `/api/reverse-geocode`.
3. O backend resolve um endereco amigavel com Google.
4. O formulario e submetido automaticamente com coordenadas e rotulo resolvido.
5. O ranking e gerado com o mesmo pipeline da busca manual.

## Camadas e responsabilidades
- UI: coleta input e exibe resultados.
- Controller Flask: valida entrada e coordena o fluxo.
- Service layer: resolve localizacao externa e normaliza payloads.
- Domain logic: calcula distancia, pontuacao e ordenacao.
- External providers: Google e Open-Meteo.
- A busca dinamica do Google Places usa um raio maximo de 50 km por chamada, e a interface respeita esse limite.

## Configuracao e segredos
- `GOOGLE_MAPS_API_KEY`: chave principal usada por Google Geocoding e Google Places.
- `GOOGLE_GEOCODING_BASE_URL`: override opcional para testes e mocks.
- `GOOGLE_PLACES_NEARBY_BASE_URL`: override opcional do endpoint `places:searchNearby`.
- `GOOGLE_PLACES_AUTOCOMPLETE_BASE_URL`: override opcional do endpoint `places:autocomplete`.
- As variaveis ficam fora do codigo, em `.env` local ou no ambiente de deploy.
- O carregamento do `.env` e feito a partir da pasta `Demo`, evitando dependencia do diretorio atual do terminal.
- Se a biblioteca `python-dotenv` nao estiver instalada, um loader interno assume a leitura do `.env`.

## Caching
O sistema usa cache em memoria para:
- respostas de condicoes marinhas;
- respostas de forecast;
- resultado de buscas por coordenadas e filtros.

O sistema tambem persiste esses caches em disco dentro de `Demo/.cache/`, permitindo reaproveitar respostas mesmo apos reiniciar o app.

## Otimizacoes de performance
- o ranking avalia primeiro as praias mais proximas e limita quantos candidatos recebem chamadas externas;
- spots dinamicos sem sinal util da Marine API nao consomem chamada adicional de forecast;
- a concorrencia de avaliacao foi ampliada para acelerar o carregamento local.
- as chamadas para Open-Meteo usam retry curto e timeouts menores para falhar mais rapido quando o provedor esta lento.
