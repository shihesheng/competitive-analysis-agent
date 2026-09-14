import { useEffect, useState } from "react";

export type NavItem = {
  key: string;
  label: string;
};

export type AgentSidebarStatus =
  | "waiting"
  | "running"
  | "done"
  | "limited"
  | "partial"
  | "failed";

export type AgentSidebarItem = {
  name: string;
  role: string;
  status: AgentSidebarStatus;
  current?: boolean;
  selected?: boolean;
};

type SidebarProps = {
  items: NavItem[];
  activeKey: string;
  taskId?: string;
  displayTaskId?: string;
  onNavigate: (key: string) => void;
  agentItems?: AgentSidebarItem[];
  showAgentTasks?: boolean;
  onAgentSelect?: (agentName: string) => void;
};

const SIDEBAR_COLLAPSED_KEY = "sidebarCollapsed";

function getStoredCollapsed() {
  if (typeof window === "undefined") {
    return false;
  }
  return window.sessionStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "true";
}

export function Sidebar({
  items,
  activeKey,
  taskId,
  displayTaskId,
  onNavigate,
  agentItems = [],
  showAgentTasks = false,
  onAgentSelect,
}: SidebarProps) {
  const [collapsed, setCollapsed] = useState(getStoredCollapsed);

  useEffect(() => {
    if (typeof window !== "undefined") {
      window.sessionStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(collapsed));
    }
  }, [collapsed]);

  const hasSelectedAgent = showAgentTasks && agentItems.some((agent) => agent.selected);

  return (
    <aside
      className={`flex w-full flex-col border-b border-cyan-300/15 bg-slate-950/85 px-4 py-4 shadow-[18px_0_50px_rgba(2,6,23,0.34)] backdrop-blur-xl transition-[width] duration-200 ease-out md:sticky md:top-0 md:h-screen md:border-b-0 md:border-r ${
        collapsed ? "md:w-[78px] md:px-2" : "md:w-72"
      }`}
    >
      <div className="mb-6 flex items-center justify-between gap-2">
        <div className={collapsed ? "md:hidden" : ""}>
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-cyan-300/90">
            Agent Console
          </p>
          <h1 className="mt-2 text-xl font-semibold text-white">
            竞品分析控制台
          </h1>
        </div>
        <button
          aria-label={collapsed ? "展开导航" : "收起导航"}
          aria-pressed={collapsed}
          className="hidden h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-cyan-300/25 bg-slate-900/70 text-cyan-200 transition hover:border-cyan-200/60 hover:bg-cyan-400/10 md:flex"
          onClick={() => setCollapsed((value) => !value)}
          title={collapsed ? "展开导航" : "收起导航"}
          type="button"
        >
          <span className="text-base leading-none">{collapsed ? ">" : "<"}</span>
        </button>
      </div>

      <div className={`mb-3 ${collapsed ? "md:hidden" : ""}`}>
        <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-cyan-300">
          Task Board
        </p>
        <h2 className="mt-1 text-base font-semibold text-white">任务栏</h2>
      </div>

      <nav className="grid gap-1 md:block md:space-y-2">
        {items.map((item, index) => {
          const isActive = item.key === activeKey && !(item.key === "workflow" && hasSelectedAgent);

          return (
            <button
              className={`group flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm transition duration-200 ${
                collapsed ? "md:justify-center md:px-0" : ""
              } ${
                isActive
                  ? "bg-cyan-400/10 text-cyan-100 ring-1 ring-cyan-300/30 shadow-[0_0_24px_rgba(34,211,238,0.12)]"
                  : "text-slate-400 hover:bg-white/[0.04] hover:text-slate-100"
              }`}
              key={item.key}
              onClick={() => onNavigate(item.key)}
              title={collapsed ? item.label : undefined}
              type="button"
            >
              <span
                className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-[11px] font-semibold transition ${
                  isActive
                    ? "border-cyan-300 bg-cyan-300/15 text-cyan-100"
                    : "border-slate-700 bg-slate-900/80 text-slate-500"
                }`}
              >
                {index + 1}
              </span>
              <span className={`min-w-0 flex-1 truncate ${collapsed ? "md:hidden" : ""}`}>
                {item.label}
              </span>
            </button>
          );
        })}

        {showAgentTasks && agentItems.length
          ? agentItems.map((agent, index) => {
              const selected = agent.selected;
              const running = agent.current || agent.status === "running";
              const limited = agent.status === "limited" || agent.status === "partial";
              const failed = agent.status === "failed";
              const number = items.length + index + 1;

              return (
                <button
                  className={`group flex w-full items-center gap-3 rounded-lg border px-3 py-2.5 text-left transition duration-200 hover:-translate-y-0.5 hover:border-cyan-300/55 ${
                    collapsed ? "md:justify-center md:px-0" : ""
                  } ${
                    selected
                      ? "border-cyan-300/60 bg-cyan-400/12 text-cyan-100 shadow-[0_0_22px_rgba(34,211,238,0.12)]"
                      : "border-slate-800 bg-slate-900/45 text-slate-300 hover:bg-white/[0.04]"
                  }`}
                  key={agent.name}
                  onClick={() => onAgentSelect?.(agent.name)}
                  title={collapsed ? agent.name : undefined}
                  type="button"
                >
                  <span
                    className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full border text-xs font-semibold ${
                      running
                        ? "border-cyan-300 bg-cyan-300/15 text-cyan-100"
                        : selected
                          ? "border-cyan-300/60 text-cyan-100"
                          : "border-slate-700 text-slate-500"
                    }`}
                  >
                    {number}
                  </span>
                  <span className={`min-w-0 flex-1 ${collapsed ? "md:hidden" : ""}`}>
                    <span className="block truncate text-sm font-semibold">{agent.name}</span>
                    <span className="mt-0.5 block truncate text-xs text-slate-500">
                      {agent.role}
                    </span>
                  </span>
                  <span className={`relative flex h-2.5 w-2.5 shrink-0 ${collapsed ? "md:hidden" : ""}`}>
                    {running ? (
                      <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-cyan-300 opacity-70" />
                    ) : null}
                    <span
                      className={`relative inline-flex h-2.5 w-2.5 rounded-full ${
                        running
                          ? "bg-cyan-300"
                          : failed
                            ? "bg-rose-300"
                            : limited
                              ? "bg-amber-300"
                              : agent.status === "done"
                                ? "bg-emerald-300"
                                : "bg-slate-600"
                      }`}
                    />
                  </span>
                </button>
              );
            })
          : null}
      </nav>

      <div
        className={`mt-6 rounded-xl border border-cyan-300/15 bg-slate-900/55 p-3 shadow-[0_12px_34px_rgba(2,6,23,0.24)] md:mt-auto ${
          collapsed ? "md:hidden" : ""
        }`}
        title={taskId ? `真实任务 ID：${taskId}` : undefined}
      >
        <p className="text-xs uppercase tracking-[0.18em] text-slate-500">
          当前任务
        </p>
        <p className="mt-2 break-all text-sm font-medium text-slate-100">
          {displayTaskId || "暂无任务"}
        </p>
      </div>
    </aside>
  );
}
