"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { MouseEvent } from "react";
import { TagLink } from "./tag-link";

type TagSearchActionsProps = {
  category: "general" | "character" | "copyright" | "meta" | "artist";
  displayName: string;
  tagName: string;
  usageCount: number;
};

function mergeTokenList(currentQuery: string, tagName: string, mode: "include" | "exclude"): string {
  const includeToken = tagName;
  const excludeToken = `-${tagName}`;
  const tokens = currentQuery
    .split(/\s+/)
    .map((token) => token.trim())
    .filter(Boolean)
    .filter((token) => token !== includeToken && token !== excludeToken);

  tokens.push(mode === "include" ? includeToken : excludeToken);
  return tokens.join(" ");
}

export function TagSearchActions({ category, displayName, tagName, usageCount }: TagSearchActionsProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  function pushQuery(nextQuery: string) {
    const params = new URLSearchParams(searchParams.toString());
    if (nextQuery) {
      params.set("q", nextQuery);
    } else {
      params.delete("q");
    }
    params.delete("page");
    const targetPath = pathname === "/" ? "/" : "/";
    router.push(params.toString() ? `${targetPath}?${params.toString()}` : targetPath);
  }

  function handleMode(mode: "include" | "exclude") {
    const currentQuery = searchParams.get("q") ?? "";
    pushQuery(mergeTokenList(currentQuery, tagName, mode));
  }

  function stopAnchorJump(event: MouseEvent<HTMLButtonElement>) {
    event.preventDefault();
    event.stopPropagation();
  }

  return (
    <div className="tag-search-row">
      <button
        aria-label={`Include ${displayName}`}
        className="tag-search-toggle include"
        onClick={(event) => {
          stopAnchorJump(event);
          handleMode("include");
        }}
        title={`Include ${displayName}`}
        type="button"
      >
        +
      </button>
      <button
        aria-label={`Exclude ${displayName}`}
        className="tag-search-toggle exclude"
        onClick={(event) => {
          stopAnchorJump(event);
          handleMode("exclude");
        }}
        title={`Exclude ${displayName}`}
        type="button"
      >
        -
      </button>
      <TagLink
        className={`tag tag-${category} tag-search-link`}
        href={`/?q=${encodeURIComponent(tagName)}`}
        tagName={tagName}
      >
        {displayName} <span className="tag-usage-count">({usageCount})</span>
      </TagLink>
    </div>
  );
}
