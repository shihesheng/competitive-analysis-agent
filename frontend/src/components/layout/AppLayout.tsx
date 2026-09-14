import type { ReactNode } from "react";
import { Sidebar, type AgentSidebarItem, type NavItem } from "./Sidebar";
import { TopBar } from "./TopBar";
import { ParticleField } from "../common/ParticleField";
import type { AuthUser } from "../../api/authApi";

type AppLayoutProps = {
  children: ReactNode;
  navItems: NavItem[];
  activePage: string;
  taskId?: string;
  displayTaskId?: string;
  onNavigate: (key: string) => void;
  agentItems?: AgentSidebarItem[];
  showAgentTasks?: boolean;
  onAgentSelect?: (agentName: string) => void;
  onLogout?: () => void;
  currentUser?: AuthUser | null;
  /** 分析前界面显示自研粒子背景；进入分析后关闭，给 3D 留干净舞台。 */
  showAmbientParticles?: boolean;
};

export function AppLayout({
  children,
  navItems,
  activePage,
  taskId,
  displayTaskId,
  onNavigate,
  agentItems,
  showAgentTasks = false,
  onAgentSelect,
  onLogout,
  currentUser,
  showAmbientParticles = false,
}: AppLayoutProps) {
  return (
    <div className="app-background min-h-screen bg-[#020617] text-slate-100">
      {showAmbientParticles ? (
        <ParticleField className="pointer-events-none fixed inset-0 z-0" />
      ) : null}
      <div className="relative z-10 flex min-h-screen flex-col md:h-screen md:flex-row">
        <Sidebar
          items={navItems}
          activeKey={activePage}
          taskId={taskId}
          displayTaskId={displayTaskId}
          onNavigate={onNavigate}
          agentItems={agentItems}
          showAgentTasks={showAgentTasks}
          onAgentSelect={onAgentSelect}
        />
        <div className="flex min-h-screen min-w-0 flex-1 flex-col md:h-screen md:min-h-0">
          <TopBar
            taskId={taskId}
            displayTaskId={displayTaskId}
            onLogout={onLogout}
            currentUser={currentUser}
          />

          <main
            id="app-main"
            className="min-h-0 flex-1 overflow-y-auto px-5 py-6 md:px-8 lg:px-10"
          >
            {children}
          </main>
        </div>
      </div>
    </div>
  );
}
