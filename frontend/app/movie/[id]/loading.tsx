import { RowSkeleton, Skeleton } from "@/components/ui/Skeleton";

export default function Loading() {
  return (
    <div className="relative">
      <div className="min-h-[88svh] px-4 pb-14 pt-40 md:px-12">
        <div className="flex items-end gap-10 pt-[20vh]">
          <Skeleton className="hidden aspect-[2/3] w-64 lg:block" />
          <div className="w-full max-w-2xl space-y-4">
            <Skeleton className="h-6 w-40" />
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-4 w-2/3" />
            <div className="flex gap-3 pt-4">
              <Skeleton className="h-12 w-40 rounded-full" />
              <Skeleton className="h-12 w-32 rounded-full" />
            </div>
          </div>
        </div>
      </div>
      <RowSkeleton />
    </div>
  );
}
