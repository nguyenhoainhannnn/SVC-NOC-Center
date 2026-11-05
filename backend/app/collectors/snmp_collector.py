from typing import Any

from .mac_vendor import lookup_mac_vendor

# Standard SNMP OIDs (numeric to avoid runtime MIB compilation dependency)
OID_SYS_DESCR = "1.3.6.1.2.1.1.1.0"        # SNMPv2-MIB::sysDescr.0
OID_SYS_UPTIME = "1.3.6.1.2.1.1.3.0"       # SNMPv2-MIB::sysUpTime.0
OID_SYS_NAME = "1.3.6.1.2.1.1.5.0"         # SNMPv2-MIB::sysName.0

OID_IF_DESCR = "1.3.6.1.2.1.2.2.1.2"       # IF-MIB::ifDescr
OID_IF_OPER_STATUS = "1.3.6.1.2.1.2.2.1.8" # IF-MIB::ifOperStatus (1=up, 2=down)
OID_IF_HIGH_SPEED = "1.3.6.1.2.1.31.1.1.1.15"  # IF-MIB::ifHighSpeed (Mbps)

OID_DOT1D_BASE_PORT_IFINDEX = "1.3.6.1.2.1.17.1.4.1.2"  # BRIDGE-MIB::dot1dBasePortIfIndex
OID_DOT1D_TP_FDB_PORT = "1.3.6.1.2.1.17.4.3.1.2"        # BRIDGE-MIB::dot1dTpFdbPort
OID_DOT1Q_TP_FDB_PORT = "1.3.6.1.2.1.17.7.1.2.2.1.2"    # Q-BRIDGE-MIB::dot1qTpFdbPort

OID_LLDP_REM_PORT_ID = "1.3.6.1.0.8802.1.1.2.1.4.1.1.7"   # LLDP-MIB::lldpRemPortId
OID_LLDP_REM_SYS_NAME = "1.3.6.1.0.8802.1.1.2.1.4.1.1.9"  # LLDP-MIB::lldpRemSysName

# Vendor Enterprise OIDs (CPU % / Memory %)
VENDOR_METRIC_OIDS: dict[str, tuple[str, str]] = {
    # Fortinet: fgSysCpuUsage.0, fgSysMemUsage.0
    "Fortinet": ("1.3.6.1.4.1.12356.101.4.1.3.0", "1.3.6.1.4.1.12356.101.4.1.4.0"),
    # DrayTek: vigorCpuUsage, vigorMemoryUsage
    "DrayTek": ("1.3.6.1.4.1.7367.3.1.2.0", "1.3.6.1.4.1.7367.3.1.3.0"),
    # Aruba (ProCurve/AOS-S): hpSwitchCpuStat.0, hpLocalMemAllocBytes (fallback%)
    "Aruba": ("1.3.6.1.4.1.11.2.14.11.5.1.9.6.1.0", "1.3.6.1.4.1.14823.2.2.1.2.1.13.0"),
}


def detect_snmp_vendor_and_role(sys_descr: str, sys_name: str = "") -> tuple[str, str]:
    text = f"{sys_descr} {sys_name}".lower()
    if "fortigate" in text or "fortinet" in text or "fortios" in text:
        return "Fortinet", "managed_switch" if "fortiswitch" in text else "router"
    if "draytek" in text or "vigor" in text:
        return "DrayTek", "router"
    if "aruba" in text or "procurve" in text or "jl" in text:
        return "Aruba", "ap" if "instant" in text or "iap" in text else "managed_switch"
    if "ruijie" in text or "reyee" in text:
        return "Ruijie", "managed_switch"
    if "cisco" in text:
        return "Cisco", "router" if "isr" in text or "asr" in text else "managed_switch"
    if "hikvision" in text:
        return "Hikvision", "managed_switch"
    if "mikrotik" in text or "routeros" in text:
        return "MikroTik", "router"
    return "Generic", "managed_switch"


def format_speed_mbps(mbps: int) -> str:
    if mbps >= 10000:
        return "10G"
    if mbps >= 1000:
        return "1G"
    return "100M"


