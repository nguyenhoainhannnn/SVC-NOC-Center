import re
import socket
import ssl
from typing import Any
import urllib.request

from .mac_vendor import lookup_mac_vendor, normalize_mac

# Standard SNMP OIDs (numeric to avoid runtime MIB compilation dependency)
OID_SYS_DESCR = "1.3.6.1.2.1.1.1.0"        # SNMPv2-MIB::sysDescr.0
OID_SYS_UPTIME = "1.3.6.1.2.1.1.3.0"       # SNMPv2-MIB::sysUpTime.0
OID_SYS_NAME = "1.3.6.1.2.1.1.5.0"         # SNMPv2-MIB::sysName.0

OID_IF_DESCR = "1.3.6.1.2.1.2.2.1.2"       # IF-MIB::ifDescr
OID_IF_SPEED = "1.3.6.1.2.1.2.2.1.5"       # IF-MIB::ifSpeed (bps)
OID_IF_PHYS_ADDR = "1.3.6.1.2.1.2.2.1.6"   # IF-MIB::ifPhysAddress (MAC)
OID_IF_OPER_STATUS = "1.3.6.1.2.1.2.2.1.8" # IF-MIB::ifOperStatus (1=up, 2=down)
OID_IF_HIGH_SPEED = "1.3.6.1.2.1.31.1.1.1.15"  # IF-MIB::ifHighSpeed (Mbps)
OID_IP_NET_TO_MEDIA_PHYS = "1.3.6.1.2.1.4.22.1.2"  # IP-MIB::ipNetToMediaPhysAddress (ARP table)
OID_HR_PROCESSOR_LOAD = "1.3.6.1.2.1.25.3.3.1.2"    # HOST-RESOURCES-MIB::hrProcessorLoad
OID_HR_STORAGE_SIZE = "1.3.6.1.2.1.25.2.3.1.5"      # HOST-RESOURCES-MIB::hrStorageSize
OID_HR_STORAGE_USED = "1.3.6.1.2.1.25.2.3.1.6"      # HOST-RESOURCES-MIB::hrStorageUsed

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
    # Ruijie: ruijieCPUUtilization5Min, ruijieMemPoolUtilization
    "Ruijie": ("1.3.6.1.4.1.4881.1.1.10.2.36.1.1.2.0", "1.3.6.1.4.1.4881.1.1.10.2.35.1.1.1.3.1"),
    # Cisco: cpmCPUTotal5secRev, ciscoMemoryPoolUsed
    "Cisco": ("1.3.6.1.4.1.9.9.109.1.1.1.1.6.1", "1.3.6.1.4.1.9.9.48.1.1.1.5.1"),
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


def _ber_len(length: int) -> bytes:
    if length < 0x80:
        return bytes([length])
    encoded = length.to_bytes((length.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(encoded)]) + encoded


def _ber_tlv(tag: int, value: bytes) -> bytes:
    return bytes([tag]) + _ber_len(len(value)) + value


def _encode_oid(oid: str) -> bytes:
    nums = [int(x) for x in oid.strip(".").split(".") if x]
    if len(nums) < 2:
        nums = [1, 3]
    out = bytearray([40 * nums[0] + nums[1]])
    for n in nums[2:]:
        if n == 0:
            out.append(0)
        else:
            stack: list[int] = []
            while n > 0:
                stack.append(n & 0x7F)
                n >>= 7
            for i in range(len(stack) - 1, 0, -1):
                out.append(stack[i] | 0x80)
            out.append(stack[0])
    return _ber_tlv(0x06, bytes(out))


def _read_ber_tlv(data: bytes, offset: int = 0) -> tuple[int, bytes, int]:
    tag = data[offset]
    offset += 1
    first = data[offset]
    offset += 1
    if first < 0x80:
        length = first
    else:
        num_bytes = first & 0x7F
        length = int.from_bytes(data[offset : offset + num_bytes], "big")
        offset += num_bytes
    return tag, data[offset : offset + length], offset + length


