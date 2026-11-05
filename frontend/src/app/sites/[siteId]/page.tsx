"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  Background,
  Controls,
  Edge,
  MiniMap,
  Node,
  ReactFlow,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Camera,
  CheckCircle2,
  ExternalLink,
  Network,
  PlusCircle,
  Radar,
  Router as RouterIcon,
  ShieldAlert,
  Terminal,
  Trash2,
  Wifi,
  X,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  applyDagreLayout,
  NocEdgeData,
  NocNodeData,
  nocNodeTypes,
  RemoteManageModal,
  traceUpstreamPath,
} from "@/components/topology";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const NAV_TABS = [
  "Tổng quan",
  "Router",
  "Switch",
  "Wi-Fi",
  "Thiết bị",
  "Camera",
  "Cảnh báo",
  "VPN",
] as const;

type NavTab = (typeof NAV_TABS)[number];

interface AlertItem {
  id: number;
  severity: "info" | "warning" | "critical";
  message: string;
  port_index?: number;
}

const INITIAL_WAN_SERIES = [
  { time: "23:00", vnpt: 280, fpt: 145 },
  { time: "23:05", vnpt: 310, fpt: 162 },
  { time: "23:10", vnpt: 295, fpt: 158 },
  { time: "23:15", vnpt: 342, fpt: 190 },
  { time: "23:20", vnpt: 318, fpt: 174 },
  { time: "23:25", vnpt: 365, fpt: 205 },
];

