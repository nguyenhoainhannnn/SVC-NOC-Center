import asyncio
import os
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import Body, Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .collectors import HikvisionISAPICollector, MikroTikCollector, SNMPSwitchCollector, lookup_mac_vendor, normalize_mac
from .collectors.snmp_collector import probe_http_device
from .database import Base, engine, get_db
from .models import Alert, DevicePort, DeviceRole, LinkType, NetworkDevice, Site, TopologyEdge
from .services.topology_builder import (
    build_site_topology,
    format_reactflow_topology,
    persist_site_topology,
)
from .services.vpn_proxy import (
    build_snapshot_svg,
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
    local_port: Optional[int] = None
    vlan_id: Optional[int] = None
    total_ports: Optional[int] = None
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
    try:
        clean_ip = validate_lan_target_ip(payload.ip_address)
    except ValueError as exc:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"notification": False, "success": False, "detail": str(exc)},
        )

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
    creds = payload.credentials_json or {}

    cpu_usage = 0.0
    ram_usage = 0.0
    uptime = 0
    detected_model = payload.model or vendor
    discovered_ports: list[dict[str, Any]] = []
    device_reachable = False

    # Strictly verify live reachability before creating any device (never fabricate virtual devices)
    if role in (DeviceRole.MANAGED_SWITCH.value, DeviceRole.ROUTER.value, DeviceRole.AP.value):
        comm = str(creds.get("community") or "public")
        snmp_p = int(creds.get("snmp_port") or 161)
        snmp_info = await asyncio.to_thread(
            SNMPSwitchCollector(host=clean_ip, community=comm, port=snmp_p, timeout=2.0).collect_all
        )
        if snmp_info.get("is_online"):
            device_reachable = True
            sys_meta = snmp_info.get("system") or {}
            cpu_usage = float(sys_meta.get("cpu_usage") or 0.0)
            ram_usage = float(sys_meta.get("ram_usage") or 0.0)
            uptime = int(sys_meta.get("uptime_seconds") or 0)
            detected_model = payload.model or sys_meta.get("sys_descr") or vendor
            discovered_ports = snmp_info.get("interfaces") or []
        else:
            http_p = int(creds.get("port") or 0)
            custom_http_p = http_p if http_p and http_p != 161 else None
            http_info = await asyncio.to_thread(
                probe_http_device,
                clean_ip,
                2.0,
                custom_http_p,
                str(creds.get("username") or "admin"),
                str(creds.get("password") or ""),
            )
            if http_info.get("is_online"):
                device_reachable = True
                sys_meta = http_info.get("system") or {}
                cpu_usage = float(sys_meta.get("cpu_usage") or 0.0)
                ram_usage = float(sys_meta.get("ram_usage") or 0.0)
                uptime = int(sys_meta.get("uptime_seconds") or 0)
                detected_model = payload.model or sys_meta.get("sys_descr") or vendor
                discovered_ports = http_info.get("interfaces") or []

        if not device_reachable:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "notification": False,
                    "success": False,
                    "detail": (
                        f"Không thể kết nối tới {payload.name} ({clean_ip}): "
                        f"Thiết bị không phản hồi SNMP (UDP {snmp_p}) hoặc HTTP/HTTPS. "
                        "Hệ thống từ chối tạo Switch/Thiết bị ảo."
                    ),
                },
            )
    else:
        # Probe NVR / Camera / Endpoint via ISAPI, HTTP/HTTPS, or TCP port (554/80/8000/443)
        srv_port = int(creds.get("port") or (80 if role == DeviceRole.NVR.value else 554))
        if role == DeviceRole.NVR.value:
            nvr_col = HikvisionISAPICollector(
                host=clean_ip,
                username=str(creds.get("username") or "admin"),
                password=str(creds.get("password") or ""),
                port=srv_port,
                timeout=2.0,
            )
            nvr_live = await asyncio.to_thread(nvr_col.collect_all, payload.name)
            if nvr_live.get("is_online"):
                device_reachable = True
                detected_model = payload.model or f"{vendor} NVR ({nvr_live.get('total_channels', 0)} CH)"

        if not device_reachable:
            def _probe_tcp_ports(target_host: str, primary_port: int) -> bool:
                import socket as _sock
                for p_try in dict.fromkeys([primary_port, 80, 443, 554, 8000, 8080]):
                    if p_try <= 0:
                        continue
                    try:
                        with _sock.create_connection((target_host, p_try), timeout=1.5):
                            return True
                    except OSError:
                        continue
                return False

            device_reachable = await asyncio.to_thread(_probe_tcp_ports, clean_ip, srv_port)

        if not device_reachable:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "notification": False,
                    "success": False,
                    "detail": (
                        f"Không thể kết nối tới {payload.name} ({clean_ip}:{srv_port}): "
                        "Thiết bị không phản hồi trên mạng. Hệ thống từ chối tạo thiết bị ảo."
                    ),
                },
            )

    new_dev = NetworkDevice(
        site_id=site_id,
        name=payload.name,
        ip_address=clean_ip,
        mac_address=clean_mac,
        vendor=vendor,
        model=detected_model,
        role=role,
        cpu_usage=cpu_usage,
        ram_usage=ram_usage,
        uptime=uptime,
        credentials_json=payload.credentials_json,
        is_online=True,
    )
    db.add(new_dev)
    await db.flush()

    # Auto-link to upstream device (or primary switch/router in this site)
    upstream_id = payload.upstream_device_id
    upstream_dev: Optional[NetworkDevice] = None
    if upstream_id:
        upstream_dev = await db.get(NetworkDevice, upstream_id)
        if not upstream_dev or upstream_dev.site_id != site_id:
            await db.rollback()
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"notification": False, "success": False, "detail": "Thiết bị cấp trên (upstream) không tồn tại trong Site."},
            )
    elif role != DeviceRole.ROUTER.value:
        existing_res = await db.execute(
            select(NetworkDevice)
            .where(NetworkDevice.site_id == site_id, NetworkDevice.id != new_dev.id)
            .order_by(NetworkDevice.id)
        )
        candidates = list(existing_res.scalars().all())
        sw = next((d for d in candidates if d.role == DeviceRole.MANAGED_SWITCH.value), None)
        rtr = next((d for d in candidates if d.role == DeviceRole.ROUTER.value), None)
        upstream_dev = sw if (sw and role != DeviceRole.MANAGED_SWITCH.value) else (rtr or (candidates[0] if candidates else None))
        if upstream_dev:
            upstream_id = upstream_dev.id

    target_port = payload.local_port or (24 if role == DeviceRole.MANAGED_SWITCH.value else 1)

    if role in (DeviceRole.MANAGED_SWITCH.value, DeviceRole.ROUTER.value) and discovered_ports:
        for p in discovered_ports:
            p_idx = int(p.get("port_index") or 1)
            is_up = p_idx == target_port or p.get("status") == "up"
            db.add(
                DevicePort(
                    device_id=new_dev.id,
                    port_index=p_idx,
                    port_name=p.get("port_name") or f"Gi0/{p_idx}",
                    status="up" if is_up else "down",
                    speed=p.get("speed") or "1G",
                    vlan_id=payload.vlan_id if p_idx == target_port else None,
                    is_uplink=(p_idx == target_port and upstream_id is not None),
                )
            )

    if upstream_id:
        link_type = LinkType.TRUNK.value if role == DeviceRole.MANAGED_SWITCH.value else LinkType.ACCESS.value
        # If upstream is a Router that names LAN ports LAN-P1..LAN-P5, map LAN port N to its actual port_index
        resolved_upstream_port = payload.upstream_port
        up_port_obj: Optional[DevicePort] = None
        if upstream_dev and upstream_dev.role == DeviceRole.ROUTER.value:
            lan_port_res = await db.execute(
                select(DevicePort).where(
                    DevicePort.device_id == upstream_id,
                    DevicePort.port_name == f"LAN-P{payload.upstream_port}",
                )
            )
            up_port_obj = lan_port_res.scalars().first()
            if up_port_obj:
                resolved_upstream_port = up_port_obj.port_index

        if not up_port_obj:
            up_port_res = await db.execute(
                select(DevicePort).where(
                    DevicePort.device_id == upstream_id,
                    DevicePort.port_index == resolved_upstream_port,
                )
            )
            up_port_obj = up_port_res.scalars().first()

        db.add(
            TopologyEdge(
                site_id=site_id,
                source_device_id=upstream_id,
                source_port=resolved_upstream_port,
                target_device_id=new_dev.id,
                target_port=target_port,
                link_type=link_type,
            )
        )
        if up_port_obj:
            up_port_obj.status = "up"
            if payload.vlan_id:
                up_port_obj.vlan_id = payload.vlan_id
        else:
            db.add(
                DevicePort(
                    device_id=upstream_id,
                    port_index=resolved_upstream_port,
                    port_name=f"Port-{resolved_upstream_port}",
                    status="up",
                    speed="1G",
                    vlan_id=payload.vlan_id,
                    is_uplink=(role == DeviceRole.MANAGED_SWITCH.value),
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
    return {"site_id": site_id, "notification": True, "success": True, "nodes": [], "edges": [], "alerts": []}


class SiteScanRequest(BaseModel):
    scan_mode: str = "auto"  # "wan" | "vpn" | "snmp" | "auto"
    router_ip: Optional[str] = None
    router_user: str = "admin"
    router_pass: str = ""
    switch_ips: list[str] = []
    community: str = "public"
    port: Optional[int] = None
    router_data: Optional[dict[str, Any]] = None
    switches_data: Optional[list[dict[str, Any]]] = None
    dhcp_pools: Optional[list[dict[str, Any]]] = None
    cctv_vlans: Optional[list[int]] = None


@app.post("/api/sites/{site_id}/scan")
async def scan_site_topology(
    site_id: int,
    payload: Optional[SiteScanRequest] = Body(default=None),
    db: AsyncSession = Depends(get_db),
):
    req = payload or SiteScanRequest()
    mode = (req.scan_mode or "auto").lower().strip()
    allow_public_ip = mode != "vpn"
    router_ip = (req.router_ip or "").strip()
    clean_switch_ips = [ip.strip() for ip in (req.switch_ips or []) if ip and ip.strip()]

    router_data = req.router_data
    switches_data = req.switches_data
    dhcp_pools = req.dhcp_pools

    if router_data is None and switches_data is None and not router_ip and not clean_switch_ips:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "notification": False,
                "success": False,
                "detail": "Chưa nhập địa chỉ IP Router hoặc Switch để quét. Hệ thống không tự tạo sơ đồ mẫu.",
            },
        )

    scan_errors: list[str] = []
    snmp_port = req.port if (mode == "snmp" and req.port) else 161

    if router_data is None and router_ip:
        try:
            router_ip = validate_lan_target_ip(router_ip, allow_public=allow_public_ip)
        except ValueError as exc:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "notification": False,
                    "success": False,
                    "detail": f"Thông số IP Router không hợp lệ: {exc}",
                },
            )

        if mode == "snmp":
            router_data = await asyncio.to_thread(
                SNMPSwitchCollector(host=router_ip, community=req.community, port=snmp_port, timeout=2.5).collect_all
            )
            if not router_data.get("is_online"):
                err_msg = router_data.get("error") or f"Không phản hồi SNMP (UDP {snmp_port})"
                scan_errors.append(f"Router {router_ip}: {err_msg}")
        else:
            # 1) Try RouterOS API (TCP 8728 or custom port)
            api_port = req.port if (req.port and req.port not in (80, 443, 8080, 8443, 161)) else 8728
            router_collector = MikroTikCollector(
                host=router_ip,
                username=req.router_user,
                password=req.router_pass,
                port=api_port,
                timeout=2.0,
            )
            router_data = await asyncio.to_thread(router_collector.collect_all)

            # 2) Fallback to SNMPv2c (UDP 161) for DrayTek / FortiGate / Cisco / MikroTik SNMP
            if not router_data.get("is_online"):
                snmp_router = await asyncio.to_thread(
                    SNMPSwitchCollector(host=router_ip, community=req.community, port=snmp_port, timeout=2.0).collect_all
                )
                if snmp_router.get("is_online"):
                    router_data = snmp_router

            # 3) Fallback to HTTP/HTTPS Management probe (ports 443/80/8443/8080) for WAN/LAN routers (e.g. DrayTek Vigor2927)
            if not router_data.get("is_online"):
                http_port = req.port if (req.port in (80, 443, 8080, 8443)) else None
                http_router = await asyncio.to_thread(
                    probe_http_device,
                    router_ip,
                    2.5,
                    http_port,
                    req.router_user,
                    req.router_pass,
                )
                if http_router.get("is_online"):
                    router_data = http_router

            if not router_data.get("is_online"):
                err_msg = router_data.get("error") or "Không phản hồi qua RouterOS API (8728), SNMP (161) hoặc HTTPS/HTTP (443/80)"
                scan_errors.append(f"Router {router_ip}: {err_msg}")

    valid_switch_ips: list[str] = []
    for raw_sw_ip in clean_switch_ips:
        try:
            clean_sw = validate_lan_target_ip(raw_sw_ip, allow_public=allow_public_ip)
            if router_ip and clean_sw == router_ip:
                scan_errors.append(f"Switch {clean_sw}: Trùng với IP Router ({router_ip})")
            else:
                valid_switch_ips.append(clean_sw)
        except ValueError as exc:
            scan_errors.append(str(exc))

    if switches_data is None and valid_switch_ips:
        async def _poll_switch(ip: str) -> dict[str, Any]:
            sw_res = await asyncio.to_thread(
                SNMPSwitchCollector(host=ip, community=req.community, port=snmp_port, timeout=2.0).collect_all
            )
            if not sw_res.get("is_online") and mode != "snmp":
                http_sw = await asyncio.to_thread(probe_http_device, ip, 2.0)
                if http_sw.get("is_online") and (http_sw.get("system") or {}).get("role") == "managed_switch":
                    return http_sw
            return sw_res

        switches_data = list(await asyncio.gather(*[_poll_switch(ip) for ip in valid_switch_ips]))
        for sw in switches_data:
            if not sw.get("is_online"):
                sw_host = sw.get("host") or "Switch"
                err_msg = sw.get("error") or f"Không phản hồi SNMP (UDP {snmp_port}) hoặc Web Switch"
                scan_errors.append(f"Switch {sw_host}: {err_msg}")

    # Strictly fail with notification: false if any user-entered Router/Switch IP failed to respond
    if scan_errors and req.router_data is None and req.switches_data is None:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "notification": False,
                "success": False,
                "detail": "Quét thất bại — Không kết nối được tới thiết bị: " + " | ".join(scan_errors),
                "errors": scan_errors,
            },
        )

    resolved = build_site_topology(
        site_id=site_id,
        router_data=router_data or {},
        switches_data=switches_data or [],
        dhcp_pools=dhcp_pools,
        cctv_vlans=set(req.cctv_vlans) if req.cctv_vlans else {10},
    )

    if not resolved["devices"]:
        detail_msg = (
            "Quét không có kết quả — Không kết nối được tới thiết bị: " + " | ".join(scan_errors)
            if scan_errors
            else "Quét không có kết quả: Không tìm thấy thiết bị nào phản hồi."
        )
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "notification": False,
                "success": False,
                "detail": detail_msg,
                "errors": scan_errors,
            },
        )

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

    result = await persist_site_topology(db, resolved)
    result["notification"] = True
    result["success"] = True
    return result


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

    router_data = payload.router_data
    switches_data = payload.switches_data
    dhcp_pools = payload.dhcp_pools

    if router_data is None and not switches_data:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "notification": False,
                "success": False,
                "detail": "Agent Push không có dữ liệu thiết bị thực tế (router_data và switches_data đều rỗng).",
            },
        )

    resolved = build_site_topology(
        site_id=site_id,
        router_data=router_data or {},
        switches_data=switches_data or [],
        dhcp_pools=dhcp_pools,
        cctv_vlans=set(payload.cctv_vlans) if payload.cctv_vlans else {10},
    )
    if not resolved["devices"]:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "notification": False,
                "success": False,
                "detail": "Agent Push thất bại: Không có thiết bị nào online trong gói tin gửi lên.",
            },
        )

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

    result = await persist_site_topology(db, resolved)
    result["notification"] = True
    result["success"] = True
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
        dev_ids = [d.id for d in devices]
        ports: list[DevicePort] = []
        if dev_ids:
            port_res = await db.execute(
                select(DevicePort).where(DevicePort.device_id.in_(dev_ids)).order_by(DevicePort.port_index)
            )
            ports = list(port_res.scalars().all())
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
            ports,
        )
    return {"site_id": site_id, "notification": False, "success": True, "nodes": [], "edges": [], "alerts": []}


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
            up_sw, up_port = upstream_by_target.get(nvr.id, ("Chưa xác định", "-"))
            nvrs.append(
                {
                    "id": f"nvr-{nvr.id}",
                    "name": nvr.name,
                    "model": nvr.model or nvr.vendor or "NVR",
                    "ip_address": nvr.ip_address,
                    "mac_address": nvr.mac_address,
                    "online_channels": 0,
                    "total_channels": 0,
                    "is_online": nvr.is_online,
                    "upstream_switch": up_sw,
                    "upstream_port": up_port,
                    "hdds": [],
                }
            )

        for cam in cam_devs:
            up_sw, up_port = upstream_by_target.get(cam.id, ("Chưa xác định", "-"))
            cameras.append(
                {
                    "id": f"cam-{cam.id}",
                    "name": cam.name,
                    "model": cam.model or cam.vendor or "IP Camera",
                    "vendor": cam.vendor or "Unknown",
                    "ip_address": cam.ip_address,
                    "mac_address": cam.mac_address or "",
                    "is_online": cam.is_online,
                    "upstream_switch": up_sw,
                    "upstream_port": up_port,
                    "vlan_id": None,
                    "nvr_links": [],
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
        except ValueError as exc:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"notification": False, "success": False, "detail": str(exc)},
            )
        collector = HikvisionISAPICollector(host=clean_ip, username=nvr_user, password=nvr_pass)
        live_nvr = await asyncio.to_thread(collector.collect_all, f"Hikvision-NVR ({clean_ip})")
        if not live_nvr.get("is_online"):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "notification": False,
                    "success": False,
                    "detail": f"Không kết nối được tới đầu ghi NVR {clean_ip}: {live_nvr.get('error') or 'Timeout'}",
                },
            )
        nvrs.insert(0, live_nvr)
        alerts.extend(live_nvr.get("alerts", []))

    return {
        "site_id": site_id,
        "notification": len(nvrs) > 0 or len(cameras) > 0,
        "nvrs": nvrs,
        "cameras": cameras,
        "alerts": alerts,
    }


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
