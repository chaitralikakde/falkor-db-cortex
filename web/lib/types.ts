export type Company = {
  id: string;
  name: string;
  graph: string;
  finished: boolean;
  admin: string;
  created: string;
};

export type GNode = {
  id: string;
  label: string;
  color: string;
  data: Record<string, unknown> & { name: string; url?: string };
};

export type GLink = {
  id: string;
  source: string;
  target: string;
  relationship: string;
  data: Record<string, unknown>;
};

export type GraphData = { nodes: GNode[]; links: GLink[] };

export type Step = {
  agent: "Mapper" | "Clerk";
  tool: string;
  cypher: string;
  ms: number;
  nodes: GNode[];
  links: GLink[];
};

export type Source = {
  id: string;
  kind: string;
  name: string;
  url: string;
  date: string;
};

export type AskResult = {
  sentence: string;
  sources: Source[];
  steps: Step[];
  refused: boolean;
  session: string | null;
  finding: string | null;
  system?: string;
  intent?: string;
  ms: number;
  model: string;
};

export type Task = {
  id: string;
  title: string;
  status: "open" | "done";
  created: string;
  assignee: { id: string; name: string };
  system: { id: string; name: string };
  current_owner: string | null;
  sources: Source[];
};

export type ApplyResult = {
  task: string;
  system: { id: string; name: string };
  new_owner: { id: string; name: string; start: string };
  ended: { id: string; name: string; start: string; end: string }[];
};

export type UploadResult = {
  file: string;
  error?: string;
  notes?: string[];
  nodes?: GNode[];
  links?: GLink[];
  tasks?: string[];
  ms?: number;
};

export type Stats = {
  company: Company;
  nodes: Record<string, number>;
  total_nodes: number;
  total_links: number;
  people: number;
};

export type Skill = { name: string; on: boolean; when: string; steps: string };

export type Settings = {
  super_prompt: string;
  skills: Skill[];
  model: ModelConfig;
};

export type ModelConfig = {
  provider: string;
  model: string;
  base_url: string;
  has_key: boolean;
  key_hint: string;
  connected: boolean;
  label: string;
};

export type Provider = {
  id: string;
  name: string;
  base_url: string;
  default_model: string;
  key_url?: string;
  note?: string;
  recommended?: boolean;
  no_key?: boolean;
};

export type SlackChannel = { id: string; name: string; im: boolean; private: boolean; listening: boolean };

export type SlackBot = {
  id: string;
  label: string;
  team: string;
  bot_user: string;
  bot_hint: string;
  department: string;
  running: boolean;
  error: string | null;
  answered: number;
  channels: SlackChannel[];
  settings: SlackBotSettings;
  missing_scopes: string[];
};

export type Department = {
  id: string;
  name: string;
  blurb: string;
  try: string[];
  systems: { id: string; name: string; department: string; owner: string | null }[];
  people: { id: string; name: string; role: string; team: string }[];
};

export type SlackBotSettings = { thread: boolean; sources: boolean; max_sources: number };

export type SlackStatus = { bots: SlackBot[] };

export type SlackChannelRow = {
  id: string;
  name: string;
  kind: "public" | "private" | "dm";
  member: boolean;
  members: number;
  listening: boolean;
};

export type GitHubResult = {
  at: string;
  repos: number;
  prs: number;
  people_linked: number;
  people_added: string[];
  nodes: number;
  links: number;
  errors: string[];
};

export type GitHubStatus = {
  connected: boolean;
  env_available: boolean;
  env_hint: string;
  pr_limits: number[];
  login: string;
  name: string;
  scopes: string[];
  source: "" | "stored" | "server";
  token_hint: string;
  repos: string[];
  pr_limit: number;
  last_sync: string | null;
  last_result: GitHubResult | null;
  token_missing: boolean;
};

export type GitHubRepo = {
  full_name: string;
  name: string;
  owner: string;
  private: boolean;
  archived: boolean;
  fork: boolean;
  description: string;
  language: string;
  pushed: string;
  url: string;
  open_issues: number;
  selected: boolean;
};

export type SlackChannelList = { channels: SlackChannelRow[]; warning: string | null };

export type JiraResult = {
  at: string;
  projects: number;
  tickets: number;
  people_linked: number;
  people_added: string[];
  nodes: number;
  links: number;
  errors: string[];
};

export type JiraStatus = {
  connected: boolean;
  env_available: boolean;
  env_hint: string;
  env_site: string;
  issue_limits: number[];
  site: string;
  email: string;
  name: string;
  token_hint: string;
  projects: string[];
  issue_limit: number;
  last_sync: string | null;
  last_result: JiraResult | null;
  token_missing: boolean;
};

export type JiraProject = { key: string; name: string; type: string; url: string; selected: boolean };

export type LinearResult = {
  at: string;
  teams: number;
  tickets: number;
  people_linked: number;
  people_added: string[];
  nodes: number;
  links: number;
  errors: string[];
};

export type LinearStatus = {
  connected: boolean;
  env_available: boolean;
  env_hint: string;
  issue_limits: number[];
  name: string;
  email: string;
  token_hint: string;
  teams: string[];
  issue_limit: number;
  last_sync: string | null;
  last_result: LinearResult | null;
  token_missing: boolean;
};

export type LinearTeam = { id: string; key: string; name: string; url: string; selected: boolean };

export type NotionResult = {
  at: string;
  databases: number;
  docs: number;
  people_linked: number;
  people_added: string[];
  nodes: number;
  links: number;
  errors: string[];
};

export type NotionStatus = {
  connected: boolean;
  env_available: boolean;
  env_hint: string;
  page_limits: number[];
  name: string;
  workspace: string;
  token_hint: string;
  databases: string[];
  page_limit: number;
  last_sync: string | null;
  last_result: NotionResult | null;
  token_missing: boolean;
};

export type NotionDatabase = { id: string; name: string; url: string; selected: boolean };

export type ModelDraft = { provider: string; model: string; base_url: string; api_key: string };

export type Connector = {
  id: string;
  name: string;
  connected: boolean;
  read: boolean;
  write: boolean;
  from_seed: boolean;
  last_sync: string | null;
  detail?: string | null;
};

export type Answer = {
  id: string;
  question: string;
  at: string;
  asked_by: string;
  conclusion: string;
  nodes: string[];
};

export type NodeDetail = {
  node: GNode;
  links: {
    direction: "out" | "in";
    rel: string;
    props: Record<string, unknown>;
    other: { id: string; label: string; name: string };
    source: string;
    target: string;
  }[];
};

export type Risk = { system: string; authors: string[] };
