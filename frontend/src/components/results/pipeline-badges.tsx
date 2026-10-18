import { CircleCheck, CircleDashed, CircleX } from "lucide-react";
import { Badge, type Tone } from "@/components/ui/badge";
import type { QueryResponse } from "@/lib/api-types";

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

const toneFor: Record<Step["state"], Tone> = { yes: "success", no: "danger", unknown: "neutral" };

export function PipelineBadges({ response }: { response: QueryResponse }) {
  const steps = pipelineSteps(response);
  return (
    <ul className="flex flex-wrap gap-1.5" aria-label="Query pipeline status">
      {steps.map((s) => {
        const Icon = s.state === "yes" ? CircleCheck : s.state === "no" ? CircleX : CircleDashed;
        const tone = s.label === "Not executed" && response.status === "success" ? "warning" : toneFor[s.state];
        return (
          <li key={s.label} title={s.detail}>
            <Badge tone={tone} icon={<Icon className="size-3" />}>
              {s.label}
            </Badge>
          </li>
        );
      })}
    </ul>
  );
}
