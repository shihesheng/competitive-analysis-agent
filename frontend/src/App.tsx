import { useEffect, useMemo, useState } from "react";
import { analysisApi } from "./api/analysisApi";
import type { AuthUser } from "./api/authApi";
import { AppLayout } from "./components/layout/AppLayout";
import type { AgentSidebarItem, NavItem } from "./components/layout/Sidebar";
import { HomePage } from "./pages/HomePage";
import { ObservabilityPage } from "./pages/ObservabilityPage";
import { ProductComparePage } from "./pages/ProductComparePage";
import { ReportPage } from "./pages/ReportPage";
import { WelcomePage } from "./pages/WelcomePage";
import { WorkflowPage } from "./pages/WorkflowPage";
import { getDisplayTaskId } from "./utils/taskDisplay";

const AUTH_TOKEN_KEY = "authToken";
const CURRENT_USER_KEY = "currentUser";
const ACTIVE_TASK_KEY = "activeTaskId";

type PageKey = "overview" | "product-compare" | "workflow" | "observability" | "report";

const navItems: Array<NavItem & { key: PageKey }> = [
  { key: "overview", label: "总览" },
  { key: "product-compare", label: "产品输入" },
  { key: "workflow", label: "Agent 工作流" },
  { key: "observability", label: "运行观测" },
  { key: "report", label: "最终报告" },
];

const defaultWorkflowAgentItems: AgentSidebarItem[] = [
  { name: "ResearchAgent", role: "调研规划员", status: "waiting" },
  { name: "CollectorAgent", role: "采集与实体识别员", status: "waiting" },
  { name: "EvidenceAgent", role: "证据结构化员", status: "waiting" },
  { name: "AnalysisAgent", role: "分析师", status: "waiting" },
  { name: "VerificationAgent", role: "事实校验员", status: "waiting" },
  { name: "QualityAgent", role: "质量门控员", status: "waiting" },
  { name: "ReportAgent", role: "报告撰写员", status: "waiting" },
];

function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.sessionStorage.getItem(AUTH_TOKEN_KEY);
}

function getStoredUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  const raw = window.sessionStorage.getItem(CURRENT_USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}

function getStoredTaskId(): string | null {
  if (typeof window === "undefined") return null;
  return window.sessionStorage.getItem(ACTIVE_TASK_KEY);
}

function isPageKey(value: string): value is PageKey {
  return navItems.some((item) => item.key === value);
}

