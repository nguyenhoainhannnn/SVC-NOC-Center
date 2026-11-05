"use client";

import { useEffect, useState } from "react";
import {
  Check,
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
  onTopologyUpdated: (data: { nodes?: unknown[]; edges?: unknown[]; alerts?: unknown[] }) => void;
}

export function RemoteManageModal({
  siteId,
  initialMode,
  onClose,
  onSiteCreated,
  onTopologyUpdated,
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

  // Tab 2: Remote Auto-Scan (RouterOS API + Switch SNMP)
  const [routerIp, setRouterIp] = useState("10.10.0.1");
  const [routerUser, setRouterUser] = useState("admin");
  const [routerPass, setRouterPass] = useState("");
  const [switchIps, setSwitchIps] = useState("10.10.0.2, 10.10.0.3");
  const [community, setCommunity] = useState("public");
  const [cctvVlan, setCctvVlan] = useState("10");
  const [scanning, setScanning] = useState(false);

  // Tab 3: Add Manual Device
  const [devName, setDevName] = useState("");
  const [devIp, setDevIp] = useState("10.10.10.105");
  const [devMac, setDevMac] = useState("BC:AD:28:00:11:05");
  const [devRole, setDevRole] = useState("camera");
  const [devVendor, setDevVendor] = useState("Hikvision");
  const [devPort, setDevPort] = useState(5);
  const [addingDevice, setAddingDevice] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

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
  }, [siteId, nocPublicIp]);

  const handleCreateSite = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!siteName.trim()) return;
    setCreatingSite(true);
    setStatusMsg(null);
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
      setStatusMsg(`Đã tạo điểm mới "${data.name}" (Site #${data.id}). Chọn Script VPN hoặc Agent bên dưới!`);
      onSiteCreated(data.id);
    } catch (err: unknown) {
      setStatusMsg(err instanceof Error ? err.message : "Lỗi khi tạo Site");
    } finally {
      setCreatingSite(false);
    }
  };

  const handleRemoteScan = async (e: React.FormEvent) => {
    e.preventDefault();
    setScanning(true);
    setStatusMsg(null);
    try {
      const swList = switchIps
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      const res = await fetch(`${API_URL}/api/sites/${siteId}/scan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          router_ip: routerIp.trim() || undefined,
          router_user: routerUser.trim() || "admin",
          router_pass: routerPass,
          switch_ips: swList,
          community: community.trim() || "public",
          cctv_vlans: cctvVlan ? [Number(cctvVlan)] : [10],
        }),
      });
      const data = await res.json();
      if (res.ok) {
        onTopologyUpdated(data);
        onClose();
      } else {
        setStatusMsg(data.detail || "Quét thất bại");
      }
    } catch {
      setStatusMsg("Không kết nối được tới Backend API");
    } finally {
      setScanning(false);
    }
  };

  const handleAddManualDevice = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!devName.trim() || !devIp.trim()) return;
    setAddingDevice(true);
    setStatusMsg(null);
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
          upstream_port: Number(devPort) || 1,
        }),
      });
      const data = await res.json();
      if (res.ok) {
        onTopologyUpdated(data);
        onClose();
      } else {
        setStatusMsg(data.detail || "Không thể thêm thiết bị");
      }
    } catch {
      setStatusMsg("Lỗi kết nối tới Backend API");
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

  const handleTestAgentPush = async () => {
    setScanning(true);
    setStatusMsg(null);
    try {
      const res = await fetch(`${API_URL}/api/sites/${siteId}/agent-push`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-NOC-Agent-Key": "noc-agent-key",
        },
        body: JSON.stringify({
          agent_hostname: `Agent-Site-${siteId}`,
        }),
      });
      const data = await res.json();
      if (res.ok) {
        onTopologyUpdated(data);
        onClose();
      } else {
        setStatusMsg(data.detail || "Agent Push thất bại");
      }
    } catch {
      setStatusMsg("Không kết nối được tới Backend API");
    } finally {
      setScanning(false);
    }
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
            onClick={() => setTab("site")}
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
            onClick={() => setTab("scan")}
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
            onClick={() => setTab("manual")}
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
            <div className="mb-4 rounded-lg border border-cyan-500/40 bg-cyan-950/40 px-3.5 py-2.5 text-cyan-200">
              {statusMsg}
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
                      onClick={handleTestAgentPush}
                      className="rounded bg-emerald-500/20 px-2.5 py-1 text-[11px] font-semibold text-emerald-300 ring-1 ring-emerald-500/40 hover:bg-emerald-500/30"
                    >
                      Test Agent Push Ngay
                    </button>
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
            <form onSubmit={handleRemoteScan} className="space-y-3.5">
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <div>
                  <label className="block text-slate-300">IP Router (LAN hoặc VPN)</label>
                  <input
                    value={routerIp}
                    onChange={(e) => setRouterIp(e.target.value)}
                    placeholder="10.10.0.1"
                    className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-white"
                  />
                </div>
                <div>
                  <label className="block text-slate-300">Tài khoản API Router</label>
                  <input
                    value={routerUser}
                    onChange={(e) => setRouterUser(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                  />
                </div>
                <div>
                  <label className="block text-slate-300">Mật khẩu API Router</label>
                  <input
                    type="password"
                    value={routerPass}
                    onChange={(e) => setRouterPass(e.target.value)}
                    placeholder="Để trống nếu chạy mẫu"
                    className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <div className="sm:col-span-2">
                  <label className="block text-slate-300">
                    Danh sách IP Switch Quản Lý (cách nhau dấu phẩy)
                  </label>
                  <input
                    value={switchIps}
                    onChange={(e) => setSwitchIps(e.target.value)}
                    placeholder="10.10.0.2, 10.10.0.3"
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

              <button
                type="submit"
                disabled={scanning}
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-500 px-4 py-2.5 font-bold text-slate-950 hover:bg-emerald-400 disabled:opacity-50"
              >
                <Radar className={`h-4 w-4 ${scanning ? "animate-spin" : ""}`} />
                {scanning
                  ? "Đang quét RouterOS API + Switch SNMP qua VPN..."
                  : "Bắt Đầu Quét Tự Động & Vẽ Lại Sơ Đồ"}
              </button>
            </form>
          )}

          {tab === "manual" && (
            <form onSubmit={handleAddManualDevice} className="space-y-3.5">
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div>
                  <label className="block text-slate-300">Tên Thiết Bị</label>
                  <input
                    required
                    placeholder="VD: Camera Kho Hàng 05"
                    value={devName}
                    onChange={(e) => setDevName(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                  />
                </div>
                <div>
                  <label className="block text-slate-300">Địa chỉ IP Nội Bộ</label>
                  <input
                    required
                    value={devIp}
                    onChange={(e) => setDevIp(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-white"
                  />
                </div>
                <div>
                  <label className="block text-slate-300">Địa chỉ MAC (Tự nhận diện hãng)</label>
                  <input
                    value={devMac}
                    onChange={(e) => setDevMac(e.target.value)}
                    placeholder="BC:AD:28:00:11:05"
                    className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-white"
                  />
                </div>
                <div>
                  <label className="block text-slate-300">Loại Thiết Bị</label>
                  <select
                    value={devRole}
                    onChange={(e) => setDevRole(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                  >
                    <option value="camera">Camera IP</option>
                    <option value="nvr">Đầu ghi hình NVR</option>
                    <option value="managed_switch">Managed Switch</option>
                    <option value="ap">Bộ phát Wi-Fi AP</option>
                    <option value="router">Router / Firewall</option>
                    <option value="endpoint">Máy tính / Server (Endpoint)</option>
                  </select>
                </div>
                <div>
                  <label className="block text-slate-300">Hãng Sản Xuất (Vendor)</label>
                  <select
                    value={devVendor}
                    onChange={(e) => setDevVendor(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                  >
                    <option value="Hikvision">Hikvision</option>
                    <option value="Dahua">Dahua</option>
                    <option value="Ruijie">Ruijie / Reyee</option>
                    <option value="MikroTik">MikroTik</option>
                    <option value="Fortinet">Fortinet</option>
                    <option value="DrayTek">DrayTek</option>
                    <option value="Aruba">Aruba</option>
                    <option value="Cisco">Cisco</option>
                    <option value="Ubiquiti">Ubiquiti</option>
                    <option value="TP-Link">TP-Link</option>
                  </select>
                </div>
                <div>
                  <label className="block text-slate-300">Cắm Vào Cổng Switch Số (Port)</label>
                  <input
                    type="number"
                    min={1}
                    max={48}
                    value={devPort}
                    onChange={(e) => setDevPort(Number(e.target.value))}
                    className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-white"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={addingDevice}
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-violet-500 px-4 py-2.5 font-bold text-white hover:bg-violet-400 disabled:opacity-50"
              >
                <PlusCircle className="h-4 w-4" />
                {addingDevice ? "Đang lưu vào PostgreSQL..." : "Thêm Thiết Bị Vào Sơ Đồ Ngay"}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
