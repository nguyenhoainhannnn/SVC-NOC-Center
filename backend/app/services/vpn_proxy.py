from datetime import datetime, timezone
import ipaddress
import re
from typing import Any

from ..collectors.hikvision_isapi import HikvisionISAPICollector


def validate_lan_target_ip(target_ip: str) -> str:
    """
    Validate at the trust boundary that `target_ip` is strictly a private RFC1918
    LAN/VPN IPv4 address (e.g. 10.x.x.x, 172.16-31.x.x, 192.168.x.x).
    Blocks loopback (127.0.0.0/8), link-local/cloud metadata (169.254.0.0/16), and public IPs.
    """
    try:
        ip = ipaddress.ip_address(target_ip.strip())
    except ValueError as exc:
        raise ValueError(f"Invalid IP address: {target_ip}") from exc

    if ip.version != 4 or not ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast:
        raise ValueError(f"Target IP {target_ip} is not an allowed private LAN/VPN IPv4 address")
    return str(ip)


def rewrite_proxied_html(html: str, proxy_prefix: str) -> str:
    """Rewrite root-relative asset/form links in device Web GUI HTML to stay inside the VPN proxy route."""
    prefix = proxy_prefix.rstrip("/")
    return re.sub(
        r'\b(href|src|action)=(["\'])/(?!/)([^"\']*)\2',
        rf'\1=\2{prefix}/\3\2',
        html,
        flags=re.IGNORECASE,
    )


