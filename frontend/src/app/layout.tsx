import type { Metadata, Viewport } from "next";
import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";
import { AppShell } from "@/components/layout/app-shell";
import { ToastProvider } from "@/components/ui/toast";
import { WorkspaceProvider } from "@/components/workspace-provider";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "DataMind — Talk to your data", template: "%s · DataMind" },
  description: "Ask questions about structured data in plain language and inspect the SQL, rows and evidence behind every answer.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#0e1013" },
    { media: "(prefers-color-scheme: light)", color: "#fafafa" },
  ],
};

// Applies the saved theme before first paint to avoid a flash.
const themeScript = `try{var t=JSON.parse(localStorage.getItem("datamind.theme")||'"dark"');document.documentElement.setAttribute("data-theme",t==="light"?"light":"dark")}catch(e){document.documentElement.setAttribute("data-theme","dark")}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="dark" className={`${GeistSans.variable} ${GeistMono.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>
        <WorkspaceProvider>
          <ToastProvider>
            <AppShell>{children}</AppShell>
          </ToastProvider>
        </WorkspaceProvider>
      </body>
    </html>
  );
}
