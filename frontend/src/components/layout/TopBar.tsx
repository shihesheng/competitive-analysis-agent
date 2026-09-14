import { useEffect, useState } from "react";
import { analysisApi } from "../../api/analysisApi";
import type { AuthUser } from "../../api/authApi";
import { StatusBadge } from "../common/StatusBadge";

type TopBarProps = {
  taskId?: string;
  displayTaskId?: string;
  onLogout?: () => void;
  currentUser?: AuthUser | null;
};

export function TopBar({
  taskId,
  displayTaskId,
  onLogout,
  currentUser,
}: TopBarProps) {
  const [apiStatus, setApiStatus] = useState<"checking" | "online" | "offline">(
    "checking",
  );

  useEffect(() => {
    let ignore = false;

    analysisApi
      .health()
      .then(() => {
        if (!ignore) {
          setApiStatus("online");
        }
      })
      .catch(() => {
        if (!ignore) {
          setApiStatus("offline");
        }
      });

    return () => {
      ignore = true;
    };
  }, []);

  const statusTone =
    apiStatus === "online"
      ? "success"
      : apiStatus === "offline"
        ? "danger"
        : "warning";

  const statusLabel =
    apiStatus === "online"
      ? "API 在线"
      : apiStatus === "offline"
        ? "API 离线"
        : "检查 API";

  return (
    <header className="flex flex-col gap-3 border-b border-cyan-300/15 bg-slate-950/75 px-5 py-4 shadow-[0_12px_34px_rgba(2,6,23,0.22)] backdrop-blur-xl md:flex-row md:items-center md:justify-between lg:px-8">
      <div>
        <p className="text-sm font-medium text-slate-100">
          AI 驱动的竞品分析系统
        </p>
        <p className="mt-1 text-xs text-slate-500">系统服务状态</p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge label={statusLabel} tone={statusTone} />
        <span title={taskId ? `真实任务 ID：${taskId}` : undefined}>
          <StatusBadge
            label={displayTaskId ? `当前任务：${displayTaskId}` : "暂无任务"}
            tone={displayTaskId ? "info" : "neutral"}
          />
        </span>
        {currentUser ? (
          <StatusBadge label={`${currentUser.username}`} tone="neutral" />
        ) : null}
        {onLogout ? (
          <button
            className="rounded-full border border-slate-700 bg-slate-900/55 px-3 py-1 text-xs font-medium text-slate-300 transition hover:border-rose-300/50 hover:bg-rose-500/10 hover:text-rose-200"
            onClick={onLogout}
            title="退出登录并返回登录页"
            type="button"
          >
            退出登录
          </button>
        ) : null}
      </div>
    </header>
  );
}
