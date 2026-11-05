import argparse
import json
from pathlib import Path
import socket
import sys
import time
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.collectors import (  # noqa: E402
    MikroTikCollector,
    SNMPSwitchCollector,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="SVC NOC-Center On-Site Agent (Runs in parallel with VPN)"
    )
    parser.add_argument(
        "--noc-url",
        default="http://localhost:8000",
        help="Central NOC-Center Backend URL (default: http://localhost:8000)",
    )
    parser.add_argument("--site-id", type=int, default=1, help="Target Site ID (default: 1)")
    parser.add_argument(
        "--agent-key",
        default="noc-agent-key",
        help="Agent authentication key (X-NOC-Agent-Key)",
    )
    parser.add_argument("--router-ip", help="Local Router IP in LAN (e.g. 10.10.0.1)")
    parser.add_argument("--router-user", default="admin", help="RouterOS API username")
    parser.add_argument("--router-pass", default="", help="RouterOS API password")
    parser.add_argument(
        "--switch-ips",
        default="",
        help="Comma-separated Managed Switch IPs in LAN (e.g. 10.10.0.2,10.10.0.3)",
    )
    parser.add_argument("--community", default="public", help="SNMPv2c community string")
    parser.add_argument(
        "--interval",
        type=int,
        default=0,
        help="Push interval in seconds (0 = push once and exit, >0 = continuous daemon)",
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Push sample LAN discovery payload when testing without physical router/switches",
    )
    return parser


def collect_local_lan(args: argparse.Namespace) -> dict:
    hostname = socket.gethostname()
    if args.simulate or (not args.router_ip and not args.switch_ips):
        return {
            "agent_hostname": hostname,
            "router_data": None,
            "switches_data": None,
            "cctv_vlans": [10],
        }

    router_data = None
    if args.router_ip:
        router_data = MikroTikCollector(
            host=args.router_ip,
            username=args.router_user,
            password=args.router_pass,
        ).collect_all()

    switches_data = []
    for ip in [s.strip() for s in args.switch_ips.split(",") if s.strip()]:
        switches_data.append(
            SNMPSwitchCollector(host=ip, community=args.community).collect_all()
        )

    return {
        "agent_hostname": hostname,
        "router_data": router_data,
        "switches_data": switches_data,
        "cctv_vlans": [10],
    }


def push_to_noc(noc_url: str, site_id: int, agent_key: str, payload: dict) -> dict:
    endpoint = f"{noc_url.rstrip('/')}/api/sites/{site_id}/agent-push"
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-NOC-Agent-Key": agent_key,
        },
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    args = build_parser().parse_args()
    while True:
        payload = collect_local_lan(args)
        result = push_to_noc(args.noc_url, args.site_id, args.agent_key, payload)
        print(
            json.dumps(
                {
                    "status": "pushed",
                    "site_id": result.get("site_id"),
                    "connection_mode": result.get("connection_mode"),
                    "nodes": len(result.get("nodes", [])),
                    "edges": len(result.get("edges", [])),
                    "alerts": len(result.get("alerts", [])),
                },
                ensure_ascii=False,
            )
        )
        if args.interval <= 0:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
