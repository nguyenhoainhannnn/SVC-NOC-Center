"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  AlertTriangle,
  ArrowLeft,
  Camera,
  CheckCircle2,
  ExternalLink,
  HardDrive,
  Network,
  RefreshCw,
  ShieldAlert,
  Video,
  X,
} from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface HddInfo {
  id: number;
  name: string;
  status: string;
  capacity_gb: number;
  free_gb: number;
}

interface NvrCardItem {
  id: string;
  name: string;
  model: string;
  ip_address: string;
  mac_address?: string;
  online_channels: number;
  total_channels: number;
  is_online: boolean;
  upstream_switch?: string;
  upstream_port?: string;
  hdds: HddInfo[];
}

interface CameraNvrLink {
  nvr_name: string;
  nvr_ip: string;
  channel_id: number;
  status: "online" | "warning" | "offline";
}

interface DiscoveredCameraItem {
  id: string;
  name: string;
  model: string;
  vendor: string;
  ip_address: string;
  mac_address: string;
  is_online: boolean;
  upstream_switch: string;
  upstream_port: string;
  vlan_id?: number;
  nvr_links: CameraNvrLink[];
}

interface CctvAlert {
  severity: string;
  message: string;
}

const FALLBACK_CCTV_DATA: {
  nvrs: NvrCardItem[];
  cameras: DiscoveredCameraItem[];
  alerts: CctvAlert[];
} = {
  nvrs: [
    {
      id: "nvr-1",
      name: "Hikvision-NVR-01 (Chính)",
      model: "DS-7732NI-I4/16P",
      ip_address: "10.10.10.50",
      mac_address: "4C:0F:6E:10:20:30",
      online_channels: 32,
      total_channels: 32,
      is_online: true,
      upstream_switch: "Core-SW-01",
      upstream_port: "Gi0/1",
      hdds: [
        { id: 1, name: "HDD-1 (WD Purple)", status: "ok", capacity_gb: 6000, free_gb: 1840 },
        { id: 2, name: "HDD-2 (WD Purple)", status: "ok", capacity_gb: 6000, free_gb: 2120 },
        { id: 3, name: "HDD-3 (SkyHawk)", status: "error", capacity_gb: 6000, free_gb: 0 },
      ],
    },
    {
      id: "nvr-2",
      name: "Hikvision-NVR-02 (Dự phòng)",
      model: "DS-9664NI-I8",
      ip_address: "10.10.10.51",
      mac_address: "80:48:A5:11:22:33",
      online_channels: 31,
      total_channels: 32,
      is_online: true,
      upstream_switch: "Core-SW-01",
      upstream_port: "Gi0/4",
      hdds: [
        { id: 1, name: "HDD-1 (SkyHawk AI)", status: "ok", capacity_gb: 8000, free_gb: 3400 },
        { id: 2, name: "HDD-2 (SkyHawk AI)", status: "ok", capacity_gb: 8000, free_gb: 3910 },
      ],
    },
  ],
  cameras: [
    {
      id: "cam-1",
      name: "Gate-Cam-01 (Cổng chính)",
      model: "DS-2CD2T47G2-L (ColorVu 4MP)",
      vendor: "Hikvision",
      ip_address: "10.10.10.101",
      mac_address: "BC:AD:28:00:11:01",
      is_online: true,
      upstream_switch: "Access-SW-CCTV",
      upstream_port: "Gi0/1 (100M)",
      vlan_id: 10,
      nvr_links: [
        { nvr_name: "Hikvision-NVR-01", nvr_ip: "10.10.10.50", channel_id: 1, status: "online" },
        { nvr_name: "Hikvision-NVR-02", nvr_ip: "10.10.10.51", channel_id: 1, status: "online" },
      ],
    },
    {
      id: "cam-2",
      name: "Lobby-Cam-02 (Sảnh lễ tân)",
      model: "DS-2CD2143G2-I (AcuSense)",
      vendor: "Hikvision",
      ip_address: "10.10.10.102",
      mac_address: "BC:AD:28:00:11:02",
      is_online: true,
      upstream_switch: "Access-SW-CCTV (qua Hub)",
      upstream_port: "Gi0/2 (VLAN 10)",
      vlan_id: 10,
      nvr_links: [
        { nvr_name: "Hikvision-NVR-01", nvr_ip: "10.10.10.50", channel_id: 2, status: "online" },
        { nvr_name: "Hikvision-NVR-02", nvr_ip: "10.10.10.51", channel_id: 2, status: "warning" },
      ],
    },
    {
      id: "cam-3",
      name: "Parking-Cam-03 (Bãi xe B1)",
      model: "DS-2CD2043G2-I",
      vendor: "Hikvision",
      ip_address: "10.10.10.103",
      mac_address: "BC:AD:28:00:11:03",
      is_online: true,
      upstream_switch: "Access-SW-CCTV (qua Hub)",
      upstream_port: "Gi0/2 (VLAN 10)",
      vlan_id: 10,
      nvr_links: [
        { nvr_name: "Hikvision-NVR-01", nvr_ip: "10.10.10.50", channel_id: 3, status: "online" },
      ],
    },
    {
      id: "cam-4",
      name: "Warehouse-Cam-04 (Kho hàng)",
      model: "IPC-HFW2439S-SA-LED",
      vendor: "Dahua",
      ip_address: "10.10.10.104",
      mac_address: "3C:EF:8C:10:20:04",
      is_online: true,
      upstream_switch: "Access-SW-CCTV",
      upstream_port: "Gi0/6 (1G)",
      vlan_id: 10,
      nvr_links: [
        { nvr_name: "Hikvision-NVR-01", nvr_ip: "10.10.10.50", channel_id: 4, status: "online" },
        { nvr_name: "Hikvision-NVR-02", nvr_ip: "10.10.10.51", channel_id: 4, status: "online" },
      ],
    },
  ],
  alerts: [
    {
      severity: "critical",
      message:
        "Lỗi ổ cứng NVR 10.10.10.50 (HDD-3 SkyHawk): trạng thái 'ERROR' (Dung lượng 6000.0 GB)",
    },
  ],
};

