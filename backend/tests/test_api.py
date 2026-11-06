import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import ValidationError
from app.models import Alert, DevicePort, NetworkDevice, Site, TopologyEdge
from app.main import SiteCreate, SiteUpdate, get_site_topology
from app.collectors.mac_vendor import lookup_mac_vendor, normalize_mac
from app.collectors.mikrotik_collector import MikroTikCollector, parse_routeros_uptime
from app.collectors.snmp_collector import (
    detect_snmp_vendor_and_role,
    format_speed_mbps,
    parse_mac_from_oid_suffix,
)
from app.services.alert_engine import evaluate_site_alerts
from app.services.topology_builder import UNMANAGED_LABEL, build_site_topology
from app.collectors.hikvision_isapi import HikvisionISAPICollector
from app.services.vpn_proxy import rewrite_proxied_html, validate_lan_target_ip


def test_schema_and_topology():
    tables = {
        Site.__tablename__,
        NetworkDevice.__tablename__,
        DevicePort.__tablename__,
        TopologyEdge.__tablename__,
        Alert.__tablename__,
    }
    assert tables == {"sites", "network_devices", "device_ports", "topology_edges", "alerts"}

    topo = asyncio.run(get_site_topology(1))
    assert topo["site_id"] == 1
    assert isinstance(topo["nodes"], list)
    assert isinstance(topo["edges"], list)


def test_site_models_validation():
    # Valid site create
    payload = SiteCreate(name="Hanoi-DC", subnet="10.20.0.0/24")
    assert payload.name == "Hanoi-DC"
    assert payload.status == "online"
    assert payload.vpn_ip is None

    # Missing required name raises ValidationError
    try:
        SiteCreate(subnet="10.20.0.0/24")  # type: ignore
        assert False, "Should have failed without name"
    except ValidationError:
        pass

    # Partial update model
    update = SiteUpdate(name="DaNang-DC")
    assert update.model_dump(exclude_unset=True) == {"name": "DaNang-DC"}


def test_mac_vendor_lookup():
    assert normalize_mac("00-0c-42-1a-2b-3c") == "00:0C:42:1A:2B:3C"
    result = lookup_mac_vendor("00:0c:42:1a:2b:3c")
    assert result["vendor"] == "MikroTik"
    assert result["device_type"] == "router"

    assert lookup_mac_vendor("00:1D:AA:11:22:33") == {
        "mac": "00:1D:AA:11:22:33",
        "oui": "001DAA",
        "vendor": "DrayTek",
        "device_type": "router",
    }
    assert lookup_mac_vendor("00:09:0F:AA:BB:CC")["vendor"] == "Fortinet"
    assert lookup_mac_vendor("18:64:72:AA:BB:CC") == {
        "mac": "18:64:72:AA:BB:CC",
        "oui": "186472",
        "vendor": "Aruba",
        "device_type": "managed_switch",
    }
    assert detect_snmp_vendor_and_role("DrayTek Vigor2927 Series") == ("DrayTek", "router")
    assert detect_snmp_vendor_and_role("FortiGate-60F v7.2.5") == ("Fortinet", "router")
    assert detect_snmp_vendor_and_role("Aruba JL678A 6100 24G") == ("Aruba", "managed_switch")

    unknown = lookup_mac_vendor("00:00:00:11:22:33")
    assert unknown["vendor"] == "Unknown"


def test_collector_parsers():
    assert parse_routeros_uptime("1d2h30m10s") == 86400 + 7200 + 1800 + 10
    hosts = MikroTikCollector.normalize_arp_and_dhcp(
        arp_rows=[{"address": "10.10.0.101", "mac-address": "bc:ad:28:01:02:03", "interface": "vlan10"}],
        dhcp_rows=[{"address": "10.10.0.101", "mac-address": "BC:AD:28:01:02:03", "host-name": "cam-gate-01"}],
        vlan_rows=[{"name": "vlan10", "vlan-id": 10}],
    )
    assert len(hosts) == 1
    assert hosts[0]["hostname"] == "cam-gate-01"
    assert hosts[0]["vlan"] == 10
    assert hosts[0]["vendor"] == "Hikvision"
    assert hosts[0]["device_type"] == "camera"

    vlan_id, mac = parse_mac_from_oid_suffix("20.0.208.248.10.20.30", has_vlan_prefix=True)
    assert vlan_id == 20
    assert mac == "00:D0:F8:0A:14:1E"
    assert format_speed_mbps(1000) == "1G"


