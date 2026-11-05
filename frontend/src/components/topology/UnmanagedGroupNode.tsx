"use client";

import { Handle, NodeProps, Position } from "@xyflow/react";
import { AlertTriangle, HelpCircle } from "lucide-react";
import { NocNodeData } from "./types";

export function UnmanagedGroupNode({ data }: NodeProps) {
  const d = data as NocNodeData;
  const items = d.group_items || [];

  return (
    <div
      className={`w-[295px] rounded-xl border-2 border-dashed bg-slate-900/90 p-3 shadow-xl transition-all duration-200 ${
        d.isDimmed ? "opacity-30" : "opacity-100"
      } ${
        d.isHighlighted
          ? "border-cyan-400 ring-2 ring-cyan-400/50 shadow-cyan-500/20"
          : "border-amber-500/60 hover:border-amber-400"
      }`}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!h-3 !w-3 !border-2 !border-slate-950 !bg-amber-400"
      />

      <div className="flex items-start justify-between gap-2 border-b border-slate-800 pb-2">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-amber-500/15 text-amber-400">
            <HelpCircle className="h-4 w-4" />
          </div>
          <div>
            <p className="text-xs font-bold text-amber-300">
              Chưa xác định switch hoặc AP
            </p>
            <p className="text-[11px] text-slate-400">
              Uplink: <span className="font-mono text-slate-200">{d.upstream_port_label || d.label}</span>
            </p>
          </div>
        </div>
        <span className="flex items-center gap-1 rounded bg-amber-500/20 px-1.5 py-0.5 text-[10px] font-semibold text-amber-300">
          <AlertTriangle className="h-3 w-3" /> {items.length || 2} MACs
        </span>
      </div>

      <div className="mt-2 max-h-28 space-y-1 overflow-y-auto pr-1">
        {items.length > 0 ? (
          items.map((item, idx) => (
            <div
              key={item.mac_address || idx}
              className="flex items-center justify-between rounded bg-slate-950/80 px-2 py-1 text-[10px]"
            >
              <div className="truncate">
                <span className="font-medium text-slate-200">{item.name}</span>
                <span className="ml-1.5 text-slate-400">({item.vendor})</span>
              </div>
              <span className="font-mono text-cyan-300">{item.ip_address}</span>
            </div>
          ))
        ) : (
          <p className="text-[11px] text-slate-400">
            Phát hiện nhiều thiết bị nối tầng qua cổng Access
          </p>
        )}
      </div>

      <Handle
        type="source"
        position={Position.Right}
        className="!h-3 !w-3 !border-2 !border-slate-950 !bg-amber-400"
      />
    </div>
  );
}
