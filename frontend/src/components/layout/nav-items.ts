import { Database, History, MessageSquareText, Settings2, type LucideIcon } from "lucide-react";

export type NavItem = { href: string; label: string; icon: LucideIcon; description: string };

export const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Ask Data", icon: MessageSquareText, description: "Ask questions in plain language" },
  { href: "/history", label: "Query History", icon: History, description: "Questions asked in this browser" },
  { href: "/schema", label: "Schema Explorer", icon: Database, description: "Tables and columns of the active source" },
  { href: "/settings", label: "Settings", icon: Settings2, description: "Connection, mode and appearance" },
];

export function titleForPath(pathname: string): NavItem {
  return NAV_ITEMS.find((n) => (n.href === "/" ? pathname === "/" : pathname.startsWith(n.href))) ?? NAV_ITEMS[0]!;
}
