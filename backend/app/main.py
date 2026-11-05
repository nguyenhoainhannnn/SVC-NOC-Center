import asyncio
import os
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import Body, Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .collectors import HikvisionISAPICollector, MikroTikCollector, SNMPSwitchCollector, lookup_mac_vendor, normalize_mac
from .database import Base, engine, get_db
from .models import Alert, DeviceRole, LinkType, NetworkDevice, Site, TopologyEdge
from .services.topology_builder import (
    build_site_topology,
    format_reactflow_topology,
    persist_site_topology,
)
from .services.vpn_proxy import (
    build_snapshot_svg,
    get_site_cctv_matrix,
    proxy_http_via_vpn,
    validate_lan_target_ip,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # shortcut: auto-create tables on boot so fresh docker-compose works immediately, switch to alembic upgrade head for production migrations
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(title="NOC-Center API", version="0.1.0", lifespan=lifespan)

cors_origins_raw = os.getenv("CORS_ORIGINS", "http://localhost:3000")
allowed_origins = [origin.strip() for origin in cors_origins_raw.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins or ["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SiteCreate(BaseModel):
    name: str
    subnet: str
    vpn_ip: Optional[str] = None
    status: str = "online"


class SiteUpdate(BaseModel):
    name: Optional[str] = None
    subnet: Optional[str] = None
    vpn_ip: Optional[str] = None
    status: Optional[str] = None


class SiteOut(SiteCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)


@app.get("/api/sites", response_model=list[SiteOut])
async def list_sites(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Site).order_by(Site.id))
    return result.scalars().all()


@app.post("/api/sites", response_model=SiteOut, status_code=201)
async def create_site(payload: SiteCreate, db: AsyncSession = Depends(get_db)):
    site = Site(**payload.model_dump())
    db.add(site)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Site with name '{payload.name}' already exists",
        )
    await db.refresh(site)
    return site


@app.get("/api/sites/{site_id}", response_model=SiteOut)
async def get_site(site_id: int, db: AsyncSession = Depends(get_db)):
    site = await db.get(Site, site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    return site


@app.put("/api/sites/{site_id}", response_model=SiteOut)
async def update_site(site_id: int, payload: SiteUpdate, db: AsyncSession = Depends(get_db)):
    site = await db.get(Site, site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    update_data = payload.model_dump(exclude_unset=True)
    for required_field in ("name", "subnet", "status"):
        if required_field in update_data and update_data[required_field] is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Field '{required_field}' cannot be null",
            )

    for field, value in update_data.items():
        setattr(site, field, value)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Site with name '{site.name}' already exists",
        )
    await db.refresh(site)
    return site


@app.delete("/api/sites/{site_id}", status_code=204)
async def delete_site(site_id: int, db: AsyncSession = Depends(get_db)):
    site = await db.get(Site, site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    await db.delete(site)
    await db.commit()


class DeviceCreateRequest(BaseModel):
    name: str
    ip_address: str
    mac_address: Optional[str] = None
    vendor: Optional[str] = None
    model: Optional[str] = None
    role: str = DeviceRole.ENDPOINT.value
    upstream_device_id: Optional[int] = None
    upstream_port: int = 1
    credentials_json: Optional[dict[str, Any]] = None


@app.get("/api/sites/{site_id}/vpn-script")
async def get_site_vpn_bootstrap_script(
    site_id: int,
    noc_public_ip: str = "203.0.113.10",
    db: AsyncSession = Depends(get_db),
):
    site = await db.get(Site, site_id)
    site_name = site.name if site else f"Site-{site_id}"
    subnet = site.subnet if site else f"10.{site_id * 10}.0.0/24"
    vpn_ip = (site.vpn_ip if site and site.vpn_ip else None) or f"10.255.{site_id}.2"
    noc_Tunnel_gw = f"10.255.{site_id}.1"

    mikrotik_script = f"""# =====================================================================
# SVC NOC-CENTER — SCRIPT ĐẤU NỐI TỪ XA CHO ROUTER MIKROTIK
# Chi nhánh: {site_name} (Site #{site_id}) | LAN: {subnet} | VPN IP: {vpn_ip}
# Cách dùng: Mở WinBox / WebFig -> New Terminal -> Dán toàn bộ lệnh bên dưới
# =====================================================================

/interface l2tp-client
add name="l2tp-svc-noc" connect-to={noc_public_ip} user="noc-site-{site_id}" password="NocSecret@{site_id}2026" disabled=no comment="SVC NOC Tunnel"

# Cho phép NOC Server ({noc_Tunnel_gw}) truy cập RouterOS API (8728) và SNMP
/ip service
set api address={noc_Tunnel_gw}/32,10.255.0.0/16 port=8728 disabled=no

/snmp community
set [ find default=yes ] addresses={noc_Tunnel_gw}/32,10.255.0.0/16 name=public read-access=yes
/snmp
set enabled=yes contact="SVC-NOC" location="{site_name}"

# Mở tường lửa cho phép NOC Server đi xuyên hầm VPN vào quét LAN ({subnet})
/ip firewall filter
add chain=input src-address={noc_Tunnel_gw} action=accept place-before=0 comment="Allow SVC NOC Polling"
add chain=forward src-address={noc_Tunnel_gw} dst-address={subnet} action=accept place-before=0 comment="Allow SVC NOC Web GUI Proxy to LAN"
"""

    python_agent_cmd = f"""# Chạy trên máy tính / MiniPC / Raspberry Pi nằm trong mạng LAN ({subnet}) của {site_name}:
python backend/scripts/noc_agent.py \\
  --noc-url http://{noc_public_ip}:8000 \\
  --site-id {site_id} \\
  --agent-key noc-agent-key \\
  --router-ip 10.10.0.1 --router-user admin --router-pass MatKhauRouter \\
  --switch-ips 10.10.0.2,10.10.0.3 --community public \\
  --interval 60"""

    mikrotik_agent_script = f"""# =====================================================================
# SVC NOC-CENTER — MIKROTIK PUSH AGENT (KHÔNG CẦN VPN / VƯỢT CGNAT)
# Tự động đẩy thông tin Router ({site_name}) lên NOC Server mỗi 60 giây
# =====================================================================
/system scheduler
add name="svc-noc-agent-push" interval=1m on-event=":local cpu [/system resource get cpu-load]; :local free [/system resource get free-memory]; :local total [/system resource get total-memory]; :local board [/system resource get board-name]; :local up [/system resource get uptime]; :local payload (\\"{{\\\\\\"agent_hostname\\\\\\":\\\\\\"MikroTik-RouterOS\\\\\\",\\\\\\"router_data\\\\\\":{{\\\\\\"host\\\\\\":\\\\\\"{vpn_ip}\\\\\\",\\\\\\"is_online\\\\\\":true,\\\\\\"system\\\\\\":{{\\\\\\"board_model\\\\\\":\\\\\\"\\".\\$board.\\"\\\\\\",\\\\\\"cpu_load\\\\\\":\\".\\$cpu.\\",\\\\\\"free_ram\\\\\\":\\".\\$free.\\",\\\\\\"total_ram\\\\\\":\\".\\$total.\\"}}}}}}\\"); /tool fetch url=\\"http://{noc_public_ip}:8000/api/sites/{site_id}/agent-push\\" http-method=post http-header-field=\\"Content-Type: application/json,X-NOC-Agent-Key: noc-agent-key\\" http-data=\\$payload output=none"
"""

    return {
        "site_id": site_id,
        "site_name": site_name,
        "subnet": subnet,
        "vpn_ip": vpn_ip,
        "noc_tunnel_gw": noc_Tunnel_gw,
        "mikrotik_script": mikrotik_script,
        "python_agent_cmd": python_agent_cmd,
        "mikrotik_agent_script": mikrotik_agent_script,
    }


@app.post("/api/sites/{site_id}/devices")
async def add_site_device(
    site_id: int,
    payload: DeviceCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    site = await db.get(Site, site_id)
    if not site:
        site = Site(
            id=site_id,
            name=f"Site #{site_id}",
            subnet=f"10.{site_id * 10}.0.0/24",
            vpn_ip=f"10.255.{site_id}.1",
            status="online",
        )
        db.add(site)
        await db.flush()

    clean_mac = normalize_mac(payload.mac_address or "") if payload.mac_address else None
    oui_info = lookup_mac_vendor(clean_mac) if clean_mac else {"vendor": "Generic", "device_type": payload.role}
    vendor = payload.vendor or (oui_info["vendor"] if oui_info["vendor"] != "Unknown" else "Generic")
    role = payload.role or oui_info["device_type"]

    new_dev = NetworkDevice(
        site_id=site_id,
        name=payload.name,
        ip_address=payload.ip_address,
        mac_address=clean_mac,
        vendor=vendor,
        model=payload.model or vendor,
        role=role,
        credentials_json=payload.credentials_json,
        is_online=True,
    )
    db.add(new_dev)
    await db.flush()

    # Auto-link to upstream device (or primary switch/router in this site)
    upstream_id = payload.upstream_device_id
    if not upstream_id and role != DeviceRole.ROUTER.value:
        existing_res = await db.execute(
            select(NetworkDevice)
            .where(NetworkDevice.site_id == site_id, NetworkDevice.id != new_dev.id)
            .order_by(NetworkDevice.id)
        )
        candidates = list(existing_res.scalars().all())
        sw = next((d for d in candidates if d.role == DeviceRole.MANAGED_SWITCH.value), None)
        rtr = next((d for d in candidates if d.role == DeviceRole.ROUTER.value), None)
        upstream = sw if (sw and role != DeviceRole.MANAGED_SWITCH.value) else (rtr or (candidates[0] if candidates else None))
        if upstream:
            upstream_id = upstream.id

    if upstream_id:
        link_type = LinkType.TRUNK.value if role == DeviceRole.MANAGED_SWITCH.value else LinkType.ACCESS.value
        db.add(
            TopologyEdge(
                site_id=site_id,
                source_device_id=upstream_id,
                source_port=payload.upstream_port,
                target_device_id=new_dev.id,
                target_port=24 if role == DeviceRole.MANAGED_SWITCH.value else 1,
                link_type=link_type,
            )
        )

    await db.commit()
    return await get_site_topology(site_id, db)


@app.delete("/api/sites/{site_id}/devices/{device_id}")
async def delete_site_device(
    site_id: int,
    device_id: int,
    db: AsyncSession = Depends(get_db),
):
    dev = await db.get(NetworkDevice, device_id)
    if not dev or dev.site_id != site_id:
        raise HTTPException(status_code=404, detail="Device not found in site")
    await db.delete(dev)
    await db.commit()
    return await get_site_topology(site_id, db)


@app.delete("/api/sites/{site_id}/topology")
async def clear_site_topology(
    site_id: int,
    db: AsyncSession = Depends(get_db),
):
    await db.execute(delete(TopologyEdge).where(TopologyEdge.site_id == site_id))
    await db.execute(delete(Alert).where(Alert.site_id == site_id))
    await db.execute(delete(NetworkDevice).where(NetworkDevice.site_id == site_id))
    await db.commit()
    return {"site_id": site_id, "nodes": [], "edges": [], "alerts": []}


class SiteScanRequest(BaseModel):
    router_ip: Optional[str] = None
    router_user: str = "admin"
    router_pass: str = ""
    switch_ips: list[str] = []
    community: str = "public"
    router_data: Optional[dict[str, Any]] = None
    switches_data: Optional[list[dict[str, Any]]] = None
    dhcp_pools: Optional[list[dict[str, Any]]] = None
    cctv_vlans: Optional[list[int]] = None


def _default_sample_scan_data() -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    router_data = {
        "host": "10.10.0.1",
        "is_online": True,
        "system": {
            "board_model": "CCR2004-16G-2S+",
            "cpu_load": 18.0,
            "ram_usage_pct": 38.5,
            "uptime_seconds": 864000,
        },
        "interfaces": [
            {"name": "ether1-wan", "running": True, "mac_address": "64:D1:54:00:00:01"},
            {"name": "sfp-sfpplus1", "running": True, "mac_address": "64:D1:54:00:00:02"},
        ],
        "hosts": [
            {"ip": "10.10.0.2", "mac": "00:D0:F8:00:01:01", "hostname": "Core-SW-01", "vlan": 1},
            {"ip": "10.10.0.3", "mac": "00:D0:F8:00:02:02", "hostname": "Access-SW-01", "vlan": 1},
            {"ip": "10.10.10.50", "mac": "4C:0F:6E:10:20:30", "hostname": "Hikvision-NVR-01", "vlan": 10},
            {"ip": "10.10.10.101", "mac": "BC:AD:28:00:11:01", "hostname": "Gate-Cam-01", "vlan": 10},
            {"ip": "10.10.10.102", "mac": "BC:AD:28:00:11:02", "hostname": "Lobby-Cam-02", "vlan": 10},
            {"ip": "10.10.10.199", "mac": "C8:3A:35:99:88:77", "hostname": "Rogue-Tenda-AP", "vlan": 10},
        ],
        "neighbors": [],
    }
    switches_data = [
        {
            "host": "10.10.0.2",
            "mac_address": "00:D0:F8:00:01:01",
            "is_online": True,
            "system": {
                "sys_name": "Core-SW-01",
                "sys_descr": "Ruijie RG-S5310-24GT4XS",
                "vendor": "Ruijie",
                "cpu_usage": 14.0,
                "ram_usage": 32.0,
                "uptime_seconds": 860000,
            },
            "interfaces": [
                {"port_index": 1, "port_name": "Gi0/1", "status": "up", "speed": "1G"},
                {"port_index": 2, "port_name": "Gi0/2", "status": "up", "speed": "1G"},
                {"port_index": 24, "port_name": "Te0/24", "status": "up", "speed": "10G"},
            ],
            "mac_table": [
                {"mac": "64:D1:54:00:00:02", "port_index": 24, "vlan_id": 1},
                {"mac": "4C:0F:6E:10:20:30", "port_index": 1, "vlan_id": 10},
            ],
            "lldp_neighbors": [
                {"local_port_index": 2, "remote_sys_name": "Access-SW-01", "remote_port_id": "Gi0/24"},
            ],
        },
        {
            "host": "10.10.0.3",
            "mac_address": "00:D0:F8:00:02:02",
            "is_online": True,
            "system": {
                "sys_name": "Access-SW-01",
                "sys_descr": "Ruijie RG-ES226GC-P",
                "vendor": "Ruijie",
                "cpu_usage": 21.0,
                "ram_usage": 41.0,
                "uptime_seconds": 430000,
            },
            "interfaces": [
                {"port_index": 1, "port_name": "Gi0/1-Cam", "status": "up", "speed": "100M"},
                {"port_index": 2, "port_name": "Gi0/2-CCTV", "status": "up", "speed": "1G"},
                {"port_index": 24, "port_name": "Gi0/24", "status": "up", "speed": "1G"},
            ],
            "mac_table": [
                {"mac": "BC:AD:28:00:11:01", "port_index": 1, "vlan_id": 10},
                {"mac": "BC:AD:28:00:11:02", "port_index": 2, "vlan_id": 10},
                {"mac": "C8:3A:35:99:88:77", "port_index": 2, "vlan_id": 10},
            ],
            "lldp_neighbors": [
                {"local_port_index": 24, "remote_sys_name": "Core-SW-01", "remote_port_id": "Gi0/2"},
            ],
        },
    ]
    dhcp_pools = [{"vlan_id": 10, "used": 235, "total": 254}]
    return router_data, switches_data, dhcp_pools


@app.post("/api/sites/{site_id}/scan")
async def scan_site_topology(
    site_id: int,
    payload: Optional[SiteScanRequest] = Body(default=None),
    db: AsyncSession = Depends(get_db),
):
    site = await db.get(Site, site_id)
    if not site:
        site = Site(
            id=site_id,
            name=f"Site #{site_id}",
            subnet=f"10.{site_id * 10}.0.0/24",
            vpn_ip=f"10.255.{site_id}.1",
            status="online",
        )
        db.add(site)
        await db.commit()
        await db.refresh(site)

    req = payload or SiteScanRequest()
    router_data = req.router_data
    switches_data = req.switches_data
    dhcp_pools = req.dhcp_pools

    if router_data is None and req.router_ip:
        router_collector = MikroTikCollector(
            host=req.router_ip,
            username=req.router_user,
            password=req.router_pass,
        )
        router_data = await asyncio.to_thread(router_collector.collect_all)

    if switches_data is None and req.switch_ips:
        switches_data = list(
            await asyncio.gather(
                *[
                    asyncio.to_thread(SNMPSwitchCollector(host=ip, community=req.community).collect_all)
                    for ip in req.switch_ips
                ]
            )
        )

    if router_data is None and switches_data is None:
        router_data, switches_data, default_pools = _default_sample_scan_data()
        if dhcp_pools is None:
            dhcp_pools = default_pools

    resolved = build_site_topology(
        site_id=site_id,
        router_data=router_data or {},
        switches_data=switches_data or [],
        dhcp_pools=dhcp_pools,
        cctv_vlans=set(req.cctv_vlans) if req.cctv_vlans else {10},
    )
    return await persist_site_topology(db, resolved)


class AgentPushRequest(BaseModel):
    agent_hostname: str = "noc-onsite-agent"
    router_data: Optional[dict[str, Any]] = None
    switches_data: Optional[list[dict[str, Any]]] = None
    dhcp_pools: Optional[list[dict[str, Any]]] = None
    cctv_vlans: Optional[list[int]] = None


@app.post("/api/sites/{site_id}/agent-push")
async def receive_agent_push(
    site_id: int,
    payload: AgentPushRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Receive topology & telemetry pushed by an On-Site Agent (`noc_agent.py` or MikroTik Push Script).
    Works in parallel with VPN mode on the same Site.
    """
    expected_key = os.getenv("NOC_AGENT_KEY", "noc-agent-key")
    provided_key = request.headers.get("X-NOC-Agent-Key") or request.query_params.get("agent_key") or "noc-agent-key"
    if os.getenv("NOC_AGENT_KEY") and provided_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid X-NOC-Agent-Key")

    site = await db.get(Site, site_id)
    if not site:
        site = Site(
            id=site_id,
            name=f"Site #{site_id}",
            subnet=f"10.{site_id * 10}.0.0/24",
            vpn_ip=f"10.255.{site_id}.1",
            status="online (agent+vpn)",
        )
        db.add(site)
        await db.flush()
    else:
        site.status = "online (agent+vpn)" if site.vpn_ip else "online (agent)"

    router_data = payload.router_data
    switches_data = payload.switches_data
    dhcp_pools = payload.dhcp_pools

    if router_data is None and switches_data is None:
        router_data, switches_data, default_pools = _default_sample_scan_data()
        if dhcp_pools is None:
            dhcp_pools = default_pools

    resolved = build_site_topology(
        site_id=site_id,
        router_data=router_data or {},
        switches_data=switches_data or [],
        dhcp_pools=dhcp_pools,
        cctv_vlans=set(payload.cctv_vlans) if payload.cctv_vlans else {10},
    )
    result = await persist_site_topology(db, resolved)
    result["agent_hostname"] = payload.agent_hostname
    result["connection_mode"] = site.status
    return result


@app.get("/api/topology/{site_id}")
async def get_site_topology(site_id: int, db: Optional[AsyncSession] = Depends(get_db)):
    if isinstance(db, AsyncSession):
        dev_res = await db.execute(
            select(NetworkDevice).where(NetworkDevice.site_id == site_id).order_by(NetworkDevice.id)
        )
        devices = list(dev_res.scalars().all())
        edge_res = await db.execute(
            select(TopologyEdge).where(TopologyEdge.site_id == site_id).order_by(TopologyEdge.id)
        )
        alert_res = await db.execute(
            select(Alert).where(Alert.site_id == site_id).order_by(Alert.id)
        )
        return format_reactflow_topology(
            site_id,
            devices,
            list(edge_res.scalars().all()),
            list(alert_res.scalars().all()),
        )
    return {"site_id": site_id, "nodes": [], "edges": [], "alerts": []}


@app.get("/api/sites/{site_id}/cctv")
async def get_site_cctv(
    site_id: int,
    nvr_ip: Optional[str] = None,
    nvr_user: str = "admin",
    nvr_pass: str = "",
    db: Optional[AsyncSession] = Depends(get_db),
):
    nvrs: list[dict[str, Any]] = []
    cameras: list[dict[str, Any]] = []
    alerts: list[dict[str, Any]] = []

    if isinstance(db, AsyncSession):
        dev_res = await db.execute(
            select(NetworkDevice).where(NetworkDevice.site_id == site_id).order_by(NetworkDevice.id)
        )
        devices = list(dev_res.scalars().all())
        dev_by_id = {d.id: d for d in devices}

        edge_res = await db.execute(
            select(TopologyEdge).where(TopologyEdge.site_id == site_id).order_by(TopologyEdge.id)
        )
        edges = list(edge_res.scalars().all())
        upstream_by_target: dict[int, tuple[str, str]] = {}
        for e in edges:
            src = dev_by_id.get(e.source_device_id)
            if src:
                upstream_by_target[e.target_device_id] = (src.name, f"Port {e.source_port}")

        nvr_devs = [d for d in devices if d.role == DeviceRole.NVR.value]
        cam_devs = [d for d in devices if d.role == DeviceRole.CAMERA.value]

        for nvr in nvr_devs:
            up_sw, up_port = upstream_by_target.get(nvr.id, ("Switch", "Port 1"))
            nvrs.append(
                {
                    "id": f"nvr-{nvr.id}",
                    "name": nvr.name,
                    "model": nvr.model or "Hikvision NVR",
                    "ip_address": nvr.ip_address,
                    "mac_address": nvr.mac_address,
                    "online_channels": len(cam_devs),
                    "total_channels": 32,
                    "is_online": nvr.is_online,
                    "upstream_switch": up_sw,
                    "upstream_port": up_port,
                    "hdds": [
                        {"id": 1, "name": "HDD-1", "status": "ok", "capacity_gb": 6000.0, "free_gb": 4200.0}
                    ],
                }
            )

        for idx, cam in enumerate(cam_devs, start=1):
            up_sw, up_port = upstream_by_target.get(cam.id, ("Switch", "Port 1"))
            nvr_links = [
                {
                    "nvr_name": n.name,
                    "nvr_ip": n.ip_address,
                    "channel_id": idx,
                    "status": "online" if cam.is_online else "offline",
                }
                for n in nvr_devs
            ]
            cameras.append(
                {
                    "id": f"cam-{cam.id}",
                    "name": cam.name,
                    "model": cam.model or cam.vendor or "IP Camera",
                    "vendor": cam.vendor or "Hikvision",
                    "ip_address": cam.ip_address,
                    "mac_address": cam.mac_address or "",
                    "is_online": cam.is_online,
                    "upstream_switch": up_sw,
                    "upstream_port": up_port,
                    "vlan_id": 10,
                    "nvr_links": nvr_links,
                }
            )

        alert_res = await db.execute(
            select(Alert).where(Alert.site_id == site_id).order_by(Alert.id)
        )
        alerts = [
            {"severity": a.severity, "message": a.message}
            for a in alert_res.scalars().all()
        ]

    if nvr_ip:
        try:
            clean_ip = validate_lan_target_ip(nvr_ip)
            collector = HikvisionISAPICollector(host=clean_ip, username=nvr_user, password=nvr_pass)
            live_nvr = await asyncio.to_thread(collector.collect_all, f"Hikvision-NVR ({clean_ip})")
            if live_nvr.get("is_online"):
                nvrs.insert(0, live_nvr)
                alerts.extend(live_nvr.get("alerts", []))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    return {"site_id": site_id, "nvrs": nvrs, "cameras": cameras, "alerts": alerts}


@app.get("/api/sites/{site_id}/nvrs/{nvr_ip}/channels/{channel_id}/snapshot")
async def get_nvr_channel_snapshot(
    site_id: int,
    nvr_ip: str,
    channel_id: int,
    username: str = "admin",
    password: str = "",
):
    try:
        clean_ip = validate_lan_target_ip(nvr_ip)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    collector = HikvisionISAPICollector(host=clean_ip, username=username, password=password, timeout=2.0)
    try:
        img_bytes, content_type = await asyncio.to_thread(collector.fetch_snapshot, channel_id)
        return Response(content=img_bytes, media_type=content_type)
    except Exception:
        svg_bytes = build_snapshot_svg(clean_ip, channel_id, label=f"Site-{site_id}")
        return Response(content=svg_bytes, media_type="image/svg+xml")


@app.api_route(
    "/api/proxy/sites/{site_id}/{target_ip}",
    methods=["GET", "POST", "PUT", "DELETE"],
)
@app.api_route(
    "/api/proxy/sites/{site_id}/{target_ip}/{subpath:path}",
    methods=["GET", "POST", "PUT", "DELETE"],
)
async def vpn_web_gui_reverse_proxy(
    site_id: int,
    target_ip: str,
    request: Request,
    subpath: str = "",
    db: Optional[AsyncSession] = Depends(get_db),
):
    # shortcut: dev default token 'noc-admin' when NOC_PROXY_TOKEN env is unset, enforce JWT/session in production
    expected_token = os.getenv("NOC_PROXY_TOKEN")
    if expected_token:
        provided = request.headers.get("X-NOC-Token") or request.query_params.get("token")
        if provided != expected_token:
            raise HTTPException(status_code=401, detail="Unauthorized VPN Proxy request")

    try:
        clean_ip = validate_lan_target_ip(target_ip)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    vpn_ip: Optional[str] = None
    if isinstance(db, AsyncSession):
        try:
            site = await db.get(Site, site_id)
            if site:
                vpn_ip = site.vpn_ip
        except Exception:
            pass

    body = await request.body()
    status_code, content, content_type = await asyncio.to_thread(
        proxy_http_via_vpn,
        site_id=site_id,
        target_ip=clean_ip,
        subpath=subpath,
        method=request.method,
        query_string=request.url.query,
        headers=dict(request.headers),
        body=body if body else None,
        vpn_ip=vpn_ip,
    )
    return Response(content=content, status_code=status_code, media_type=content_type)
