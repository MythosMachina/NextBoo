"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useSearchParams } from "next/navigation";
import { authFetch, useAuthState } from "./auth";

type Post = {
  id: string;
  uuid_short: string;
  original_filename: string;
  width: number;
  height: number;
  duration_seconds?: number | null;
  has_audio?: boolean;
  rating: "general" | "sensitive" | "questionable" | "explicit";
  processing_status: string;
  uploaded_by: {
    id: number;
    username: string;
  } | null;
  thumb_url: string | null;
  preview_url?: string | null;
  preview_mime_type?: string | null;
};

type MediaTypeTag = {
  id: number;
  name_normalized: string;
  display_name: string;
  category: string;
  usage_count: number;
};

function ratingCode(rating: Post["rating"]): string {
  if (rating === "sensitive") return "s";
  if (rating === "questionable") return "q";
  if (rating === "explicit") return "x";
  return "g";
}

function mediaBadge(post: Post): string | null {
  const extension = post.original_filename.split(".").pop()?.toLowerCase() ?? "";
  if (["mp4", "mkv", "webm"].includes(extension)) {
    return "VIDEO";
  }
  if ((post.duration_seconds ?? 0) > 0) {
    return "ANIMATION";
  }
  return "IMAGE";
}

function parseRatingFilter(query: string): "general" | "sensitive" | "questionable" | "explicit" | "all" {
  const ratingToken = query
    .split(/\s+/)
    .map((token) => token.trim())
    .find((token) => token.startsWith("rating:"));
  if (!ratingToken) {
    return "all";
  }
  const value = ratingToken.split(":", 2)[1];
  if (value === "safe") return "general";
  if (value === "e") return "explicit";
  if (value === "q" || value === "s" || value === "general" || value === "sensitive" || value === "questionable" || value === "explicit") {
    return value === "q" ? "questionable" : value === "s" ? "sensitive" : value;
  }
  return "all";
}

function parseMediaTypeFilter(query: string): "all" | "image" | "animated" | "video" {
  const mediaToken = query
    .split(/\s+/)
    .map((token) => token.trim())
    .find((token) => token === "image" || token === "animated" || token === "video");
  if (mediaToken === "image" || mediaToken === "animated" || mediaToken === "video") {
    return mediaToken;
  }
  return "all";
}

function parseRatingParam(value: string | null): "general" | "sensitive" | "questionable" | "explicit" | "all" {
  if (!value) {
    return "all";
  }
  if (value === "safe") return "general";
  if (value === "e") return "explicit";
  if (value === "q") return "questionable";
  if (value === "s") return "sensitive";
  if (value === "general" || value === "sensitive" || value === "questionable" || value === "explicit") {
    return value;
  }
  return "all";
}

function parseMediaTypeParam(value: string | null): "all" | "image" | "animated" | "video" {
  if (value === "image" || value === "animated" || value === "video") {
    return value;
  }
  return "all";
}

function stripLegacyFilterTokens(query: string): string {
  return query
    .split(/\s+/)
    .map((token) => token.trim())
    .filter(Boolean)
    .filter((token) => !token.startsWith("rating:"))
    .filter((token) => token !== "image" && token !== "animated" && token !== "video")
    .join(" ");
}

const RATING_STORAGE_KEY = "nextboo-rating-filter";
const MEDIA_TYPE_STORAGE_KEY = "nextboo-media-type-filter";

