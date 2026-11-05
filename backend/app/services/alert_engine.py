from typing import Any

ROGUE_AP_VENDORS = {"Tenda", "TP-Link", "Mercury"}


def is_cctv_port(
    port_name: str,
    vlan_id: int | None,
    port_endpoints: list[dict[str, Any]],
    cctv_vlans: set[int] | None = None,
) -> bool:
    name_lower = (port_name or "").lower()
    if "cam" in name_lower or "cctv" in name_lower or "nvr" in name_lower:
        return True
    if vlan_id is not None and cctv_vlans and vlan_id in cctv_vlans:
        return True
    return any(ep.get("device_type") in ("camera", "nvr") for ep in port_endpoints)


def evaluate_site_alerts(
    site_id: int,
    port_Attachment_groups: list[dict[str, Any]],
    dhcp_pools: list[dict[str, Any]] | None = None,
    cctv_vlans: set[int] | None = None,
) -> list[dict[str, Any]]:
    """
    Evaluate security and anomaly alert rules for a site:
    1. Rogue consumer router/AP (Tenda, TP-Link, Mercury) on a CCTV/Camera port.
    2. Unmanaged switch group with >50 devices cascaded behind a single 1G port.
    3. VLAN DHCP pool usage > 90%.
    """
    alerts: list[dict[str, Any]] = []

    for group in port_Attachment_groups:
        sw_device_key = group.get("switch_key")
        sw_name = group.get("switch_name", "Switch")
        port_index = group.get("port_index")
        port_name = group.get("port_name", f"Port-{port_index}")
        port_speed = group.get("speed", "1G")
        vlan_id = group.get("vlan_id")
        endpoints: list[dict[str, Any]] = group.get("endpoints", [])

        # Rule 1: Rogue consumer router/AP vendor on a CCTV/Camera designated port
        if is_cctv_port(port_name, vlan_id, endpoints, cctv_vlans):
            for ep in endpoints:
                vendor = ep.get("vendor", "")
                if vendor in ROGUE_AP_VENDORS:
                    alerts.append(
                        {
                            "site_id": site_id,
                            "switch_key": sw_device_key,
                            "port_index": port_index,
                            "severity": "critical",
                            "message": (
                                f"Phát hiện thiết bị Router/AP dân dụng lạ ({vendor} - MAC {ep.get('mac')}) "
                                f"cắm vào cổng Camera/CCTV {sw_name}:{port_name}"
                            ),
                        }
                    )

        # Rule 2: Unmanaged switch group >50 devices cascaded behind a single 1G port
        if len(endpoints) > 50 and port_speed in ("1G", "100M"):
            alerts.append(
                {
                    "site_id": site_id,
                    "switch_key": sw_device_key,
                    "port_index": port_index,
                    "severity": "critical",
                    "message": (
                        f"Quá tải cụm Switch không quản lý: {len(endpoints)} thiết bị nối tầng "
                        f"sau một cổng {port_speed} ({sw_name}:{port_name})"
                    ),
                }
            )

    # Rule 3: VLAN DHCP pool usage exceeds 90%
    for pool in dhcp_pools or []:
        vlan = pool.get("vlan_id")
        used = int(pool.get("used", 0))
        total = int(pool.get("total", 0))
        if total > 0:
            usage_pct = (used / total) * 100.0
            if usage_pct > 90.0:
                alerts.append(
                    {
                        "site_id": site_id,
                        "switch_key": None,
                        "port_index": None,
                        "severity": "warning",
                        "message": (
                            f"Cảnh báo đầy tải DHCP VLAN {vlan}: đã cấp {used}/{total} IP ({usage_pct:.1f}% > 90%)"
                        ),
                    }
                )

    return alerts