const FALLBACK_TOPOLOGY: {
  nodes: Node<NocNodeData>[];
  edges: Edge<NocEdgeData>[];
  alerts: AlertItem[];
} = {
  nodes: [
    {
      id: "dev-1",
      type: "routerNode",
      position: { x: 0, y: 0 },
      data: {
        label: "CCR2004-16G-2S+",
        name: "CCR2004-16G-2S+",
        role: "router",
        vendor: "MikroTik",
        model: "CCR2004-16G-2S+",
        ip_address: "10.10.0.1",
        mac_address: "64:D1:54:00:00:01",
        cpu_usage: 18,
        ram_usage: 39,
        uptime: 1231200,
        wan_rx_mbps: 365.4,
        wan_tx_mbps: 205.1,
        lan_tx_mbps: 570.5,
        is_online: true,
      },
    },
    {
      id: "dev-2",
      type: "switchNode",
      position: { x: 0, y: 0 },
      data: {
        label: "Core-SW-01",
        name: "Core-SW-01",
        role: "managed_switch",
        vendor: "Ruijie",
        model: "RG-S5310-24GT4XS",
        ip_address: "10.10.0.2",
        mac_address: "00:D0:F8:00:01:01",
        cpu_usage: 14,
        ram_usage: 32,
        total_ports: 24,
        connected_count: 8,
        is_online: true,
        ports: [
          { port_index: 1, port_name: "Gi0/1", status: "up", speed: "1G", vlan_id: 10 },
          { port_index: 2, port_name: "Gi0/2", status: "up", speed: "1G", vlan_id: 1, is_uplink: true },
          { port_index: 3, port_name: "Gi0/3", status: "up", speed: "1G", vlan_id: 20 },
          { port_index: 24, port_name: "Te0/24", status: "up", speed: "10G", vlan_id: 1, is_uplink: true },
        ],
      },
    },
    {
      id: "dev-3",
      type: "switchNode",
      position: { x: 0, y: 0 },
      data: {
        label: "Access-SW-CCTV",
        name: "Access-SW-CCTV",
        role: "managed_switch",
        vendor: "Hikvision",
        model: "DS-3E1526P-EI",
        ip_address: "10.10.0.3",
        mac_address: "BC:AD:28:00:02:02",
        cpu_usage: 22,
        ram_usage: 41,
        total_ports: 24,
        connected_count: 12,
        is_online: true,
        ports: [
          { port_index: 1, port_name: "Gi0/1", status: "up", speed: "100M", vlan_id: 10 },
          { port_index: 2, port_name: "Gi0/2", status: "up", speed: "1G", vlan_id: 10 },
          { port_index: 5, port_name: "Gi0/5", status: "up", speed: "1G", vlan_id: 20 },
          { port_index: 24, port_name: "Gi0/24", status: "up", speed: "1G", vlan_id: 1, is_uplink: true },
        ],
      },
    },
    {
      id: "dev-4",
      type: "endpointNode",
      position: { x: 0, y: 0 },
      data: {
        label: "Hikvision-NVR-01",
        name: "Hikvision-NVR-01",
        role: "nvr",
        vendor: "Hikvision",
        ip_address: "10.10.10.50",
        mac_address: "4C:0F:6E:10:20:30",
        vlan_id: 10,
        channels: "32 CH",
        is_online: true,
      },
    },
    {
      id: "dev-5",
      type: "endpointNode",
      position: { x: 0, y: 0 },
      data: {
        label: "Floor1-AP-Aruba",
        name: "Floor1-AP-Aruba",
        role: "ap",
        vendor: "Aruba",
        ip_address: "10.10.20.15",
        mac_address: "24:DE:C6:11:22:33",
        vlan_id: 20,
        channels: "Wi-Fi 6",
        is_online: true,
      },
    },
    {
      id: "dev-6",
      type: "endpointNode",
      position: { x: 0, y: 0 },
      data: {
        label: "Gate-Cam-01",
        name: "Gate-Cam-01",
        role: "camera",
        vendor: "Hikvision",
        ip_address: "10.10.10.101",
        mac_address: "BC:AD:28:00:11:01",
        vlan_id: 10,
        channels: "CH-01",
        is_online: true,
      },
    },
    {
      id: "dev-7",
      type: "unmanagedGroupNode",
      position: { x: 0, y: 0 },
      data: {
        label: "Chưa xác định switch hoặc AP (Access-SW-CCTV:Gi0/2)",
        name: "Chưa xác định switch hoặc AP",
        role: "unmanaged_group",
        vendor: "Unmanaged",
        ip_address: "Access-SW-CCTV : Gi0/2",
        upstream_port_label: "Access-SW-CCTV : Port 2 (VLAN 10)",
        is_online: true,
        group_items: [
          {
            name: "Lobby-Cam-02",
            ip_address: "10.10.10.102",
            mac_address: "BC:AD:28:00:11:02",
            vendor: "Hikvision",
            role: "camera",
            vlan_id: 10,
          },
          {
            name: "Parking-Cam-03",
            ip_address: "10.10.10.103",
            mac_address: "BC:AD:28:00:11:03",
            vendor: "Hikvision",
            role: "camera",
            vlan_id: 10,
          },
          {
            name: "Rogue-Tenda-AP",
            ip_address: "10.10.10.199",
            mac_address: "C8:3A:35:99:88:77",
            vendor: "Tenda",
            role: "ap",
            vlan_id: 10,
          },
        ],
      },
    },
    {
      id: "dev-8",
      type: "endpointNode",
      position: { x: 0, y: 0 },
      data: {
        label: "Lobby-Cam-02",
        name: "Lobby-Cam-02",
        role: "camera",
        vendor: "Hikvision",
        ip_address: "10.10.10.102",
        mac_address: "BC:AD:28:00:11:02",
        vlan_id: 10,
        channels: "CH-02",
        is_online: true,
      },
    },
    {
      id: "dev-9",
      type: "endpointNode",
      position: { x: 0, y: 0 },
      data: {
        label: "Rogue-Tenda-AP",
        name: "Rogue-Tenda-AP",
        role: "ap",
        vendor: "Tenda",
        ip_address: "10.10.10.199",
        mac_address: "C8:3A:35:99:88:77",
        vlan_id: 10,
        channels: "ROGUE",
        is_online: true,
      },
    },
  ],
  edges: [
    {
      id: "e1-2",
      source: "dev-1",
      target: "dev-2",
      label: "P1 -> P24 (10G Trunk)",
      data: { link_type: "trunk", speed: "10G", source_port: 1, target_port: 24 },
    },
    {
      id: "e2-3",
      source: "dev-2",
      target: "dev-3",
      label: "P2 -> P24 (1G Trunk)",
      data: { link_type: "trunk", speed: "1G", source_port: 2, target_port: 24 },
    },
    {
      id: "e2-4",
      source: "dev-2",
      target: "dev-4",
      label: "P1 -> eth0 (1G)",
      data: { link_type: "access", speed: "1G", source_port: 1, target_port: 1, vlan_id: 10 },
    },
    {
      id: "e2-5",
      source: "dev-2",
      target: "dev-5",
      label: "P3 -> eth0 (1G)",
      data: { link_type: "access", speed: "1G", source_port: 3, target_port: 1, vlan_id: 20 },
    },
    {
      id: "e3-6",
      source: "dev-3",
      target: "dev-6",
      label: "P1 -> eth0 (100M)",
      data: { link_type: "access", speed: "100M", source_port: 1, target_port: 1, vlan_id: 10 },
    },
    {
      id: "e3-7",
      source: "dev-3",
      target: "dev-7",
      label: "P2 -> Hub (Unmanaged)",
      data: { link_type: "unmanaged", speed: "1G", source_port: 2, target_port: 0, vlan_id: 10 },
    },
    {
      id: "e7-8",
      source: "dev-7",
      target: "dev-8",
      label: "Hub -> Cam-02",
      data: { link_type: "unmanaged", speed: "100M", source_port: 1, target_port: 1, vlan_id: 10 },
    },
    {
      id: "e7-9",
      source: "dev-7",
      target: "dev-9",
      label: "Hub -> Rogue-Tenda",
      data: { link_type: "unmanaged", speed: "100M", source_port: 2, target_port: 1, vlan_id: 10 },
    },
  ],
  alerts: [
    {
      id: 1,
      severity: "critical",
      port_index: 2,
      message:
        "Phát hiện thiết bị Router/AP dân dụng lạ (Tenda - MAC C8:3A:35:99:88:77) cắm vào cổng Camera/CCTV Access-SW-CCTV:Gi0/2",
    },
    {
      id: 2,
      severity: "warning",
      message: "Cảnh báo đầy tải DHCP VLAN 10: đã cấp 235/254 IP (92.5% > 90%)",
    },
  ],
};