function normalizeHashToPage(): PageKey {
  if (typeof window === "undefined") return "overview";
  const raw = window.location.hash.replace(/^#\/?/, "");
  if (raw === "new-analysis") return "product-compare";
  if (["evidence", "claims", "quality", "metrics"].includes(raw)) {
    return "workflow";
  }
  return isPageKey(raw) ? raw : "overview";
}

export default function App() {
  const [authToken, setAuthToken] = useState<string | null>(getStoredToken);
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(getStoredUser);
  const [activePage, setActivePage] = useState<PageKey>(normalizeHashToPage);
  const [taskId, setTaskId] = useState<string | null>(getStoredTaskId);
  const [displayTaskId, setDisplayTaskId] = useState<string | null>(() =>
    getDisplayTaskId(getStoredTaskId()),
  );
  const [staleTaskNotice, setStaleTaskNotice] = useState(false);
  const [selectedDomain, setSelectedDomain] = useState<string | null>(null);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [selectedIndustryKey, setSelectedIndustryKey] = useState<string | null>(null);
  const [workflowSelectedAgent, setWorkflowSelectedAgent] = useState("ResearchAgent");
  const [workflowAgentItems, setWorkflowAgentItems] = useState<AgentSidebarItem[]>([]);
  const [workflowDetailAgent, setWorkflowDetailAgent] = useState<string | null>(null);

  const sidebarAgentItems = useMemo(() => {
    const runtimeItems = new Map(workflowAgentItems.map((item) => [item.name, item]));
    return defaultWorkflowAgentItems.map((item) => {
      const runtime = runtimeItems.get(item.name);
      return {
        ...item,
        ...runtime,
        selected:
          runtime?.selected ??
          (activePage === "workflow" && workflowDetailAgent === item.name),
      };
    });
  }, [activePage, workflowAgentItems, workflowDetailAgent]);

  useEffect(() => {
    function syncFromHash() {
      setActivePage(normalizeHashToPage());
    }
    window.addEventListener("hashchange", syncFromHash);
    window.addEventListener("popstate", syncFromHash);
    return () => {
      window.removeEventListener("hashchange", syncFromHash);
      window.removeEventListener("popstate", syncFromHash);
    };
  }, []);

  useEffect(() => {
    setDisplayTaskId(getDisplayTaskId(taskId));
  }, [taskId]);

  useEffect(() => {
    setWorkflowSelectedAgent("ResearchAgent");
    setWorkflowDetailAgent(null);
  }, [taskId]);

  useEffect(() => {
    if (activePage !== "workflow" || !taskId) {
      setWorkflowAgentItems([]);
      setWorkflowDetailAgent(null);
    }
  }, [activePage, taskId]);

  useEffect(() => {
    if (!taskId) return;
    let cancelled = false;
    let timer: number | undefined;

    async function validate(currentTaskId: string) {
      try {
        await analysisApi.getStatus(currentTaskId);
      } catch (error) {
        if (cancelled) return;
        const message = error instanceof Error ? error.message : "";
        if (message.includes("404")) {
          window.sessionStorage.removeItem(ACTIVE_TASK_KEY);
          setTaskId(null);
          setDisplayTaskId(null);
          setStaleTaskNotice(true);
          if (timer) window.clearInterval(timer);
        }
      }
    }

    validate(taskId);
    timer = window.setInterval(() => validate(taskId), 4000);
    return () => {
      cancelled = true;
      if (timer) window.clearInterval(timer);
    };
  }, [taskId]);

  function navigate(key: string) {
    if (!isPageKey(key)) return;
    setActivePage(key);
    if (typeof window !== "undefined" && window.location.hash !== `#${key}`) {
      window.history.pushState(null, "", `#${key}`);
    }
  }

  function handleTaskCreated(nextTaskId: string) {
    setTaskId(nextTaskId);
    setDisplayTaskId(getDisplayTaskId(nextTaskId));
    setStaleTaskNotice(false);
    window.sessionStorage.setItem(ACTIVE_TASK_KEY, nextTaskId);
  }

  function handleLogin(token: string, user: AuthUser) {
    setAuthToken(token);
    setCurrentUser(user);
    window.sessionStorage.setItem(AUTH_TOKEN_KEY, token);
    window.sessionStorage.setItem(CURRENT_USER_KEY, JSON.stringify(user));
  }

  function handleLogout() {
    setAuthToken(null);
    setCurrentUser(null);
    window.sessionStorage.removeItem(AUTH_TOKEN_KEY);
    window.sessionStorage.removeItem(CURRENT_USER_KEY);
  }

  function handleWorkflowAgentOpen(agentName: string) {
    setWorkflowSelectedAgent(agentName);
    setWorkflowDetailAgent(agentName);
    if (activePage !== "workflow") {
      navigate("workflow");
    }
  }

  function renderPage() {
    if (activePage === "product-compare") {
      return (
        <ProductComparePage
          displayTaskId={displayTaskId ?? undefined}
          onNavigate={navigate}
          onTaskCreated={handleTaskCreated}
        />
      );
    }

    if (activePage === "workflow") {
      return (
        <WorkflowPage
          agentDetailName={workflowDetailAgent}
          displayTaskId={displayTaskId ?? undefined}
          onAgentDetailClose={() => setWorkflowDetailAgent(null)}
          onAgentOpen={handleWorkflowAgentOpen}
          onSelectedAgentChange={setWorkflowSelectedAgent}
          onNavigate={navigate}
          onSidebarAgentsChange={setWorkflowAgentItems}
          selectedAgent={workflowSelectedAgent}
          taskId={taskId ?? undefined}
        />
      );
    }

    if (activePage === "report") {
      return (
        <ReportPage
          displayTaskId={displayTaskId ?? undefined}
          onNavigate={navigate}
          taskId={taskId ?? undefined}
        />
      );
    }

    if (activePage === "observability") {
      return (
        <ObservabilityPage
          displayTaskId={displayTaskId ?? undefined}
          onNavigate={navigate}
          taskId={taskId ?? undefined}
        />
      );
    }

    return (
      <HomePage
        displayTaskId={displayTaskId ?? undefined}
        onNavigate={navigate}
        onSelectionChange={(selection) => {
          if ("selectedDomain" in selection) {
            setSelectedDomain(selection.selectedDomain ?? null);
          }
          if ("selectedCategory" in selection) {
            setSelectedCategory(selection.selectedCategory ?? null);
          }
          if ("selectedIndustryKey" in selection) {
            setSelectedIndustryKey(selection.selectedIndustryKey ?? null);
          }
        }}
        selectedCategory={selectedCategory}
        selectedDomain={selectedDomain}
        selectedIndustryKey={selectedIndustryKey}
        taskId={taskId ?? undefined}
      />
    );
  }

  if (!authToken) {
    return <WelcomePage onLogin={handleLogin} />;
  }

  return (
    <AppLayout
      activePage={activePage}
      currentUser={currentUser}
      displayTaskId={displayTaskId ?? undefined}
      navItems={navItems}
      agentItems={sidebarAgentItems}
      onAgentSelect={handleWorkflowAgentOpen}
      onLogout={handleLogout}
      onNavigate={navigate}
      showAmbientParticles={activePage === "overview" || activePage === "product-compare"}
      showAgentTasks
      taskId={taskId ?? undefined}
    >
      {staleTaskNotice ? (
        <div className="mb-5 flex flex-col gap-3 rounded-lg border border-amber-400/35 bg-amber-400/10 px-4 py-3 text-sm text-amber-100 sm:flex-row sm:items-center sm:justify-between">
          <span>上一轮分析任务已失效，请重新创建一次分析。</span>
          <button
            className="rounded-md bg-amber-300 px-3 py-1.5 text-xs font-semibold text-slate-950 transition hover:bg-amber-200"
            onClick={() => {
              setStaleTaskNotice(false);
              navigate("product-compare");
            }}
            type="button"
          >
            回到产品输入
          </button>
        </div>
      ) : null}
      <div className="page-enter" key={activePage}>
        {renderPage()}
      </div>
    </AppLayout>
  );
}
