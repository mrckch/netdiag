from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.collectors.link import get_link_info
from app.collectors.lldp import get_lldp_neighbors
from app.collectors.sniff import sniff_port
from app.collectors.dhcp import discover_dhcp
from app.collectors.reach import ping_test, scan_subnet

app = FastAPI(title="netdiag", description="Lokaler Netzwerk-Port-Tester")

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/autotest")
def autotest(interface: str = Query("eth0"), sniff_seconds: int = Query(6, ge=2, le=30)):
    """Führt den kompletten Test-Zyklus auf einem Interface aus,
    analog zum 'Autotest' der Hardware-Tester."""
    link = get_link_info(interface)
    lldp = get_lldp_neighbors(interface)
    sniff = sniff_port(interface, duration=sniff_seconds)
    dhcp = discover_dhcp(interface)

    ping_gateway = None
    if dhcp.get("router"):
        ping_gateway = ping_test(dhcp["router"], count=3)

    return {
        "interface": interface,
        "link": link,
        "lldp": lldp,
        "sniff": sniff,
        "dhcp": dhcp,
        "ping_gateway": ping_gateway,
    }


@app.get("/api/link")
def api_link(interface: str = Query("eth0")):
    return get_link_info(interface)


@app.get("/api/lldp")
def api_lldp(interface: str = Query("eth0")):
    return get_lldp_neighbors(interface)


@app.get("/api/sniff")
def api_sniff(interface: str = Query("eth0"), duration: int = Query(8, ge=2, le=60)):
    return sniff_port(interface, duration=duration)


@app.get("/api/dhcp")
def api_dhcp(interface: str = Query("eth0")):
    return discover_dhcp(interface)


@app.get("/api/ping")
def api_ping(target: str = Query(...), count: int = Query(4, ge=1, le=20)):
    return ping_test(target, count=count)


@app.get("/api/scan")
def api_scan(subnet: str = Query(...)):
    return scan_subnet(subnet)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8642)
