"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { authFetch } from "./auth";
import { TagSearchActions } from "./tag-search-actions";

type Tag = {
  id: number;
  name_normalized: string;
  display_name: string;
  category: "general" | "character" | "copyright" | "meta" | "artist";
  usage_count: number;
};

type NamespaceKey = "character" | "artist" | "series" | "creature" | "meta" | "general";

type SidebarPayload = {
  special: Tag[];
  limits: Record<string, number>;
  counts?: Partial<Record<NamespaceKey, number>>;
  browser: Record<NamespaceKey, {
    items: Tag[];
    count: number;
    page: number;
    total_pages: number;
  } | null>;
};

type ExplorerState = {
  items: Tag[];
  page: number;
  totalPages: number;
  totalCount: number;
  loading: boolean;
  query: string;
};

const NAMESPACE_CONFIG: Array<{ key: NamespaceKey; title: string }> = [
  { key: "character", title: "Characters" },
  { key: "artist", title: "Artists" },
  { key: "series", title: "Series" },
  { key: "creature", title: "Creatures" },
  { key: "meta", title: "Other Tags" },
  { key: "general", title: "General" },
];

function parseRatingParam(value: string | null): "general" | "sensitive" | "questionable" | "explicit" | "all" {
  if (!value) return "all";
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

function buildScopeParams(viewQuery: string, ratingFilter: string, mediaTypeFilter: string) {
  const params = new URLSearchParams();
  if (viewQuery) {
    params.set("view_q", viewQuery);
    params.set("q", viewQuery);
  }
  if (ratingFilter !== "all") {
    params.set("view_rating", ratingFilter);
    params.set("rating", ratingFilter);
  }
  if (mediaTypeFilter !== "all") {
    params.set("view_media_type", mediaTypeFilter);
    params.set("media_type", mediaTypeFilter);
  }
  return params;
}

function activeFilterLabels(viewQuery: string, ratingFilter: string, mediaTypeFilter: string): string[] {
  const labels: string[] = [];
  if (ratingFilter !== "all") {
    labels.push(`rating:${ratingFilter}`);
  }
  if (mediaTypeFilter !== "all") {
    labels.push(`media:${mediaTypeFilter}`);
  }
  if (viewQuery) {
    labels.push(...viewQuery.split(/\s+/).filter(Boolean));
  }
  return labels;
}

export function SidebarTagPanels() {
  const searchParams = useSearchParams();
  const viewQuery = stripLegacyFilterTokens(searchParams.get("q")?.trim() ?? "");
  const ratingFilter = parseRatingParam(searchParams.get("rating"));
  const mediaTypeFilter = parseMediaTypeParam(searchParams.get("media_type"));
  const [payload, setPayload] = useState<SidebarPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [explorerOpen, setExplorerOpen] = useState(false);
  const [explorerNamespace, setExplorerNamespace] = useState<NamespaceKey>("character");
  const [explorer, setExplorer] = useState<ExplorerState>({
    items: [],
    page: 1,
    totalPages: 1,
    totalCount: 0,
    loading: false,
    query: "",
  });

  useEffect(() => {
    let cancelled = false;

    async function loadSidebar() {
      setLoading(true);
      const params = buildScopeParams(viewQuery, ratingFilter, mediaTypeFilter);
      const response = await authFetch(`/api/v1/tags/sidebar?${params.toString()}`);
      if (!response.ok) {
        if (!cancelled) {
          setPayload(null);
          setLoading(false);
        }
        return;
      }
      const nextPayload = await response.json();
      if (!cancelled) {
        setPayload(nextPayload.data as SidebarPayload);
        setLoading(false);
      }
    }

    loadSidebar();
    return () => {
      cancelled = true;
    };
  }, [mediaTypeFilter, ratingFilter, viewQuery]);

  useEffect(() => {
    if (!explorerOpen) {
      return;
    }
    let cancelled = false;
    const timeout = window.setTimeout(async () => {
      const sectionLimit = explorerNamespace === "general" ? 30 : 20;
      const params = buildScopeParams(viewQuery, ratingFilter, mediaTypeFilter);
      params.set("namespace", explorerNamespace);
      params.set("limit", String(sectionLimit));
      params.set("page", String(explorer.page));
      if (explorer.query.trim()) {
        params.set("q", explorer.query.trim());
      } else {
        params.delete("q");
      }

      setExplorer((current) => ({ ...current, loading: true }));
      const response = await authFetch(`/api/v1/tags/browser?${params.toString()}`);
      if (!response.ok) {
        if (!cancelled) {
          setExplorer((current) => ({ ...current, items: [], totalCount: 0, totalPages: 1, loading: false }));
        }
        return;
      }
      const nextPayload = await response.json();
      if (!cancelled) {
        setExplorer((current) => ({
          ...current,
          items: nextPayload.data,
          totalCount: nextPayload.meta.total_count,
          totalPages: nextPayload.meta.total_pages,
          loading: false,
        }));
      }
    }, 140);

    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
    };
  }, [explorer.page, explorer.query, explorerNamespace, explorerOpen, mediaTypeFilter, ratingFilter, viewQuery]);

  const activeFilters = useMemo(() => activeFilterLabels(viewQuery, ratingFilter, mediaTypeFilter), [mediaTypeFilter, ratingFilter, viewQuery]);
  const suggestedCharacters = payload?.browser.character?.items ?? [];
  const suggestedGeneral = payload?.browser.general?.items ?? [];
  const namespaceCounts = payload?.counts ?? {};

  function openExplorer(namespace: NamespaceKey) {
    setExplorerNamespace(namespace);
    setExplorer((current) => ({
      ...current,
      page: 1,
      query: "",
      items: [],
      totalCount: 0,
      totalPages: 1,
    }));
    setExplorerOpen(true);
  }

  return (
    <>
      <section className="panel tag-explorer-panel">
        <h2>Tag Explorer</h2>

        <div className="tag-explorer-launchers">
          {NAMESPACE_CONFIG.map((namespace) => (
            <button
              className="tag-explorer-launcher"
              key={namespace.key}
              onClick={() => openExplorer(namespace.key)}
              type="button"
            >
              <span>{namespace.title}</span>
              <small>{namespaceCounts[namespace.key] ?? "..."}</small>
            </button>
          ))}
        </div>

        <div className="tag-explorer-active">
          <h3>Active Filters</h3>
          {activeFilters.length ? (
            <div className="active-filter-list">
              {activeFilters.map((filter) => (
                <span className="active-filter-chip" key={filter}>
                  {filter}
                </span>
              ))}
            </div>
          ) : (
            <p>No active filters. Showing the current board view.</p>
          )}
        </div>

        <div className="tag-explorer-suggestions">
          <div className="tag-explorer-suggestion-group">
            <h3>Suggested Characters</h3>
            {loading ? (
              <div className="empty-state compact-empty-state">
                <strong>Loading tags.</strong>
              </div>
            ) : suggestedCharacters.length ? (
              suggestedCharacters.slice(0, 8).map((tag) => (
                <TagSearchActions
                  category={tag.category}
                  displayName={tag.display_name}
                  key={tag.id}
                  tagName={tag.name_normalized}
                  usageCount={tag.usage_count}
                />
              ))
            ) : (
              <div className="empty-state compact-empty-state">
                <strong>No character tags in this view.</strong>
              </div>
            )}
          </div>

          <div className="tag-explorer-suggestion-group">
            <h3>Suggested General Tags</h3>
            {loading ? (
              <div className="empty-state compact-empty-state">
                <strong>Loading tags.</strong>
              </div>
            ) : suggestedGeneral.length ? (
              suggestedGeneral.slice(0, 10).map((tag) => (
                <TagSearchActions
                  category={tag.category}
                  displayName={tag.display_name}
                  key={tag.id}
                  tagName={tag.name_normalized}
                  usageCount={tag.usage_count}
                />
              ))
            ) : (
              <div className="empty-state compact-empty-state">
                <strong>No general tags in this view.</strong>
              </div>
            )}
          </div>
        </div>
      </section>

      {explorerOpen ? (
        <div className="modal-backdrop" onClick={() => setExplorerOpen(false)} role="presentation">
          <section className="modal-panel modal-panel-wide tag-explorer-modal" onClick={(event) => event.stopPropagation()}>
            <h2>Tag Explorer</h2>
            <div className="tag-explorer-modal-toolbar">
              <div className="tag-explorer-modal-tabs">
                {NAMESPACE_CONFIG.map((namespace) => (
                  <button
                    className={explorerNamespace === namespace.key ? "page-number active" : "page-number"}
                    key={namespace.key}
                    onClick={() => {
                      setExplorerNamespace(namespace.key);
                      setExplorer((current) => ({ ...current, page: 1, query: "", items: [] }));
                    }}
                    type="button"
                  >
                    {namespace.title}
                  </button>
                ))}
              </div>
              <button className="theme-toggle" onClick={() => setExplorerOpen(false)} type="button">
                Close
              </button>
            </div>

            <div className="tag-explorer-search-row">
              <input
                aria-label="Search tags in namespace"
                className="tag-explorer-search"
                onChange={(event) =>
                  setExplorer((current) => ({
                    ...current,
                    query: event.target.value,
                    page: 1,
                  }))
                }
                placeholder={`Search ${NAMESPACE_CONFIG.find((item) => item.key === explorerNamespace)?.title.toLowerCase()}`}
                type="search"
                value={explorer.query}
              />
              <span className="tag-explorer-results">
                {explorer.totalCount} tags
              </span>
            </div>

            <div className="tag-explorer-modal-list">
              {explorer.loading ? (
                <div className="empty-state">
                  <strong>Loading tags.</strong>
                  <p>Fetching the current namespace.</p>
                </div>
              ) : explorer.items.length ? (
                explorer.items.map((tag) => (
                  <TagSearchActions
                    category={tag.category}
                    displayName={tag.display_name}
                    key={tag.id}
                    tagName={tag.name_normalized}
                    usageCount={tag.usage_count}
                  />
                ))
              ) : (
                <div className="empty-state">
                  <strong>No matching tags.</strong>
                  <p>Try a broader term or switch the namespace.</p>
                </div>
              )}
            </div>

            <div className="board-pagination board-pagination-bottom">
              <button
                className="theme-toggle"
                disabled={explorer.page <= 1 || explorer.loading}
                onClick={() => setExplorer((current) => ({ ...current, page: current.page - 1 }))}
                type="button"
              >
                Prev
              </button>
              <span className="page-number active">
                {explorer.page} / {explorer.totalPages}
              </span>
              <button
                className="theme-toggle"
                disabled={explorer.page >= explorer.totalPages || explorer.loading}
                onClick={() => setExplorer((current) => ({ ...current, page: current.page + 1 }))}
                type="button"
              >
                Next
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </>
  );
}
