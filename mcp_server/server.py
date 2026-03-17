from mcp.server.fastmcp import FastMCP

from .location_service import GoogleLocationService

mcp = FastMCP("surfspot-google")
location_service = GoogleLocationService.from_env()


@mcp.tool()
def geocode_address(query: str):
    """Resolve a human-readable location into coordinates."""
    return location_service.geocode_address(query)


@mcp.tool()
def reverse_geocode(lat: float, lon: float):
    """Resolve coordinates into a human-readable location."""
    return location_service.reverse_geocode(lat, lon)


if __name__ == "__main__":
    mcp.run()
