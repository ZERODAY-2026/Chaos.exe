import type { Metadata } from "next";
import { SchemaExplorer } from "@/components/schema/schema-explorer";

export const metadata: Metadata = { title: "Schema Explorer" };

export default function SchemaPage() {
  return <SchemaExplorer />;
}
