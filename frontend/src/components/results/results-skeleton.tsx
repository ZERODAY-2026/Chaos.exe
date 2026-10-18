/** Mirrors the real results layout so the page does not jump when data arrives. */
export function ResultsSkeleton() {
  return (
    <div aria-hidden="true" className="space-y-4">
      <div className="rounded-xl border border-line bg-surface p-6">
        <div className="skeleton h-3 w-24" />
        <div className="skeleton mt-4 h-5 w-3/5" />
        <div className="skeleton mt-4 h-3.5 w-full max-w-2xl" />
        <div className="skeleton mt-2 h-3.5 w-4/5 max-w-xl" />
      </div>
      <div className="rounded-xl border border-line bg-surface p-4">
        <div className="skeleton h-3 w-28" />
        <div className="mt-6 flex h-52 items-end gap-3 px-4">
          {[62, 88, 45, 74, 56, 92, 38].map((h, i) => (
            <div key={i} className="skeleton flex-1" style={{ height: `${h}%` }} />
          ))}
        </div>
      </div>
      <div className="grid gap-4 xl:grid-cols-5">
        <div className="rounded-xl border border-line bg-surface p-4 xl:col-span-3">
          <div className="skeleton h-3 w-16" />
          <div className="skeleton mt-4 h-28 w-full" />
        </div>
        <div className="rounded-xl border border-line bg-surface p-4 xl:col-span-2">
          <div className="skeleton h-3 w-20" />
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="skeleton mt-4 h-3 w-full" />
          ))}
        </div>
      </div>
    </div>
  );
}
