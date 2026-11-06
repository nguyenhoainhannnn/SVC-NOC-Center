"use client";

import { Handle, NodeProps, Position } from "@xyflow/react";
import { Clock, Cpu, MemoryStick, Router } from "lucide-react";
import { NocNodeData } from "./types";

function formatUptime(seconds?: number): string {
  if (!seconds || seconds <= 0) return "Đang hoạt động";
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h ${mins}m`;
  return `${hours}h ${mins}m`;
}

export function RouterNode({ data }: NodeProps) {
  const d = data as NocNodeData;
  const cpu = Number(d.cpu_usage ?? 0);
  const ram = Number(d.ram_usage ?? 0);
  const rawPorts = Array.isArray(d.ports) && d.ports.length > 0 ? d.ports : [
    { port_index: 1, port_name: "WAN1", status: "up" as const, speed: "1G", is_uplink: false },
    { port_index: 2, port_name: "WAN2", status: "down" as const, speed: "1G", is_uplink: false },
    { port_index: 3, port_name: "LAN-P1", status: "up" as const, speed: "1G", is_uplink: false },
    { port_index: 4, port_name: "LAN-P2", status: "down" as const, speed: "1G", is_uplink: false },
    { port_index: 5, port_name: "LAN-P3", status: "down" as const, speed: "1G", is_uplink: false },
    { port_index: 6, port_name: "LAN-P4", status: "down" as const, speed: "1G", is_uplink: false },
    { port_index: 7, port_name: "LAN-P5", status: "down" as const, speed: "1G", is_uplink: false },
    { port_index: 8, port_name: "USB", status: "down" as const, speed: "480M", is_uplink: false },
  ];
  const highlightedSet = new Set(d.highlightedPorts || []);
  const activePorts = rawPorts.filter((p) => p.status === "up");
  const wanPorts = rawPorts.filter((p) => /^(wan|usb|sfp-wan)/i.test(p.port_name));
  const lanPorts = rawPorts.filter((p) => !/^(wan|usb|sfp-wan)/i.test(p.port_name));

  return (
    <div
      className={`w-[325px] rounded-xl border bg-slate-900/95 p-3.5 shadow-xl transition-all duration-200 ${
        d.isDimmed ? "opacity-30" : "opacity-100"
      } ${
        d.isHighlighted
          ? "border-cyan-400 ring-2 ring-cyan-400/50 shadow-cyan-500/20"
          : "border-emerald-500/40 hover:border-emerald-400"
      }`}
    >
      <div className="flex items-start justify-between gap-2 border-b border-slate-800 pb-2.5">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-500/15 text-emerald-400">
            <Router className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="rounded bg-emerald-500/20 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-emerald-300">
                {d.vendor || "Router"}
              </span>
              <span className="h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_8px_#34d399]" />
            </div>
            <p className="mt-0.5 text-sm font-semibold text-slate-100">
              {d.name || d.model || "Gateway Router"}
            </p>
            <p className="font-mono text-[11px] text-slate-400">{d.ip_address}</p>
          </div>
        </div>
        <span className="flex items-center gap-1 rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-300">
          <Clock className="h-3 w-3 text-sky-400" />
          {formatUptime(d.uptime)}
        </span>
      </div>

      <div className="mt-2.5 grid grid-cols-2 gap-2 text-xs">
        <div className="rounded-lg bg-slate-950/80 p-2">
          <div className="flex items-center justify-between text-[11px] text-slate-400">
            <span className="flex items-center gap-1">
              <Cpu className="h-3 w-3 text-cyan-400" /> CPU
            </span>
            <span className="font-semibold text-slate-200">
              {cpu > 0 ? `${cpu.toFixed(0)}%` : "SNMP tắt"}
            </span>
          </div>
          <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
            <div
              className="h-full rounded-full bg-cyan-400 transition-all"
              style={{ width: `${Math.min(100, cpu)}%` }}
            />
          </div>
        </div>
        <div className="rounded-lg bg-slate-950/80 p-2">
          <div className="flex items-center justify-between text-[11px] text-slate-400">
            <span className="flex items-center gap-1">
              <MemoryStick className="h-3 w-3 text-violet-400" /> RAM
            </span>
            <span className="font-semibold text-slate-200">
              {ram > 0 ? `${ram.toFixed(0)}%` : "SNMP tắt"}
            </span>
          </div>
          <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
            <div
              className="h-full rounded-full bg-violet-400 transition-all"
              style={{ width: `${Math.min(100, ram)}%` }}
            />
          </div>
        </div>
      </div>

      {/* Router Physical WAN + LAN Port LED Matrix */}
      <div className="mt-2.5 space-y-2 rounded-lg border border-slate-800 bg-slate-950/90 p-2.5">
        <div className="flex items-center justify-between text-[10px] text-slate-400">
          <span className="font-semibold uppercase tracking-wider text-slate-300">
            Sơ đồ Cổng WAN & LAN
          </span>
          <span className="rounded bg-emerald-500/20 px-1.5 py-0.5 font-mono text-[10px] font-bold text-emerald-300">
            {activePorts.length}/{rawPorts.length} CỔNG UP
          </span>
        </div>

        {/* WAN Ports Row */}
        {wanPorts.length > 0 && (
          <div>
            <p className="mb-1 text-[9px] font-semibold uppercase tracking-wider text-cyan-400">
              Cổng WAN / Internet
            </p>
            <div className="grid grid-cols-3 gap-1.5">
              {wanPorts.map((p) => {
                const isUp = p.status === "up";
                return (
                  <div
                    key={p.port_index}
                    title={`${p.port_name}: ${isUp ? "ĐANG HOẠT ĐỘNG (UP)" : "KHÔNG CẮM (DOWN)"} (${p.speed || "1G"})`}
                    className={`flex items-center justify-between rounded border px-2 py-1 font-mono text-[10px] ${
                      isUp
                        ? "border-emerald-400/60 bg-emerald-500/20 font-bold text-emerald-200 shadow-[0_0_8px_rgba(16,185,129,0.25)]"
                        : "border-slate-800 bg-slate-900 text-slate-500"
                    }`}
                  >
                    <span>{p.port_name}</span>
                    <span
                      className={`h-2 w-2 rounded-full ${
                        isUp ? "bg-emerald-400 shadow-[0_0_6px_#34d399]" : "bg-slate-700"
                      }`}
                    />
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* LAN Ports Row */}
        {lanPorts.length > 0 && (
          <div>
            <p className="mb-1 text-[9px] font-semibold uppercase tracking-wider text-emerald-400">
              Cổng LAN Nội Bộ ({lanPorts.filter((p) => p.status === "up").length}/{lanPorts.length} Active)
            </p>
            <div className="grid grid-cols-5 gap-1.5">
              {lanPorts.map((p) => {
                const isUp = p.status === "up";
                const isHighlighted = highlightedSet.has(p.port_index);
                const shortLabel = p.port_name.replace(/^LAN-?/i, "");
                return (
                  <div
                    key={p.port_index}
                    title={`${p.port_name}: ${isUp ? "ĐANG CẮM (UP)" : "TRỐNG (DOWN)"} (${p.speed || "1G"})${
                      p.connected_label ? ` ➔ ${p.connected_label}` : ""
                    }`}
                    className={`flex flex-col items-center justify-center rounded border py-1 font-mono text-[10px] transition-all ${
                      isHighlighted
                        ? "border-white bg-cyan-300 font-extrabold text-slate-950 ring-2 ring-cyan-400"
                        : isUp
                        ? "border-emerald-400/70 bg-emerald-500/85 font-bold text-slate-950 shadow-[0_0_8px_rgba(16,185,129,0.3)]"
                        : "border-slate-800 bg-slate-900 text-slate-500"
                    }`}
                  >
                    <span>{shortLabel}</span>
                    <span className="text-[8px] uppercase">
                      {isUp ? p.speed || "1G" : "OFF"}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      <Handle
        type="source"
        position={Position.Right}
        className="!h-3 !w-3 !border-2 !border-slate-950 !bg-emerald-400"
      />
    </div>
  );
}