def test_topology_and_alert_engine():
    router_data = {
        "host": "10.10.0.1",
        "is_online": True,
        "system": {"board_model": "CCR2004", "cpu_load": 15.0, "ram_usage_pct": 35.0, "uptime_seconds": 3600},
        "interfaces": [{"name": "ether1", "running": True, "mac_address": "64:D1:54:00:00:01"}],
        "hosts": [
            {"ip": "10.10.10.101", "mac": "BC:AD:28:00:11:01", "hostname": "Gate-Cam-01", "vlan": 10},
            {"ip": "10.10.10.102", "mac": "BC:AD:28:00:11:02", "hostname": "Lobby-Cam-02", "vlan": 10},
            {"ip": "10.10.10.199", "mac": "C8:3A:35:99:88:77", "hostname": "Rogue-Tenda", "vlan": 10},
        ],
    }
    switches_data = [
        {
            "host": "10.10.0.2",
            "mac_address": "00:D0:F8:00:01:01",
            "is_online": True,
            "system": {"sys_name": "Core-SW-01", "vendor": "Ruijie"},
            "interfaces": [
                {"port_index": 2, "port_name": "Gi0/2", "status": "up", "speed": "1G"},
                {"port_index": 24, "port_name": "Te0/24", "status": "up", "speed": "10G"},
            ],
            "mac_table": [{"mac": "64:D1:54:00:00:01", "port_index": 24, "vlan_id": 1}],
            "lldp_neighbors": [{"local_port_index": 2, "remote_sys_name": "Access-SW-01", "remote_port_id": "Gi0/24"}],
        },
        {
            "host": "10.10.0.3",
            "mac_address": "00:D0:F8:00:02:02",
            "is_online": True,
            "system": {"sys_name": "Access-SW-01", "vendor": "Ruijie"},
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
            "lldp_neighbors": [{"local_port_index": 24, "remote_sys_name": "Core-SW-01", "remote_port_id": "Gi0/2"}],
        },
    ]

    resolved = build_site_topology(
        site_id=1,
        router_data=router_data,
        switches_data=switches_data,
        dhcp_pools=[{"vlan_id": 10, "used": 240, "total": 254}],
        cctv_vlans={10},
    )

    roles = [d["role"] for d in resolved["devices"]]
    assert "unmanaged_group" in roles
    assert any(UNMANAGED_LABEL in d["name"] for d in resolved["devices"])
    uplinks = [p for p in resolved["ports"] if p["is_uplink"]]
    assert len(uplinks) >= 4

    # Check alerts: Rogue Tenda on CCTV port + DHCP > 90%
    assert len(resolved["alerts"]) == 2

    # Check >50 devices on a single 1G port rule
    overloaded = evaluate_site_alerts(
        site_id=1,
        port_Attachment_groups=[
            {
                "switch_key": "switch-2",
                "switch_name": "Access-SW-01",
                "port_index": 5,
                "port_name": "Gi0/5",
                "speed": "1G",
                "vlan_id": 20,
                "endpoints": [{"mac": f"00:1B:21:00:00:{i:02X}", "vendor": "Intel"} for i in range(55)],
            }
        ],
    )
    assert len(overloaded) == 1
    assert "55" in overloaded[0]["message"]

    # Ensure offline/unreachable router & switches produce ZERO fabricated devices or edges
    empty_resolved = build_site_topology(
        site_id=1,
        router_data={"host": "10.99.99.1", "is_online": False, "error": "Timeout"},
        switches_data=[{"host": "10.99.99.2", "is_online": False, "error": "SNMP Timeout"}],
    )
    assert empty_resolved["devices"] == []
    assert empty_resolved["edges"] == []
    assert empty_resolved["ports"] == []


def test_hikvision_isapi_and_vpn_proxy():
    sample_hdd_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <hddList xmlns="http://www.hikvision.com/ver20/XMLSchema">
      <hdd><id>1</id><hddName>HDD-1</hddName><status>ok</status><capacity>6144000</capacity><freeSpace>2048000</freeSpace></hdd>
      <hdd><id>2</id><hddName>HDD-2</hddName><status>error</status><capacity>6144000</capacity><freeSpace>0</freeSpace></hdd>
    </hddList>"""
    hdds, alerts = HikvisionISAPICollector.parse_hdd_xml(sample_hdd_xml, nvr_host="10.10.10.50")
    assert len(hdds) == 2
    assert hdds[0]["status"] == "ok"
    assert hdds[1]["status"] == "error"
    assert len(alerts) == 1
    assert alerts[0]["severity"] == "critical"

    sample_channels_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <InputProxyChannelList xmlns="http://www.hikvision.com/ver20/XMLSchema">
      <InputProxyChannel>
        <id>1</id>
        <name>Gate-Cam-01</name>
        <sourceInputPortDescriptor>
          <proxyProtocol>HIKVISION</proxyProtocol>
          <ipAddress>10.10.10.101</ipAddress>
          <managePortNo>8000</managePortNo>
        </sourceInputPortDescriptor>
      </InputProxyChannel>
    </InputProxyChannelList>"""
    sample_status_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <InputProxyChannelStatusList>
      <InputProxyChannelStatus><id>1</id><online>true</online></InputProxyChannelStatus>
    </InputProxyChannelStatusList>"""
    channels = HikvisionISAPICollector.parse_channels_xml(
        sample_channels_xml, sample_status_xml, nvr_host="10.10.10.50", nvr_name="NVR-01"
    )
    assert len(channels) == 1
    assert channels[0]["camera_ip"] == "10.10.10.101"
    assert channels[0]["channel_id"] == 1
    assert channels[0]["online"] is True

    assert validate_lan_target_ip("10.100.1.253") == "10.100.1.253"
    assert validate_lan_target_ip("192.168.1.250") == "192.168.1.250"
    assert validate_lan_target_ip("14.224.195.129") == "14.224.195.129"
    for blocked_ip in ("127.0.0.1", "169.254.169.254", "192.168.10.255"):
        try:
            validate_lan_target_ip(blocked_ip)
            assert False, f"Should have rejected {blocked_ip}"
        except ValueError:
            pass

    rewritten = rewrite_proxied_html('<a href="/doc/page/login.asp">', "/api/proxy/sites/1/10.100.1.253")
    assert rewritten == '<a href="/api/proxy/sites/1/10.100.1.253/doc/page/login.asp">'


if __name__ == "__main__":
    test_schema_and_topology()
    test_site_models_validation()
    test_mac_vendor_lookup()
    test_collector_parsers()
    test_topology_and_alert_engine()
    test_hikvision_isapi_and_vpn_proxy()
    print("All tests passed.")
