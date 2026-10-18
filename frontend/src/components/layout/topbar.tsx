"use client";

import { Menu, Moon, RefreshCw, Sun } from "lucide-react";
import { usePathname } from "next/navigation";
import { IconButton } from "@/components/ui/button";
import { useWorkspace } from "@/components/workspace-provider";
import { cn } from "@/lib/utils";
import { LogoMark } from "./logo";
import { titleForPath } from "./nav-items";
import { ProviderSwitcher } from "./provider-switcher";

export function Topbar({ onOpenMenu }: { onOpenMenu: () => void }) {
  const pathname = usePathname();
  const item = titleForPath(pathname);
  const { theme, setTheme, refreshHealth, health } = useWorkspace();
  const checking = health.state === "loading";

  return (
    <header className="sticky top-0 z-30 flex h-12 shrink-0 items-center gap-2 border-b border-line bg-bg px-3 sm:px-5">
      <IconButton label="Open navigation" onClick={onOpenMenu} className="-ml-1 lg:hidden">
        <Menu className="size-4" />
      </IconButton>
      <LogoMark className="size-5 lg:hidden" />
      <span className="truncate text-[13px] font-medium text-fg" aria-current="page">
        {item.label}
      </span>

      <div className="ml-auto flex items-center gap-1">
        <ProviderSwitcher />
        <IconButton label={checking ? "Checking connection" : "Check connection"} onClick={refreshHealth} disabled={checking}>
          <RefreshCw className={cn("size-3.5", checking && "animate-spin")} />
        </IconButton>
        <IconButton
          label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
        >
          {theme === "dark" ? <Sun className="size-3.5" /> : <Moon className="size-3.5" />}
        </IconButton>
      </div>
    </header>
  );
}