export function HomePageClient() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { authenticated, isAdmin, loading: authLoading, user } = useAuthState();
  const rawQuery = searchParams.get("q")?.trim() ?? "";
  const query = stripLegacyFilterTokens(rawQuery);
  const legacyRatingFilter = parseRatingFilter(rawQuery);
  const legacyMediaTypeFilter = parseMediaTypeFilter(rawQuery);
  const ratingFilter = parseRatingParam(searchParams.get("rating")) !== "all"
    ? parseRatingParam(searchParams.get("rating"))
    : legacyRatingFilter;
  const mediaTypeFilter = parseMediaTypeParam(searchParams.get("media_type")) !== "all"
    ? parseMediaTypeParam(searchParams.get("media_type"))
    : legacyMediaTypeFilter;
  const requestedViewCount = Number.parseInt(searchParams.get("view") ?? "", 10);
  const requestedPage = Number.parseInt(searchParams.get("page") ?? "1", 10);
  const page = Number.isFinite(requestedPage) && requestedPage > 0 ? requestedPage : 1;
  const [viewCount, setViewCount] = useState(50);
  const [posts, setPosts] = useState<Post[]>([]);
  const [count, setCount] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [bulkDeleteMode, setBulkDeleteMode] = useState(false);
  const [selectedPostIds, setSelectedPostIds] = useState<string[]>([]);
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [mediaTypes, setMediaTypes] = useState<MediaTypeTag[]>([]);

  useEffect(() => {
    const stored = typeof window === "undefined" ? null : window.localStorage.getItem("nextboo-view-count");
    const storedValue = stored ? Number.parseInt(stored, 10) : NaN;
    const nextValue = [25, 50, 75, 100, 200].includes(requestedViewCount)
      ? requestedViewCount
      : [25, 50, 75, 100, 200].includes(storedValue)
        ? storedValue
        : 50;
    setViewCount(nextValue);
  }, [requestedViewCount]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const hasExplicitRatingParam = parseRatingParam(searchParams.get("rating")) !== "all";
    const hasExplicitMediaTypeParam = parseMediaTypeParam(searchParams.get("media_type")) !== "all";
    const storedRating = window.localStorage.getItem(RATING_STORAGE_KEY);
    const storedMediaType = window.localStorage.getItem(MEDIA_TYPE_STORAGE_KEY);
    if (hasExplicitRatingParam || hasExplicitMediaTypeParam || legacyRatingFilter !== "all" || legacyMediaTypeFilter !== "all") {
      return;
    }
    const params = new URLSearchParams(searchParams.toString());
    let changed = false;
    if (storedRating && ["safe", "general", "sensitive", "questionable", "explicit"].includes(storedRating)) {
      const normalizedStoredRating =
        storedRating === "safe" ? "general" : (storedRating as "general" | "sensitive" | "questionable" | "explicit");
      params.set("rating", normalizedStoredRating);
      changed = true;
    }
    if (storedMediaType && ["image", "animated", "video"].includes(storedMediaType)) {
      params.set("media_type", storedMediaType);
      changed = true;
    }
    if (!changed) {
      return;
    }
    params.delete("page");
    if (!params.get("view")) {
      params.set("view", String(viewCount));
    }
    updateRoute(params);
  }, [legacyMediaTypeFilter, legacyRatingFilter, searchParams, viewCount]);

  useEffect(() => {
    const hasLegacyQueryFilters = rawQuery !== query || legacyRatingFilter !== "all" || legacyMediaTypeFilter !== "all";
    if (!hasLegacyQueryFilters) {
      return;
    }
    const params = new URLSearchParams(searchParams.toString());
    let changed = false;
    if (rawQuery !== query) {
      if (query) {
        params.set("q", query);
      } else {
        params.delete("q");
      }
      changed = true;
    }
    if (legacyRatingFilter !== "all" && parseRatingParam(searchParams.get("rating")) === "all") {
      params.set("rating", legacyRatingFilter);
      changed = true;
    }
    if (legacyMediaTypeFilter !== "all" && parseMediaTypeParam(searchParams.get("media_type")) === "all") {
      params.set("media_type", legacyMediaTypeFilter);
      changed = true;
    }
    if (!changed) {
      return;
    }
    updateRoute(params);
  }, [legacyMediaTypeFilter, legacyRatingFilter, query, rawQuery, searchParams]);

  useEffect(() => {
    async function loadPosts() {
      if (authLoading) {
        return;
      }
      setLoading(true);
      const params = new URLSearchParams({
        limit: String(viewCount),
        page: String(page),
      });
      if (ratingFilter !== "all") {
        params.set("rating", ratingFilter);
      }
      if (mediaTypeFilter !== "all") {
        params.set("media_type", mediaTypeFilter);
      }
      if (query) {
        params.set("q", query);
      }
      const path = query ? `/api/v1/search?${params.toString()}` : `/api/v1/images?${params.toString()}`;
      const response = await authFetch(path, { method: "GET" });
      if (!response.ok) {
        setPosts([]);
        setCount(0);
        setTotalPages(1);
        setLoading(false);
        return;
      }
      const payload = await response.json();
      setPosts(payload.data);
      setCount(payload.meta.total_count ?? payload.meta.count ?? payload.data.length);
      setTotalPages(payload.meta.total_pages ?? 1);
      setLoading(false);
    }

    loadPosts();
  }, [authLoading, authenticated, mediaTypeFilter, page, query, ratingFilter, user?.can_view_questionable, user?.can_view_explicit, user?.role, user?.tag_blacklist.join("|"), viewCount]);

  useEffect(() => {
    async function loadMediaTypes() {
      const params = new URLSearchParams();
      if (query) {
        params.set("q", query);
      }
      if (ratingFilter !== "all") {
        params.set("rating", ratingFilter);
      }
      if (mediaTypeFilter !== "all") {
        params.set("media_type", mediaTypeFilter);
      }
      const response = await authFetch(`/api/v1/tags/sidebar?${params.toString()}`, { method: "GET" });
      if (!response.ok) {
        setMediaTypes([]);
        return;
      }
      const payload = await response.json();
      setMediaTypes(payload.data.special ?? []);
    }

    loadMediaTypes();
  }, [mediaTypeFilter, query, ratingFilter, user?.can_view_questionable, user?.can_view_explicit, user?.tag_blacklist.join("|")]);

  useEffect(() => {
    if (!isAdmin) {
      setBulkDeleteMode(false);
      setSelectedPostIds([]);
    }
  }, [isAdmin]);

  function toggleSelected(postId: string) {
    setSelectedPostIds((current) =>
      current.includes(postId) ? current.filter((item) => item !== postId) : [...current, postId]
    );
  }

  function updateRoute(nextParams: URLSearchParams) {
    router.push(nextParams.toString() ? `/?${nextParams.toString()}` : "/");
  }

  function applyViewCount(nextCount: number) {
    window.localStorage.setItem("nextboo-view-count", String(nextCount));
    setViewCount(nextCount);
    const params = new URLSearchParams(searchParams.toString());
    params.set("view", String(nextCount));
    params.set("page", "1");
    updateRoute(params);
  }

  function navigatePage(nextPage: number) {
    const params = new URLSearchParams(searchParams.toString());
    if (nextPage <= 1) {
      params.delete("page");
    } else {
      params.set("page", String(nextPage));
    }
    if (!params.get("view")) {
      params.set("view", String(viewCount));
    }
    updateRoute(params);
  }

  async function handleBulkDeleteToggle() {
    if (!bulkDeleteMode) {
      setBulkDeleteMode(true);
      setSelectedPostIds([]);
      return;
    }
    if (!selectedPostIds.length) {
      setBulkDeleteMode(false);
      return;
    }
    if (!window.confirm(`Really removing ${selectedPostIds.length} images?`)) {
      return;
    }
    setBulkDeleting(true);
    const results = await Promise.all(
      selectedPostIds.map((postId) =>
        authFetch(`/api/v1/images/${postId}/delete`, {
          method: "POST"
        })
      )
    );
    setBulkDeleting(false);
    if (results.some((response) => !response.ok)) {
      return;
    }
    setPosts((current) => current.filter((post) => !selectedPostIds.includes(post.id)));
    setCount((current) => Math.max(current - selectedPostIds.length, 0));
    setSelectedPostIds([]);
    setBulkDeleteMode(false);
  }

  const pageNumbers = useMemo(() => {
    const pages = new Set<number>([1, totalPages, page]);
    for (let offset = -2; offset <= 2; offset += 1) {
      const nextPage = page + offset;
      if (nextPage >= 1 && nextPage <= totalPages) {
        pages.add(nextPage);
      }
    }
    return Array.from(pages).sort((a, b) => a - b);
  }, [page, totalPages]);

  function applyRatingFilter(nextRating: "general" | "sensitive" | "questionable" | "explicit" | "all") {
    if (typeof window !== "undefined") {
      if (nextRating === "all") {
        window.localStorage.removeItem(RATING_STORAGE_KEY);
      } else {
        window.localStorage.setItem(RATING_STORAGE_KEY, nextRating);
      }
    }
    const params = new URLSearchParams(searchParams.toString());
    if (nextRating === "all") {
      params.delete("rating");
    } else {
      params.set("rating", nextRating);
    }
    params.delete("page");
    if (!params.get("view")) {
      params.set("view", String(viewCount));
    }
    updateRoute(params);
  }

  function applyMediaTypeFilter(nextMediaType: "all" | "image" | "animated" | "video") {
    if (typeof window !== "undefined") {
      if (nextMediaType === "all") {
        window.localStorage.removeItem(MEDIA_TYPE_STORAGE_KEY);
      } else {
        window.localStorage.setItem(MEDIA_TYPE_STORAGE_KEY, nextMediaType);
      }
    }
    const params = new URLSearchParams(searchParams.toString());
    if (nextMediaType === "all") {
      params.delete("media_type");
    } else {
      params.set("media_type", nextMediaType);
    }
    params.delete("page");
    if (!params.get("view")) {
      params.set("view", String(viewCount));
    }
    updateRoute(params);
  }

  function renderPagination(position: "top" | "bottom") {
    if (totalPages <= 1) {
      return null;
    }
    return (
      <div className={`board-pagination${position === "bottom" ? " board-pagination-bottom" : ""}`}>
        <button className="theme-toggle" disabled={page <= 1} onClick={() => navigatePage(page - 1)} type="button">
          Prev
        </button>
        {pageNumbers.map((pageNumber, index) => {
          const previousPage = pageNumbers[index - 1];
          const showGap = previousPage && pageNumber - previousPage > 1;
          return (
            <span className="page-number-wrap" key={`${position}-${pageNumber}`}>
              {showGap ? <span className="page-gap">...</span> : null}
              <button
                className={pageNumber === page ? "page-number active" : "page-number"}
                onClick={() => navigatePage(pageNumber)}
                type="button"
              >
                {pageNumber}
              </button>
            </span>
          );
        })}
        <button className="theme-toggle" disabled={page >= totalPages} onClick={() => navigatePage(page + 1)} type="button">
          Next
        </button>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="empty-state">
        <strong>Loading posts.</strong>
        <p>Fetching the latest visible images for your current filters.</p>
      </div>
    );
  }

  return (
    <>
      <div className="post-toolbar">
        <div className="pager">
          <a href="/">Index</a>
          {totalPages > 1 ? <span>Page {page} / {totalPages}</span> : null}
        </div>
        <div className="toolbar-meta">
          {query ? `Search: ${query}` : "Latest posts"} | {count} posts
        </div>
        <div className="toolbar-actions">
          <div className="rating-filter-group">
            <span className="rating-filter-label">Rating</span>
            <button
              className={ratingFilter === "all" ? "page-number active" : "page-number"}
              onClick={() => applyRatingFilter("all")}
              type="button"
            >
              All
            </button>
            <button
              className={ratingFilter === "general" ? "page-number active" : "page-number"}
              onClick={() => applyRatingFilter("general")}
              type="button"
            >
              G
            </button>
            <button
              className={ratingFilter === "sensitive" ? "page-number active" : "page-number"}
              onClick={() => applyRatingFilter("sensitive")}
              type="button"
            >
              S
            </button>
            <button
              className={ratingFilter === "questionable" ? "page-number active" : "page-number"}
              onClick={() => applyRatingFilter("questionable")}
              type="button"
            >
              Q
            </button>
            <button
              className={ratingFilter === "explicit" ? "page-number active" : "page-number"}
              onClick={() => applyRatingFilter("explicit")}
              type="button"
            >
              X
            </button>
          </div>
          <div className="rating-filter-group">
            <span className="rating-filter-label">Media Type</span>
            <button
              className={mediaTypeFilter === "all" ? "page-number active" : "page-number"}
              onClick={() => applyMediaTypeFilter("all")}
              type="button"
            >
              All
            </button>
            {mediaTypes.map((mediaType) => (
              <button
                className={mediaTypeFilter === mediaType.name_normalized ? "page-number active" : "page-number"}
                key={mediaType.id}
                onClick={() => applyMediaTypeFilter(mediaType.name_normalized as "image" | "animated" | "video")}
                type="button"
              >
                {mediaType.display_name}
              </button>
            ))}
          </div>
          <label className="view-count-select">
            View
            <select
              onChange={(event) => applyViewCount(Number.parseInt(event.target.value, 10))}
              value={viewCount}
            >
              <option value={25}>25</option>
              <option value={50}>50</option>
              <option value={75}>75</option>
              <option value={100}>100</option>
              <option value={200}>200</option>
            </select>
          </label>
        </div>
        {isAdmin ? (
          <div className="toolbar-actions">
            <button
              className={bulkDeleteMode ? "danger-button compact-danger" : "theme-toggle"}
              disabled={bulkDeleting}
              onClick={handleBulkDeleteToggle}
              type="button"
            >
              {bulkDeleteMode
                ? bulkDeleting
                  ? `Removing ${selectedPostIds.length}...`
                  : `Delete Selected (${selectedPostIds.length})`
                : "Mass Delete"}
            </button>
            {bulkDeleteMode ? (
              <>
                <button
                  className="theme-toggle"
                  onClick={() => setSelectedPostIds(posts.map((post) => post.id))}
                  type="button"
                >
                  Select All On View
                </button>
                <button
                  className="theme-toggle"
                  onClick={() => {
                    setBulkDeleteMode(false);
                    setSelectedPostIds([]);
                  }}
                  type="button"
                >
                  Cancel
                </button>
              </>
            ) : null}
          </div>
        ) : null}
      </div>

      {renderPagination("top")}

      {posts.length ? (
        <div className="thumb-grid">
          {posts.map((post) => (
            <article className={selectedPostIds.includes(post.id) ? "thumb-card selected" : "thumb-card"} key={post.id}>
              <a className="thumb-frame" href={`/posts/${post.id}`}>
                <span className={`rating rating-${ratingCode(post.rating)}`}>{ratingCode(post.rating)}</span>
                {mediaBadge(post) ? <span className="thumb-media-badge">{mediaBadge(post)}</span> : null}
                {post.thumb_url ? (
                  <>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img alt={post.original_filename} className="thumb-image" loading="lazy" src={post.thumb_url} />
                    {post.preview_url ? (
                      <video
                        autoPlay
                        aria-hidden="true"
                        className="thumb-preview"
                        loop
                        muted
                        playsInline
                        preload="none"
                        src={post.preview_url}
                      />
                    ) : null}
                  </>
                ) : (
                  <div className="thumb-art" />
                )}
              </a>
              {isAdmin && bulkDeleteMode ? (
                <label className="thumb-select-toggle">
                  <input
                    checked={selectedPostIds.includes(post.id)}
                    onChange={() => toggleSelected(post.id)}
                    type="checkbox"
                  />
                  <span>Select</span>
                </label>
              ) : null}
              <div className="thumb-caption">
                <div className="thumb-stats">
                  <span>{post.width}x{post.height}</span>
                  {post.duration_seconds ? <span>{Math.round(post.duration_seconds)}s</span> : null}
                  <span>{post.rating}</span>
                </div>
                <p>
                  Uploader:{" "}
                  {post.uploaded_by ? (
                    <a href={`/users/${encodeURIComponent(post.uploaded_by.username)}`}>{post.uploaded_by.username}</a>
                  ) : (
                    "unknown"
                  )}
                </p>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <div className="empty-state">
          <strong>No posts found.</strong>
          <p>
            {query
              ? "The current search returned no matching images."
              : "No processed images are available yet. Upload content to start the gallery."}
          </p>
        </div>
      )}

      {renderPagination("bottom")}
    </>
  );
}
