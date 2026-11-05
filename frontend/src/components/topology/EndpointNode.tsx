"use client";

import { Handle, NodeProps, Position } from "@xyflow/react";
import { Camera, HardDrive, Monitor, Wifi } from "lucide-react";
import { NocNodeData } from "./types";

export function EndpointNode({ data }: NodeProps) {
  const d = data as NocNodeData;
  const isOnline = d.is_online !== false;

  const getIcon = () => {
    switch (d.role) {
      case "camera":
        return <Camera className="h-4 w-4 text-sky-400" />;
      case "nvr":
        return <HardDrive className="h-4 w-4 text-violet-400" />;
      case "ap":
        return <Wifi className="h-4 w-4 text-emerald-400" />;
      default:
        return <Monitor className="h-4 w-4 text-slate-300" />;
    }
  };

  return (
    <div
      className={`w-[230px] rounded-full border bg-slate-900/95 px-3.5 py-2 shadow-lg transition-all duration-200 ${
        d.isDimmed ? "opacity-30" : "opacity-100"
      } ${
        d.isHighlighted
          ? "border-cyan-400 ring-2 ring-cyan-400/60 shadow-cyan-500/25"
          : isOnline
          ? "border-slate-700/80 hover:border-cyan-400/60"
          : "border-rose-500/70 bg-rose-950/30"
      }`}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!h-2.5 !w-2.5 !border-2 !border-slate-950 !bg-cyan-400"
      />

      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-slate-800">
            {getIcon()}
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <span
                className={`h-2 w-2 flex-shrink-0 rounded-full ${
                  isOnline
                    ? "bg-emerald-400 shadow-[0_0_6px_#34d399]"
                    : "bg-rose-500 shadow-[0_0_6px_#f43f5e]"
                }`}
              />
              <p className="truncate text-xs font-semibold text-slate-100">
                {d.name || d.label}
              </p>
            </div>
            <div className="flex items-center gap-1.5 text-[10px] text-slate-400">
              <span className="font-mono">{d.ip_address}</span>
              {d.channels && (
                <span className="rounded bg-violet-500/20 px-1 text-[9px] font-semibold text-violet-300">
                  {d.channels}
                </span>
              )}
            </div>
          </div>
        </div>
        {d.vendor && (
          <span className="flex-shrink-0 rounded bg-slate-800 px-1.5 py-0.5 text-[9px] font-medium text-slate-300">
            {d.vendor}
          </span>
        )}
      </div>

      <Handle
        type="source"
        position={Position.Right}
        className="!h-2 !w-2 !border-0 !bg-transparent"
      />
    </div>
  );
}
