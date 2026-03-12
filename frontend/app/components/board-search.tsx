"use client";

import { FormEvent, useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { authFetch } from "./auth";

type TagSuggestion = {
  id: number;
  name_normalized: string;
  display_name: string;
  usage_count: number;
};

export function BoardSearch() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [query, setQuery] = useState(searchParams.get("q") ?? "");
  const [suggestions, setSuggestions] = useState<TagSuggestion[]>([]);
  const [focused, setFocused] = useState(false);

  useEffect(() => {
    setQuery(searchParams.get("q") ?? "");
  }, [searchParams]);

  useEffect(() => {
    let cancelled = false;

    async function loadSuggestions() {
      const token = query.split(/\s+/).filter(Boolean).at(-1) ?? "";
      const normalizedToken = token.startsWith("-") ? token.slice(1) : token;
      if (!normalizedToken || normalizedToken.includes(":")) {
        setSuggestions([]);
        return;
      }
      const response = await authFetch(`/api/v1/tags/autocomplete?q=${encodeURIComponent(normalizedToken)}&limit=8`);
      if (!response.ok) {
        if (!cancelled) {
          setSuggestions([]);
        }
        return;
      }
      const payload = await response.json();
      if (!cancelled) {
        setSuggestions(payload.data);
      }
    }

    loadSuggestions();
    return () => {
      cancelled = true;
    };
  }, [query]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextQuery = query.trim();
    const params = new URLSearchParams(searchParams.toString());
    if (nextQuery) {
      params.set("q", nextQuery);
    } else {
      params.delete("q");
    }
    params.delete("page");
    const targetPath = pathname === "/" ? "/" : "/";
    const target = params.toString() ? `${targetPath}?${params.toString()}` : targetPath;
    router.push(target);
  }

  function applySuggestion(tagName: string) {
    const tokens = query.split(/\s+/).filter(Boolean);
    const lastToken = tokens.at(-1) ?? "";
    const prefix = lastToken.startsWith("-") ? "-" : "";
    if (tokens.length) {
      tokens[tokens.length - 1] = `${prefix}${tagName}`;
    } else {
      tokens.push(tagName);
    }
    setQuery(`${tokens.join(" ")} `);
    setSuggestions([]);
  }

  return (
    <form className="search-form" onSubmit={handleSubmit}>
      <div className="search-input-wrap">
        <div className="search-autocomplete">
          <input
            aria-label="Search posts"
            onBlur={() => window.setTimeout(() => setFocused(false), 120)}
            name="q"
            onChange={(event) => setQuery(event.target.value)}
            onFocus={() => setFocused(true)}
            placeholder="Search tags"
            type="search"
            value={query}
          />
          {focused && suggestions.length ? (
            <div className="autocomplete-dropdown">
              {suggestions.map((suggestion) => (
                <button
                  className="autocomplete-item"
                  key={suggestion.id}
                  onMouseDown={(event) => {
                    event.preventDefault();
                    applySuggestion(suggestion.name_normalized);
                    setFocused(true);
                  }}
                  type="button"
                >
                  <span>{suggestion.display_name}</span>
                  <small>{suggestion.usage_count}</small>
                </button>
              ))}
            </div>
          ) : null}
        </div>
        <div className="search-help">
          <button aria-label="Show search syntax help" className="search-help-trigger" type="button">
            ?
          </button>
          <div className="search-help-tooltip" role="tooltip">
            <strong>Search Syntax</strong>
            <span><code>tag</code> include tag</span>
            <span><code>-tag</code> exclude tag</span>
            <span><code>rating:general</code> rating filter</span>
            <span><code>rating:sensitive</code> soft-NSFW filter</span>
            <span><code>sort:recent</code> ordering</span>
          </div>
        </div>
      </div>
      <button type="submit">Search</button>
    </form>
  );
}
