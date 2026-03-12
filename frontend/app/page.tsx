import { Suspense } from "react";
import { HomePageClient } from "./components/home-page-client";

export default function HomePage() {
  return (
    <Suspense
      fallback={
        <div className="empty-state">
          <strong>Loading posts.</strong>
          <p>Fetching the latest visible images for your current filters.</p>
        </div>
      }
    >
      <HomePageClient />
    </Suspense>
  );
}
