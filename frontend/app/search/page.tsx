import type { Metadata } from "next";
import { Suspense } from "react";

import { SearchView } from "@/components/search/SearchView";
import { GridSkeleton } from "@/components/ui/Skeleton";

export const metadata: Metadata = { title: "Search" };

export default function SearchPage() {
  return (
    <div className="min-h-svh px-4 pb-24 pt-28 md:px-12">
      <Suspense fallback={<GridSkeleton />}>
        <SearchView />
      </Suspense>
    </div>
  );
}