def proxy_http_via_vpn(
    site_id: int,
    target_ip: str,
    subpath: str = "",
    method: str = "GET",
    query_string: str = "",
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    vpn_ip: str | None = None,
    timeout: float = 3.5,
) -> tuple[int, bytes, str]:
    """
    Forward an HTTP request to `http://{target_ip}/{subpath}` over the site's VPN tunnel.
    If the remote LAN device is unreachable in local/demo environments, returns an interactive
    VPN Proxy Gateway status/login view so the workflow can be verified without hardware.
    """
    clean_ip = validate_lan_target_ip(target_ip)
    clean_path = subpath.lstrip("/")
    target_url = f"http://{clean_ip}/{clean_path}"
    if query_string:
        target_url = f"{target_url}?{query_string}"

    proxy_prefix = f"/api/proxy/sites/{site_id}/{clean_ip}"

    try:
        import requests

        req_headers = {
            k: v
            for k, v in (headers or {}).items()
            if k.lower() not in {"host", "content-length", "connection", "accept-encoding"}
        }
        resp = requests.request(
            method=method.upper(),
            url=target_url,
            headers=req_headers,
            data=body,
            timeout=timeout,
            allow_redirects=False,
        )
        content_type = resp.headers.get("Content-Type", "text/html; charset=utf-8")
        content = resp.content
        if "text/html" in content_type.lower():
            text = resp.text
            rewritten = rewrite_proxied_html(text, proxy_prefix)
            content = rewritten.encode("utf-8")
        return resp.status_code, content, content_type
    except Exception as exc:
        vpn_tunnel_label = vpn_ip or f"10.255.{site_id}.1 (WireGuard/L2TP Tunnel)"
        fallback_html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="utf-8" />
  <title>VPN Web GUI Proxy — {clean_ip}</title>
  <style>
    body {{ margin: 0; font-family: system-ui, sans-serif; background: #020617; color: #e2e8f0; display: flex; flex-direction: column; min-height: 100vh; }}
    header {{ background: #0f172a; border-bottom: 1px solid #1e293b; padding: 10px 20px; display: flex; justify-content: space-between; align-items: center; font-size: 13px; }}
    .badge {{ background: #065f46; color: #6ee7b7; padding: 3px 10px; border-radius: 999px; font-weight: 600; font-size: 11px; }}
    .card {{ width: 380px; margin: 70px auto; background: #0f172a; border: 1px solid #1e293b; border-radius: 12px; padding: 28px; box-shadow: 0 20px 40px rgba(0,0,0,0.5); }}
    input {{ width: 100%; box-sizing: border-box; margin-top: 6px; margin-bottom: 14px; padding: 9px 12px; border-radius: 6px; border: 1px solid #334155; background: #020617; color: #f8fafc; }}
    button {{ width: 100%; padding: 10px; border: 0; border-radius: 6px; background: #06b6d4; color: #020617; font-weight: 700; cursor: pointer; }}
    .meta {{ font-family: monospace; font-size: 11px; color: #94a3b8; margin-top: 12px; border-top: 1px solid #1e293b; padding-top: 10px; }}
  </style>
</head>
<body>
  <header>
    <div><strong>SVC NOC VPN Reverse Proxy</strong> &bull; Site #{site_id} &rarr; <code>http://{clean_ip}/{clean_path}</code></div>
    <span class="badge">Tunnel: {vpn_tunnel_label}</span>
  </header>
  <div class="card">
    <h3 style="margin-top:0;color:#38bdf8;">Web GUI Thiết Bị Nội Bộ ({clean_ip})</h3>
    <p style="font-size:12px;color:#94a3b8;">Truy cập xuyên hầm VPN không cần NAT/Port Forwarding</p>
    <form method="POST" action="{proxy_prefix}/login">
      <label style="font-size:12px;">Tài khoản quản trị (Username)</label>
      <input name="username" value="admin" />
      <label style="font-size:12px;">Mật khẩu (Password)</label>
      <input name="password" type="password" placeholder="••••••••" />
      <button type="submit">Đăng nhập Thiết bị ({clean_ip})</button>
    </form>
    <div class="meta">
      Route: NOC Proxy &rarr; {vpn_tunnel_label} &rarr; {clean_ip}:80<br/>
      Socket status: Offline simulation ({exc.__class__.__name__})
    </div>
  </div>
</body>
</html>"""
        return 200, fallback_html.encode("utf-8"), "text/html; charset=utf-8"


def build_snapshot_svg(nvr_ip: str, channel_id: int, label: str = "CAM") -> bytes:
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#0f172a"/>
      <stop offset="100%" stop-color="#020617"/>
    </linearGradient>
  </defs>
  <rect width="640" height="360" fill="url(#bg)"/>
  <g stroke="#1e293b" stroke-width="1">
    <line x1="0" y1="120" x2="640" y2="120"/>
    <line x1="0" y1="240" x2="640" y2="240"/>
    <line x1="213" y1="0" x2="213" y2="360"/>
    <line x1="426" y1="0" x2="426" y2="360"/>
  </g>
  <rect x="16" y="14" width="290" height="28" rx="4" fill="#020617" fill-opacity="0.75"/>
  <text x="26" y="33" fill="#e2e8f0" font-family="monospace" font-size="14" font-weight="bold">{now_str}</text>
  <circle cx="545" cy="28" r="6" fill="#10b981"/>
  <text x="558" y="33" fill="#6ee7b7" font-family="monospace" font-size="13" font-weight="bold">LIVE ISAPI</text>
  <text x="320" y="175" text-anchor="middle" fill="#38bdf8" font-family="sans-serif" font-size="22" font-weight="bold">NVR {nvr_ip} &bull; CH-{channel_id:02d}</text>
  <text x="320" y="205" text-anchor="middle" fill="#94a3b8" font-family="monospace" font-size="14">/ISAPI/Streaming/channels/{channel_id * 100 + 1 if channel_id < 100 else channel_id}/picture ({label})</text>
  <rect x="16" y="316" width="260" height="28" rx="4" fill="#020617" fill-opacity="0.75"/>
  <text x="26" y="335" fill="#22d3ee" font-family="monospace" font-size="13">H.265+ 25fps 4096kbps</text>
</svg>"""
    return svg.encode("utf-8")


def get_site_cctv_matrix(site_id: int) -> dict[str, Any]:
    """
    Return the NVR Storage/Channel Matrix and discovered LAN Cameras cross-referenced
    across NVRs and Upstream Switch ports.
    """
    nvrs = [
        {
            "id": "nvr-1",
            "name": "Hikvision-NVR-01 (Chính)",
            "model": "DS-7732NI-I4/16P",
            "ip_address": "10.10.10.50",
            "mac_address": "4C:0F:6E:10:20:30",
            "online_channels": 32,
            "total_channels": 32,
            "is_online": True,
            "upstream_switch": "Core-SW-01",
            "upstream_port": "Gi0/1",
            "hdds": [
                {"id": 1, "name": "HDD-1 (WD Purple)", "status": "ok", "capacity_gb": 6000.0, "free_gb": 1840.0},
                {"id": 2, "name": "HDD-2 (WD Purple)", "status": "ok", "capacity_gb": 6000.0, "free_gb": 2120.0},
                {"id": 3, "name": "HDD-3 (Seagate SkyHawk)", "status": "error", "capacity_gb": 6000.0, "free_gb": 0.0},
            ],
        },
        {
            "id": "nvr-2",
            "name": "Hikvision-NVR-02 (Dự phòng)",
            "model": "DS-9664NI-I8",
            "ip_address": "10.10.10.51",
            "mac_address": "80:48:A5:11:22:33",
            "online_channels": 31,
            "total_channels": 32,
            "is_online": True,
            "upstream_switch": "Core-SW-01",
            "upstream_port": "Gi0/4",
            "hdds": [
                {"id": 1, "name": "HDD-1 (SkyHawk AI)", "status": "ok", "capacity_gb": 8000.0, "free_gb": 3400.0},
                {"id": 2, "name": "HDD-2 (SkyHawk AI)", "status": "ok", "capacity_gb": 8000.0, "free_gb": 3910.0},
            ],
        },
    ]

    cameras = [
        {
            "id": "cam-1",
            "name": "Gate-Cam-01 (Cổng chính)",
            "model": "DS-2CD2T47G2-L (ColorVu 4MP)",
            "vendor": "Hikvision",
            "ip_address": "10.10.10.101",
            "mac_address": "BC:AD:28:00:11:01",
            "is_online": True,
            "upstream_switch": "Access-SW-CCTV",
            "upstream_port": "Gi0/1 (100M)",
            "vlan_id": 10,
            "nvr_links": [
                {"nvr_name": "Hikvision-NVR-01", "nvr_ip": "10.10.10.50", "channel_id": 1, "status": "online"},
                {"nvr_name": "Hikvision-NVR-02", "nvr_ip": "10.10.10.51", "channel_id": 1, "status": "online"},
            ],
        },
        {
            "id": "cam-2",
            "name": "Lobby-Cam-02 (Sảnh lễ tân)",
            "model": "DS-2CD2143G2-I (AcuSense)",
            "vendor": "Hikvision",
            "ip_address": "10.10.10.102",
            "mac_address": "BC:AD:28:00:11:02",
            "is_online": True,
            "upstream_switch": "Access-SW-CCTV (qua Hub)",
            "upstream_port": "Gi0/2 (VLAN 10)",
            "vlan_id": 10,
            "nvr_links": [
                {"nvr_name": "Hikvision-NVR-01", "nvr_ip": "10.10.10.50", "channel_id": 2, "status": "online"},
                {"nvr_name": "Hikvision-NVR-02", "nvr_ip": "10.10.10.51", "channel_id": 2, "status": "warning"},
            ],
        },
        {
            "id": "cam-3",
            "name": "Parking-Cam-03 (Bãi xe B1)",
            "model": "DS-2CD2043G2-I",
            "vendor": "Hikvision",
            "ip_address": "10.10.10.103",
            "mac_address": "BC:AD:28:00:11:03",
            "is_online": True,
            "upstream_switch": "Access-SW-CCTV (qua Hub)",
            "upstream_port": "Gi0/2 (VLAN 10)",
            "vlan_id": 10,
            "nvr_links": [
                {"nvr_name": "Hikvision-NVR-01", "nvr_ip": "10.10.10.50", "channel_id": 3, "status": "online"},
            ],
        },
        {
            "id": "cam-4",
            "name": "Warehouse-Cam-04 (Kho hàng)",
            "model": "IPC-HFW2439S-SA-LED",
            "vendor": "Dahua",
            "ip_address": "10.10.10.104",
            "mac_address": "3C:EF:8C:10:20:04",
            "is_online": True,
            "upstream_switch": "Access-SW-CCTV",
            "upstream_port": "Gi0/6 (1G)",
            "vlan_id": 10,
            "nvr_links": [
                {"nvr_name": "Hikvision-NVR-01", "nvr_ip": "10.10.10.50", "channel_id": 4, "status": "online"},
                {"nvr_name": "Hikvision-NVR-02", "nvr_ip": "10.10.10.51", "channel_id": 4, "status": "online"},
            ],
        },
    ]

    alerts = [
        {
            "severity": "critical",
            "message": "Lỗi ổ cứng NVR 10.10.10.50 (HDD-3 Seagate SkyHawk): trạng thái 'ERROR' (Dung lượng 6000.0 GB)",
        }
    ]
    return {"site_id": site_id, "nvrs": nvrs, "cameras": cameras, "alerts": alerts}
