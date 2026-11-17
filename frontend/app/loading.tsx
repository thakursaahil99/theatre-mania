import { RowSkeleton, Skeleton } from "@/components/ui/Skeleton";

export default function Loading() {
  return (
    <div>
      <Skeleton className="h-[80svh] w-full rounded-none" />
      <div className="-mt-[8vh] space-y-10">
        <RowSkeleton />
        <RowSkeleton />
      </div>
    </div>
  );
}
