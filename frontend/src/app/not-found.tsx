import { Compass } from "lucide-react";
import Link from "next/link";
import { EmptyState } from "@/components/ui/empty-state";

export default function NotFound() {
  return (
    <div className="mx-auto max-w-xl px-4 py-20">
      <EmptyState
        icon={<Compass />}
        title="Page not found"
        action={
          <Link href="/" className="inline-flex h-9 items-center rounded-lg bg-accent px-3.5 text-sm font-medium text-accent-fg hover:bg-accent-strong">
            Back to Ask Data
          </Link>
        }
      >
        This page does not exist in DataMind.
      </EmptyState>
    </div>
  );
}
