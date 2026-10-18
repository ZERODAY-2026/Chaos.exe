"use client";

import { Menu, Moon, RefreshCw, Sun } from "lucide-react";
import { usePathname } from "next/navigation";
import { IconButton } from "@/components/ui/button";
import { useWorkspace } from "@/components/workspace-provider";
import { cn } from "@/lib/utils";
import { titleForPath } from "./nav-items";
import { ProviderSwitcher } from "./provider-switcher";
import { LogoMark } from "./logo";

export function Topbar({ onOpenMenu }: { onOpenMenu: () => void }) {
  const pathname = usePathname();
  const item = titleForPath(pathname);
  const { theme, setTheme, refreshHealth, health } = useWorkspace();
  const checking = health.state === "loading";

  return (
    <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center gap-2 border-b border-line bg-bg/80 px-3 backdrop-blur-md sm:px-5">
      <IconButton label="Open navigation" onClick={onOpenMenu} className="lg:hidden">
        <Menu className="size-4.5" />
      </IconButton>
      <div className="flex items-center gap-2 lg:hidden">
        <LogoMark className="size-6" />
      </div>
      <nav aria-label="Breadcrumb" className="hidden min-w-0 items-center gap-1.5 text-[13px] sm:flex">
        <span className="text-faint lg:inline">DataMind</span>
        <span className="text-faint" aria-hidden="true">/</span>
        <span className="truncate font-medium text-fg" aria-current="page">
          {item.label}
        </span>
      </nav>
      <span className="truncate text-[13px] font-medium text-fg sm:hidden">{item.label}</span>

      <div className="ml-auto flex items-center gap-1.5">
        <ProviderSwitcher />
        <IconButton label={checking ? "Checking connection" : "Check connection"} onClick={refreshHealth} disabled={checking}>
          <RefreshCw className={cn("size-4", checking && "animate-spin")} />
        </IconButton>
        <IconButton
          label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
        >
          {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
        </IconButton>
      </div>
    </header>
  );
}
