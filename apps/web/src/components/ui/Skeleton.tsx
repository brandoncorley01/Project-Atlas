interface SkeletonProps {
  className?: string;
}

export function Skeleton({ className = "" }: SkeletonProps) {
  return <div className={`atlas-skeleton ${className}`} aria-hidden />;
}

export function SignalCardSkeleton() {
  return (
    <div className="atlas-card space-y-4 p-5">
      <div className="flex justify-between gap-4">
        <div className="flex-1 space-y-2">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="h-6 w-3/4 max-w-xs" />
          <Skeleton className="h-4 w-full max-w-sm" />
        </div>
        <div className="hidden gap-2 sm:grid sm:grid-cols-3 sm:min-w-[200px]">
          <Skeleton className="h-14 rounded-lg" />
          <Skeleton className="h-14 rounded-lg" />
          <Skeleton className="h-14 rounded-lg" />
        </div>
      </div>
      <div className="flex gap-2">
        <Skeleton className="h-7 w-28 rounded-md" />
        <Skeleton className="h-7 w-20 rounded-md" />
      </div>
    </div>
  );
}

export function ListSkeleton({ count = 3 }: { count?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: count }).map((_, i) => (
        <SignalCardSkeleton key={i} />
      ))}
    </div>
  );
}

export function DashboardSkeleton() {
  return (
    <div className="space-y-8">
      <Skeleton className="h-24 w-full rounded-xl" />
      <div>
        <Skeleton className="mb-4 h-4 w-32" />
        <ListSkeleton count={2} />
      </div>
      <div>
        <Skeleton className="mb-4 h-4 w-40" />
        <ListSkeleton count={2} />
      </div>
    </div>
  );
}
