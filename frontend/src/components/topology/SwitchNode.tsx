"use client";

import { Handle, NodeProps, Position } from "@xyflow/react";
import { ArrowUpRight, Network } from "lucide-react";
import { NocNodeData, SwitchPortSquare } from "./types";

function buildDefaultPorts(
  total: 24 | 48 = 24,
  customPorts?: SwitchPortSquare[]
): SwitchPortSquare[] {
  const byIdx = new Map((customPorts || []).map((p) => [p.port_index, p]));
  const result: SwitchPortSquare[] = [];
  for (let i = 1; i <= total; i++) {
    const existing = byIdx.get(i);
    if (existing) {
      result.push(existing);
    } else {
      result.push({
        port_index: i,
        port_name: `Gi0/${i}`,
        status: i <= 6 || i === total ? "up" : "down",
        speed: i === 2 ? "100M" : i === total ? "10G" : "1G",
        is_uplink: i === total,
      });
    }
  }
  return result;
}

export function SwitchNode({ data }: NodeProps) {
  const d = data as NocNodeData;
  const totalPorts: 24 | 48 = d.total_ports === 48 ? 48 : 24;
  const ports = buildDefaultPorts(totalPorts, d.ports);
  const highlightedSet = new Set(d.highlightedPorts || []);
  const upCount = ports.filter((p) => p.status === "up").length;

  return (
    <div
      className={`w-[345px] rounded-xl border bg-slate-900/95 p-3.5 shadow-xl transition-all duration-200 ${
        d.isDimmed ? "opacity-30" : "opacity-100"
      } ${
        d.isHighlighted
          ? "border-cyan-400 ring-2 ring-cyan-400/60 shadow-cyan-500/25"
          : "border-slate-700/90 hover:border-sky-400/70"
      }`}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!h-3 !w-3 !border-2 !border-slate-950 !bg-cyan-400"
      />

      <div className="flex items-start justify-between gap-2 border-b border-slate-800 pb-2">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-sky-500/15 text-sky-400">
            <Network className="h-4 w-4" />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="rounded bg-sky-500/20 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-sky-300">
                {d.vendor || "Ruijie"}
              </span>
              <span className="text-[11px] text-slate-400">
                {d.model || "RG-S5310-24GT4XS"}
              </span>
            </div>
            <p className="text-sm font-semibold text-slate-100">
              {d.name || d.label}
            </p>
          </div>
        </div>
        <div className="text-right">
          <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-semibold text-emerald-300">
            {d.connected_count ?? upCount} Active
          </span>
          <p className="mt-0.5 font-mono text-[11px] text-slate-400">
            {d.ip_address}
          </p>
        </div>
      </div>

      {/* Visual Port Grid (12 columns x 2 or 4 rows) */}
      <div className="mt-2.5 rounded-lg border border-slate-800 bg-slate-950/90 p-2">
        <div className="mb-1.5 flex items-center justify-between text-[10px] text-slate-400">
          <span>PORT LED MATRIX ({totalPorts}P)</span>
          <div className="flex items-center gap-2">
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-sm bg-emerald-500" /> 1G/10G
            </span>
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-sm bg-amber-500" /> 100M
            </span>
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-sm bg-slate-700" /> Down
            </span>
          </div>
        </div>

        <div className="grid grid-cols-12 gap-1">
          {ports.map((p) => {
            const isPortHighlighted = highlightedSet.has(p.port_index);
            const isUp = p.status === "up";
            const is100M = isUp && p.speed === "100M";

            let bgClass = "bg-slate-800 text-slate-500 border-slate-700/60";
            if (isUp) {
              bgClass = is100M
                ? "bg-amber-500/90 text-slate-950 border-amber-300 font-bold"
                : "bg-emerald-500/90 text-slate-950 border-emerald-300 font-bold";
            }
            if (isPortHighlighted) {
              bgClass =
                "bg-cyan-300 text-slate-950 border-white ring-2 ring-cyan-400 scale-110 z-10 font-extrabold shadow-[0_0_12px_#22d3ee]";
            }

            return (
              <div
                key={p.port_index}
                title={`Port ${p.port_index} (${p.port_name}) - ${p.status.toUpperCase()} ${p.speed}${
                  p.is_uplink ? " [UPLINK]" : ""
                }`}
                className={`relative flex h-5 items-center justify-center rounded-[3px] border text-[9px] transition-all ${bgClass}`}
              >
                {p.is_uplink ? (
                  <ArrowUpRight className="h-2.5 w-2.5 stroke-[2.5]" />
                ) : (
                  p.port_index
                )}
              </div>
            );
          })}
        </div>
      </div>

      <Handle
        type="source"
        position={Position.Right}
        className="!h-3 !w-3 !border-2 !border-slate-950 !bg-cyan-400"
      />
    </div>
  );
}