def parse_mac_from_oid_suffix(suffix: str, has_vlan_prefix: bool = False) -> tuple[int | None, str | None]:
    parts = [int(p) for p in suffix.strip(".").split(".") if p.isdigit()]
    if has_vlan_prefix and len(parts) >= 7:
        vlan_id = parts[0]
        octets = parts[-6:]
        return vlan_id, ":".join(f"{b:02X}" for b in octets)
    if not has_vlan_prefix and len(parts) >= 6:
        octets = parts[-6:]
        return None, ":".join(f"{b:02X}" for b in octets)
    return None, None


class SNMPSwitchCollector:
    def __init__(
        self,
        host: str,
        community: str = "public",
        port: int = 161,
        timeout: float = 2.5,
        retries: int = 1,
    ):
        self.host = host
        self.community = community
        self.port = port
        self.timeout = timeout
        self.retries = retries

    def _snmp_get(self, *oids: str) -> dict[str, str]:
        from pysnmp.hlapi import (
            CommunityData,
            ContextData,
            ObjectIdentity,
            ObjectType,
            SnmpEngine,
            UdpTransportTarget,
            getCmd,
        )

        obj_types = [ObjectType(ObjectIdentity(oid)) for oid in oids]
        error_indication, error_status, _, var_binds = next(
            getCmd(
                SnmpEngine(),
                CommunityData(self.community, mpModel=1),
                UdpTransportTarget((self.host, self.port), timeout=self.timeout, retries=self.retries),
                ContextData(),
                *obj_types,
            )
        )
        if error_indication or error_status:
            raise RuntimeError(str(error_indication or error_status.prettyPrint()))
        return {str(name): str(val.prettyPrint()) for name, val in var_binds}

    def _snmp_walk(self, base_oid: str) -> dict[str, str]:
        from pysnmp.hlapi import (
            CommunityData,
            ContextData,
            ObjectIdentity,
            ObjectType,
            SnmpEngine,
            UdpTransportTarget,
            nextCmd,
        )

        results: dict[str, str] = {}
        prefix = base_oid.rstrip(".") + "."
        for error_indication, error_status, _, var_binds in nextCmd(
            SnmpEngine(),
            CommunityData(self.community, mpModel=1),
            UdpTransportTarget((self.host, self.port), timeout=self.timeout, retries=self.retries),
            ContextData(),
            ObjectType(ObjectIdentity(base_oid)),
            lexicographicMode=False,
        ):
            if error_indication or error_status:
                break
            for name, val in var_binds:
                oid_str = str(name)
                if oid_str.startswith(prefix):
                    suffix = oid_str[len(prefix) :]
                    results[suffix] = str(val.prettyPrint())
        return results

    def collect_all(self) -> dict[str, Any]:
        try:
            sys_raw = self._snmp_get(OID_SYS_DESCR, OID_SYS_UPTIME, OID_SYS_NAME)
            uptime_ticks = int(sys_raw.get(OID_SYS_UPTIME, "0") or 0)
            sys_descr = sys_raw.get(OID_SYS_DESCR, "")
            sys_name = sys_raw.get(OID_SYS_NAME, "")
            vendor, role = detect_snmp_vendor_and_role(sys_descr, sys_name)

            cpu_usage = 0.0
            ram_usage = 0.0
            if vendor in VENDOR_METRIC_OIDS:
                cpu_oid, ram_oid = VENDOR_METRIC_OIDS[vendor]
                try:
                    metrics = self._snmp_get(cpu_oid, ram_oid)
                    cpu_val = metrics.get(cpu_oid, "0")
                    ram_val = metrics.get(ram_oid, "0")
                    cpu_usage = float(cpu_val) if cpu_val.replace(".", "", 1).isdigit() else 0.0
                    ram_usage = float(ram_val) if ram_val.replace(".", "", 1).isdigit() else 0.0
                except Exception:
                    pass

            system_info = {
                "sys_name": sys_name,
                "sys_descr": sys_descr,
                "vendor": vendor,
                "role": role,
                "cpu_usage": cpu_usage,
                "ram_usage": ram_usage,
                "uptime_seconds": uptime_ticks // 100,
            }

            if_descr = self._snmp_walk(OID_IF_DESCR)
            if_status = self._snmp_walk(OID_IF_OPER_STATUS)
            if_speed = self._snmp_walk(OID_IF_HIGH_SPEED)

            interfaces: dict[int, dict[str, Any]] = {}
            for idx_str, descr in if_descr.items():
                if not idx_str.isdigit():
                    continue
                if_index = int(idx_str)
                oper_raw = if_status.get(idx_str, "2")
                speed_mbps = int(if_speed.get(idx_str, "1000") or 1000)
                interfaces[if_index] = {
                    "port_index": if_index,
                    "port_name": descr,
                    "status": "up" if oper_raw == "1" else "down",
                    "speed": format_speed_mbps(speed_mbps),
                }

            bridge_to_if = {
                int(bp): int(if_idx)
                for bp, if_idx in self._snmp_walk(OID_DOT1D_BASE_PORT_IFINDEX).items()
                if bp.isdigit() and if_idx.isdigit()
            }

            fdb_entries: list[dict[str, Any]] = []
            seen_mac_port: set[tuple[str, int]] = set()

            for suffix, bp_str in self._snmp_walk(OID_DOT1Q_TP_FDB_PORT).items():
                if not bp_str.isdigit():
                    continue
                vlan_id, mac = parse_mac_from_oid_suffix(suffix, has_vlan_prefix=True)
                if not mac:
                    continue
                bp = int(bp_str)
                if_idx = bridge_to_if.get(bp, bp)
                if (mac, if_idx) in seen_mac_port:
                    continue
                seen_mac_port.add((mac, if_idx))
                vendor_info = lookup_mac_vendor(mac)
                fdb_entries.append(
                    {
                        "mac": mac,
                        "vlan_id": vlan_id,
                        "bridge_port": bp,
                        "port_index": if_idx,
                        "port_name": interfaces.get(if_idx, {}).get("port_name", f"Port-{if_idx}"),
                        "vendor": vendor_info["vendor"],
                        "device_type": vendor_info["device_type"],
                    }
                )

            for suffix, bp_str in self._snmp_walk(OID_DOT1D_TP_FDB_PORT).items():
                if not bp_str.isdigit():
                    continue
                _, mac = parse_mac_from_oid_suffix(suffix, has_vlan_prefix=False)
                if not mac:
                    continue
                bp = int(bp_str)
                if_idx = bridge_to_if.get(bp, bp)
                if (mac, if_idx) in seen_mac_port:
                    continue
                seen_mac_port.add((mac, if_idx))
                vendor_info = lookup_mac_vendor(mac)
                fdb_entries.append(
                    {
                        "mac": mac,
                        "vlan_id": None,
                        "bridge_port": bp,
                        "port_index": if_idx,
                        "port_name": interfaces.get(if_idx, {}).get("port_name", f"Port-{if_idx}"),
                        "vendor": vendor_info["vendor"],
                        "device_type": vendor_info["device_type"],
                    }
                )

            lldp_sys = self._snmp_walk(OID_LLDP_REM_SYS_NAME)
            lldp_port = self._snmp_walk(OID_LLDP_REM_PORT_ID)
            lldp_neighbors: list[dict[str, Any]] = []
            for suffix, rem_name in lldp_sys.items():
                parts = suffix.split(".")
                local_port = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else None
                lldp_neighbors.append(
                    {
                        "local_port_index": local_port,
                        "remote_sys_name": rem_name,
                        "remote_port_id": lldp_port.get(suffix, ""),
                    }
                )

            return {
                "host": self.host,
                "is_online": True,
                "system": system_info,
                "interfaces": list(interfaces.values()),
                "mac_table": fdb_entries,
                "lldp_neighbors": lldp_neighbors,
            }
        except Exception as exc:
            return {
                "host": self.host,
                "is_online": False,
                "error": str(exc),
                "system": None,
                "interfaces": [],
                "mac_table": [],
                "lldp_neighbors": [],
            }
