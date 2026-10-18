import type {
  Answer,
  ApplyResult,
  AskResult,
  Company,
  Connector,
  GraphData,
  ModelConfig,
  ModelDraft,
  NodeDetail,
  Provider,
  Risk,
  SlackStatus,
  Settings,
  Stats,
  Task,
  UploadResult,
  SlackBotSettings,
  SlackChannelList,
  GitHubRepo,
  GitHubStatus,
  Department,
  JiraProject,
  JiraStatus,
  LinearStatus,
  LinearTeam,
  NotionDatabase,
  NotionStatus,
} from "./types";

const BASE = "/api";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store", ...init });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      /* not json */
    }
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json() as Promise<T>;
}

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: body === undefined ? undefined : JSON.stringify(body),
});

export const api = {
  companies: () => call<Company[]>("/companies"),
  createCompany: (name: string) => call<Company>("/companies", json("POST", { name })),
  stats: (c: string) => call<Stats>(`/companies/${c}/stats`),
  finish: (c: string) => call<Company>(`/companies/${c}/finish`, json("POST")),
  reset: (c: string) => call<{ nodes: number; links: number }>(`/companies/${c}/reset`, json("POST")),

  graph: (c: string) => call<GraphData>(`/companies/${c}/graph`),
  node: (c: string, id: string) => call<NodeDetail>(`/companies/${c}/nodes/${encodeURIComponent(id)}`),
  unlink: (c: string, source: string, rel: string, target: string) =>
    call<{ removed: boolean }>(`/companies/${c}/unlink`, json("POST", { source, rel, target })),

  upload: (c: string, files: File[]) => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f, f.name));
    return call<{ results: UploadResult[] }>(`/companies/${c}/upload`, { method: "POST", body: fd });
  },
  form: (
    c: string,
    body: { team: string; person: string; role: string; system: string; owner: boolean },
  ) =>
    call<{ notes: string[]; nodes: GraphData["nodes"]; links: GraphData["links"] }>(
      `/companies/${c}/form`,
      json("POST", body),
    ),

  ask: (c: string, question: string) =>
    call<AskResult>(`/companies/${c}/ask`, json("POST", { question })),
  answers: (c: string) => call<Answer[]>(`/companies/${c}/answers`),

  tasks: (c: string) => call<Task[]>(`/companies/${c}/tasks`),
  apply: (c: string, task: string) =>
    call<ApplyResult>(`/companies/${c}/tasks/${task}/apply`, json("POST")),
  risks: (c: string) => call<Risk[]>(`/companies/${c}/risks`),

  settings: (c: string) => call<Settings>(`/companies/${c}/settings`),
  saveSettings: (c: string, patch: Partial<Settings>) =>
    call<Settings>(`/companies/${c}/settings`, json("PUT", patch)),

  slack: (c: string) => call<SlackStatus>(`/companies/${c}/slack`),
  addSlackBot: (c: string, bot_token: string, label: string, department = "") =>
    call<SlackStatus>(`/companies/${c}/slack/bots`, json("POST", { bot_token, label, department })),
  patchSlackBot: (c: string, bot: string, patch: { label?: string; department?: string; settings?: Partial<SlackBotSettings> }) =>
    call<SlackStatus>(`/companies/${c}/slack/bots/${bot}`, json("PATCH", patch)),
  departments: (c: string) => call<Department[]>(`/companies/${c}/departments`),
  removeSlackBot: (c: string, bot: string) => call<SlackStatus>(`/companies/${c}/slack/bots/${bot}`, json("DELETE")),
  slackChannels: (c: string, bot: string) => call<SlackChannelList>(`/companies/${c}/slack/bots/${bot}/channels`),
  leaveSlackChannel: (c: string, bot: string, channel: string) =>
    call<SlackStatus>(`/companies/${c}/slack/bots/${bot}/channels/${channel}/leave`, json("POST")),
  joinSlackChannel: (c: string, bot: string, channel: string) =>
    call<SlackStatus>(`/companies/${c}/slack/bots/${bot}/channels/${channel}/join`, json("POST")),
  listenSlackChannel: (c: string, bot: string, channel: string, listening: boolean) =>
    call<SlackStatus>(`/companies/${c}/slack/bots/${bot}/channels/${channel}`, json("PATCH", { listening })),
  slackManifest: () => call<unknown>("/slack/manifest"),

  github: (c: string) => call<GitHubStatus>(`/companies/${c}/github`),
  connectGitHub: (c: string, token: string, use_env: boolean) =>
    call<GitHubStatus>(`/companies/${c}/github`, json("PUT", { token, use_env })),
  patchGitHub: (c: string, patch: { repos?: string[]; pr_limit?: number }) =>
    call<GitHubStatus>(`/companies/${c}/github`, json("PATCH", patch)),
  disconnectGitHub: (c: string) => call<GitHubStatus>(`/companies/${c}/github`, json("DELETE")),
  githubRepos: (c: string) => call<GitHubRepo[]>(`/companies/${c}/github/repos`),
  syncGitHub: (c: string) => call<GitHubStatus>(`/companies/${c}/github/sync`, json("POST")),

  jira: (c: string) => call<JiraStatus>(`/companies/${c}/jira`),
  connectJira: (c: string, body: { site: string; email: string; token: string; use_env: boolean }) =>
    call<JiraStatus>(`/companies/${c}/jira`, json("PUT", body)),
  patchJira: (c: string, patch: { projects?: string[]; issue_limit?: number }) =>
    call<JiraStatus>(`/companies/${c}/jira`, json("PATCH", patch)),
  disconnectJira: (c: string) => call<JiraStatus>(`/companies/${c}/jira`, json("DELETE")),
  jiraProjects: (c: string) => call<JiraProject[]>(`/companies/${c}/jira/projects`),
  syncJira: (c: string) => call<JiraStatus>(`/companies/${c}/jira/sync`, json("POST")),

  linear: (c: string) => call<LinearStatus>(`/companies/${c}/linear`),
  connectLinear: (c: string, token: string, use_env: boolean) =>
    call<LinearStatus>(`/companies/${c}/linear`, json("PUT", { token, use_env })),
  patchLinear: (c: string, patch: { teams?: string[]; issue_limit?: number }) =>
    call<LinearStatus>(`/companies/${c}/linear`, json("PATCH", patch)),
  disconnectLinear: (c: string) => call<LinearStatus>(`/companies/${c}/linear`, json("DELETE")),
  linearTeams: (c: string) => call<LinearTeam[]>(`/companies/${c}/linear/teams`),
  syncLinear: (c: string) => call<LinearStatus>(`/companies/${c}/linear/sync`, json("POST")),

  notion: (c: string) => call<NotionStatus>(`/companies/${c}/notion`),
  connectNotion: (c: string, token: string, use_env: boolean) =>
    call<NotionStatus>(`/companies/${c}/notion`, json("PUT", { token, use_env })),
  patchNotion: (c: string, patch: { databases?: string[]; page_limit?: number }) =>
    call<NotionStatus>(`/companies/${c}/notion`, json("PATCH", patch)),
  disconnectNotion: (c: string) => call<NotionStatus>(`/companies/${c}/notion`, json("DELETE")),
  notionDatabases: (c: string) => call<NotionDatabase[]>(`/companies/${c}/notion/databases`),
  syncNotion: (c: string) => call<NotionStatus>(`/companies/${c}/notion/sync`, json("POST")),

  providers: () => call<Provider[]>("/llm/providers"),
  saveModel: (c: string, d: ModelDraft) => call<ModelConfig>(`/companies/${c}/model`, json("PUT", d)),
  disconnectModel: (c: string) => call<ModelConfig>(`/companies/${c}/model`, json("DELETE")),
  listModels: (c: string, d: ModelDraft) =>
    call<{ models: string[]; error: string | null }>(`/companies/${c}/model/models`, json("POST", d)),
  testModel: (c: string, d: ModelDraft) =>
    call<{ ok: boolean; reply?: string; ms?: number; message?: string }>(`/companies/${c}/model/test`, json("POST", d)),

  connectors: (c: string) => call<Connector[]>(`/companies/${c}/connectors`),
  patchConnector: (c: string, id: string, patch: Partial<Connector>) =>
    call<Connector>(`/companies/${c}/connectors/${id}`, json("PATCH", patch)),
  syncConnector: (c: string, id: string) =>
    call<{ ok: boolean; message: string }>(`/companies/${c}/connectors/${id}/sync`, json("POST")),
};
