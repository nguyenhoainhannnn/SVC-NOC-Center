from functools import lru_cache
import re
from typing import TypedDict


class MacVendorResult(TypedDict):
    mac: str
    oui: str
    vendor: str
    device_type: str


# shortcut: built-in OUI table covers common NOC/CCTV/office vendors, extend or load IEEE oui.txt when full 35k+ prefix coverage is needed
OUI_TABLE: dict[str, tuple[str, str]] = {
    # Hikvision (Cameras / NVRs / Switches)
    "001212": ("Hikvision", "camera"),
    "1868CB": ("Hikvision", "camera"),
    "2857BE": ("Hikvision", "camera"),
    "4419B6": ("Hikvision", "camera"),
    "4C0F6E": ("Hikvision", "nvr"),
    "54C415": ("Hikvision", "camera"),
    "64DB8B": ("Hikvision", "camera"),
    "8048A5": ("Hikvision", "nvr"),
    "A41437": ("Hikvision", "camera"),
    "BCAD28": ("Hikvision", "camera"),
    "C056E3": ("Hikvision", "camera"),
    "C42F90": ("Hikvision", "camera"),
    "E0508B": ("Hikvision", "camera"),
    # Dahua
    "38AF29": ("Dahua", "camera"),
    "3CEF8C": ("Dahua", "camera"),
    "9002A9": ("Dahua", "nvr"),
    # MikroTik
    "000C42": ("MikroTik", "router"),
    "085531": ("MikroTik", "router"),
    "18FD74": ("MikroTik", "router"),
    "2CC81B": ("MikroTik", "router"),
    "488F5A": ("MikroTik", "router"),
    "4C5E0C": ("MikroTik", "router"),
    "64D154": ("MikroTik", "router"),
    "744D28": ("MikroTik", "router"),
    "B869F4": ("MikroTik", "router"),
    "C4AD34": ("MikroTik", "router"),
    "DC2C6E": ("MikroTik", "router"),
    "E48D8C": ("MikroTik", "router"),
    # Ruijie / Reyee
    "001AA9": ("Ruijie", "managed_switch"),
    "00D0F8": ("Ruijie", "managed_switch"),
    "300D9E": ("Ruijie", "ap"),
    "58696C": ("Ruijie", "managed_switch"),
    "70D931": ("Ruijie", "ap"),
    "ACC662": ("Ruijie", "managed_switch"),
    "EC6CB5": ("Ruijie", "managed_switch"),
    # Cisco
    "00000C": ("Cisco", "managed_switch"),
    "001B54": ("Cisco", "managed_switch"),
    "002584": ("Cisco", "managed_switch"),
    "34DBFD": ("Cisco", "managed_switch"),
    "58AC78": ("Cisco", "managed_switch"),
    "F04A02": ("Cisco", "router"),
    # DrayTek (Vigor Routers / APs)
    "001DAA": ("DrayTek", "router"),
    "00507F": ("DrayTek", "router"),
    "1449BC": ("DrayTek", "router"),
    "EC43F6": ("DrayTek", "router"),
    # Fortinet (FortiGate / FortiSwitch / FortiAP)
    "00090F": ("Fortinet", "router"),
    "085B0E": ("Fortinet", "router"),
    "704CA5": ("Fortinet", "router"),
    "906CAC": ("Fortinet", "router"),
    "E81CBA": ("Fortinet", "router"),
    # Aruba (HPE Aruba Networking Switches / APs)
    "000B86": ("Aruba", "ap"),
    "001A1E": ("Aruba", "ap"),
    "00246C": ("Aruba", "ap"),
    "186472": ("Aruba", "managed_switch"),
    "204C03": ("Aruba", "managed_switch"),
    "24DEC6": ("Aruba", "ap"),
    "6C8B2F": ("Aruba", "managed_switch"),
    "94B40F": ("Aruba", "ap"),
    "D8C7C8": ("Aruba", "ap"),
    # Ubiquiti
    "24A43C": ("Ubiquiti", "ap"),
    "44D9E7": ("Ubiquiti", "ap"),
    "7483C2": ("Ubiquiti", "ap"),
    "802AA8": ("Ubiquiti", "ap"),
    "F09FC2": ("Ubiquiti", "ap"),
    # TP-Link
    "14CF92": ("TP-Link", "ap"),
    "50C7BF": ("TP-Link", "ap"),
    "60E327": ("TP-Link", "ap"),
    "98DAC4": ("TP-Link", "managed_switch"),
    "EC086B": ("TP-Link", "ap"),
    # Tenda
    "0495E6": ("Tenda", "ap"),
    "C83A35": ("Tenda", "ap"),
    "D83214": ("Tenda", "ap"),
    # Mercury (Consumer Router / AP)
    "388345": ("Mercury", "ap"),
    "8C210A": ("Mercury", "ap"),
    "DCFE18": ("Mercury", "ap"),
    # Apple
    "0017F2": ("Apple", "endpoint"),
    "28CFDA": ("Apple", "endpoint"),
    "3C0630": ("Apple", "endpoint"),
    "A483E7": ("Apple", "endpoint"),
    "F01898": ("Apple", "endpoint"),
    # Gigabyte / PC / Server NICs
    "1C6F65": ("Gigabyte", "endpoint"),
    "74D435": ("Gigabyte", "endpoint"),
    "B42E99": ("Gigabyte", "endpoint"),
    "E0D55E": ("Gigabyte", "endpoint"),
    "00155D": ("Microsoft Hyper-V", "endpoint"),
    "005056": ("VMware", "endpoint"),
    "001B21": ("Intel", "endpoint"),
    "00E04C": ("Realtek", "endpoint"),
}


def normalize_mac(mac: str) -> str:
    hex_chars = re.sub(r"[^0-9A-Fa-f]", "", mac or "").upper()
    if len(hex_chars) != 12:
        return (mac or "").strip().upper()
    return ":".join(hex_chars[i : i + 2] for i in range(0, 12, 2))


@lru_cache(maxsize=4096)
def lookup_mac_vendor(mac: str) -> MacVendorResult:
    normalized = normalize_mac(mac)
    hex_chars = normalized.replace(":", "")
    oui = hex_chars[:6] if len(hex_chars) >= 6 else ""
    vendor, device_type = OUI_TABLE.get(oui, ("Unknown", "endpoint"))
    return {
        "mac": normalized,
        "oui": oui,
        "vendor": vendor,
        "device_type": device_type,
    }
