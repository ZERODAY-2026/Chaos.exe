import Link from "next/link";
import { buttonClass } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";

export default function NotFound() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-16 sm:px-8">
      <EmptyState
        title="Page not found"
        action={
          <Link href="/" className={buttonClass("primary")}>
            Back to Ask Data
          </Link>
        }
      >
        This page does not exist in DataMind.
      </EmptyState>
    </div>
  );
}
