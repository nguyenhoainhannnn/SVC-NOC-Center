export type DeviceRoleType =
  | "router"
  | "managed_switch"
  | "unmanaged_group"
  | "ap"
  | "nvr"
  | "camera"
  | "endpoint";

export interface SwitchPortSquare {
  port_index: number;
  port_name: string;
  status: "up" | "down";
  speed: "100M" | "1G" | "10G";
  vlan_id?: number | null;
  is_uplink?: boolean;
  connected_label?: string;
}

export interface UnmanagedChildItem {
  id?: string;
  name: string;
  ip_address: string;
  mac_address: string;
  vendor: string;
  role: DeviceRoleType;
  vlan_id?: number;
}

export interface NocNodeData extends Record<string, unknown> {
  label: string;
  name?: string;
  role: DeviceRoleType;
  vendor?: string;
  model?: string;
  ip_address: string;
  mac_address?: string;
  cpu_usage?: number;
  ram_usage?: number;
  uptime?: number;
  is_online: boolean;
  vlan_id?: number;
  wan_rx_mbps?: number;
  wan_tx_mbps?: number;
  lan_rx_mbps?: number;
  lan_tx_mbps?: number;
  total_ports?: 24 | 48;
  connected_count?: number;
  ports?: SwitchPortSquare[];
  upstream_port_label?: string;
  group_items?: UnmanagedChildItem[];
  channels?: string;
  // Interactive highlight injected props
  isHighlighted?: boolean;
  isDimmed?: boolean;
  highlightedPorts?: number[];
}

export interface NocEdgeData extends Record<string, unknown> {
  link_type: "trunk" | "access" | "unmanaged";
  speed?: string;
  source_port?: number;
  target_port?: number;
  vlan_id?: number;
}

export interface PathHop {
  fromNodeId: string;
  fromNodeName: string;
  fromPort?: number;
  toNodeId: string;
  toNodeName: string;
  toPort?: number;
  linkType: string;
  speed?: string;
}
