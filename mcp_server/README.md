# MCP Server

This folder contains the MCP server used to centralize Google integrations for SurfSpot Finder.

## Tools exposed
- `geocode_address(query)`
- `reverse_geocode(lat, lon)`

## Run locally
1. Create and activate your virtual environment.
2. Install [`requirements.txt`](/Users/camilagoulartlima/Documents/surfspot-finder/Demo/requirements.txt).
3. Export `GOOGLE_MAPS_API_KEY`.
4. Start the server:

```bash
python -m mcp_server.server
```

## Environment variables
- `GOOGLE_MAPS_API_KEY`: required
- `GOOGLE_GEOCODING_BASE_URL`: optional override for tests or mocks

## Notes
- The Flask app uses the same location service layer, so Google-specific logic stays outside the main app flow.
- This structure is ready for additional MCP tools in future APIs.
