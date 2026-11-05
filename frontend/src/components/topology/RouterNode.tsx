"use client";

import { Handle, NodeProps, Position } from "@xyflow/react";
import { ArrowDownUp, Clock, Cpu, MemoryStick, Router } from "lucide-react";
import { NocNodeData } from "./types";

function formatUptime(seconds?: number): string {
  if (!seconds || seconds <= 0) return "14d 06h";
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  return `${days}d ${hours}h`;
}

export function RouterNode({ data }: NodeProps) {
  const d = data as NocNodeData;
  const cpu = Number(d.cpu_usage ?? 18);
  const ram = Number(d.ram_usage ?? 42);
  const wanRx = Number(d.wan_rx_mbps ?? 312.4);
  const wanTx = Number(d.wan_tx_mbps ?? 148.2);
  const lanRx = Number(d.lan_rx_mbps ?? 428.0);
  const lanTx = Number(d.lan_tx_mbps ?? 615.5);

  return (
    <div
      className={`w-[285px] rounded-xl border bg-slate-900/95 p-3.5 shadow-xl transition-all duration-200 ${
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
                {d.vendor || "MikroTik"}
              </span>
              <span className="h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_8px_#34d399]" />
            </div>
            <p className="mt-0.5 text-sm font-semibold text-slate-100">
              {d.name || d.model || "CCR2004-16G-2S+"}
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
            <span className="font-semibold text-slate-200">{cpu.toFixed(0)}%</span>
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
            <span className="font-semibold text-slate-200">{ram.toFixed(0)}%</span>
          </div>
          <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
            <div
              className="h-full rounded-full bg-violet-400 transition-all"
              style={{ width: `${Math.min(100, ram)}%` }}
            />
          </div>
        </div>
      </div>

      <div className="mt-2 flex items-center justify-between rounded-lg border border-slate-800/80 bg-slate-950/60 px-2.5 py-1.5 text-[11px]">
        <div className="flex items-center gap-1 text-slate-400">
          <ArrowDownUp className="h-3 w-3 text-emerald-400" />
          <span>WAN:</span>
          <span className="font-mono font-medium text-emerald-300">
            ↓{wanRx} / ↑{wanTx} Mbps
          </span>
        </div>
        <div className="font-mono text-[10px] text-sky-300">LAN {lanTx}M</div>
      </div>

      <Handle
        type="source"
        position={Position.Right}
        className="!h-3 !w-3 !border-2 !border-slate-950 !bg-emerald-400"
      />
    </div>
  );
}
