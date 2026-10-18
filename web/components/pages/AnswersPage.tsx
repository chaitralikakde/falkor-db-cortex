"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Answer } from "@/lib/types";
import { useDesk } from "../DeskProvider";
import { Badge, Button, Card, ErrorLine, PageHeader } from "../ui";

export function AnswersPage() {
  const { company, setPage } = useDesk();
  const [rows, setRows] = useState<Answer[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!company) return;
    api.answers(company.id).then(setRows).catch((e) => setError(e.message));
  }, [company]);

  return (
    <div className="h-full overflow-y-auto">
      <PageHeader title="Answers" subtitle="Each question is stored as a Session node linked to the path it used." />
      <div className="mx-auto max-w-3xl space-y-3 p-5">
        <ErrorLine message={error} />
        {rows.length === 0 && (
          <Card>
            <p className="text-sm text-muted">No questions yet.</p>
            <Button className="mt-3" onClick={() => setPage("ask")}>
              Go to Ask
            </Button>
          </Card>
        )}
        {rows.map((r) => (
          <Card key={r.id} title={r.question || r.id} right={<Badge>{r.at.replace("T", " ")}</Badge>}>
            <p className="text-sm">{r.conclusion || <span className="text-muted">No conclusion stored.</span>}</p>
            <p className="mt-2 text-xs text-muted">
              {r.id}
              {r.asked_by ? ` · asked by ${r.asked_by}` : ""}
              {r.nodes.length ? ` · recalls ${r.nodes.join(", ")}` : ""}
            </p>
          </Card>
        ))}
      </div>
    </div>
  );
}