export default function SiteCameraMatrixPage() {
  const params = useParams();
  const router = useRouter();
  const siteId = Number(params?.siteId || 1);

  const [nvrs, setNvrs] = useState<NvrCardItem[]>([]);
  const [cameras, setCameras] = useState<DiscoveredCameraItem[]>([]);
  const [alerts, setAlerts] = useState<CctvAlert[]>([]);
  const [selectedNvr, setSelectedNvr] = useState<NvrCardItem | null>(null);
  const [selectedCamera, setSelectedCamera] = useState<DiscoveredCameraItem | null>(null);
  const [snapshotTick, setSnapshotTick] = useState<number>(Date.now());

  const loadCctvMatrix = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/sites/${siteId}/cctv`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (Array.isArray(data.nvrs)) setNvrs(data.nvrs);
      if (Array.isArray(data.cameras)) setCameras(data.cameras);
      if (Array.isArray(data.alerts)) setAlerts(data.alerts);
    } catch {
      // Fallback dataset already populated
    }
  }, [siteId]);

  useEffect(() => {
    loadCctvMatrix();
  }, [loadCctvMatrix]);

  const getProxyUrl = (ip: string) => `${API_URL}/api/proxy/sites/${siteId}/${ip}`;

  const getSnapshotUrl = (nvrIp: string, channelId: number) =>
    `${API_URL}/api/sites/${siteId}/nvrs/${nvrIp}/channels/${channelId}/snapshot?t=${snapshotTick}`;

  // Channels to preview in the right-side thumbnail panel
  const activePreviewChannels = selectedCamera
    ? selectedCamera.nvr_links.map((link) => ({
        title: `${selectedCamera.name} — ${link.nvr_name} (CH-${link.channel_id})`,
        nvrIp: link.nvr_ip,
        channelId: link.channel_id,
        deviceIp: selectedCamera.ip_address,
      }))
    : selectedNvr
    ? [1, 2, 3, 4].map((ch) => ({
        title: `${selectedNvr.name} — Kênh ${ch}`,
        nvrIp: selectedNvr.ip_address,
        channelId: ch,
        deviceIp: selectedNvr.ip_address,
      }))
    : [];

  return (
    <div className="flex min-h-screen flex-col bg-slate-950 text-slate-100">
      {/* Header */}
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 bg-slate-900/95 px-6 py-3">
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.push(`/sites/${siteId}`)}
            className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-xs font-medium text-slate-200 transition hover:border-cyan-400"
          >
            <ArrowLeft className="h-3.5 w-3.5 text-cyan-400" />
            Sơ đồ Topology
          </button>
          <div className="flex items-center gap-2 font-bold text-emerald-400">
            <Video className="h-5 w-5" />
            <span className="text-base text-white">
              CCTV / NVR ISAPI MATRIX — SITE #{siteId}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setSnapshotTick(Date.now())}
            className="flex items-center gap-1.5 rounded-lg bg-cyan-500/20 px-3 py-1.5 text-xs font-semibold text-cyan-300 ring-1 ring-cyan-500/40 transition hover:bg-cyan-500/30"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Làm mới Snapshot ISAPI
          </button>
        </div>
      </header>

      {/* Critical HDD / Storage Alerts */}
      {alerts.length > 0 && (
        <div className="border-b border-rose-900/60 bg-rose-950/50 px-6 py-2.5">
          {alerts.map((a, i) => (
            <div key={i} className="flex items-center gap-2 text-xs text-rose-200">
              <ShieldAlert className="h-4 w-4 flex-shrink-0 text-rose-400" />
              <span className="font-semibold">{a.message}</span>
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-1 overflow-hidden">
        {/* Main Content: NVR Grid + Camera Table */}
        <main className="flex-1 space-y-6 overflow-y-auto p-6">
          {/* 1. Top Section: Grid of NVR Cards */}
          <section>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-slate-300">
                <HardDrive className="h-4 w-4 text-violet-400" />
                Đầu ghi hình NVR ({nvrs.length} thiết bị)
              </h2>
              <span className="text-xs text-slate-400">
                Click vào thẻ NVR để xem trực tiếp lưới Thumbnail các kênh
              </span>
            </div>

            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              {nvrs.map((nvr) => {
                const isSelected = selectedNvr?.id === nvr.id;
                return (
                  <div
                    key={nvr.id}
                    onClick={() => {
                      setSelectedCamera(null);
                      setSelectedNvr(nvr);
                    }}
                    className={`cursor-pointer rounded-xl border bg-slate-900/90 p-4 shadow-lg transition ${
                      isSelected
                        ? "border-cyan-400 ring-2 ring-cyan-400/50"
                        : "border-slate-800 hover:border-slate-700"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3 border-b border-slate-800 pb-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="h-2.5 w-2.5 rounded-full bg-emerald-400 shadow-[0_0_8px_#34d399]" />
                          <h3 className="text-base font-bold text-white">{nvr.name}</h3>
                          <span className="rounded bg-violet-500/20 px-2 py-0.5 text-[11px] font-bold text-violet-300">
                            {nvr.online_channels}/{nvr.total_channels} kênh
                          </span>
                        </div>
                        <p className="mt-1 font-mono text-xs text-slate-400">
                          Model: <span className="text-slate-200">{nvr.model}</span> • IP:{" "}
                          <span className="text-cyan-300">{nvr.ip_address}</span>
                        </p>
                      </div>

                      <a
                        href={getProxyUrl(nvr.ip_address)}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        className="flex items-center gap-1 rounded-lg bg-cyan-500/20 px-2.5 py-1.5 text-xs font-semibold text-cyan-300 ring-1 ring-cyan-500/40 hover:bg-cyan-500/30"
                      >
                        <ExternalLink className="h-3.5 w-3.5" />
                        Web GUI (VPN)
                      </a>
                    </div>

                    {/* HDD Status Badges */}
                    <div className="mt-3">
                      <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                        Trạng thái Ổ cứng (/ISAPI/System/Storage/hdd)
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {nvr.hdds.map((hdd) => {
                          const isOk = hdd.status.toLowerCase() === "ok";
                          return (
                            <div
                              key={hdd.id}
                              className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-medium ${
                                isOk
                                  ? "border-emerald-500/30 bg-emerald-950/40 text-emerald-300"
                                  : "border-rose-500/60 bg-rose-950/70 text-rose-200 animate-pulse"
                              }`}
                            >
                              {isOk ? (
                                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                              ) : (
                                <AlertTriangle className="h-3.5 w-3.5 text-rose-400" />
                              )}
                              <span>{hdd.name}:</span>
                              <span className="font-bold uppercase">{hdd.status}</span>
                              <span className="text-[10px] opacity-80">
                                ({hdd.free_gb}/{hdd.capacity_gb} GB)
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>

          {/* 2. Bottom Section: Discovered Cameras Table */}
          <section>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-slate-300">
                <Camera className="h-4 w-4 text-sky-400" />
                Danh sách Camera IP toàn mạng LAN ({cameras.length} Camera)
              </h2>
            </div>

            <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900/90 shadow-lg">
              <table className="w-full text-left text-xs">
                <thead className="border-b border-slate-800 bg-slate-950/80 text-[11px] uppercase tracking-wider text-slate-400">
                  <tr>
                    <th className="px-4 py-3">Camera / Model</th>
                    <th className="px-4 py-3">Địa chỉ IP (VPN Web Proxy)</th>
                    <th className="px-4 py-3">Đầu ghi & Kênh NVR đang ghi hình</th>
                    <th className="px-4 py-3">Switch & Cổng Uplink</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/80">
                  {cameras.map((cam) => {
                    const isSelected = selectedCamera?.id === cam.id;
                    return (
                      <tr
                        key={cam.id}
                        onClick={() => {
                          setSelectedNvr(null);
                          setSelectedCamera(cam);
                        }}
                        className={`cursor-pointer transition ${
                          isSelected
                            ? "bg-cyan-950/40"
                            : "hover:bg-slate-800/50"
                        }`}
                      >
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2.5">
                            <span
                              className={`h-2.5 w-2.5 rounded-full ${
                                cam.is_online ? "bg-emerald-400" : "bg-rose-500"
                              }`}
                            />
                            <div>
                              <p className="font-semibold text-white">{cam.name}</p>
                              <p className="text-[11px] text-slate-400">
                                {cam.vendor} • {cam.model} • MAC {cam.mac_address}
                              </p>
                            </div>
                          </div>
                        </td>

                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <span className="font-mono font-medium text-cyan-300">
                              {cam.ip_address}
                            </span>
                            <a
                              href={getProxyUrl(cam.ip_address)}
                              target="_blank"
                              rel="noopener noreferrer"
                              onClick={(e) => e.stopPropagation()}
                              className="inline-flex items-center gap-1 rounded bg-slate-800 px-2 py-0.5 text-[10px] font-semibold text-cyan-300 ring-1 ring-cyan-500/30 hover:bg-cyan-500 hover:text-slate-950"
                            >
                              <ExternalLink className="h-3 w-3" />
                              Web
                            </a>
                          </div>
                        </td>

                        <td className="px-4 py-3">
                          <div className="flex flex-wrap gap-1.5">
                            {cam.nvr_links.map((link, idx) => (
                              <span
                                key={idx}
                                className="inline-flex items-center gap-1.5 rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-[11px]"
                              >
                                <span
                                  className={`h-2 w-2 rounded-full ${
                                    link.status === "online"
                                      ? "bg-emerald-400"
                                      : link.status === "warning"
                                      ? "bg-amber-400"
                                      : "bg-rose-500"
                                  }`}
                                />
                                <span className="font-medium text-slate-200">
                                  {link.nvr_name}
                                </span>
                                <span className="rounded bg-violet-500/20 px-1 font-mono text-[10px] text-violet-300">
                                  CH-{link.channel_id}
                                </span>
                              </span>
                            ))}
                          </div>
                        </td>

                        <td className="px-4 py-3">
                          <div className="flex items-center gap-1.5 font-mono text-slate-200">
                            <Network className="h-3.5 w-3.5 text-sky-400" />
                            <span>{cam.upstream_switch}</span>
                            <span className="rounded bg-sky-500/15 px-1.5 py-0.5 text-[10px] text-sky-300">
                              {cam.upstream_port}
                            </span>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        </main>

        {/* 3. Right-side Live Snapshot Thumbnail Panel */}
        {(selectedCamera || selectedNvr) && (
          <aside className="flex w-[420px] flex-col border-l border-slate-800 bg-slate-900/95 p-5 shadow-2xl">
            <div className="flex items-start justify-between border-b border-slate-800 pb-3">
              <div>
                <span className="rounded bg-emerald-500/20 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-emerald-300">
                  LIVE ISAPI SNAPSHOT STREAM
                </span>
                <h3 className="mt-1 text-base font-bold text-white">
                  {selectedCamera ? selectedCamera.name : selectedNvr?.name}
                </h3>
                <p className="font-mono text-xs text-slate-400">
                  IP: {selectedCamera ? selectedCamera.ip_address : selectedNvr?.ip_address}
                </p>
              </div>
              <button
                onClick={() => {
                  setSelectedCamera(null);
                  setSelectedNvr(null);
                }}
                className="rounded-lg p-1 text-slate-400 hover:bg-slate-800 hover:text-white"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="mt-4 flex-1 space-y-4 overflow-y-auto pr-1">
              {activePreviewChannels.map((item, idx) => (
                <div
                  key={idx}
                  className="overflow-hidden rounded-xl border border-slate-800 bg-slate-950"
                >
                  <div className="flex items-center justify-between border-b border-slate-800 px-3 py-2 text-xs">
                    <span className="font-semibold text-slate-200">{item.title}</span>
                    <span className="font-mono text-[10px] text-emerald-400">
                      CH-{item.channelId}01
                    </span>
                  </div>
                  <div className="relative aspect-video w-full bg-slate-950">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={getSnapshotUrl(item.nvrIp, item.channelId)}
                      alt={item.title}
                      className="h-full w-full object-cover"
                    />
                  </div>
                </div>
              ))}
            </div>

            <div className="mt-4 flex gap-2 border-t border-slate-800 pt-3">
              <button
                onClick={() => setSnapshotTick(Date.now())}
                className="flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-2.5 text-xs font-semibold text-slate-200 hover:bg-slate-700"
              >
                <RefreshCw className="h-3.5 w-3.5" /> Chụp lại (Refresh)
              </button>
              <a
                href={getProxyUrl(
                  selectedCamera ? selectedCamera.ip_address : selectedNvr!.ip_address
                )}
                target="_blank"
                rel="noopener noreferrer"
                className="flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-cyan-500 px-3 py-2.5 text-xs font-bold text-slate-950 hover:bg-cyan-400"
              >
                <ExternalLink className="h-3.5 w-3.5" /> Mở Web GUI (VPN)
              </a>
            </div>
          </aside>
        )}
      </div>
    </div>
  );
}
