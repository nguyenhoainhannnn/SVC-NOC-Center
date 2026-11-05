import re
from typing import Any, Optional

from .mac_vendor import lookup_mac_vendor, normalize_mac


def parse_routeros_uptime(uptime_str: str) -> int:
    """Convert RouterOS uptime string (e.g. '2w3d4h5m6s') into seconds."""
    if not uptime_str:
        return 0
    multipliers = {"w": 604800, "d": 86400, "h": 3600, "m": 60, "s": 1}
    total = 0
    for amount, unit in re.findall(r"(\d+)([wdhms])", str(uptime_str)):
        total += int(amount) * multipliers[unit]
    return total


class MikroTikCollector:
    def __init__(
        self,
        host: str,
        username: str = "admin",
        password: str = "",
        port: int = 8728,
        timeout: float = 5.0,
    ):
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.timeout = timeout

    def _connect(self):
        from librouteros import connect

        return connect(
            host=self.host,
            username=self.username,
            password=self.password,
            port=self.port,
            timeout=self.timeout,
        )

    @staticmethod
    def normalize_arp_and_dhcp(
        arp_rows: list[dict[str, Any]],
        dhcp_rows: list[dict[str, Any]],
        vlan_rows: Optional[list[dict[str, Any]]] = None,
    ) -> list[dict[str, Any]]:
        vlan_map: dict[str, int] = {}
        for v in vlan_rows or []:
            if v.get("name") and v.get("vlan-id") is not None:
                vlan_map[str(v["name"])] = int(v["vlan-id"])

        dhcp_by_mac: dict[str, dict[str, Any]] = {}
        dhcp_by_ip: dict[str, dict[str, Any]] = {}
        for lease in dhcp_rows:
            mac = normalize_mac(str(lease.get("mac-address") or lease.get("active-mac-address") or ""))
            ip = str(lease.get("address") or lease.get("active-address") or "").strip()
            if mac:
                dhcp_by_mac[mac] = lease
            if ip:
                dhcp_by_ip[ip] = lease

        merged: dict[str, dict[str, Any]] = {}
        for entry in arp_rows:
            ip = str(entry.get("address") or "").strip()
            mac = normalize_mac(str(entry.get("mac-address") or ""))
            if not ip and not mac:
                continue
            iface = str(entry.get("interface") or "")
            lease = dhcp_by_mac.get(mac) or dhcp_by_ip.get(ip) or {}
            hostname = str(lease.get("host-name") or entry.get("comment") or "").strip() or None
            vendor_info = lookup_mac_vendor(mac) if mac else {"vendor": "Unknown", "device_type": "endpoint"}
            key = f"{ip}|{mac}"
            merged[key] = {
                "ip": ip,
                "mac": mac,
                "hostname": hostname,
                "interface": iface,
                "vlan": vlan_map.get(iface),
                "vendor": vendor_info["vendor"],
                "device_type": vendor_info["device_type"],
            }

        for lease in dhcp_rows:
            ip = str(lease.get("address") or lease.get("active-address") or "").strip()
            mac = normalize_mac(str(lease.get("mac-address") or lease.get("active-mac-address") or ""))
            key = f"{ip}|{mac}"
            if key in merged or (not ip and not mac):
                continue
            iface = str(lease.get("server") or "")
            vendor_info = lookup_mac_vendor(mac) if mac else {"vendor": "Unknown", "device_type": "endpoint"}
            merged[key] = {
                "ip": ip,
                "mac": mac,
                "hostname": str(lease.get("host-name") or lease.get("comment") or "").strip() or None,
                "interface": iface,
                "vlan": vlan_map.get(iface),
                "vendor": vendor_info["vendor"],
                "device_type": vendor_info["device_type"],
            }

        return list(merged.values())

    def collect_all(self) -> dict[str, Any]:
        api = None
        try:
            api = self._connect()
            res_list = list(api.path("system", "resource"))
            res = res_list[0] if res_list else {}
            total_mem = int(res.get("total-memory") or 0)
            free_mem = int(res.get("free-memory") or 0)
            ram_usage = round(((total_mem - free_mem) / total_mem) * 100.0, 2) if total_mem > 0 else 0.0
            uptime_raw = str(res.get("uptime") or "0s")

            system_info = {
                "board_model": str(res.get("board-name") or res.get("platform") or "MikroTik"),
                "version": str(res.get("version") or ""),
                "cpu_load": float(res.get("cpu-load") or 0.0),
                "free_ram": free_mem,
                "total_ram": total_mem,
                "ram_usage_pct": ram_usage,
                "uptime_raw": uptime_raw,
                "uptime_seconds": parse_routeros_uptime(uptime_raw),
            }

            interfaces = []
            for iface in api.path("interface"):
                name = str(iface.get("name") or "")
                running = bool(iface.get("running", False))
                rx_bps = 0
                tx_bps = 0
                if name and running:
                    try:
                        mon = list(api.path("interface")("monitor-traffic", interface=name, once=True))
                        if mon:
                            rx_bps = int(mon[0].get("rx-bits-per-second") or 0)
                            tx_bps = int(mon[0].get("tx-bits-per-second") or 0)
                    except Exception:
                        pass
                interfaces.append(
                    {
                        "name": name,
                        "type": str(iface.get("type") or ""),
                        "mac_address": normalize_mac(str(iface.get("mac-address") or "")),
                        "running": running,
                        "rx_bps": rx_bps,
                        "tx_bps": tx_bps,
                    }
                )

            arp_rows = list(api.path("ip", "arp"))
            dhcp_rows = list(api.path("ip", "dhcp-server", "lease"))
            try:
                vlan_rows = list(api.path("interface", "vlan"))
            except Exception:
                vlan_rows = []
            hosts = self.normalize_arp_and_dhcp(arp_rows, dhcp_rows, vlan_rows)

            neighbors = []
            for nb in api.path("ip", "neighbor"):
                mac = normalize_mac(str(nb.get("mac-address") or ""))
                neighbors.append(
                    {
                        "interface": str(nb.get("interface") or ""),
                        "ip": str(nb.get("address") or ""),
                        "mac": mac,
                        "identity": str(nb.get("identity") or ""),
                        "platform": str(nb.get("platform") or ""),
                        "board": str(nb.get("board") or ""),
                        "version": str(nb.get("version") or ""),
                    }
                )

            return {
                "host": self.host,
                "is_online": True,
                "system": system_info,
                "interfaces": interfaces,
                "hosts": hosts,
                "neighbors": neighbors,
            }
        except Exception as exc:
            return {
                "host": self.host,
                "is_online": False,
                "error": str(exc),
                "system": None,
                "interfaces": [],
                "hosts": [],
                "neighbors": [],
            }
        finally:
            if api is not None:
                try:
                    api.close()
                except Exception:
                    pass
