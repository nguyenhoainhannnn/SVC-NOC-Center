from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..collectors.mac_vendor import lookup_mac_vendor, normalize_mac
from .alert_engine import ROGUE_AP_VENDORS, evaluate_site_alerts

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from ..models import Alert, NetworkDevice, TopologyEdge

UNMANAGED_LABEL = "Chưa xác định switch hoặc AP"
MANAGED_AP_VENDORS = {"Ubiquiti", "Aruba", "Ruijie"}


def build_site_topology(
    site_id: int,
    router_data: dict[str, Any],
    switches_data: list[dict[str, Any]],
    dhcp_pools: list[dict[str, Any]] | None = None,
    cctv_vlans: set[int] | None = None,
) -> dict[str, Any]:
    """
    Pure topology resolution engine:
    - Step 1: Resolve Core & Distribution Uplinks (Router -> Core Switches -> Access Switches)
              using LLDP neighbors and shared infrastructure MAC tables; mark ports is_uplink=True.
    - Step 2: Filter out uplink ports. Map single-MAC access ports directly to endpoints, and
              group multi-MAC access ports (>1 MAC, not a single managed AP) behind a virtual
              'Chưa xác định switch hoặc AP' (unmanaged_group) node.
    - Step 3: Run security & anomaly alert rules.
    """
    devices: dict[str, dict[str, Any]] = {}
    ports: dict[tuple[str, int], dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    # 1. Register Router node
    r_sys = router_data.get("system") or {}
    r_host = router_data.get("host") or "10.10.0.1"
    r_ifaces = router_data.get("interfaces") or []
    r_mac = normalize_mac(next((i.get("mac_address") for i in r_ifaces if i.get("mac_address")), ""))
    router_key = "router-1"
    devices[router_key] = {
        "key": router_key,
        "site_id": site_id,
        "name": r_sys.get("board_model") or f"Router ({r_host})",
        "ip_address": r_host,
        "mac_address": r_mac or None,
        "vendor": "MikroTik",
        "model": r_sys.get("board_model") or "RouterOS",
        "role": "router",
        "cpu_usage": float(r_sys.get("cpu_load") or 0.0),
        "ram_usage": float(r_sys.get("ram_usage_pct") or 0.0),
        "uptime": int(r_sys.get("uptime_seconds") or 0),
        "is_online": bool(router_data.get("is_online", True)),
        "tier": 0,
    }
    for idx, iface in enumerate(r_ifaces, start=1):
        ports[(router_key, idx)] = {
            "device_key": router_key,
            "port_index": idx,
            "port_name": iface.get("name") or f"ether{idx}",
            "status": "up" if iface.get("running", True) else "down",
            "speed": "1G",
            "vlan_id": None,
            "is_uplink": False,
            "connected_to_key": None,
            "connected_to_port_index": None,
        }

    # Index ARP/DHCP hosts by MAC
    arp_by_mac: dict[str, dict[str, Any]] = {}
    arp_by_ip: dict[str, dict[str, Any]] = {}
    for h in router_data.get("hosts") or []:
        m = normalize_mac(h.get("mac") or "")
        ip = h.get("ip") or ""
        if m:
            arp_by_mac[m] = h
        if ip:
            arp_by_ip[ip] = h

    # 2. Register Managed Switches
    sw_by_name: dict[str, str] = {}
    sw_by_mac: dict[str, str] = {}
    infra_macs: set[str] = {m for m in (r_mac,) if m}

    for idx, sw in enumerate(switches_data, start=1):
        sw_key = f"switch-{idx}"
        sys_info = sw.get("system") or {}
        sw_ip = sw.get("host") or f"10.10.0.{idx + 1}"
        sw_name = sys_info.get("sys_name") or f"Switch-{idx}"
        arp_match = arp_by_ip.get(sw_ip) or {}
        sw_mac = normalize_mac(sw.get("mac_address") or arp_match.get("mac") or "")
        vendor = sys_info.get("vendor") or (lookup_mac_vendor(sw_mac)["vendor"] if sw_mac else "Generic")

        devices[sw_key] = {
            "key": sw_key,
            "site_id": site_id,
            "name": sw_name,
            "ip_address": sw_ip,
            "mac_address": sw_mac or None,
            "vendor": vendor,
            "model": sys_info.get("sys_descr") or vendor,
            "role": "managed_switch",
            "cpu_usage": float(sys_info.get("cpu_usage") or 0.0),
            "ram_usage": float(sys_info.get("ram_usage") or 0.0),
            "uptime": int(sys_info.get("uptime_seconds") or 0),
            "is_online": bool(sw.get("is_online", True)),
            "tier": 1 if idx == 1 else 2,
        }
        sw_by_name[sw_name.lower()] = sw_key
        if sw_mac:
            sw_by_mac[sw_mac] = sw_key
            infra_macs.add(sw_mac)

        for p in sw.get("interfaces") or []:
            p_idx = int(p.get("port_index") or 1)
            ports[(sw_key, p_idx)] = {
                "device_key": sw_key,
                "port_index": p_idx,
                "port_name": p.get("port_name") or f"Gi0/{p_idx}",
                "status": p.get("status") or "up",
                "speed": p.get("speed") or "1G",
                "vlan_id": p.get("vlan_id"),
                "is_uplink": False,
                "connected_to_key": None,
                "connected_to_port_index": None,
            }

    def mark_uplink_link(src_key: str, src_port: int, dst_key: str, dst_port: int) -> None:
        for k, p_idx, other_k, other_p in (
            (src_key, src_port, dst_key, dst_port),
            (dst_key, dst_port, src_key, src_port),
        ):
            if (k, p_idx) not in ports:
                ports[(k, p_idx)] = {
                    "device_key": k,
                    "port_index": p_idx,
                    "port_name": f"Port-{p_idx}",
                    "status": "up",
                    "speed": "1G",
                    "vlan_id": None,
                    "is_uplink": True,
                    "connected_to_key": other_k,
                    "connected_to_port_index": other_p,
                }
            else:
                ports[(k, p_idx)]["is_uplink"] = True
                ports[(k, p_idx)]["connected_to_key"] = other_k
                ports[(k, p_idx)]["connected_to_port_index"] = other_p

        pair = {src_key, dst_key}
        if not any({e["source_key"], e["target_key"]} == pair for e in edges):
            edges.append(
                {
                    "source_key": src_key,
                    "source_port": src_port,
                    "target_key": dst_key,
                    "target_port": dst_port,
                    "link_type": "trunk",
                }
            )

    # Step 1: Resolve Core & Distribution Uplinks via LLDP + shared MAC FDB tables
    linked_switches: set[str] = set()
    for idx, sw in enumerate(switches_data, start=1):
        sw_key = f"switch-{idx}"
        # Check LLDP neighbors on switch
        for nb in sw.get("lldp_neighbors") or []:
            local_port = int(nb.get("local_port_index") or 1)
            rem_name = str(nb.get("remote_sys_name") or "").lower()
            rem_port_str = "".join(ch for ch in str(nb.get("remote_port_id") or "") if ch.isdigit())
            rem_port = int(rem_port_str) if rem_port_str else 1

            if rem_name in sw_by_name and sw_by_name[rem_name] != sw_key:
                target_sw_key = sw_by_name[rem_name]
                mark_uplink_link(sw_key, local_port, target_sw_key, rem_port)
                linked_switches.add(sw_key)
                linked_switches.add(target_sw_key)
            elif rem_name and (
                rem_name in devices[router_key]["name"].lower() or "mikrotik" in rem_name or "router" in rem_name
            ):
                mark_uplink_link(router_key, rem_port, sw_key, local_port)
                linked_switches.add(sw_key)

        # Check FDB MAC table for Router MAC or other Switch MACs (shared MAC table uplink resolution)
        for entry in sw.get("mac_table") or []:
            entry_mac = normalize_mac(entry.get("mac") or "")
            p_idx = int(entry.get("port_index") or 1)
            if r_mac and entry_mac == r_mac:
                mark_uplink_link(router_key, 1, sw_key, p_idx)
                linked_switches.add(sw_key)
            elif entry_mac in sw_by_mac and sw_by_mac[entry_mac] != sw_key:
                other_sw = sw_by_mac[entry_mac]
                mark_uplink_link(sw_key, p_idx, other_sw, 1)
                linked_switches.add(sw_key)
                linked_switches.add(other_sw)

    # Ensure at least primary switch links to router if LLDP/MAC didn't explicitly carry router MAC
    if switches_data and not any(e["source_key"] == router_key or e["target_key"] == router_key for e in edges):
        mark_uplink_link(router_key, 1, "switch-1", 24)

    # Step 2: Edge Port Mapping (Filter out uplink ports)
    port_attachment_groups: list[dict[str, Any]] = []
    endpoint_seq = 0
    unmanaged_seq = 0

    for idx, sw in enumerate(switches_data, start=1):
        sw_key = f"switch-{idx}"
        sw_name = devices[sw_key]["name"]

        # Group non-infrastructure MACs by non-uplink port_index
        macs_by_port: dict[int, list[dict[str, Any]]] = {}
        for fdb in sw.get("mac_table") or []:
            p_idx = int(fdb.get("port_index") or 1)
            port_meta = ports.get((sw_key, p_idx))
            if port_meta and port_meta.get("is_uplink"):
                continue
            mac = normalize_mac(fdb.get("mac") or "")
            if not mac or mac in infra_macs:
                continue
            macs_by_port.setdefault(p_idx, [])
            if not any(existing["mac"] == mac for existing in macs_by_port[p_idx]):
                arp_info = arp_by_mac.get(mac) or {}
                vendor_info = lookup_mac_vendor(mac)
                macs_by_port[p_idx].append(
                    {
                        "mac": mac,
                        "ip": arp_info.get("ip") or f"0.0.0.0 ({mac[-5:]})",
                        "hostname": arp_info.get("hostname"),
                        "vlan_id": fdb.get("vlan_id") or arp_info.get("vlan"),
                        "vendor": vendor_info["vendor"],
                        "device_type": fdb.get("device_type") or vendor_info["device_type"],
                    }
                )

        for p_idx, ep_list in sorted(macs_by_port.items()):
            port_obj = ports.setdefault(
                (sw_key, p_idx),
                {
                    "device_key": sw_key,
                    "port_index": p_idx,
                    "port_name": f"Gi0/{p_idx}",
                    "status": "up",
                    "speed": "1G",
                    "vlan_id": ep_list[0].get("vlan_id"),
                    "is_uplink": False,
                    "connected_to_key": None,
                    "connected_to_port_index": None,
                },
            )
            if port_obj.get("vlan_id") is None and ep_list[0].get("vlan_id") is not None:
                port_obj["vlan_id"] = ep_list[0]["vlan_id"]

            port_attachment_groups.append(
                {
                    "switch_key": sw_key,
                    "switch_name": sw_name,
                    "port_index": p_idx,
                    "port_name": port_obj["port_name"],
                    "speed": port_obj["speed"],
                    "vlan_id": port_obj["vlan_id"],
                    "endpoints": ep_list,
                }
            )

            # Case 1: Exactly 1 MAC address learned on the access port -> direct child node
            if len(ep_list) == 1:
                ep = ep_list[0]
                endpoint_seq += 1
                ep_key = f"ep-{endpoint_seq}"
                label_name = ep.get("hostname") or f"{ep['vendor']}-{ep['mac'][-5:].replace(':', '')}"
                devices[ep_key] = {
                    "key": ep_key,
                    "site_id": site_id,
                    "name": label_name,
                    "ip_address": ep["ip"],
                    "mac_address": ep["mac"],
                    "vendor": ep["vendor"],
                    "model": ep["vendor"],
                    "role": ep["device_type"],
                    "cpu_usage": 0.0,
                    "ram_usage": 0.0,
                    "uptime": 0,
                    "is_online": True,
                    "tier": 3,
                }
                port_obj["connected_to_key"] = ep_key
                port_obj["connected_to_port_index"] = 1
                edges.append(
                    {
                        "source_key": sw_key,
                        "source_port": p_idx,
                        "target_key": ep_key,
                        "target_port": 1,
                        "link_type": "access",
                    }
                )
            else:
                # Case 2: >1 MAC addresses on a non-uplink port
                managed_aps = [
                    ep
                    for ep in ep_list
                    if ep.get("device_type") == "ap"
                    and ep.get("vendor") in MANAGED_AP_VENDORS
                    and ep.get("vendor") not in ROGUE_AP_VENDORS
                ]
                if len(managed_aps) == 1:
                    ap_ep = managed_aps[0]
                    endpoint_seq += 1
                    parent_key = f"ep-{endpoint_seq}"
                    ap_name = ap_ep.get("hostname") or f"{ap_ep['vendor']}-AP-{ap_ep['mac'][-5:].replace(':', '')}"
                    devices[parent_key] = {
                        "key": parent_key,
                        "site_id": site_id,
                        "name": ap_name,
                        "ip_address": ap_ep["ip"],
                        "mac_address": ap_ep["mac"],
                        "vendor": ap_ep["vendor"],
                        "model": ap_ep["vendor"],
                        "role": "ap",
                        "cpu_usage": 0.0,
                        "ram_usage": 0.0,
                        "uptime": 0,
                        "is_online": True,
                        "tier": 2,
                    }
                    port_obj["connected_to_key"] = parent_key
                    port_obj["connected_to_port_index"] = 0
                    edges.append(
                        {
                            "source_key": sw_key,
                            "source_port": p_idx,
                            "target_key": parent_key,
                            "target_port": 0,
                            "link_type": "access",
                        }
                    )
                    child_endpoints = [ep for ep in ep_list if ep["mac"] != ap_ep["mac"]]
                else:
                    unmanaged_seq += 1
                    parent_key = f"unmanaged-{unmanaged_seq}"
                    devices[parent_key] = {
                        "key": parent_key,
                        "site_id": site_id,
                        "name": f"{UNMANAGED_LABEL} ({sw_name}:{port_obj['port_name']})",
                        "ip_address": f"unmanaged-{sw_key}-p{p_idx}",
                        "mac_address": None,
                        "vendor": "Unmanaged",
                        "model": UNMANAGED_LABEL,
                        "role": "unmanaged_group",
                        "cpu_usage": 0.0,
                        "ram_usage": 0.0,
                        "uptime": 0,
                        "is_online": True,
                        "tier": 2,
                    }
                    port_obj["connected_to_key"] = parent_key
                    port_obj["connected_to_port_index"] = 0
                    edges.append(
                        {
                            "source_key": sw_key,
                            "source_port": p_idx,
                            "target_key": parent_key,
                            "target_port": 0,
                            "link_type": "unmanaged",
                        }
                    )
                    child_endpoints = ep_list

                for hub_port_idx, ep in enumerate(child_endpoints, start=1):
                    endpoint_seq += 1
                    ep_key = f"ep-{endpoint_seq}"
                    label_name = ep.get("hostname") or f"{ep['vendor']}-{ep['mac'][-5:].replace(':', '')}"
                    devices[ep_key] = {
                        "key": ep_key,
                        "site_id": site_id,
                        "name": label_name,
                        "ip_address": ep["ip"],
                        "mac_address": ep["mac"],
                        "vendor": ep["vendor"],
                        "model": ep["vendor"],
                        "role": ep["device_type"],
                        "cpu_usage": 0.0,
                        "ram_usage": 0.0,
                        "uptime": 0,
                        "is_online": True,
                        "tier": 3,
                    }
                    edges.append(
                        {
                            "source_key": parent_key,
                            "source_port": hub_port_idx,
                            "target_key": ep_key,
                            "target_port": 1,
                            "link_type": "unmanaged",
                        }
                    )

    alerts = evaluate_site_alerts(
        site_id=site_id,
        port_Attachment_groups=port_attachment_groups,
        dhcp_pools=dhcp_pools,
        cctv_vlans=cctv_vlans,
    )

    return {
        "site_id": site_id,
        "devices": list(devices.values()),
        "ports": list(ports.values()),
        "edges": edges,
        "alerts": alerts,
    }


def format_reactflow_topology(
    site_id: int,
    devices: list[NetworkDevice],
    edges: list[TopologyEdge],
    alerts: list[Alert] | None = None,
) -> dict[str, Any]:
    tier_by_role = {
        "router": 0,
        "managed_switch": 1,
        "unmanaged_group": 2,
        "ap": 3,
        "nvr": 3,
        "camera": 3,
        "endpoint": 3,
    }
    node_type_by_role = {
        "router": "routerNode",
        "managed_switch": "switchNode",
        "unmanaged_group": "unmanagedGroupNode",
    }
    tier_counts: dict[int, int] = {}
    rf_nodes: list[dict[str, Any]] = []

    for dev in devices:
        tier = tier_by_role.get(dev.role, 3)
        col = tier_counts.get(tier, 0)
        tier_counts[tier] = col + 1
        rf_nodes.append(
            {
                "id": f"dev-{dev.id}",
                "type": node_type_by_role.get(dev.role, "endpointNode"),
                "position": {"x": 80 + tier * 360, "y": 40 + col * 200},
                "data": {
                    "label": f"{dev.name} ({dev.ip_address})"
                    if dev.role != "unmanaged_group"
                    else dev.name,
                    "name": dev.name,
                    "role": dev.role,
                    "vendor": dev.vendor,
                    "model": dev.model,
                    "ip_address": dev.ip_address,
                    "mac_address": dev.mac_address,
                    "cpu_usage": dev.cpu_usage,
                    "ram_usage": dev.ram_usage,
                    "uptime": dev.uptime,
                    "is_online": dev.is_online,
                },
            }
        )

    rf_edges: list[dict[str, Any]] = []
    for edge in edges:
        rf_edges.append(
            {
                "id": f"e-{edge.id}",
                "source": f"dev-{edge.source_device_id}",
                "target": f"dev-{edge.target_device_id}",
                "label": f"P{edge.source_port} -> P{edge.target_port} ({edge.link_type})",
                "data": {
                    "link_type": edge.link_type,
                    "source_port": edge.source_port,
                    "target_port": edge.target_port,
                },
                "animated": edge.link_type == "trunk",
            }
        )

    return {
        "site_id": site_id,
        "nodes": rf_nodes,
        "edges": rf_edges,
        "alerts": [
            {
                "id": a.id,
                "device_id": a.device_id,
                "port_index": a.port_index,
                "severity": a.severity,
                "message": a.message,
                "is_resolved": a.is_resolved,
            }
            for a in (alerts or [])
        ],
    }


async def persist_site_topology(db: AsyncSession, resolved: dict[str, Any]) -> dict[str, Any]:
    from sqlalchemy import delete
    from ..models import Alert, DevicePort, NetworkDevice, TopologyEdge

    site_id = int(resolved["site_id"])

    # Replace previous topology snapshot for this site
    await db.execute(delete(TopologyEdge).where(TopologyEdge.site_id == site_id))
    await db.execute(delete(Alert).where(Alert.site_id == site_id))
    await db.execute(delete(NetworkDevice).where(NetworkDevice.site_id == site_id))
    await db.flush()

    key_to_db_device: dict[str, NetworkDevice] = {}
    for d in resolved["devices"]:
        db_dev = NetworkDevice(
            site_id=site_id,
            name=d["name"],
            ip_address=d["ip_address"],
            mac_address=d.get("mac_address"),
            vendor=d.get("vendor"),
            model=d.get("model"),
            role=d["role"],
            cpu_usage=d.get("cpu_usage", 0.0),
            ram_usage=d.get("ram_usage", 0.0),
            uptime=d.get("uptime", 0),
            is_online=d.get("is_online", True),
        )
        db.add(db_dev)
        key_to_db_device[d["key"]] = db_dev

    await db.flush()

    for p in resolved["ports"]:
        owner = key_to_db_device.get(p["device_key"])
        if not owner:
            continue
        db.add(
            DevicePort(
                device_id=owner.id,
                port_index=p["port_index"],
                port_name=p["port_name"],
                status=p["status"],
                speed=p["speed"],
                vlan_id=p.get("vlan_id"),
                is_uplink=p.get("is_uplink", False),
            )
        )

    db_edges: list[TopologyEdge] = []
    for e in resolved["edges"]:
        src_dev = key_to_db_device.get(e["source_key"])
        dst_dev = key_to_db_device.get(e["target_key"])
        if not src_dev or not dst_dev:
            continue
        edge_row = TopologyEdge(
            site_id=site_id,
            source_device_id=src_dev.id,
            source_port=e["source_port"],
            target_device_id=dst_dev.id,
            target_port=e["target_port"],
            link_type=e["link_type"],
        )
        db.add(edge_row)
        db_edges.append(edge_row)

    db_alerts: list[Alert] = []
    for a in resolved["alerts"]:
        sw_dev = key_to_db_device.get(a.get("switch_key")) if a.get("switch_key") else None
        alert_row = Alert(
            site_id=site_id,
            device_id=sw_dev.id if sw_dev else None,
            port_index=a.get("port_index"),
            severity=a["severity"],
            message=a["message"],
        )
        db.add(alert_row)
        db_alerts.append(alert_row)

    await db.commit()

    all_devices = list(key_to_db_device.values())
    return format_reactflow_topology(site_id, all_devices, db_edges, db_alerts)
