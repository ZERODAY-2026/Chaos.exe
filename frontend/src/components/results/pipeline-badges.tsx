import { Check, Minus, X } from "lucide-react";
import type { QueryResponse } from "@/lib/api-types";
import { cn } from "@/lib/utils";

type Step = { label: string; state: "yes" | "no" | "unknown"; detail: string };

/** Derives generated / validated / executed strictly from fields the backend returned. */
export function pipelineSteps(r: QueryResponse): Step[] {
  const generated: Step = r.sql
    ? { label: "Generated", state: "yes", detail: "The backend returned SQL" }
    : { label: "Generated", state: r.status === "error" && r.error?.stage === "generation" ? "no" : "unknown", detail: "No SQL returned" };
  const validated: Step = !r.validation
    ? { label: "Validated", state: "unknown", detail: "Validation not reported" }
    : r.validation.passed
      ? {
          label: r.validation.read_only ? "Validated read-only" : "Validated",
          state: "yes",
          detail: r.validation.limit_applied ? `LIMIT ${r.validation.limit_applied} enforced` : "Passed validation",
        }
      : { label: "Validation failed", state: "no", detail: "Rejected before execution" };
  const executed: Step =
    r.executed === true
      ? { label: "Executed", state: "yes", detail: "Ran against the data source" }
      : r.executed === false
        ? { label: "Not executed", state: "no", detail: "This SQL was not run" }
        : { label: "Execution", state: "unknown", detail: "Execution not reported" };
  return [generated, validated, executed];
}

/** A compact checklist: generated → validated → executed. */
export function PipelineBadges({ response }: { response: QueryResponse }) {
  const steps = pipelineSteps(response);
  return (
    <ul className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs" aria-label="Query pipeline status">
      {steps.map((s) => {
        const Icon = s.state === "yes" ? Check : s.state === "no" ? X : Minus;
        const soft = s.label === "Not executed" && response.status === "success";
        return (
          <li key={s.label} title={s.detail} className="inline-flex items-center gap-1.5 text-muted">
            <Icon
              className={cn(
                "size-3.5",
                s.state === "yes" && "text-success",
                s.state === "no" && (soft ? "text-warning" : "text-danger"),
                s.state === "unknown" && "text-faint",
              )}
              strokeWidth={2.25}
              aria-hidden="true"
            />
            <span>{s.label}</span>
            <span className="sr-only">{s.state === "yes" ? "(done)" : s.state === "no" ? "(no)" : "(not reported)"}</span>
          </li>
        );
      })}
    </ul>
  );
}
