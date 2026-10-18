"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { api } from "@/lib/api";
import type { Company, GraphData } from "@/lib/types";

export type PageId = "ask" | "graph" | "sources" | "answers" | "settings";

const PAGES: PageId[] = ["ask", "graph", "sources", "answers", "settings"];
/** Pages that sit beside the map. The rest use the full width. */
export const MAP_PAGES = new Set<PageId>(["ask", "graph"]);

type Lit = { nodes: Set<string>; links: Set<string> };

type Desk = {
  companies: Company[];
  company: Company | null;
  setCompanyId: (id: string) => void;
  reloadCompanies: () => Promise<Company[]>;
  page: PageId;
  setPage: (p: PageId) => void;

  /** True while the "create a new company" setup flow is open. */
  newCompany: boolean;
  setNewCompany: (v: boolean) => void;
  /** The "Add context" drawer (upload more documents or add a person). */
  contextOpen: boolean;
  setContextOpen: (v: boolean) => void;
  openContext: () => void;
  companiesLoaded: boolean;

  graph: GraphData;
  graphLoading: boolean;
  refreshGraph: () => Promise<GraphData>;

  /** Which nodes and links are lit on the canvas. Everything else is dimmed when `dim` is on. */
  lit: React.RefObject<Lit>;
  litVersion: number;
  lightNode: (id: string) => void;
  lightLink: (id: string) => void;
  clearLit: () => void;
  setLit: (nodes: string[], links: string[]) => void;
  dim: boolean;
  setDim: (v: boolean) => void;

  selectedId: string | null;
  selectNode: (id: string | null) => void;
  error: string | null;
  setError: (e: string | null) => void;
};

const Ctx = createContext<Desk | null>(null);

export function useDesk(): Desk {
  const v = useContext(Ctx);
  if (!v) throw new Error("useDesk outside DeskProvider");
  return v;
}

const EMPTY: GraphData = { nodes: [], links: [] };

export function DeskProvider({ children }: { children: ReactNode }) {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyIdState] = useState<string>("lumen");
  const [page, setPageState] = useState<PageId>("ask");
  const [newCompany, setNewCompany] = useState(false);
  const [contextOpen, setContextOpen] = useState(false);
  const [companiesLoaded, setCompaniesLoaded] = useState(false);
  const [graph, setGraph] = useState<GraphData>(EMPTY);
  const [graphLoading, setGraphLoading] = useState(true);
  const [dim, setDim] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [litVersion, setLitVersion] = useState(0);
  const lit = useRef<Lit>({ nodes: new Set(), links: new Set() });

  const bump = useCallback(() => setLitVersion((v) => v + 1), []);

  const lightNode = useCallback(
    (id: string) => {
      lit.current.nodes.add(id);
      bump();
    },
    [bump],
  );
  const lightLink = useCallback(
    (id: string) => {
      lit.current.links.add(id);
      bump();
    },
    [bump],
  );
  const clearLit = useCallback(() => {
    lit.current = { nodes: new Set(), links: new Set() };
    bump();
  }, [bump]);
  const setLit = useCallback(
    (nodes: string[], links: string[]) => {
      lit.current = { nodes: new Set(nodes), links: new Set(links) };
      bump();
    },
    [bump],
  );

  const reloadCompanies = useCallback(async () => {
    const list = await api.companies();
    setCompanies(list);
    return list;
  }, []);

  const refreshGraph = useCallback(async () => {
    setGraphLoading(true);
    try {
      const g = await api.graph(companyId);
      setGraph(g);
      return g;
    } finally {
      setGraphLoading(false);
    }
  }, [companyId]);

  // remember company and page between visits
  useEffect(() => {
    const c = localStorage.getItem("graphdesk.company");
    const p = localStorage.getItem("graphdesk.page") as PageId | null;
    if (c) setCompanyIdState(c);
    if (p && PAGES.includes(p)) setPageState(p);
  }, []);

  useEffect(() => {
    reloadCompanies()
      .then((list) => {
        // a remembered company may have been deleted since the last visit
        setCompanyIdState((cur) => (list.some((c) => c.id === cur) || list.length === 0 ? cur : list[0].id));
      })
      .catch((e) => setError(String(e.message ?? e)))
      .finally(() => setCompaniesLoaded(true));
  }, [reloadCompanies]);

  useEffect(() => {
    if (!companiesLoaded) return;
    clearLit();
    setSelectedId(null);
    refreshGraph().catch((e) => setError(String(e.message ?? e)));
  }, [companiesLoaded, companyId, refreshGraph, clearLit]);

  const setCompanyId = useCallback((id: string) => {
    localStorage.setItem("graphdesk.company", id);
    setCompanyIdState(id);
    setContextOpen(false);
  }, []);
  const setPage = useCallback((p: PageId) => {
    localStorage.setItem("graphdesk.page", p);
    setPageState(p);
  }, []);
  /** Opens the drawer. It sits beside the map, so leave pages that have no map. */
  const openContext = useCallback(() => {
    setPageState((cur) => (MAP_PAGES.has(cur) ? cur : "graph"));
    setContextOpen(true);
  }, []);

  const company = useMemo(
    () => companies.find((c) => c.id === companyId) ?? null,
    [companies, companyId],
  );

  const value: Desk = {
    companies,
    company,
    setCompanyId,
    reloadCompanies,
    page,
    setPage,
    newCompany,
    setNewCompany,
    contextOpen,
    setContextOpen,
    openContext,
    companiesLoaded,
    graph,
    graphLoading,
    refreshGraph,
    lit,
    litVersion,
    lightNode,
    lightLink,
    clearLit,
    setLit,
    dim,
    setDim,
    selectedId,
    selectNode: setSelectedId,
    error,
    setError,
  };

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