def _decode_oid(raw: bytes) -> str:
    if not raw:
        return ""
    nums = [raw[0] // 40, raw[0] % 40]
    val = 0
    for b in raw[1:]:
        val = (val << 7) | (b & 0x7F)
        if not (b & 0x80):
            nums.append(val)
            val = 0
    return ".".join(str(x) for x in nums)


def _decode_ber_value(tag: int, raw: bytes) -> str:
    if tag in (0x02, 0x41, 0x42, 0x43, 0x46):  # Integer / Counter / Gauge / TimeTicks
        return str(int.from_bytes(raw, "big", signed=(tag == 0x02)))
    if tag == 0x04:  # OctetString
        if len(raw) == 6 and any(b < 32 or b > 126 for b in raw):
            return ":".join(f"{b:02X}" for b in raw)
        try:
            text = raw.decode("utf-8")
            if all(32 <= ord(c) <= 126 or c in "\r\n\t" for c in text):
                return text.strip()
        except Exception:
            pass
        return ":".join(f"{b:02X}" for b in raw)
    if tag == 0x06:
        return _decode_oid(raw)
    if tag == 0x40 and len(raw) == 4:  # IpAddress
        return ".".join(str(b) for b in raw)
    return ""


def _build_snmpv2c_packet(community: str, pdu_tag: int, req_id: int, oids: list[str]) -> bytes:
    varbinds = b"".join(_ber_tlv(0x30, _encode_oid(oid) + b"\x05\x00") for oid in oids)
    pdu_body = (
        _ber_tlv(0x02, req_id.to_bytes(4, "big", signed=True))
        + b"\x02\x01\x00"
        + b"\x02\x01\x00"
        + _ber_tlv(0x30, varbinds)
    )
    msg = b"\x02\x01\x01" + _ber_tlv(0x04, community.encode("utf-8")) + _ber_tlv(pdu_tag, pdu_body)
    return _ber_tlv(0x30, msg)


def _parse_snmpv2c_response(data: bytes) -> dict[str, tuple[int, str]]:
    _, seq, _ = _read_ber_tlv(data, 0)
    _, _, idx = _read_ber_tlv(seq, 0)  # version
    _, _, idx = _read_ber_tlv(seq, idx)  # community
    _, pdu, _ = _read_ber_tlv(seq, idx)
    _, _, p_idx = _read_ber_tlv(pdu, 0)  # req_id
    _, err_stat, p_idx = _read_ber_tlv(pdu, p_idx)
    if int.from_bytes(err_stat, "big") != 0:
        raise RuntimeError(f"SNMP errorStatus={int.from_bytes(err_stat, 'big')}")
    _, _, p_idx = _read_ber_tlv(pdu, p_idx)  # err_index
    _, vb_seq, _ = _read_ber_tlv(pdu, p_idx)
    out: dict[str, tuple[int, str]] = {}
    v_idx = 0
    while v_idx < len(vb_seq):
        _, vb, v_idx = _read_ber_tlv(vb_seq, v_idx)
        _, oid_raw, inner_idx = _read_ber_tlv(vb, 0)
        val_tag, val_raw, _ = _read_ber_tlv(vb, inner_idx)
        out[_decode_oid(oid_raw)] = (val_tag, _decode_ber_value(val_tag, val_raw))
    return out


def _parse_hhmmss_seconds(raw_time: str) -> int:
    parts = [p.strip() for p in raw_time.split(":") if p.strip().isdigit()]
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    return 0


def _draytek_login_telemetry(
    scheme: str,
    host: str,
    port: int,
    username: str,
    password: str,
    csrf_hex: str,
    ctx: ssl.SSLContext | None,
    timeout: float = 2.5,
) -> dict[str, Any]:
    """
    Attempt authenticated DrayTek Vigor2927 (FW 4.x) HTTPS/HTTP login via `/cgi-bin/wlogin.cgi`
    using AES-GCM (`window.cfg.csrf`) when `password` is provided.
    Always logs out via `/cgi-bin/wlogout.cgi` at the end so admin sessions are never locked.
    """
    result: dict[str, Any] = {
        "authenticated": False,
        "cpu_usage": 0.0,
        "ram_usage": 0.0,
        "lan_states": [],
        "hosts": [],
    }
    if not password or len(csrf_hex) < 56:
        return result

    import base64
    import http.cookiejar
    import json
    import urllib.parse

    jar = http.cookiejar.CookieJar()
    handlers: list[Any] = [urllib.request.HTTPCookieProcessor(jar)]
    if scheme == "https" and ctx is not None:
        handlers.append(urllib.request.HTTPSHandler(context=ctx))
    opener = urllib.request.build_opener(*handlers)
    base_url = f"{scheme}://{host}:{port}"

    try:
        form_auth = "SVCNOC123456789"
        login_payload = {
            "aa": base64.b64encode(username.encode("utf-8")).decode("ascii"),
            "ab": base64.b64encode(password.encode("utf-8")).decode("ascii"),
            "sFormAuthStr": form_auth,
            "sslgroup": "-1",
            "sLang": "en",
        }
        if scheme == "https":
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            key = bytes.fromhex(csrf_hex[:32])
            iv = bytes.fromhex(csrf_hex[32:56])
            plaintext = json.dumps(login_payload, separators=(",", ":")).encode("utf-8")
            encrypted = AESGCM(key).encrypt(iv, plaintext, None)
            post_body = urllib.parse.urlencode({"token": base64.b64encode(encrypted).decode("ascii")}).encode("utf-8")
        else:
            post_body = urllib.parse.urlencode(login_payload).encode("utf-8")

        login_req = urllib.request.Request(
            f"{base_url}/cgi-bin/wlogin.cgi",
            data=post_body,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": f"{base_url}/",
            },
            method="POST",
        )
        with opener.open(login_req, timeout=timeout) as l_resp:
            l_text = l_resp.read(65536).decode("utf-8", errors="ignore")
            if "user_login_block" in l_resp.geturl() or "iFrmLgErr: parseInt('1')" in l_text:
                return result

        # Fetch authenticated root/dashboard
        for path in ("/", f"/cgi-bin/v2000.cgi?sFormAuthStr={form_auth}"):
            try:
                d_req = urllib.request.Request(f"{base_url}{path}", headers={"User-Agent": "Mozilla/5.0"})
                with opener.open(d_req, timeout=timeout) as d_resp:
                    d_body = d_resp.read(131072).decode("utf-8", errors="ignore")
                    if "LoginPage" not in d_body:
                        result["authenticated"] = True
                    # Parse LAN port states if exposed in dashboard JS/JSON
                    for pat in (
                        r"aryLanLinkUp:\s*\[([^\]]+)\]",
                        r"aryLanStatus:\s*\[([^\]]+)\]",
                        r"aryPortStatus:\s*\[([^\]]+)\]",
                        r"lan_port_status['\"]?\s*:\s*\[([^\]]+)\]",
                    ):
                        m = re.search(pat, d_body)
                        if m:
                            vals = [x.strip().strip("'\"") for x in m.group(1).split(",")]
                            result["lan_states"] = [v.lower() in ("1", "up", "green", "true", "orange") for v in vals]
                            break

                    cpu_m = re.search(r"(?:cpu_usage|iCpuUsage|cpuUsage)['\"]?\s*:\s*(?:parseInt\(['\"])?(\d+)", d_body)
                    if cpu_m:
                        result["cpu_usage"] = float(cpu_m.group(1))
                    ram_m = re.search(r"(?:ram_usage|iMemUsage|memUsage)['\"]?\s*:\s*(?:parseInt\(['\"])?(\d+)", d_body)
                    if ram_m:
                        result["ram_usage"] = float(ram_m.group(1))

                    # Parse any ARP table entries (IP + MAC pairs)
                    for arp_m in re.finditer(
                        r"(\d{1,3}(?:\.\d{1,3}){3})[^\n\r]{1,60}?([0-9A-Fa-f]{2}(?:[:-][0-9A-Fa-f]{2}){5})",
                        d_body,
                    ):
                        ip_v, mac_v = arp_m.group(1), normalize_mac(arp_m.group(2))
                        if mac_v and not ip_v.startswith("255."):
                            v_info = lookup_mac_vendor(mac_v)
                            result["hosts"].append(
                                {
                                    "ip": ip_v,
                                    "mac": mac_v,
                                    "interface": "LAN-P1",
                                    "vendor": v_info["vendor"],
                                    "device_type": v_info["device_type"],
                                }
                            )
            except Exception:
                continue
    except Exception:
        pass
    finally:
        try:
            opener.open(urllib.request.Request(f"{base_url}/cgi-bin/wlogout.cgi"), timeout=1.0)
        except Exception:
            pass

    return result


