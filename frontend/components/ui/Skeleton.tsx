import { cn } from "@/lib/utils";

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("shimmer rounded-xl", className)} aria-hidden />;
}

export const CARD_WIDTH = "w-[36vw] sm:w-[26vw] md:w-[19vw] lg:w-[15vw] xl:w-[12.4vw]";

export function RowSkeleton({ title = true }: { title?: boolean }) {
  return (
    <div className="space-y-4 px-4 md:px-12" aria-busy="true" aria-label="Loading">
      {title && <Skeleton className="h-6 w-48" />}
      <div className="flex gap-3 overflow-hidden md:gap-4">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className={cn("aspect-[2/3] shrink-0", CARD_WIDTH)} />
        ))}
      </div>
    </div>
  );
}

export function GridSkeleton({ count = 12 }: { count?: number }) {
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6" aria-busy="true">
      {Array.from({ length: count }).map((_, i) => (
        <Skeleton key={i} className="aspect-[2/3]" />
      ))}
    </div>
  );
}
