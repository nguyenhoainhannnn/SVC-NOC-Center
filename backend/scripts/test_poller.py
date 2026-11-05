import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.collectors import (  # noqa: E402
    MikroTikCollector,
    SNMPSwitchCollector,
    lookup_mac_vendor,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="NOC-Center Router & Switch Poller CLI")
    parser.add_argument("--router-ip", help="MikroTik Router IP address")
    parser.add_argument("--router-user", default="admin", help="MikroTik API username (default: admin)")
    parser.add_argument("--router-pass", default="", help="MikroTik API password")
    parser.add_argument("--router-port", type=int, default=8728, help="MikroTik API port (default: 8728)")
    parser.add_argument("--switch-ip", help="Managed Switch IP address for SNMP polling")
    parser.add_argument("--community", default="public", help="SNMPv2c community string (default: public)")
    parser.add_argument("--mac", nargs="*", default=[], help="Optional MAC addresses to test OUI vendor lookup")
    parser.add_argument("--timeout", type=float, default=3.0, help="Socket timeout in seconds")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    output: dict = {}

    if args.router_ip:
        router = MikroTikCollector(
            host=args.router_ip,
            username=args.router_user,
            password=args.router_pass,
            port=args.router_port,
            timeout=args.timeout,
        )
        output["router"] = router.collect_all()

    if args.switch_ip:
        switch = SNMPSwitchCollector(
            host=args.switch_ip,
            community=args.community,
            timeout=args.timeout,
        )
        output["switch"] = switch.collect_all()

    if args.mac or not output:
        sample_macs = args.mac or [
            "BC:AD:28:11:22:33",
            "00-D0-F8-AA-BB-CC",
            "64d1.5412.3456",
            "B4:2E:99:00:11:22",
        ]
        output["mac_lookup"] = [lookup_mac_vendor(m) for m in sample_macs]

    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
