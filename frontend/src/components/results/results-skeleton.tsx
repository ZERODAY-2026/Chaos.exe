/** Mirrors the real results layout so the page does not jump when data arrives. */
export function ResultsSkeleton() {
  return (
    <div aria-hidden="true" className="space-y-6 pt-2">
      <div className="space-y-2">
        <div className="skeleton h-3.5 w-full max-w-2xl" />
        <div className="skeleton h-3.5 w-3/5 max-w-xl" />
      </div>
      <div className="panel">
        <div className="border-b border-line px-4 py-3">
          <div className="skeleton h-3 w-20" />
        </div>
        {[0, 1, 2, 3, 4].map((i) => (
          <div key={i} className="flex gap-6 border-b border-line px-4 py-2.5 last:border-0">
            <div className="skeleton h-3 w-1/4" />
            <div className="skeleton h-3 w-1/6" />
            <div className="skeleton ml-auto h-3 w-16" />
          </div>
        ))}
      </div>
      <div className="grid gap-4 xl:grid-cols-5">
        <div className="panel p-4 xl:col-span-3">
          <div className="skeleton h-24 w-full" />
        </div>
        <div className="panel space-y-3 p-4 xl:col-span-2">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="skeleton h-3 w-full" />
          ))}
        </div>
      </div>
    </div>
  );
}