function mapRoleToNodeType(role?: string): string {
  switch (role) {
    case "router":
      return "routerNode";
    case "managed_switch":
      return "switchNode";
    case "unmanaged_group":
      return "unmanagedGroupNode";
    default:
      return "endpointNode";
  }
}

function normalizeIncomingGraph(
  rawNodes: Node<NocNodeData>[],
  rawEdges: Edge<NocEdgeData>[]
): { nodes: Node<NocNodeData>[]; edges: Edge<NocEdgeData>[] } {
  const mappedNodes: Node<NocNodeData>[] = rawNodes.map((n) => ({
    ...n,
    type: n.type && n.type !== "default" ? n.type : mapRoleToNodeType(n.data?.role),
  }));

  const mappedEdges: Edge<NocEdgeData>[] = rawEdges.map((e) => {
    const labelStr = String(e.label || "");
    const portMatches = labelStr.match(/P?(\d+)\s*->\s*P?(\d+)/i);
    const srcPort = e.data?.source_port ?? (portMatches ? Number(portMatches[1]) : 1);
    const dstPort = e.data?.target_port ?? (portMatches ? Number(portMatches[2]) : 24);
    return {
      ...e,
      data: {
        link_type: e.data?.link_type || "access",
        speed: e.data?.speed || "1G",
        source_port: srcPort,
        target_port: dstPort,
      },
    };
  });

  return {
    nodes: applyDagreLayout(mappedNodes, mappedEdges, "LR"),
    edges: mappedEdges,
  };
}

