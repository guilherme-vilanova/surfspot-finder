# Implementation And Installation

## Requisitos
- Python 3.9+
- acesso a internet para Google Geocoding, Google Places e Open-Meteo
- chave valida da Google Maps Platform com Geocoding API e Places API habilitadas

## Dependencias atuais
Definidas em [`requirements.txt`](/Users/camilagoulartlima/Documents/surfspot-finder/Demo/requirements.txt):
- `Flask`
- `requests`
- `gunicorn`
- `python-dotenv`
- `mcp`

## Instalacao local
1. Entrar na pasta [`Demo`](/Users/camilagoulartlima/Documents/surfspot-finder/Demo).
2. Criar ambiente virtual.
3. Instalar dependencias.

```bash
cd /Users/camilagoulartlima/Documents/surfspot-finder/Demo
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configurar Google API
1. Criar projeto no Google Cloud Console.
2. Habilitar `Geocoding API`.
3. Habilitar `Places API`.
4. Habilitar `Maps Embed API` se quiser que o quadro lateral do mapa use o `place_id` exato da praia vencedora.
5. Criar uma API key em `APIs & Services > Credentials`.
6. Restringir a key para `Geocoding API`, `Places API` e `Maps Embed API`.
5. Definir a variavel `GOOGLE_MAPS_API_KEY`.

Use como base [`.env.example`](/Users/camilagoulartlima/Documents/surfspot-finder/Demo/.env.example).

Exemplo de `.env`:

```env
GOOGLE_MAPS_API_KEY=your_google_key_here
GOOGLE_GEOCODING_BASE_URL=https://maps.googleapis.com/maps/api/geocode/json
GOOGLE_PLACES_NEARBY_BASE_URL=https://places.googleapis.com/v1/places:searchNearby
GOOGLE_PLACES_AUTOCOMPLETE_BASE_URL=https://places.googleapis.com/v1/places:autocomplete
```

O app e o MCP server carregam esse arquivo por caminho absoluto a partir da pasta `Demo`, entao funcionam mesmo se o comando for executado de outro diretorio.
Se `python-dotenv` nao estiver disponivel no ambiente, o projeto usa um loader interno como fallback para continuar lendo o `.env`.

## Executar o app
```bash
cd /Users/camilagoulartlima/Documents/surfspot-finder/Demo
source .venv/bin/activate
python app.py
```

O app sobe por padrao na porta `5001`, salvo override via `PORT`.

## Executar o MCP server
```bash
cd /Users/camilagoulartlima/Documents/surfspot-finder/Demo
source .venv/bin/activate
python -m mcp_server.server
```

## Executar testes
```bash
cd /Users/camilagoulartlima/Documents/surfspot-finder/Demo
source .venv/bin/activate
python -m unittest discover -s tests
```

## Estrategia de implementacao atual
### Backend
- `app.py` resolve a origem e gera o ranking.
- `mcp_server/location_service.py` resolve a origem e descobre praias dinamicamente via Google Places.
- `persistent_cache.py` persiste caches de busca, mar e clima em disco.
- a origem agora e dinamica e pode vir de texto ou coordenadas.

### Frontend
- campo livre `location_query`;
- autocomplete remoto via Google Places;
- campos ocultos para coordenadas e metadados da origem;
- chamada AJAX para reverse geocoding;
- submit automatico no fluxo de geolocalizacao.

### Integracao Google
- concentrada em `mcp_server/google_client.py`;
- normalizada por `mcp_server/location_service.py`;
- reaproveitavel via `mcp_server/server.py`.

## Deploy
Para producao:
- definir `GOOGLE_MAPS_API_KEY` no ambiente do servidor;
- habilitar `Places API` no mesmo projeto da chave usada pelo app;
- restringir a key por HTTP referrer, ja que o embed do mapa usa essa chave no frontend;
- manter liberado acesso HTTP de saida para Google Places e Open-Meteo;
- nao commitar `.env`;
- reiniciar o servico apos configurar variaveis;
- se usar Render ou similar, manter a chave apenas nas environment variables da plataforma.

## Leitura complementar
- setup detalhado da Google API em [`README_GOOGLE_SETUP.md`](/Users/camilagoulartlima/Documents/surfspot-finder/Demo/README_GOOGLE_SETUP.md)
- MCP server em [`mcp_server/README.md`](/Users/camilagoulartlima/Documents/surfspot-finder/Demo/mcp_server/README.md)
