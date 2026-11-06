"use client";

import { useEffect, useState } from "react";
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  Copy,
  PlusCircle,
  Radar,
  Server,
  Terminal,
  X,
} from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface RemoteManageModalProps {
  siteId: number;
  initialMode: "site" | "device";
  onClose: () => void;
  onSiteCreated: (newSiteId: number) => void;
  onTopologyUpdated: (data: {
    notification?: boolean;
    nodes?: unknown[];
    edges?: unknown[];
    alerts?: unknown[];
  }) => void;
  onNotify?: (notification: boolean, message: string) => void;
}

export function RemoteManageModal({
  siteId,
  initialMode,
  onClose,
  onSiteCreated,
  onTopologyUpdated,
  onNotify,
}: RemoteManageModalProps) {
  const [tab, setTab] = useState<"site" | "scan" | "manual">(
    initialMode === "site" ? "site" : "scan"
  );

  // Tab 1: Create Remote Site + VPN Bootstrap Script
  const [siteName, setSiteName] = useState("");
  const [siteSubnet, setSiteSubnet] = useState("192.168.50.0/24");
  const [siteVpnIp, setSiteVpnIp] = useState(`10.255.${siteId + 1}.2`);
  const [nocPublicIp, setNocPublicIp] = useState("203.0.113.10");
  const [vpnScript, setVpnScript] = useState("");
  const [pythonAgentCmd, setPythonAgentCmd] = useState("");
  const [mikrotikAgentScript, setMikrotikAgentScript] = useState("");
  const [scriptMode, setScriptMode] = useState<"vpn" | "python_agent" | "mikrotik_agent">("vpn");
  const [copied, setCopied] = useState(false);
  const [creatingSite, setCreatingSite] = useState(false);

  // Tab 2: Remote Auto-Scan with 3 protocol/connection options (WAN | VPN | SNMP)
  const [scanMode, setScanMode] = useState<"wan" | "vpn" | "snmp">("wan");
  const [routerIp, setRouterIp] = useState("");
  const [routerUser, setRouterUser] = useState("admin");
  const [routerPass, setRouterPass] = useState("");
  const [scanPort, setScanPort] = useState("");
  const [switchIps, setSwitchIps] = useState("");
  const [community, setCommunity] = useState("public");
  const [cctvVlan, setCctvVlan] = useState("10");
  const [scanning, setScanning] = useState(false);

  // Tab 3: Add Manual Device — dedicated panels for Switch, NVR, Camera, AP
  const [devRole, setDevRole] = useState<"managed_switch" | "nvr" | "camera" | "ap">("managed_switch");
  const [devName, setDevName] = useState("");
  const [devIp, setDevIp] = useState("");
  const [devMac, setDevMac] = useState("");
  const [devVendor, setDevVendor] = useState("Ruijie");
  const [devModel, setDevModel] = useState("");
  const [upstreamId, setUpstreamId] = useState<string>("");
  const [devPort, setDevPort] = useState(1);
  const [localPort, setLocalPort] = useState(24);
  const [totalPorts, setTotalPorts] = useState(24);
  const [devVlan, setDevVlan] = useState("10");
  const [devUser, setDevUser] = useState("admin");
  const [devPass, setDevPass] = useState("");
  const [devCommunity, setDevCommunity] = useState("public");
  const [devServicePort, setDevServicePort] = useState("161");
  const [devExtra, setDevExtra] = useState("");
  const [siteDevices, setSiteDevices] = useState<Array<{ id: number; name: string; ip: string; role: string }>>([]);
  const [addingDevice, setAddingDevice] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [isError, setIsError] = useState<boolean>(false);

  useEffect(() => {
    fetch(
      `${API_URL}/api/sites/${siteId}/vpn-script?noc_public_ip=${encodeURIComponent(
        nocPublicIp
      )}`
    )
      .then((r) => r.json())
      .then((d) => {
        if (d.mikrotik_script) setVpnScript(d.mikrotik_script);
        if (d.python_agent_cmd) setPythonAgentCmd(d.python_agent_cmd);
        if (d.mikrotik_agent_script) setMikrotikAgentScript(d.mikrotik_agent_script);
      })
      .catch(() => {});

    fetch(`${API_URL}/api/topology/${siteId}`)
      .then((r) => r.json())
      .then((topo) => {
        if (Array.isArray(topo.nodes)) {
          const list = topo.nodes
            .map((n: { id: string; data?: { name?: string; ip_address?: string; role?: string } }) => ({
              id: Number(String(n.id).replace("dev-", "")),
              name: n.data?.name || n.id,
              ip: n.data?.ip_address || "",
              role: n.data?.role || "endpoint",
            }))
            .filter((d: { id: number; role: string }) => !Number.isNaN(d.id) && (d.role === "router" || d.role === "managed_switch"));
          setSiteDevices(list);
          if (list.length > 0) setUpstreamId(String(list[0].id));
        }
      })
      .catch(() => {});
  }, [siteId, nocPublicIp]);

  const handleCreateSite = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!siteName.trim()) return;
    setCreatingSite(true);
    setStatusMsg(null);
    setIsError(false);
    try {
      const res = await fetch(`${API_URL}/api/sites`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: siteName.trim(),
          subnet: siteSubnet.trim(),
          vpn_ip: siteVpnIp.trim(),
          status: "online",
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Không thể tạo Site");

      const scriptRes = await fetch(
        `${API_URL}/api/sites/${data.id}/vpn-script?noc_public_ip=${encodeURIComponent(
          nocPublicIp
        )}`
      );
      const scriptData = await scriptRes.json();
      if (scriptData.mikrotik_script) setVpnScript(scriptData.mikrotik_script);
      if (scriptData.python_agent_cmd) setPythonAgentCmd(scriptData.python_agent_cmd);
      if (scriptData.mikrotik_agent_script) setMikrotikAgentScript(scriptData.mikrotik_agent_script);
      setIsError(false);
      setStatusMsg(`Đã tạo điểm mới "${data.name}" (Site #${data.id}). Chọn Script VPN hoặc Agent bên dưới!`);
      onSiteCreated(data.id);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Lỗi khi tạo Site";
      setIsError(true);
      setStatusMsg(msg);
      onNotify?.(false, msg);
    } finally {
      setCreatingSite(false);
    }
  };

  const handleRemoteScan = async (e: React.FormEvent) => {
    e.preventDefault();
    setScanning(true);
    setStatusMsg(null);
    setIsError(false);
    try {
      const swList =
        scanMode === "wan"
          ? []
          : switchIps
              .split(",")
              .map((s) => s.trim())
              .filter(Boolean);
      const parsedPort = scanPort.trim() ? Number(scanPort.trim()) : undefined;
      const res = await fetch(`${API_URL}/api/sites/${siteId}/scan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scan_mode: scanMode,
          router_ip: routerIp.trim() || undefined,
          router_user: routerUser.trim() || "admin",
          router_pass: routerPass,
          port: parsedPort && !Number.isNaN(parsedPort) ? parsedPort : undefined,
          switch_ips: swList,
          community: community.trim() || "public",
          cctv_vlans: cctvVlan ? [Number(cctvVlan)] : [10],
        }),
      });
      const data = await res.json();
      if (res.ok && data.notification !== false) {
        onNotify?.(
          true,
          `notification: true — Quét thành công ${Array.isArray(data.nodes) ? data.nodes.length : 0} thiết bị.`
        );
        onTopologyUpdated(data);
        onClose();
      } else {
        const errDetail = data.detail || "Quét không có kết quả";
        setIsError(true);
        setStatusMsg(errDetail);
        onNotify?.(false, errDetail);
      }
    } catch {
      const errDetail = "Không kết nối được tới Backend API";
      setIsError(true);
      setStatusMsg(errDetail);
      onNotify?.(false, errDetail);
    } finally {
      setScanning(false);
    }
  };

  const handleAddManualDevice = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!devName.trim() || !devIp.trim()) return;
    setAddingDevice(true);
    setStatusMsg(null);
    setIsError(false);
    try {
      const res = await fetch(`${API_URL}/api/sites/${siteId}/devices`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: devName.trim(),
          ip_address: devIp.trim(),
          mac_address: devMac.trim() || undefined,
          role: devRole,
          vendor: devVendor,
          model: devModel.trim() || (devExtra.trim() ? `${devVendor} (${devExtra.trim()})` : devVendor),
          upstream_device_id: upstreamId ? Number(upstreamId) : undefined,
          upstream_port: Number(devPort) || 1,
          local_port: devRole === "managed_switch" ? Number(localPort) || 24 : 1,
          total_ports: devRole === "managed_switch" ? Number(totalPorts) || 24 : undefined,
          vlan_id: devVlan ? Number(devVlan) : undefined,
          credentials_json: {
            username: devUser.trim() || "admin",
            password: devPass,
            community: devCommunity.trim() || "public",
            port: Number(devServicePort) || (devRole === "managed_switch" ? 161 : 80),
            snmp_port: Number(devServicePort) || 161,
            extra: devExtra.trim() || undefined,
          },
        }),
      });
      const data = await res.json();
      if (res.ok && data.notification !== false) {
        onNotify?.(true, `notification: true — Đã thêm ${devName.trim()} (${devIp.trim()}) vào sơ đồ.`);
        onTopologyUpdated(data);
        onClose();
      } else {
        const errDetail = data.detail || "Không thể thêm thiết bị";
        setIsError(true);
        setStatusMsg(errDetail);
        onNotify?.(false, errDetail);
      }
    } catch {
      const errDetail = "Lỗi kết nối tới Backend API";
      setIsError(true);
      setStatusMsg(errDetail);
      onNotify?.(false, errDetail);
    } finally {
      setAddingDevice(false);
    }
  };

  const activeScriptText =
    scriptMode === "vpn"
      ? vpnScript
      : scriptMode === "python_agent"
      ? pythonAgentCmd
      : mikrotikAgentScript;

  const copyScript = () => {
    navigator.clipboard.writeText(activeScriptText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm">
      <div className="flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-slate-800 bg-slate-900 shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800 px-6 py-4">
          <div>
            <h2 className="text-base font-bold text-white">
              Quản Trị & Đấu Nối Từ Xa (Site #{siteId})
            </h2>
            <p className="text-xs text-slate-400">
              Thêm chi nhánh mới, sinh Script VPN cho Router MikroTik hoặc thêm/quét thiết bị qua hầm VPN
            </p>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-white"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Mode Tabs */}
        <div className="flex border-b border-slate-800 bg-slate-950/60 px-6 pt-2 text-xs font-semibold">
          <button
            onClick={() => {
              setTab("site");
              setStatusMsg(null);
            }}
            className={`flex items-center gap-1.5 border-b-2 px-4 py-2.5 transition ${
              tab === "site"
                ? "border-cyan-400 text-cyan-300"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            <Terminal className="h-3.5 w-3.5" />
            1. Thêm Điểm & Sinh Script VPN
          </button>
          <button
            onClick={() => {
              setTab("scan");
              setStatusMsg(null);
            }}
            className={`flex items-center gap-1.5 border-b-2 px-4 py-2.5 transition ${
              tab === "scan"
                ? "border-emerald-400 text-emerald-300"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            <Radar className="h-3.5 w-3.5" />
            2. Quét Tự Động Từ Xa (Router/Switch)
          </button>
          <button
            onClick={() => {
              setTab("manual");
              setStatusMsg(null);
            }}
            className={`flex items-center gap-1.5 border-b-2 px-4 py-2.5 transition ${
              tab === "manual"
                ? "border-violet-400 text-violet-300"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            <PlusCircle className="h-3.5 w-3.5" />
            3. Thêm Thiết Bị Lẻ Vào Sơ Đồ
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-6 text-xs">
          {statusMsg && (
            <div
              className={`mb-4 flex items-start gap-2.5 rounded-lg border px-3.5 py-2.5 ${
                isError
                  ? "border-rose-500/50 bg-rose-950/60 text-rose-200"
                  : "border-cyan-500/40 bg-cyan-950/40 text-cyan-200"
              }`}
            >
              {isError ? (
                <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-rose-400" />
              ) : (
                <CheckCircle2 className="mt-0.5 h-4 w-4 flex-shrink-0 text-emerald-400" />
              )}
              <div>
                <span className="font-mono text-[11px] font-bold uppercase">
                  {isError ? "[notification: false] " : "[notification: true] "}
                </span>
                <span>{statusMsg}</span>
              </div>
            </div>
          )}

          {tab === "site" && (
            <div className="space-y-4">
              <form onSubmit={handleCreateSite} className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div>
                  <label className="block text-slate-300">Tên Chi Nhánh / Điểm Mới</label>
                  <input
                    required
                    placeholder="VD: Chi Nhánh TP.HCM"
                    value={siteName}
                    onChange={(e) => setSiteName(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white focus:border-cyan-400 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-slate-300">Dải mạng LAN Chi Nhánh (Subnet)</label>
                  <input
                    required
                    value={siteSubnet}
                    onChange={(e) => setSiteSubnet(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-white focus:border-cyan-400 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-slate-300">IP Hầm VPN Cấp Cho Router</label>
                  <input
                    value={siteVpnIp}
                    onChange={(e) => setSiteVpnIp(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-white focus:border-cyan-400 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-slate-300">IP Public Máy Chủ NOC (VPN Server)</label>
                  <input
                    value={nocPublicIp}
                    onChange={(e) => setNocPublicIp(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-white focus:border-cyan-400 focus:outline-none"
                  />
                </div>
                <div className="sm:col-span-2">
                  <button
                    type="submit"
                    disabled={creatingSite}
                    className="flex w-full items-center justify-center gap-2 rounded-lg bg-cyan-500 px-4 py-2.5 font-bold text-slate-950 hover:bg-cyan-400 disabled:opacity-50"
                  >
                    <Server className="h-4 w-4" />
                    {creatingSite ? "Đang tạo điểm mới..." : "Tạo Điểm Mới & Cập Nhật Script VPN"}
                  </button>
                </div>
              </form>

              <div className="rounded-xl border border-slate-800 bg-slate-950 p-3.5">
                <div className="mb-2.5 flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap gap-1.5">
                    <button
                      type="button"
                      onClick={() => setScriptMode("vpn")}
                      className={`rounded-md px-2.5 py-1 text-[11px] font-semibold transition ${
                        scriptMode === "vpn"
                          ? "bg-emerald-500/20 text-emerald-300 ring-1 ring-emerald-500/50"
                          : "bg-slate-900 text-slate-400 hover:text-slate-200"
                      }`}
                    >
                      1. Script VPN MikroTik (Pull)
                    </button>
                    <button
                      type="button"
                      onClick={() => setScriptMode("python_agent")}
                      className={`rounded-md px-2.5 py-1 text-[11px] font-semibold transition ${
                        scriptMode === "python_agent"
                          ? "bg-cyan-500/20 text-cyan-300 ring-1 ring-cyan-500/50"
                          : "bg-slate-900 text-slate-400 hover:text-slate-200"
                      }`}
                    >
                      2. Python Agent Tại Chỗ (Push + VPN)
                    </button>
                    <button
                      type="button"
                      onClick={() => setScriptMode("mikrotik_agent")}
                      className={`rounded-md px-2.5 py-1 text-[11px] font-semibold transition ${
                        scriptMode === "mikrotik_agent"
                          ? "bg-violet-500/20 text-violet-300 ring-1 ring-violet-500/50"
                          : "bg-slate-900 text-slate-400 hover:text-slate-200"
                      }`}
                    >
                      3. MikroTik Push Agent (Không cần VPN)
                    </button>
                  </div>

                  <div className="flex items-center gap-1.5">
                    <button
                      type="button"
                      onClick={copyScript}
                      className="flex items-center gap-1 rounded bg-slate-800 px-2.5 py-1 text-[11px] font-medium text-cyan-300 hover:bg-slate-700"
                    >
                      {copied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
                      {copied ? "Đã Copy!" : "Copy Lệnh"}
                    </button>
                  </div>
                </div>
                <pre className="max-h-48 overflow-x-auto whitespace-pre-wrap font-mono text-[11px] text-slate-300">
                  {activeScriptText}
                </pre>
              </div>
            </div>
          )}

          {tab === "scan" && (
            <form onSubmit={handleRemoteScan} className="space-y-4">
              {/* 3 Connection / Protocol Options */}
              <div>
                <label className="mb-2 block font-semibold text-slate-200">
                  Chọn Phương Thức / Giao Thức Kết Nối Thiết Bị (Chọn 1 trong 3):
                </label>
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                  <button
                    type="button"
                    onClick={() => {
                      setScanMode("wan");
                      setScanPort("");
                      setStatusMsg(null);
                    }}
                    className={`rounded-xl border p-3 text-left transition ${
                      scanMode === "wan"
                        ? "border-emerald-400 bg-emerald-500/15 text-emerald-200 ring-1 ring-emerald-400/50"
                        : "border-slate-800 bg-slate-950/80 text-slate-400 hover:border-slate-700 hover:text-slate-200"
                    }`}
                  >
                    <p className="font-bold text-white">1. Bằng IP WAN</p>
                    <p className="mt-0.5 text-[11px] text-slate-400">
                      Quét Modem/Router từ xa qua IP WAN Public (HTTPS 443 / API 8728 / SNMP)
                    </p>
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      setScanMode("vpn");
                      setScanPort("");
                      setStatusMsg(null);
                    }}
                    className={`rounded-xl border p-3 text-left transition ${
                      scanMode === "vpn"
                        ? "border-cyan-400 bg-cyan-500/15 text-cyan-200 ring-1 ring-cyan-400/50"
                        : "border-slate-800 bg-slate-950/80 text-slate-400 hover:border-slate-700 hover:text-slate-200"
                    }`}
                  >
                    <p className="font-bold text-white">2. Bằng Đường Hầm VPN</p>
                    <p className="mt-0.5 text-[11px] text-slate-400">
                      Quét xuyên hầm VPN / LAN nội bộ (Router Gateway + cụm Switch LAN)
                    </p>
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      setScanMode("snmp");
                      setScanPort("161");
                      setStatusMsg(null);
                    }}
                    className={`rounded-xl border p-3 text-left transition ${
                      scanMode === "snmp"
                        ? "border-violet-400 bg-violet-500/15 text-violet-200 ring-1 ring-violet-400/50"
                        : "border-slate-800 bg-slate-950/80 text-slate-400 hover:border-slate-700 hover:text-slate-200"
                    }`}
                  >
                    <p className="font-bold text-white">3. Bằng Giao Thức SNMP</p>
                    <p className="mt-0.5 text-[11px] text-slate-400">
                      Đọc CPU, RAM, Uptime, Port đang cắm qua SNMPv2c (DrayTek, FortiGate, Ruijie...)
                    </p>
                  </button>
                </div>
              </div>

              {/* Option 1: IP WAN */}
              {scanMode === "wan" && (
                <div className="space-y-3 rounded-xl border border-slate-800 bg-slate-950/50 p-4">
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                    <div className="sm:col-span-2">
                      <label className="block text-slate-300">
                        Địa chỉ IP WAN của Router / Modem (VD: DrayTek, MikroTik, FortiGate)
                      </label>
                      <input
                        required
                        value={routerIp}
                        onChange={(e) => setRouterIp(e.target.value)}
                        placeholder="VD: 14.224.195.129"
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-white"
                      />
                    </div>
                    <div>
                      <label className="block text-slate-300">Cổng (Port) Web/API</label>
                      <input
                        value={scanPort}
                        onChange={(e) => setScanPort(e.target.value)}
                        placeholder="Tự động (443 / 80 / 8728)"
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-white"
                      />
                    </div>
                  </div>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                    <div>
                      <label className="block text-slate-300">Tài khoản quản trị</label>
                      <input
                        value={routerUser}
                        onChange={(e) => setRouterUser(e.target.value)}
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                      />
                    </div>
                    <div>
                      <label className="block text-slate-300">Mật khẩu quản trị</label>
                      <input
                        type="password"
                        value={routerPass}
                        onChange={(e) => setRouterPass(e.target.value)}
                        placeholder="Nhập mật khẩu thiết bị"
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                      />
                    </div>
                    <div>
                      <label className="block text-slate-300">SNMP Community (nếu mở)</label>
                      <input
                        value={community}
                        onChange={(e) => setCommunity(e.target.value)}
                        placeholder="public"
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-white"
                      />
                    </div>
                  </div>
                </div>
              )}

              {/* Option 2: Đường Hầm VPN / LAN */}
              {scanMode === "vpn" && (
                <div className="space-y-3 rounded-xl border border-slate-800 bg-slate-950/50 p-4">
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                    <div>
                      <label className="block text-slate-300">IP Router (Trong hầm VPN / LAN)</label>
                      <input
                        value={routerIp}
                        onChange={(e) => setRouterIp(e.target.value)}
                        placeholder="VD: 10.255.1.2 hoặc 192.168.1.1"
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-white"
                      />
                    </div>
                    <div>
                      <label className="block text-slate-300">Tài khoản Router</label>
                      <input
                        value={routerUser}
                        onChange={(e) => setRouterUser(e.target.value)}
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                      />
                    </div>
                    <div>
                      <label className="block text-slate-300">Mật khẩu Router</label>
                      <input
                        type="password"
                        value={routerPass}
                        onChange={(e) => setRouterPass(e.target.value)}
                        placeholder="Nhập mật khẩu Router"
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                      />
                    </div>
                  </div>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                    <div className="sm:col-span-2">
                      <label className="block text-slate-300">
                        Danh sách IP Switch LAN Quản Lý (cách nhau dấu phẩy)
                      </label>
                      <input
                        value={switchIps}
                        onChange={(e) => setSwitchIps(e.target.value)}
                        placeholder="VD: 192.168.1.2, 192.168.1.3"
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-white"
                      />
                    </div>
                    <div>
                      <label className="block text-slate-300">SNMP Community</label>
                      <input
                        value={community}
                        onChange={(e) => setCommunity(e.target.value)}
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-white"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="block text-slate-300">VLAN ID Dành Cho Camera/CCTV</label>
                    <input
                      value={cctvVlan}
                      onChange={(e) => setCctvVlan(e.target.value)}
                      className="mt-1 w-32 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-white"
                    />
                  </div>
                </div>
              )}

              {/* Option 3: Giao thức SNMP */}
              {scanMode === "snmp" && (
                <div className="space-y-3 rounded-xl border border-slate-800 bg-slate-950/50 p-4">
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <div>
                      <label className="block text-slate-300">
                        IP Router / Modem SNMP (DrayTek, FortiGate, Cisco, MikroTik...)
                      </label>
                      <input
                        value={routerIp}
                        onChange={(e) => setRouterIp(e.target.value)}
                        placeholder="VD: 192.168.1.1 hoặc 14.224.195.129"
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-white"
                      />
                    </div>
                    <div>
                      <label className="block text-slate-300">
                        Danh sách IP Switch SNMP (cách nhau dấu phẩy, nếu có)
                      </label>
                      <input
                        value={switchIps}
                        onChange={(e) => setSwitchIps(e.target.value)}
                        placeholder="VD: 192.168.1.2, 192.168.1.3"
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-white"
                      />
                    </div>
                  </div>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                    <div>
                      <label className="block text-slate-300">SNMP Community (Read)</label>
                      <input
                        required
                        value={community}
                        onChange={(e) => setCommunity(e.target.value)}
                        placeholder="public"
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-white"
                      />
                    </div>
                    <div>
                      <label className="block text-slate-300">Cổng UDP SNMP</label>
                      <input
                        value={scanPort}
                        onChange={(e) => setScanPort(e.target.value)}
                        placeholder="161"
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-white"
                      />
                    </div>
                    <div>
                      <label className="block text-slate-300">VLAN ID Camera/CCTV</label>
                      <input
                        value={cctvVlan}
                        onChange={(e) => setCctvVlan(e.target.value)}
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-white"
                      />
                    </div>
                  </div>
                </div>
              )}

              <button
                type="submit"
                disabled={scanning}
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-500 px-4 py-2.5 font-bold text-slate-950 hover:bg-emerald-400 disabled:opacity-50"
              >
                <Radar className={`h-4 w-4 ${scanning ? "animate-spin" : ""}`} />
                {scanning
                  ? "Đang kết nối thiết bị & đọc CPU, RAM, Uptime, Port..."
                  : "Bắt Đầu Quét Thiết Bị & Đọc Thông Số"}
              </button>
            </form>
          )}

          {tab === "manual" && (
            <form onSubmit={handleAddManualDevice} className="space-y-4">
              {/* 4 Dedicated Device Type Selector Cards */}
              <div>
                <label className="mb-2 block font-semibold text-slate-200">
                  Chọn Loại Thiết Bị Cần Đấu Nối Vào Sơ Đồ (Mỗi loại có bảng thông số riêng):
                </label>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                  <button
                    type="button"
                    onClick={() => {
                      setDevRole("managed_switch");
                      setDevVendor("Ruijie");
                      setDevServicePort("161");
                      setDevVlan("1");
                      setStatusMsg(null);
                    }}
                    className={`rounded-xl border p-2.5 text-left transition ${
                      devRole === "managed_switch"
                        ? "border-sky-400 bg-sky-500/15 text-sky-200 ring-1 ring-sky-400/50"
                        : "border-slate-800 bg-slate-950/80 text-slate-400 hover:border-slate-700"
                    }`}
                  >
                    <p className="font-bold text-white">1. Switch Quản Lý</p>
                    <p className="mt-0.5 text-[10px] text-slate-400">SNMP / Cổng Uplink / 8–48 Port</p>
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      setDevRole("nvr");
                      setDevVendor("Hikvision");
                      setDevServicePort("80");
                      setDevExtra("32 CH");
                      setDevVlan("10");
                      setStatusMsg(null);
                    }}
                    className={`rounded-xl border p-2.5 text-left transition ${
                      devRole === "nvr"
                        ? "border-emerald-400 bg-emerald-500/15 text-emerald-200 ring-1 ring-emerald-400/50"
                        : "border-slate-800 bg-slate-950/80 text-slate-400 hover:border-slate-700"
                    }`}
                  >
                    <p className="font-bold text-white">2. Đầu Ghi NVR</p>
                    <p className="mt-0.5 text-[10px] text-slate-400">ISAPI / Ổ cứng HDD / Số kênh</p>
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      setDevRole("camera");
                      setDevVendor("Hikvision");
                      setDevServicePort("554");
                      setDevExtra("CH-01");
                      setDevVlan("10");
                      setStatusMsg(null);
                    }}
                    className={`rounded-xl border p-2.5 text-left transition ${
                      devRole === "camera"
                        ? "border-amber-400 bg-amber-500/15 text-amber-200 ring-1 ring-amber-400/50"
                        : "border-slate-800 bg-slate-950/80 text-slate-400 hover:border-slate-700"
                    }`}
                  >
                    <p className="font-bold text-white">3. Camera IP</p>
                    <p className="mt-0.5 text-[10px] text-slate-400">RTSP / PoE Port / Gán kênh NVR</p>
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      setDevRole("ap");
                      setDevVendor("Aruba");
                      setDevServicePort("161");
                      setDevExtra("Wi-Fi 6");
                      setDevVlan("20");
                      setStatusMsg(null);
                    }}
                    className={`rounded-xl border p-2.5 text-left transition ${
                      devRole === "ap"
                        ? "border-violet-400 bg-violet-500/15 text-violet-200 ring-1 ring-violet-400/50"
                        : "border-slate-800 bg-slate-950/80 text-slate-400 hover:border-slate-700"
                    }`}
                  >
                    <p className="font-bold text-white">4. Bộ Phát Wi-Fi AP</p>
                    <p className="mt-0.5 text-[10px] text-slate-400">SSID / Băng tần / Cổng PoE</p>
                  </button>
                </div>
              </div>

              {/* Panel 1: Switch Quản Lý */}
              {devRole === "managed_switch" && (
                <div className="space-y-3 rounded-xl border border-sky-500/30 bg-slate-950/60 p-4">
                  <p className="font-semibold text-sky-300">
                    Bảng Kết Nối Switch Quản Lý (Đọc cổng UP/DOWN, CPU, RAM qua SNMP)
                  </p>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                    <div>
                      <label className="block text-slate-300">Tên Switch</label>
                      <input
                        required
                        placeholder="VD: Core-SW-Tầng-1"
                        value={devName}
                        onChange={(e) => setDevName(e.target.value)}
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                      />
                    </div>
                    <div>
                      <label className="block text-slate-300">Địa chỉ IP Switch</label>
                      <input
                        required
                        placeholder="VD: 192.168.10.2"
                        value={devIp}
                        onChange={(e) => setDevIp(e.target.value)}
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-white"
                      />
                    </div>
                    <div>
                      <label className="block text-slate-300">Hãng Switch</label>
                      <select
                        value={devVendor}
                        onChange={(e) => setDevVendor(e.target.value)}
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                      >
                        <option value="Ruijie">Ruijie / Reyee</option>
                        <option value="Aruba">Aruba / HPE</option>
                        <option value="Cisco">Cisco</option>
                        <option value="Hikvision">Hikvision PoE Switch</option>
                        <option value="MikroTik">MikroTik CRS/CSS</option>
                        <option value="TP-Link">TP-Link Omada / JetStream</option>
                        <option value="Fortinet">FortiSwitch</option>
                      </select>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-4">
                    <div>
                      <label className="block text-slate-300">Tổng số Port</label>
                      <select
                        value={totalPorts}
                        onChange={(e) => {
                          const tot = Number(e.target.value);
                          setTotalPorts(tot);
                          setLocalPort(tot);
                        }}
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-white"
                      >
                        <option value={8}>8 Ports</option>
                        <option value={16}>16 Ports</option>
                        <option value={24}>24 Ports</option>
                        <option value={48}>48 Ports</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-slate-300">SNMP Community</label>
                      <input
                        value={devCommunity}
                        onChange={(e) => setDevCommunity(e.target.value)}
                        placeholder="public"
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-white"
                      />
                    </div>
                    <div>
                      <label className="block text-slate-300">Cổng UDP SNMP</label>
                      <input
                        value={devServicePort}
                        onChange={(e) => setDevServicePort(e.target.value)}
                        placeholder="161"
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-white"
                      />
                    </div>
                    <div>
                      <label className="block text-slate-300">Địa chỉ MAC (Tùy chọn)</label>
                      <input
                        value={devMac}
                        onChange={(e) => setDevMac(e.target.value)}
                        placeholder="00:D0:F8:00:01:01"
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-white"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-1 gap-3 border-t border-slate-800 pt-3 sm:grid-cols-3">
                    <div>
                      <label className="block text-slate-300">Nối Uplink lên Thiết Bị nào?</label>
                      <select
                        value={upstreamId}
                        onChange={(e) => setUpstreamId(e.target.value)}
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                      >
                        {siteDevices.length === 0 ? (
                          <option value="">Tự động chọn Router gốc</option>
                        ) : (
                          siteDevices.map((d) => (
                            <option key={d.id} value={d.id}>
                              {d.name} ({d.ip})
                            </option>
                          ))
                        )}
                      </select>
                    </div>
                    <div>
                      <label className="block text-slate-300">Cổng LAN trên Router/Switch trên</label>
                      <input
                        type="number"
                        min={1}
                        max={48}
                        value={devPort}
                        onChange={(e) => setDevPort(Number(e.target.value))}
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-white"
                      />
                    </div>
                    <div>
                      <label className="block text-slate-300">Cổng Uplink trên Switch này</label>
                      <input
                        type="number"
                        min={1}
                        max={48}
                        value={localPort}
                        onChange={(e) => setLocalPort(Number(e.target.value))}
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-white"
                      />
                    </div>
                  </div>
                </div>
              )}

              {/* Panel 2: Đầu Ghi Hình NVR */}
              {devRole === "nvr" && (
                <div className="space-y-3 rounded-xl border border-emerald-500/30 bg-slate-950/60 p-4">
                  <p className="font-semibold text-emerald-300">
                    Bảng Kết Nối Đầu Ghi Hình NVR (Đọc ổ cứng HDD & Kênh Camera qua ISAPI/Web)
                  </p>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                    <div>
                      <label className="block text-slate-300">Tên Đầu Ghi NVR</label>
                      <input
                        required
                        placeholder="VD: NVR-Hikvision-Chính"
                        value={devName}
                        onChange={(e) => setDevName(e.target.value)}
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                      />
                    </div>
                    <div>
                      <label className="block text-slate-300">Địa chỉ IP Đầu Ghi</label>
                      <input
                        required
                        placeholder="VD: 192.168.10.50"
                        value={devIp}
                        onChange={(e) => setDevIp(e.target.value)}
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-white"
                      />
                    </div>
                    <div>
                      <label className="block text-slate-300">Hãng Đầu Ghi</label>
                      <select
                        value={devVendor}
                        onChange={(e) => setDevVendor(e.target.value)}
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                      >
                        <option value="Hikvision">Hikvision</option>
                        <option value="Dahua">Dahua</option>
                        <option value="Uniview">Uniview (UNV)</option>
                        <option value="Kbvision">KBVision</option>
                        <option value="Hanwha">Hanwha Vision</option>
                      </select>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-4">
                    <div>
                      <label className="block text-slate-300">Tài khoản NVR</label>
                      <input
                        value={devUser}
                        onChange={(e) => setDevUser(e.target.value)}
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                      />
                    </div>
                    <div>
                      <label className="block text-slate-300">Mật khẩu NVR</label>
                      <input
                        type="password"
                        value={devPass}
                        onChange={(e) => setDevPass(e.target.value)}
                        placeholder="Mật khẩu ISAPI/Web"
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                      />
                    </div>
                    <div>
                      <label className="block text-slate-300">Cổng HTTP/ISAPI</label>
                      <input
                        value={devServicePort}
                        onChange={(e) => setDevServicePort(e.target.value)}
                        placeholder="80"
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-white"
                      />
                    </div>
                    <div>
                      <label className="block text-slate-300">Số kênh tối đa</label>
                      <select
                        value={devExtra}
                        onChange={(e) => setDevExtra(e.target.value)}
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                      >
                        <option value="8 CH">8 Kênh (8 CH)</option>
                        <option value="16 CH">16 Kênh (16 CH)</option>
                        <option value="32 CH">32 Kênh (32 CH)</option>
                        <option value="64 CH">64 Kênh (64 CH)</option>
                      </select>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 gap-3 border-t border-slate-800 pt-3 sm:grid-cols-3">
                    <div>
                      <label className="block text-slate-300">Cắm vào Switch / Router nào?</label>
                      <select
                        value={upstreamId}
                        onChange={(e) => setUpstreamId(e.target.value)}
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                      >
                        {siteDevices.length === 0 ? (
                          <option value="">Tự động chọn Switch/Router</option>
                        ) : (
                          siteDevices.map((d) => (
                            <option key={d.id} value={d.id}>
                              {d.name} ({d.ip})
                            </option>
                          ))
                        )}
                      </select>
                    </div>
                    <div>
                      <label className="block text-slate-300">Cắm vào Cổng (Port) số mấy</label>
                      <input
                        type="number"
                        min={1}
                        max={48}
                        value={devPort}
                        onChange={(e) => setDevPort(Number(e.target.value))}
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-white"
                      />
                    </div>
                    <div>
                      <label className="block text-slate-300">VLAN ID</label>
                      <input
                        value={devVlan}
                        onChange={(e) => setDevVlan(e.target.value)}
                        placeholder="10"
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-white"
                      />
                    </div>
                  </div>
                </div>
              )}

              {/* Panel 3: Camera IP */}
              {devRole === "camera" && (
                <div className="space-y-3 rounded-xl border border-amber-500/30 bg-slate-950/60 p-4">
                  <p className="font-semibold text-amber-300">
                    Bảng Kết Nối Camera IP (Định vị cổng Switch PoE, VLAN & Kênh ghi hình)
                  </p>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                    <div>
                      <label className="block text-slate-300">Tên Camera IP</label>
                      <input
                        required
                        placeholder="VD: Cam-Cổng-Chính-01"
                        value={devName}
                        onChange={(e) => setDevName(e.target.value)}
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                      />
                    </div>
                    <div>
                      <label className="block text-slate-300">Địa chỉ IP Camera</label>
                      <input
                        required
                        placeholder="VD: 192.168.10.101"
                        value={devIp}
                        onChange={(e) => setDevIp(e.target.value)}
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-white"
                      />
                    </div>
                    <div>
                      <label className="block text-slate-300">Hãng Camera</label>
                      <select
                        value={devVendor}
                        onChange={(e) => setDevVendor(e.target.value)}
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                      >
                        <option value="Hikvision">Hikvision</option>
                        <option value="Dahua">Dahua</option>
                        <option value="Imou">Imou</option>
                        <option value="Ezviz">Ezviz</option>
                        <option value="Uniview">Uniview (UNV)</option>
                        <option value="Hanwha">Hanwha Vision</option>
                        <option value="Axis">Axis</option>
                      </select>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-4">
                    <div>
                      <label className="block text-slate-300">Địa chỉ MAC Camera</label>
                      <input
                        value={devMac}
                        onChange={(e) => setDevMac(e.target.value)}
                        placeholder="BC:AD:28:00:11:01"
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-white"
                      />
                    </div>
                    <div>
                      <label className="block text-slate-300">Kênh trên NVR</label>
                      <input
                        value={devExtra}
                        onChange={(e) => setDevExtra(e.target.value)}
                        placeholder="VD: CH-01"
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-white"
                      />
                    </div>
                    <div>
                      <label className="block text-slate-300">Cổng RTSP / HTTP</label>
                      <input
                        value={devServicePort}
                        onChange={(e) => setDevServicePort(e.target.value)}
                        placeholder="554"
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-white"
                      />
                    </div>
                    <div>
                      <label className="block text-slate-300">Mật khẩu Camera</label>
                      <input
                        type="password"
                        value={devPass}
                        onChange={(e) => setDevPass(e.target.value)}
                        placeholder="Tùy chọn"
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-1 gap-3 border-t border-slate-800 pt-3 sm:grid-cols-3">
                    <div>
                      <label className="block text-slate-300">Cắm vào Switch PoE / Router nào?</label>
                      <select
                        value={upstreamId}
                        onChange={(e) => setUpstreamId(e.target.value)}
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                      >
                        {siteDevices.length === 0 ? (
                          <option value="">Tự động chọn Switch/Router</option>
                        ) : (
                          siteDevices.map((d) => (
                            <option key={d.id} value={d.id}>
                              {d.name} ({d.ip})
                            </option>
                          ))
                        )}
                      </select>
                    </div>
                    <div>
                      <label className="block text-slate-300">Cắm tại Cổng (Port) số mấy</label>
                      <input
                        type="number"
                        min={1}
                        max={48}
                        value={devPort}
                        onChange={(e) => setDevPort(Number(e.target.value))}
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-white"
                      />
                    </div>
                    <div>
                      <label className="block text-slate-300">VLAN Camera</label>
                      <input
                        value={devVlan}
                        onChange={(e) => setDevVlan(e.target.value)}
                        placeholder="10"
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-white"
                      />
                    </div>
                  </div>
                </div>
              )}

              {/* Panel 4: Bộ Phát Wi-Fi AP */}
              {devRole === "ap" && (
                <div className="space-y-3 rounded-xl border border-violet-500/30 bg-slate-950/60 p-4">
                  <p className="font-semibold text-violet-300">
                    Bảng Kết Nối Bộ Phát Wi-Fi Access Point (SSID, SNMP & Cổng Uplink PoE)
                  </p>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                    <div>
                      <label className="block text-slate-300">Tên Access Point</label>
                      <input
                        required
                        placeholder="VD: AP-Sảnh-Tầng-1"
                        value={devName}
                        onChange={(e) => setDevName(e.target.value)}
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                      />
                    </div>
                    <div>
                      <label className="block text-slate-300">Địa chỉ IP AP</label>
                      <input
                        required
                        placeholder="VD: 192.168.20.15"
                        value={devIp}
                        onChange={(e) => setDevIp(e.target.value)}
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-white"
                      />
                    </div>
                    <div>
                      <label className="block text-slate-300">Hãng Wi-Fi AP</label>
                      <select
                        value={devVendor}
                        onChange={(e) => setDevVendor(e.target.value)}
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                      >
                        <option value="Aruba">Aruba Instant On / IAP</option>
                        <option value="Ubiquiti">Ubiquiti UniFi</option>
                        <option value="Ruijie">Ruijie / Reyee</option>
                        <option value="MikroTik">MikroTik cAP / wAP</option>
                        <option value="TP-Link">TP-Link Omada EAP</option>
                        <option value="Cisco">Cisco Catalyst / Meraki</option>
                      </select>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                    <div>
                      <label className="block text-slate-300">Địa chỉ MAC AP</label>
                      <input
                        value={devMac}
                        onChange={(e) => setDevMac(e.target.value)}
                        placeholder="24:DE:C6:11:22:33"
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-white"
                      />
                    </div>
                    <div>
                      <label className="block text-slate-300">Tên Sóng (SSID) / Chuẩn Wi-Fi</label>
                      <input
                        value={devExtra}
                        onChange={(e) => setDevExtra(e.target.value)}
                        placeholder="VD: SVC-Corp (Wi-Fi 6)"
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                      />
                    </div>
                    <div>
                      <label className="block text-slate-300">SNMP Community (nếu bật)</label>
                      <input
                        value={devCommunity}
                        onChange={(e) => setDevCommunity(e.target.value)}
                        placeholder="public"
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-white"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-1 gap-3 border-t border-slate-800 pt-3 sm:grid-cols-3">
                    <div>
                      <label className="block text-slate-300">Cắm vào Switch PoE / Router nào?</label>
                      <select
                        value={upstreamId}
                        onChange={(e) => setUpstreamId(e.target.value)}
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                      >
                        {siteDevices.length === 0 ? (
                          <option value="">Tự động chọn Switch/Router</option>
                        ) : (
                          siteDevices.map((d) => (
                            <option key={d.id} value={d.id}>
                              {d.name} ({d.ip})
                            </option>
                          ))
                        )}
                      </select>
                    </div>
                    <div>
                      <label className="block text-slate-300">Cắm tại Cổng (Port) số mấy</label>
                      <input
                        type="number"
                        min={1}
                        max={48}
                        value={devPort}
                        onChange={(e) => setDevPort(Number(e.target.value))}
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-white"
                      />
                    </div>
                    <div>
                      <label className="block text-slate-300">VLAN Wi-Fi</label>
                      <input
                        value={devVlan}
                        onChange={(e) => setDevVlan(e.target.value)}
                        placeholder="20"
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-white"
                      />
                    </div>
                  </div>
                </div>
              )}

              <button
                type="submit"
                disabled={addingDevice}
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-violet-500 px-4 py-2.5 font-bold text-white hover:bg-violet-400 disabled:opacity-50"
              >
                <PlusCircle className="h-4 w-4" />
                {addingDevice
                  ? "Đang kiểm tra kết nối & lưu vào sơ đồ..."
                  : "Thêm Thiết Bị & Đấu Nối Cổng Ngay"}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
