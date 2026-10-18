import { Braces, Calendar, Hash, ToggleLeft, Type } from "lucide-react";
import { isNumericType, isTemporalType } from "@/lib/formatters";

export function typeCategory(t: string): "number" | "date" | "text" | "boolean" | "other" {
  if (isNumericType(t)) return "number";
  if (isTemporalType(t)) return "date";
  if (/bool/i.test(t)) return "boolean";
  if (/char|string|text/i.test(t)) return "text";
  return "other";
}

const ICONS = { number: Hash, date: Calendar, text: Type, boolean: ToggleLeft, other: Braces };
const COLORS = { number: "text-accent", date: "text-cyan", text: "text-muted", boolean: "text-warning", other: "text-faint" };

export function TypeIcon({ dataType }: { dataType: string }) {
  const cat = typeCategory(dataType);
  const Icon = ICONS[cat];
  return <Icon className={`size-3.5 shrink-0 ${COLORS[cat]}`} aria-label={`${cat} column`} />;
}
