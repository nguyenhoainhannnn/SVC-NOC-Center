from typing import Any
import xml.etree.ElementTree as ET


def _strip_ns(xml_text: str) -> ET.Element:
    """Parse XML and strip namespace prefixes from all tags for clean ElementTree queries."""
    root = ET.fromstring(xml_text.strip())
    for elem in root.iter():
        if "}" in elem.tag:
            elem.tag = elem.tag.split("}", 1)[1]
    return root


def _child_text(elem: ET.Element, tag: str, default: str = "") -> str:
    node = elem.find(tag)
    return (node.text or default).strip() if node is not None else default


class HikvisionISAPICollector:
    def __init__(
        self,
        host: str,
        username: str = "admin",
        password: str = "",
        port: int = 80,
        timeout: float = 4.0,
    ):
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.timeout = timeout
        self.base_url = f"http://{host}:{port}" if port != 80 else f"http://{host}"

    def _get(self, path: str, stream: bool = False):
        import requests
        from requests.auth import HTTPDigestAuth

        url = f"{self.base_url}{path}"
        resp = requests.get(
            url,
            auth=HTTPDigestAuth(self.username, self.password),
            timeout=self.timeout,
            stream=stream,
        )
        resp.raise_for_status()
        return resp

    @staticmethod
    def parse_hdd_xml(xml_text: str, nvr_host: str = "") -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """
        Parse `/ISAPI/System/Storage/hdd` XML response.
        Returns (hdds, critical_alerts).
        """
        root = _strip_ns(xml_text)
        hdd_nodes = root.findall(".//hdd") if root.tag != "hdd" else [root]
        hdds: list[dict[str, Any]] = []
        alerts: list[dict[str, Any]] = []

        for h in hdd_nodes:
            hdd_id = int(_child_text(h, "id", "1") or 1)
            hdd_name = _child_text(h, "hddName", f"HDD-{hdd_id}")
            status = _child_text(h, "status", "unknown").lower()
            capacity_mb = int(_child_text(h, "capacity", "0") or 0)
            free_mb = int(_child_text(h, "freeSpace", "0") or 0)

            hdd_info = {
                "id": hdd_id,
                "name": hdd_name,
                "status": status,
                "capacity_gb": round(capacity_mb / 1024, 1),
                "free_gb": round(free_mb / 1024, 1),
            }
            hdds.append(hdd_info)

            if status != "ok":
                alerts.append(
                    {
                        "severity": "critical",
                        "message": (
                            f"Lỗi ổ cứng NVR {nvr_host or 'Hikvision'} ({hdd_name}): "
                            f"trạng thái '{status.upper()}' (Dung lượng {hdd_info['capacity_gb']} GB)"
                        ),
                    }
                )

        return hdds, alerts

    @staticmethod
    def parse_channels_xml(
        channels_xml: str,
        status_xml: str = "",
        nvr_host: str = "",
        nvr_name: str = "NVR",
    ) -> list[dict[str, Any]]:
        """
        Parse `/ISAPI/ContentMgmt/InputProxy/channels` and `/ISAPI/ContentMgmt/InputProxy/channels/status`.
        Maps each channel to its Camera IP, protocol, and online/offline state.
        """
        status_by_id: dict[int, bool] = {}
        if status_xml.strip():
            s_root = _strip_ns(status_xml)
            for st in s_root.findall(".//InputProxyChannelStatus"):
                ch_id = int(_child_text(st, "id", "0") or 0)
                online_str = _child_text(st, "online", "false").lower()
                if ch_id:
                    status_by_id[ch_id] = online_str == "true"

        c_root = _strip_ns(channels_xml)
        channels: list[dict[str, Any]] = []
        for ch in c_root.findall(".//InputProxyChannel"):
            ch_id = int(_child_text(ch, "id", "0") or 0)
            ch_name = _child_text(ch, "name", f"Channel {ch_id}")
            desc = ch.find("sourceInputPortDescriptor")
            cam_ip = _child_text(desc, "ipAddress", "") if desc is not None else _child_text(ch, "ipAddress", "")
            protocol = _child_text(desc, "proxyProtocol", "HIKVISION") if desc is not None else "HIKVISION"
            manage_port = int(_child_text(desc, "managePortNo", "8000") or 8000) if desc is not None else 8000
            is_online = status_by_id.get(ch_id, True)

            channels.append(
                {
                    "channel_id": ch_id,
                    "stream_id": ch_id * 100 + 1,
                    "name": ch_name,
                    "camera_ip": cam_ip,
                    "protocol": protocol,
                    "manage_port": manage_port,
                    "online": is_online,
                    "nvr_host": nvr_host,
                    "nvr_name": nvr_name,
                }
            )
        return channels

    def get_storage_hdds(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        resp = self._get("/ISAPI/System/Storage/hdd")
        return self.parse_hdd_xml(resp.text, nvr_host=self.host)

    def get_input_channels(self, nvr_name: str = "NVR") -> list[dict[str, Any]]:
        ch_resp = self._get("/ISAPI/ContentMgmt/InputProxy/channels")
        try:
            st_resp = self._get("/ISAPI/ContentMgmt/InputProxy/channels/status")
            status_xml = st_resp.text
        except Exception:
            status_xml = ""
        return self.parse_channels_xml(ch_resp.text, status_xml, nvr_host=self.host, nvr_name=nvr_name)

    def fetch_snapshot(self, channel_id: int) -> tuple[bytes, str]:
        """
        Fetch a live JPEG snapshot from `/ISAPI/Streaming/channels/{stream_id}/picture`.
        Normalizes channel_id (e.g. 1 -> 101 main stream if < 100).
        """
        stream_id = channel_id * 100 + 1 if channel_id < 100 else channel_id
        resp = self._get(f"/ISAPI/Streaming/channels/{stream_id}/picture")
        content_type = resp.headers.get("Content-Type", "image/jpeg")
        return resp.content, content_type

    def collect_all(self, nvr_name: str = "Hikvision-NVR") -> dict[str, Any]:
        try:
            hdds, alerts = self.get_storage_hdds()
            channels = self.get_input_channels(nvr_name=nvr_name)
            online_channels = sum(1 for c in channels if c["online"])
            return {
                "host": self.host,
                "name": nvr_name,
                "is_online": True,
                "total_channels": len(channels),
                "online_channels": online_channels,
                "hdds": hdds,
                "channels": channels,
                "alerts": alerts,
            }
        except Exception as exc:
            return {
                "host": self.host,
                "name": nvr_name,
                "is_online": False,
                "error": str(exc),
                "total_channels": 0,
                "online_channels": 0,
                "hdds": [],
                "channels": [],
                "alerts": [],
            }
