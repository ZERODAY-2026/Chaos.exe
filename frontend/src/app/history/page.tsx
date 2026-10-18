import type { Metadata } from "next";
import { QueryHistory } from "@/components/history/query-history";

export const metadata: Metadata = { title: "Query History" };

export default function HistoryPage() {
  return <QueryHistory />;
}