export default function SiteNocDashboardPage() {
  const params = useParams();
  const router = useRouter();
  const siteId = Number(params?.siteId || 1);

  const [activeTab, setActiveTab] = useState<NavTab>("Tổng quan");
  const [rawNodes, setRawNodes] = useState<Node<NocNodeData>[]>([]);
  const [rawEdges, setRawEdges] = useState<Edge<NocEdgeData>[]>([]);
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);
  const [wanSeries, setWanSeries] = useState(INITIAL_WAN_SERIES);
  const [remoteModalMode, setRemoteModalMode] = useState<"site" | "device" | null>(null);
  const [sitesList, setSitesList] = useState<Array<{ id: number; name: string; subnet: string }>>([]);

  const loadSitesList = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/sites`);
      if (res.ok) {
        const list = await res.json();
        if (Array.isArray(list)) {
          setSitesList(list);
        }
      }
    } catch {
      // Ignore offline error
    }
  }, []);

  const loadTopology = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/topology/${siteId}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const normalized = normalizeIncomingGraph(data.nodes || [], data.edges || []);
      setRawNodes(normalized.nodes);
      setRawEdges(normalized.edges);
      setAlerts(Array.isArray(data.alerts) ? data.alerts : []);
    } catch {
      setRawNodes([]);
      setRawEdges([]);
      setAlerts([]);
    }
  }, [siteId]);

  useEffect(() => {
    loadSitesList();
    loadTopology();
  }, [loadSitesList, loadTopology]);

  // Simulate live Multi-WAN telemetry updates
  useEffect(() => {
    const timer = setInterval(() => {
      setWanSeries((prev) => {
        const now = new Date();
        const label = now.toTimeString().slice(0, 5);
        const nextVnpt = Math.round(290 + Math.random() * 95);
        const nextFpt = Math.round(140 + Math.random() * 75);
        return [...prev.slice(1), { time: label, vnpt: nextVnpt, fpt: nextFpt }];
      });
    }, 4000);
    return () => clearInterval(timer);
  }, []);

  const handleScanSite = async () => {
    setScanning(true);
    try {
      const res = await fetch(`${API_URL}/api/sites/${siteId}/scan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      if (res.ok) {
        const data = await res.json();
        const normalized = normalizeIncomingGraph(data.nodes || [], data.edges || []);
        setRawNodes(normalized.nodes);
        setRawEdges(normalized.edges);
        if (Array.isArray(data.alerts)) setAlerts(data.alerts);
      } else {
        await loadTopology();
      }
    } catch {
      await loadTopology();
    } finally {
      setScanning(false);
    }
  };

  const handleDeleteSite = async () => {
    if (!window.confirm(`Bạn có chắc muốn xóa hoàn toàn Điểm #${siteId} và toàn bộ thiết bị của điểm này?`)) {
      return;
    }
    try {
      await fetch(`${API_URL}/api/sites/${siteId}`, { method: "DELETE" });
      const res = await fetch(`${API_URL}/api/sites`);
      const remaining = res.ok ? await res.json() : [];
      setSitesList(Array.isArray(remaining) ? remaining : []);
      setSelectedNodeId(null);
      if (Array.isArray(remaining) && remaining.length > 0) {
        router.push(`/sites/${remaining[0].id}`);
      } else {
        setRawNodes([]);
        setRawEdges([]);
        setAlerts([]);
      }
    } catch {
      // Ignore network error
    }
  };

  const handleClearTopology = async () => {
    if (!window.confirm(`Xóa toàn bộ thiết bị trên sơ đồ của Site #${siteId} để làm sạch?`)) {
      return;
    }
    try {
      const res = await fetch(`${API_URL}/api/sites/${siteId}/topology`, {
        method: "DELETE",
      });
      if (res.ok) {
        setRawNodes([]);
        setRawEdges([]);
        setAlerts([]);
        setSelectedNodeId(null);
      }
    } catch {
      // Ignore error
    }
  };

  const handleDeleteSelectedDevice = async () => {
    if (!selectedNode) return;
    const numericId = Number(String(selectedNode.id).replace(/\D+/g, ""));
    if (!numericId) return;
    try {
      const res = await fetch(`${API_URL}/api/sites/${siteId}/devices/${numericId}`, {
        method: "DELETE",
      });
      if (res.ok) {
        const data = await res.json();
        const normalized = normalizeIncomingGraph(data.nodes || [], data.edges || []);
        setRawNodes(normalized.nodes);
        setRawEdges(normalized.edges);
        setAlerts(Array.isArray(data.alerts) ? data.alerts : []);
        setSelectedNodeId(null);
      }
    } catch {
      // Ignore error
    }
  };

  const focusNodeId = hoveredNodeId || selectedNodeId;

  const highlightState = useMemo(
    () => traceUpstreamPath(focusNodeId, rawNodes, rawEdges),
    [focusNodeId, rawNodes, rawEdges]
  );

  // Filter / highlight nodes and edges
  const displayNodes = useMemo(() => {
    const hasFocus = Boolean(focusNodeId);
    return rawNodes.map((node) => {
      const isHighlighted = hasFocus && highlightState.activeNodeIds.has(node.id);
      const isDimmed = hasFocus && !isHighlighted;
      const highlightedPorts = highlightState.switchPortsByNodeId[node.id] || [];
      return {
        ...node,
        data: {
          ...node.data,
          isHighlighted,
          isDimmed,
          highlightedPorts,
        },
      };
    });
  }, [rawNodes, focusNodeId, highlightState]);

  const displayEdges = useMemo(() => {
    const hasFocus = Boolean(focusNodeId);
    return rawEdges.map((edge) => {
      const isHighlighted = hasFocus && highlightState.activeEdgeIds.has(edge.id);
      const isDimmed = hasFocus && !isHighlighted;
      const srcPort = edge.data?.source_port;
      const dstPort = edge.data?.target_port;
      return {
        ...edge,
        animated: isHighlighted || edge.data?.link_type === "trunk",
        label:
          isHighlighted && srcPort
            ? `Port ${srcPort} ➔ Port ${dstPort || 1} (${edge.data?.speed || "1G"})`
            : edge.label,
        labelStyle: {
          fill: isHighlighted ? "#22d3ee" : "#94a3b8",
          fontWeight: isHighlighted ? 700 : 500,
          fontSize: 11,
        },
        labelBgStyle: {
          fill: "#0f172a",
          fillOpacity: 0.9,
        },
        style: {
          stroke: isHighlighted
            ? "#22d3ee"
            : edge.data?.link_type === "unmanaged"
            ? "#f59e0b"
            : "#475569",
          strokeWidth: isHighlighted ? 3.2 : 1.8,
          strokeDasharray:
            isHighlighted || edge.data?.link_type === "unmanaged" ? "6 4" : undefined,
          opacity: isDimmed ? 0.25 : 1,
        },
      };
    });
  }, [rawEdges, focusNodeId, highlightState]);

  const selectedNode = useMemo(
    () => rawNodes.find((n) => n.id === selectedNodeId) || null,
    [rawNodes, selectedNodeId]
  );

  const selectedNodePath = useMemo(
    () => traceUpstreamPath(selectedNodeId, rawNodes, rawEdges).hops,
    [selectedNodeId, rawNodes, rawEdges]
  );

  // Summary metrics
  const stats = useMemo(() => {
    const total = rawNodes.length;
    const offline = rawNodes.filter((n) => n.data?.is_online === false).length;
    const online = total - offline;
    const routers = rawNodes.filter((n) => n.data?.role === "router").length;
    const switches = rawNodes.filter((n) => n.data?.role === "managed_switch").length;
    const aps = rawNodes.filter((n) => n.data?.role === "ap").length;
    const cameras = rawNodes.filter(
      (n) => n.data?.role === "camera" || n.data?.role === "nvr"
    ).length;
    return { total, online, offline, routers, switches, aps, cameras };
  }, [rawNodes]);

  const ringCircumference = 2 * Math.PI * 36;
  const ringOffset =
    ringCircumference - (stats.online / Math.max(stats.total, 1)) * ringCircumference;

  return (
    <div className="flex h-screen flex-col bg-slate-950 text-slate-100">
      {/* 1. Top Navigation Bar */}
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800/90 bg-slate-900/95 px-5 py-2.5 backdrop-blur">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 font-bold tracking-tight text-emerald-400">
            <Network className="h-5 w-5" />
            <span className="text-base text-white">SVC NOC-CENTER</span>
          </div>

          <select
            value={siteId}
            onChange={(e) => router.push(`/sites/${e.target.value}`)}
            className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-xs font-medium text-slate-200 focus:border-cyan-400 focus:outline-none"
          >
            {sitesList.length === 0 ? (
              <option value={siteId}>Chưa có chi nhánh nào (Site #{siteId})</option>
            ) : (
              sitesList.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name.startsWith("Site #") ? `${s.name} (${s.subnet})` : `Site #${s.id} — ${s.name} (${s.subnet})`}
                </option>
              ))
            )}
          </select>

          <button
            onClick={() => setRemoteModalMode("site")}
            className="flex items-center gap-1 rounded-lg border border-cyan-500/40 bg-cyan-500/15 px-2.5 py-1.5 text-xs font-semibold text-cyan-300 transition hover:bg-cyan-500/25"
          >
            <Terminal className="h-3.5 w-3.5" />
            + Thêm Điểm & Script VPN
          </button>

          {sitesList.length > 0 && (
            <button
              onClick={handleDeleteSite}
              title="Xóa Điểm (Site) hiện tại"
              className="flex items-center gap-1 rounded-lg border border-rose-500/40 bg-rose-500/15 px-2.5 py-1.5 text-xs font-semibold text-rose-300 transition hover:bg-rose-500/25"
            >
              <Trash2 className="h-3.5 w-3.5" />
              Xóa Điểm
            </button>
          )}
        </div>

        <nav className="flex items-center gap-1 overflow-x-auto">
          {NAV_TABS.map((tab) => {
            const active = activeTab === tab;
            return (
              <button
                key={tab}
                onClick={() => {
                  if (tab === "Camera") {
                    router.push(`/sites/${siteId}/cameras`);
                    return;
                  }
                  setActiveTab(tab);
                }}
                className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                  active
                    ? "bg-cyan-500/20 text-cyan-300 ring-1 ring-cyan-400/50"
                    : "text-slate-400 hover:bg-slate-800/70 hover:text-slate-200"
                }`}
              >
                {tab}
                {tab === "Cảnh báo" && alerts.length > 0 && (
                  <span className="ml-1.5 rounded-full bg-rose-500 px-1.5 py-0.2 text-[10px] font-bold text-white">
                    {alerts.length}
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        <div className="flex items-center gap-2">
          {rawNodes.length > 0 && (
            <button
              onClick={handleClearTopology}
              className="flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-800/80 px-2.5 py-1.5 text-xs font-medium text-slate-300 transition hover:border-rose-500/50 hover:text-rose-300"
            >
              <Trash2 className="h-3.5 w-3.5" />
              Làm Sạch Sơ Đồ
            </button>
          )}
          <button
            onClick={() => setRemoteModalMode("device")}
            className="flex items-center gap-1.5 rounded-lg bg-violet-500/20 px-3 py-1.5 text-xs font-semibold text-violet-300 ring-1 ring-violet-500/40 transition hover:bg-violet-500/30"
          >
            <PlusCircle className="h-3.5 w-3.5" />
            + Thiết Bị / Quét Từ Xa
          </button>
          <button
            onClick={handleScanSite}
            disabled={scanning}
            className="flex items-center gap-1.5 rounded-lg bg-emerald-500/20 px-3 py-1.5 text-xs font-semibold text-emerald-300 ring-1 ring-emerald-500/40 transition hover:bg-emerald-500/30 disabled:opacity-50"
          >
            <Radar className={`h-3.5 w-3.5 ${scanning ? "animate-spin" : ""}`} />
            {scanning ? "Đang quét LLDP/ARP..." : "Quét Sơ Đồ (Scan)"}
          </button>
        </div>
      </header>

      {/* 2. Header Overview Cards */}
      <section className="grid grid-cols-1 gap-3 border-b border-slate-800/80 bg-slate-900/40 px-5 py-3 lg:grid-cols-12">
        {/* Left Card: Online Ring + Device & Alert Summary */}
        <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-slate-800 bg-slate-900/90 p-3.5 lg:col-span-6">
          <div className="flex items-center gap-4">
            <div className="relative flex h-20 w-20 items-center justify-center">
              <svg className="h-20 w-20 -rotate-90 transform">
                <circle
                  cx="40"
                  cy="40"
                  r="36"
                  stroke="#1e293b"
                  strokeWidth="7"
                  fill="transparent"
                />
                <circle
                  cx="40"
                  cy="40"
                  r="36"
                  stroke="#10b981"
                  strokeWidth="7"
                  strokeDasharray={ringCircumference}
                  strokeDashoffset={ringOffset}
                  strokeLinecap="round"
                  fill="transparent"
                />
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
                <span className="text-sm font-extrabold text-emerald-400">
                  {stats.online}/{stats.total}
                </span>
                <span className="text-[9px] font-bold tracking-wider text-slate-400">
                  ONLINE
                </span>
              </div>
            </div>

            <div>
              <div className="flex items-center gap-2">
                <span className="flex items-center gap-1 rounded-md bg-emerald-500/15 px-2 py-0.5 text-xs font-semibold text-emerald-300">
                  <CheckCircle2 className="h-3.5 w-3.5" /> Hệ thống ổn định
                </span>
                <span className="flex items-center gap-1 rounded-md bg-amber-500/15 px-2 py-0.5 text-xs font-semibold text-amber-300">
                  <AlertTriangle className="h-3.5 w-3.5" />{" "}
                  {alerts.filter((a) => a.severity === "warning").length} Cảnh báo
                </span>
                <span className="flex items-center gap-1 rounded-md bg-rose-500/15 px-2 py-0.5 text-xs font-semibold text-rose-300">
                  <ShieldAlert className="h-3.5 w-3.5" />{" "}
                  {alerts.filter((a) => a.severity === "critical").length} Nghiêm trọng
                </span>
              </div>
              <p className="mt-1.5 text-xs text-slate-400">
                Rê chuột hoặc click vào bất kỳ Switch/Camera nào để làm sáng đường truyền Uplink về Router.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-4 gap-2 text-center">
            <div className="rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-1.5">
              <p className="text-xs font-bold text-emerald-400">{stats.routers}</p>
              <p className="text-[10px] text-slate-400">Router</p>
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-1.5">
              <p className="text-xs font-bold text-sky-400">{stats.switches}</p>
              <p className="text-[10px] text-slate-400">Switch</p>
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-1.5">
              <p className="text-xs font-bold text-violet-400">{stats.aps}</p>
              <p className="text-[10px] text-slate-400">Wi-Fi AP</p>
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-1.5">
              <p className="text-xs font-bold text-cyan-400">{stats.cameras}</p>
              <p className="text-[10px] text-slate-400">Camera/NVR</p>
            </div>
          </div>
        </div>

        {/* Right Card: Real-time Recharts Multi-WAN Bandwidth */}
        <div className="flex flex-col justify-between rounded-xl border border-slate-800 bg-slate-900/90 p-3.5 lg:col-span-6">
          <div className="mb-1 flex items-center justify-between">
            <div className="flex items-center gap-2 text-xs font-semibold text-slate-200">
              <Activity className="h-4 w-4 text-cyan-400" />
              <span>Multi-WAN Real-Time Bandwidth (Mbps)</span>
            </div>
            <div className="flex items-center gap-4 text-xs">
              <span className="flex items-center gap-1.5 font-mono text-cyan-300">
                <span className="h-2 w-2 rounded-full bg-cyan-400" />
                VNPT: {wanSeries[wanSeries.length - 1]?.vnpt} Mbps
              </span>
              <span className="flex items-center gap-1.5 font-mono text-emerald-300">
                <span className="h-2 w-2 rounded-full bg-emerald-400" />
                FPT: {wanSeries[wanSeries.length - 1]?.fpt} Mbps
              </span>
            </div>
          </div>

          <div className="h-20 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={wanSeries} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="vnptGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#22d3ee" stopOpacity={0.45} />
                    <stop offset="95%" stopColor="#22d3ee" stopOpacity={0.0} />
                  </linearGradient>
                  <linearGradient id="fptGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.45} />
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0.0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="time" tick={{ fill: "#64748b", fontSize: 10 }} />
                <YAxis tick={{ fill: "#64748b", fontSize: 10 }} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#0f172a",
                    borderColor: "#334155",
                    fontSize: "11px",
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="vnpt"
                  name="WAN1 - VNPT"
                  stroke="#22d3ee"
                  strokeWidth={2}
                  fillOpacity={1}
                  fill="url(#vnptGrad)"
                />
                <Area
                  type="monotone"
                  dataKey="fpt"
                  name="WAN2 - FPT"
                  stroke="#10b981"
                  strokeWidth={2}
                  fillOpacity={1}
                  fill="url(#fptGrad)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      </section>

      {/* 3. Main Interactive Topology Canvas + Slide-Over Inspector Drawer */}
      <div className="relative flex-1 overflow-hidden">
        {/* Alert Banner Floating Pill */}
        {alerts.length > 0 && (
          <div className="absolute left-4 top-4 z-10 max-w-xl space-y-1.5">
            {alerts.slice(0, 2).map((alert) => (
              <div
                key={alert.id}
                className={`flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs shadow-lg backdrop-blur ${
                  alert.severity === "critical"
                    ? "border-rose-500/50 bg-rose-950/90 text-rose-200"
                    : "border-amber-500/50 bg-amber-950/90 text-amber-200"
                }`}
              >
                <ShieldAlert className="h-4 w-4 flex-shrink-0 text-rose-400" />
                <span className="truncate">{alert.message}</span>
              </div>
            ))}
          </div>
        )}

        <ReactFlow
          nodes={displayNodes}
          edges={displayEdges}
          nodeTypes={nocNodeTypes}
          fitView
          colorMode="dark"
          onNodeMouseEnter={(_, node) => setHoveredNodeId(node.id)}
          onNodeMouseLeave={() => setHoveredNodeId(null)}
          onNodeClick={(_, node) => setSelectedNodeId(node.id)}
          onPaneClick={() => setSelectedNodeId(null)}
        >
          <Background color="#1e293b" gap={20} />
          <Controls />
          <MiniMap
            pannable
            zoomable
            className="!bg-slate-900 !border !border-slate-800"
            nodeColor={(n) => {
              if (n.type === "routerNode") return "#10b981";
              if (n.type === "switchNode") return "#38bdf8";
              if (n.type === "unmanagedGroupNode") return "#f59e0b";
              return "#94a3b8";
            }}
          />
        </ReactFlow>

        {/* Slide-over Right Drawer for Clicked Device */}
        {selectedNode && (
          <aside className="absolute bottom-0 right-0 top-0 z-20 flex w-96 flex-col border-l border-slate-800 bg-slate-900/95 p-5 shadow-2xl backdrop-blur">
            <div className="flex items-start justify-between border-b border-slate-800 pb-3">
              <div>
                <span className="rounded bg-cyan-500/20 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-cyan-300">
                  {selectedNode.data.vendor || selectedNode.data.role}
                </span>
                <h2 className="mt-1 text-base font-bold text-white">
                  {selectedNode.data.name || selectedNode.data.label}
                </h2>
                <p className="font-mono text-xs text-slate-400">
                  IP: {selectedNode.data.ip_address}
                  {selectedNode.data.mac_address
                    ? ` • MAC: ${selectedNode.data.mac_address}`
                    : ""}
                </p>
              </div>
              <button
                onClick={() => setSelectedNodeId(null)}
                className="rounded-lg p-1 text-slate-400 hover:bg-slate-800 hover:text-white"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="mt-4 flex-1 space-y-4 overflow-y-auto pr-1 text-xs">
              {/* Upstream Path Trace */}
              <div className="rounded-xl border border-slate-800 bg-slate-950/80 p-3">
                <p className="mb-2 font-semibold uppercase tracking-wider text-cyan-400">
                  Đường truyền Uplink về Router ({selectedNodePath.length} chặng)
                </p>
                {selectedNodePath.length === 0 ? (
                  <p className="text-slate-400">
                    Đây là Router gốc (Core Gateway) của Site.
                  </p>
                ) : (
                  <div className="space-y-2">
                    {selectedNodePath.map((hop, idx) => (
                      <div
                        key={idx}
                        className="flex items-center justify-between rounded-lg border border-cyan-500/30 bg-cyan-950/20 px-2.5 py-2"
                      >
                        <div className="truncate">
                          <p className="font-semibold text-slate-100">
                            {hop.fromNodeName}
                          </p>
                          <p className="font-mono text-[10px] text-cyan-300">
                            Port {hop.fromPort || 1} ({hop.speed || "1G"} {hop.linkType})
                          </p>
                        </div>
                        <ArrowRight className="mx-2 h-4 w-4 flex-shrink-0 text-cyan-400" />
                        <div className="truncate text-right">
                          <p className="font-semibold text-slate-100">
                            {hop.toNodeName}
                          </p>
                          <p className="font-mono text-[10px] text-emerald-300">
                            Port {hop.toPort || 1}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* VLAN & Device Details */}
              <div className="rounded-xl border border-slate-800 bg-slate-950/80 p-3 space-y-1.5">
                <p className="font-semibold uppercase tracking-wider text-slate-300">
                  Thông số kỹ thuật & VLAN
                </p>
                <div className="flex justify-between text-slate-400">
                  <span>Phân loại:</span>
                  <span className="font-medium text-slate-200">
                    {selectedNode.data.role}
                  </span>
                </div>
                <div className="flex justify-between text-slate-400">
                  <span>VLAN ID:</span>
                  <span className="font-mono text-cyan-300">
                    {selectedNode.data.vlan_id
                      ? `VLAN ${selectedNode.data.vlan_id}`
                      : "Trunk / Native VLAN 1"}
                  </span>
                </div>
                <div className="flex justify-between text-slate-400">
                  <span>Trạng thái:</span>
                  <span className="font-semibold text-emerald-400">
                    {selectedNode.data.is_online !== false ? "ONLINE" : "OFFLINE"}
                  </span>
                </div>
              </div>
            </div>

            <div className="mt-4 space-y-2 border-t border-slate-800 pt-3">
              <a
                href={`${API_URL}/api/proxy/sites/${siteId}/${selectedNode.data.ip_address}`}
                target="_blank"
                rel="noopener noreferrer"
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-cyan-500 px-4 py-2.5 text-xs font-bold text-slate-950 transition hover:bg-cyan-400"
              >
                <ExternalLink className="h-4 w-4" />
                Mở Web GUI qua VPN ({selectedNode.data.ip_address})
              </a>
              <button
                onClick={handleDeleteSelectedDevice}
                className="flex w-full items-center justify-center gap-2 rounded-lg border border-rose-500/40 bg-rose-500/15 px-4 py-2 text-xs font-semibold text-rose-300 transition hover:bg-rose-500/25"
              >
                <Trash2 className="h-3.5 w-3.5" />
                Xóa Thiết Bị Này Khỏi Sơ Đồ
              </button>
            </div>
          </aside>
        )}

        {remoteModalMode && (
          <RemoteManageModal
            siteId={siteId}
            initialMode={remoteModalMode}
            onClose={() => setRemoteModalMode(null)}
            onSiteCreated={(newSiteId) => {
              loadSitesList();
              router.push(`/sites/${newSiteId}`);
            }}
            onTopologyUpdated={(data) => {
              if (Array.isArray(data.nodes)) {
                const normalized = normalizeIncomingGraph(
                  data.nodes as Node<NocNodeData>[],
                  (data.edges || []) as Edge<NocEdgeData>[]
                );
                setRawNodes(normalized.nodes);
                setRawEdges(normalized.edges);
              }
              if (Array.isArray(data.alerts)) {
                setAlerts(data.alerts as AlertItem[]);
              }
            }}
          />
        )}
      </div>
    </div>
  );
}