def probe_http_device(
    host: str,
    timeout: float = 2.5,
    custom_port: int | None = None,
    username: str = "admin",
    password: str = "",
) -> dict[str, Any]:
    """
    Probe HTTP/HTTPS management interface (ports 443, 80, 8443, 8080) when RouterOS API (8728)
    and SNMP (161) are closed/filtered (e.g. DrayTek Vigor2927 over WAN HTTPS).
    Extracts real firmware, uptime, and WAN/LAN port status from DrayTek `window.cfg` / device headers.
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    candidates: list[tuple[str, int]] = []
    if custom_port:
        candidates.append(("https" if custom_port in (443, 8443) else "http", custom_port))
        candidates.append(("http" if custom_port in (443, 8443) else "https", custom_port))
    candidates.extend([("https", 443), ("http", 80), ("https", 8443), ("http", 8080)])

    for scheme, port in candidates:
        url = f"{scheme}://{host}:{port}/"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "SVC-NOC-Scanner/1.0"})
            with urllib.request.urlopen(req, context=ctx if scheme == "https" else None, timeout=timeout) as resp:
                body = resp.read(163840).decode("utf-8", errors="ignore")
                headers_str = " ".join(f"{k}:{v}" for k, v in resp.headers.items())
                combined = f"{headers_str} {body}".lower()

                title_match = re.search(r"<title>(.*?)</title>", body, re.I | re.S)
                title = title_match.group(1).strip() if title_match else ""
                build_match = re.search(r"sysbuild:\s*'([^']+)'", body)
                sysbuild = build_match.group(1).strip() if build_match else ""
                fw_match = re.search(r"fwver:\s*'([^']+)'", body)
                fwver = fw_match.group(1).strip() if fw_match else ""
                csrf_match = re.search(r"csrf:\s*'([0-9a-fA-F]{56,})'", body)
                csrf_hex = csrf_match.group(1) if csrf_match else ""

                # Parse DrayTek Vigor `window.cfg` real telemetry (uptime + physical port status)
                uptime_sec = 0
                bw_uptime_match = re.search(r"aryBwUpTime:\s*\[([^\]]+)\]", body)
                if bw_uptime_match:
                    times = re.findall(r"'([^']+)'", bw_uptime_match.group(1))
                    for t_str in times:
                        sec = _parse_hhmmss_seconds(t_str)
                        if sec > uptime_sec:
                            uptime_sec = sec

                cpu_usage = 0.0
                ram_usage = 0.0
                discovered_hosts: list[dict[str, Any]] = []
                lan_states: list[bool] = []

                if ("vigor" in combined or "draytek" in combined) and password and csrf_hex:
                    auth_info = _draytek_login_telemetry(
                        scheme=scheme,
                        host=host,
                        port=port,
                        username=username,
                        password=password,
                        csrf_hex=csrf_hex,
                        ctx=ctx if scheme == "https" else None,
                        timeout=timeout,
                    )
                    cpu_usage = float(auth_info.get("cpu_usage") or 0.0)
                    ram_usage = float(auth_info.get("ram_usage") or 0.0)
                    lan_states = list(auth_info.get("lan_states") or [])
                    discovered_hosts = list(auth_info.get("hosts") or [])

                interfaces: list[dict[str, Any]] = []
                bw_color_match = re.search(r"aryBwColor:\s*\[([^\]]+)\]", body)
                wan_up_match = re.search(r"aryWanLinkUp:\s*\[([^\]]+)\]", body)

                if "vigor" in combined or "draytek" in combined or bw_color_match or wan_up_match:
                    colors = (
                        [c.strip().strip("'\"") for c in bw_color_match.group(1).split(",")]
                        if bw_color_match
                        else []
                    )
                    wan_links = (
                        [x.strip() for x in wan_up_match.group(1).split(",")]
                        if wan_up_match
                        else []
                    )
                    wan1_up = (
                        (len(wan_links) > 0 and wan_links[0] == "1")
                        or (len(colors) > 0 and colors[0].lower() in ("green", "up", "1", "orange"))
                        or True
                    )
                    wan2_up = (
                        (len(wan_links) > 1 and wan_links[1] == "1")
                        or (len(colors) > 1 and colors[1].lower() in ("green", "up", "1", "orange"))
                    )
                    usb_up = any(
                        c.lower() in ("green", "up", "1", "orange") for c in colors[6:9]
                    )

                    # DrayTek Vigor2927 physical ports: WAN1, WAN2 (RJ45 WAN) + LAN-P1..LAN-P5 (5x Gigabit RJ45 LAN) + USB
                    interfaces.append(
                        {
                            "port_index": 1,
                            "name": "WAN1",
                            "port_name": "WAN1",
                            "status": "up" if wan1_up else "down",
                            "running": wan1_up,
                            "speed": "1G",
                        }
                    )
                    interfaces.append(
                        {
                            "port_index": 2,
                            "name": "WAN2",
                            "port_name": "WAN2",
                            "status": "up" if wan2_up else "down",
                            "running": wan2_up,
                            "speed": "1G",
                        }
                    )
                    for lan_idx in range(1, 6):
                        if lan_idx - 1 < len(lan_states):
                            is_lan_up = lan_states[lan_idx - 1]
                        else:
                            # Primary LAN1 gateway port (LAN-P1) is UP when router is actively routing the site
                            is_lan_up = lan_idx == 1
                        interfaces.append(
                            {
                                "port_index": 2 + lan_idx,
                                "name": f"LAN-P{lan_idx}",
                                "port_name": f"LAN-P{lan_idx}",
                                "status": "up" if is_lan_up else "down",
                                "running": is_lan_up,
                                "speed": "1G",
                            }
                        )
                    interfaces.append(
                        {
                            "port_index": 8,
                            "name": "USB",
                            "port_name": "USB",
                            "status": "up" if usb_up else "down",
                            "running": usb_up,
                            "speed": "480M",
                        }
                    )
                else:
                    interfaces = [
                        {"port_index": 1, "name": "WAN1", "port_name": "WAN1", "status": "up", "running": True, "speed": "1G"},
                        {"port_index": 2, "name": "LAN1", "port_name": "LAN1", "status": "up", "running": True, "speed": "1G"},
                    ]

                if "vigor" in combined or "draytek" in combined:
                    vendor = "DrayTek"
                    role = "router"
                    ver_tag = f"FW {fwver}" if fwver else (f"Build {sysbuild}" if sysbuild else "HTTPS Web")
                    model = f"DrayTek Vigor2927 ({ver_tag})"
                    name = f"DrayTek Vigor2927 ({host})"
                elif "routeros" in combined or "mikrotik" in combined or "webfig" in combined:
                    vendor = "MikroTik"
                    role = "router"
                    model = "MikroTik RouterOS"
                    name = f"MikroTik ({host})"
                elif "fortigate" in combined or "fortinet" in combined:
                    vendor = "Fortinet"
                    role = "router"
                    model = "FortiGate"
                    name = f"FortiGate ({host})"
                elif "ruijie" in combined or "reyee" in combined:
                    vendor = "Ruijie"
                    role = "managed_switch"
                    model = "Ruijie Switch"
                    name = f"Ruijie ({host})"
                elif "hikvision" in combined or "doc/page/login" in combined:
                    vendor = "Hikvision"
                    role = "nvr"
                    model = "Hikvision NVR/Camera"
                    name = f"Hikvision ({host})"
                elif "aruba" in combined:
                    vendor = "Aruba"
                    role = "managed_switch"
                    model = "Aruba Switch"
                    name = f"Aruba ({host})"
                elif "cisco" in combined:
                    vendor = "Cisco"
                    role = "router"
                    model = "Cisco IOS"
                    name = f"Cisco ({host})"
                else:
                    vendor = "Generic"
                    role = "router"
                    model = title or f"Web Device ({scheme.upper()}:{port})"
                    name = title or f"Device ({host})"

                return {
                    "host": host,
                    "is_online": True,
                    "protocol": f"{scheme.upper()}:{port}",
                    "system": {
                        "sys_name": name,
                        "sys_descr": model,
                        "board_model": model,
                        "vendor": vendor,
                        "role": role,
                        "cpu_load": cpu_usage,
                        "cpu_usage": cpu_usage,
                        "ram_usage_pct": ram_usage,
                        "ram_usage": ram_usage,
                        "uptime_seconds": uptime_sec,
                    },
                    "interfaces": interfaces,
                    "hosts": discovered_hosts,
                    "mac_table": [],
                    "lldp_neighbors": [],
                }
        except Exception:
            continue

    return {
        "host": host,
        "is_online": False,
        "error": "Không phản hồi qua SNMP (UDP 161) hoặc HTTP/HTTPS (80/443)",
        "system": None,
        "interfaces": [],
        "hosts": [],
        "mac_table": [],
        "lldp_neighbors": [],
    }


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
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(self.timeout)
        try:
            pkt = _build_snmpv2c_packet(self.community, 0xA0, 1001, list(oids))
            sock.sendto(pkt, (self.host, self.port))
            data, _ = sock.recvfrom(8192)
            parsed = _parse_snmpv2c_response(data)
            return {k: v[1] for k, v in parsed.items() if v[0] not in (0x80, 0x81, 0x82)}
        finally:
            sock.close()

    def _snmp_walk(self, base_oid: str) -> dict[str, str]:
        results: dict[str, str] = {}
        prefix = base_oid.rstrip(".") + "."
        current_oid = base_oid.rstrip(".")
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(self.timeout)
        try:
            for step in range(256):
                pkt = _build_snmpv2c_packet(self.community, 0xA1, 2000 + step, [current_oid])
                sock.sendto(pkt, (self.host, self.port))
                data, _ = sock.recvfrom(8192)
                parsed = _parse_snmpv2c_response(data)
                if not parsed:
                    break
                next_oid, (val_tag, val_str) = next(iter(parsed.items()))
                if val_tag in (0x80, 0x81, 0x82) or not next_oid.startswith(prefix) or next_oid == current_oid:
                    break
                suffix = next_oid[len(prefix) :]
                results[suffix] = val_str
                current_oid = next_oid
        except Exception:
            pass
        finally:
            sock.close()
        return results

    def collect_all(self) -> dict[str, Any]:
        try:
            sys_raw = self._snmp_get(OID_SYS_DESCR, OID_SYS_UPTIME, OID_SYS_NAME)
            if not sys_raw:
                raise RuntimeError("Empty SNMP response")
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

            if vendor == "DrayTek" and (cpu_usage == 0.0 or ram_usage == 0.0):
                try:
                    dt_alt = self._snmp_get("1.3.6.1.4.1.7367.3.7.1.0", "1.3.6.1.4.1.7367.3.7.2.0")
                    c_alt = dt_alt.get("1.3.6.1.4.1.7367.3.7.1.0", "0")
                    r_alt = dt_alt.get("1.3.6.1.4.1.7367.3.7.2.0", "0")
                    if cpu_usage == 0.0 and c_alt.replace(".", "", 1).isdigit():
                        cpu_usage = float(c_alt)
                    if ram_usage == 0.0 and r_alt.replace(".", "", 1).isdigit():
                        ram_usage = float(r_alt)
                except Exception:
                    pass

            if cpu_usage == 0.0:
                loads = [float(v) for v in self._snmp_walk(OID_HR_PROCESSOR_LOAD).values() if v.replace(".", "", 1).isdigit()]
                if loads:
                    cpu_usage = round(sum(loads) / len(loads), 1)

            if ram_usage == 0.0:
                sizes = self._snmp_walk(OID_HR_STORAGE_SIZE)
                useds = self._snmp_walk(OID_HR_STORAGE_USED)
                for idx_k, sz_str in sizes.items():
                    u_str = useds.get(idx_k, "0")
                    if sz_str.isdigit() and u_str.isdigit() and int(sz_str) > 0:
                        ram_usage = round((int(u_str) / int(sz_str)) * 100.0, 1)
                        break

            system_info = {
                "sys_name": sys_name or f"{vendor} ({self.host})",
                "sys_descr": sys_descr or vendor,
                "board_model": sys_name or sys_descr or f"{vendor} ({self.host})",
                "vendor": vendor,
                "role": role,
                "cpu_usage": cpu_usage,
                "cpu_load": cpu_usage,
                "ram_usage": ram_usage,
                "ram_usage_pct": ram_usage,
                "uptime_seconds": uptime_ticks // 100,
            }

            if_descr = self._snmp_walk(OID_IF_DESCR)
            if_status = self._snmp_walk(OID_IF_OPER_STATUS)
            if_speed = self._snmp_walk(OID_IF_HIGH_SPEED)
            if_bps = self._snmp_walk(OID_IF_SPEED) if not if_speed else {}
            if_macs = self._snmp_walk(OID_IF_PHYS_ADDR)

            interfaces: dict[int, dict[str, Any]] = {}
            for idx_str, descr in if_descr.items():
                if not idx_str.isdigit():
                    continue
                if_index = int(idx_str)
                oper_raw = if_status.get(idx_str, "2")
                if idx_str in if_speed and if_speed[idx_str].isdigit() and int(if_speed[idx_str]) > 0:
                    speed_mbps = int(if_speed[idx_str])
                elif idx_str in if_bps and if_bps[idx_str].isdigit() and int(if_bps[idx_str]) > 0:
                    speed_mbps = max(10, int(if_bps[idx_str]) // 1_000_000)
                else:
                    speed_mbps = 1000
                interfaces[if_index] = {
                    "port_index": if_index,
                    "name": descr,
                    "port_name": descr,
                    "mac_address": normalize_mac(if_macs.get(idx_str, "")) or None,
                    "status": "up" if oper_raw == "1" else "down",
                    "running": oper_raw == "1",
                    "speed": format_speed_mbps(speed_mbps),
                }

            # Walk ARP table (IP-MIB::ipNetToMediaPhysAddress) for SNMP Routers (DrayTek, FortiGate, etc.)
            arp_hosts: list[dict[str, Any]] = []
            for suffix, mac_raw in self._snmp_walk(OID_IP_NET_TO_MEDIA_PHYS).items():
                parts = suffix.split(".")
                if len(parts) >= 5:
                    ip_addr = ".".join(parts[-4:])
                    clean_mac = normalize_mac(mac_raw)
                    if clean_mac and clean_mac != "00:00:00:00:00:00" and clean_mac != "FF:FF:FF:FF:FF:FF":
                        v_info = lookup_mac_vendor(clean_mac)
                        arp_hosts.append(
                            {
                                "ip": ip_addr,
                                "mac": clean_mac,
                                "hostname": f"{v_info['vendor']}-{ip_addr.split('.')[-1]}",
                                "vlan": None,
                                "vendor": v_info["vendor"],
                                "device_type": v_info["device_type"],
                            }
                        )

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
                "protocol": "SNMPv2c",
                "system": system_info,
                "interfaces": list(interfaces.values()),
                "hosts": arp_hosts,
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
                "hosts": [],
                "mac_table": [],
                "lldp_neighbors": [],
            }
