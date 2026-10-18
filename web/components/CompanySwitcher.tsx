"use client";

import { useDesk } from "./DeskProvider";
import { PlusIcon } from "./icons";

export default function CompanySwitcher() {
  const { companies, company, setCompanyId, setNewCompany } = useDesk();

  return (
    <div className="flex items-center gap-1.5">
      <select
        value={company?.id ?? ""}
        onChange={(e) => {
          setNewCompany(false);
          setCompanyId(e.target.value);
        }}
        aria-label="Company graph"
        className="min-w-0 flex-1 rounded-lg border border-line bg-background px-2.5 py-1.5 text-sm outline-none focus:border-accent/70"
      >
        {companies.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
            {c.finished ? "" : " (setting up)"}
          </option>
        ))}
      </select>
      <button
        onClick={() => setNewCompany(true)}
        title="New company"
        aria-label="New company"
        className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-line text-muted transition hover:border-accent/60 hover:text-foreground"
      >
        <PlusIcon />
      </button>
    </div>
  );
}
