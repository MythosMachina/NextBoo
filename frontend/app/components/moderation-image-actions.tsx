"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { authFetch } from "./auth";

type EditableTag = {
  name_normalized: string;
  display_name: string;
  category: "general" | "character" | "copyright" | "meta" | "artist";
  source: "auto" | "user" | "system";
  confidence: number | null;
};

type TagSuggestion = {
  id: number;
  name_normalized: string;
  display_name: string;
  category: "general" | "character" | "copyright" | "meta" | "artist";
  usage_count: number;
};

type ModerationImageActionsProps = {
  imageId: string;
  rating: "general" | "sensitive" | "questionable" | "explicit";
  visibilityStatus: "visible" | "hidden" | "deleted";
  tags: EditableTag[];
  onUpdated: () => void | Promise<void>;
};

export function ModerationImageActions({
  imageId,
  rating,
  visibilityStatus,
  tags,
  onUpdated
}: ModerationImageActionsProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [addTagQuery, setAddTagQuery] = useState("");
  const [addSuggestions, setAddSuggestions] = useState<TagSuggestion[]>([]);
  const [focusedAdd, setFocusedAdd] = useState(false);
  const [pendingAddTags, setPendingAddTags] = useState<string[]>([]);
  const [selectedForRemoval, setSelectedForRemoval] = useState<string[]>([]);
  const [sourceFilter, setSourceFilter] = useState<"all" | "auto" | "user" | "system">("all");
  const [categoryFilter, setCategoryFilter] = useState<"all" | EditableTag["category"]>("all");
  const [moderationRating, setModerationRating] = useState(rating);
  const [moderationVisibility, setModerationVisibility] = useState(visibilityStatus);
  const [saving, setSaving] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const sortedTags = useMemo(
    () =>
      [...tags].sort((left, right) => {
        if (left.category !== right.category) {
          return left.category.localeCompare(right.category);
        }
        if (left.source !== right.source) {
          return left.source.localeCompare(right.source);
        }
        return left.display_name.localeCompare(right.display_name);
      }),
    [tags]
  );

  const visibleTags = useMemo(() => {
    const normalizedQuery = searchQuery.trim().toLowerCase();
    return sortedTags.filter((tag) => {
      if (sourceFilter !== "all" && tag.source !== sourceFilter) {
        return false;
      }
      if (categoryFilter !== "all" && tag.category !== categoryFilter) {
        return false;
      }
      if (!normalizedQuery) {
        return true;
      }
      return (
        tag.name_normalized.toLowerCase().includes(normalizedQuery) ||
        tag.display_name.toLowerCase().includes(normalizedQuery)
      );
    });
  }, [categoryFilter, searchQuery, sortedTags, sourceFilter]);

  useEffect(() => {
    let cancelled = false;

    async function loadSuggestions() {
      const normalized = addTagQuery.trim().toLowerCase();
      if (!normalized) {
        setAddSuggestions([]);
        return;
      }
      const response = await authFetch(`/api/v1/tags/autocomplete?q=${encodeURIComponent(normalized)}&limit=10`);
      if (!response.ok) {
        if (!cancelled) {
          setAddSuggestions([]);
        }
        return;
      }
      const payload = await response.json();
      if (!cancelled) {
        setAddSuggestions(payload.data ?? []);
      }
    }

    loadSuggestions();
    return () => {
      cancelled = true;
    };
  }, [addTagQuery]);

  function toggleRemoveTag(tagName: string) {
    setSelectedForRemoval((current) =>
      current.includes(tagName) ? current.filter((item) => item !== tagName) : [...current, tagName]
    );
  }

  function queueAddTag(tagName: string) {
    if (tags.some((item) => item.name_normalized === tagName) || pendingAddTags.includes(tagName)) {
      setAddTagQuery("");
      setAddSuggestions([]);
      return;
    }
    setPendingAddTags((current) => [...current, tagName]);
    setAddTagQuery("");
    setAddSuggestions([]);
  }

  function removePendingAddTag(tagName: string) {
    setPendingAddTags((current) => current.filter((item) => item !== tagName));
  }

  async function sendJson(path: string, method: string, body?: object) {
    setSaving(true);
    setStatusMessage(null);
    setErrorMessage(null);
    const response = await authFetch(path, {
      method,
      headers: {
        "Content-Type": "application/json"
      },
      body: body ? JSON.stringify(body) : undefined
    });
    setSaving(false);
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      setErrorMessage(payload?.detail ?? "Action failed.");
      return false;
    }
    return true;
  }

  async function handleTagSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!pendingAddTags.length && !selectedForRemoval.length) {
      setStatusMessage("No tag changes queued.");
      setErrorMessage(null);
      return;
    }
    const ok = await sendJson(`/api/v1/images/${imageId}/metadata`, "PATCH", {
      add_tag_names: pendingAddTags,
      remove_tag_names: selectedForRemoval
    });
    if (ok) {
      setStatusMessage("Tags updated.");
      setAddTagQuery("");
      setPendingAddTags([]);
      setSelectedForRemoval([]);
      await onUpdated();
    }
  }

  async function handleModerationSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const ratingOk = await sendJson(`/api/v1/images/${imageId}/metadata`, "PATCH", {
      rating: moderationRating
    });
    if (!ratingOk) {
      return;
    }
    const visibilityOk = await sendJson(`/api/v1/images/${imageId}/visibility`, "PATCH", {
      visibility_status: moderationVisibility,
      reason: "moderation_panel"
    });
    if (visibilityOk) {
      setStatusMessage("Moderation state updated.");
      await onUpdated();
    }
  }

  async function handleDelete() {
    const ok = await sendJson(`/api/v1/images/${imageId}/delete`, "POST");
    if (ok) {
      setStatusMessage("Post deleted.");
      await onUpdated();
    }
  }

  return (
    <>
      <section className="panel">
        <h2>Tag Editing</h2>
        <form className="stack-form" onSubmit={handleTagSave}>
          <div className="moderation-tag-toolbar">
            <label>
              Search current tags
              <input
                className="stack-input"
                onChange={(event) => setSearchQuery(event.target.value)}
                placeholder="Filter current tags"
                type="search"
                value={searchQuery}
              />
            </label>
            <label>
              Source
              <select
                className="stack-select"
                onChange={(event) => setSourceFilter(event.target.value as "all" | "auto" | "user" | "system")}
                value={sourceFilter}
              >
                <option value="all">all</option>
                <option value="auto">auto</option>
                <option value="user">manual</option>
                <option value="system">system</option>
              </select>
            </label>
            <label>
              Category
              <select
                className="stack-select"
                onChange={(event) => setCategoryFilter(event.target.value as "all" | EditableTag["category"])}
                value={categoryFilter}
              >
                <option value="all">all</option>
                <option value="character">character</option>
                <option value="artist">artist</option>
                <option value="copyright">series</option>
                <option value="meta">meta</option>
                <option value="general">general</option>
              </select>
            </label>
          </div>
          <label>
            Add tags
            <div className="search-autocomplete moderation-tag-add">
              <input
                className="stack-input"
                onBlur={() => window.setTimeout(() => setFocusedAdd(false), 120)}
                onChange={(event) => setAddTagQuery(event.target.value)}
                onFocus={() => setFocusedAdd(true)}
                placeholder="Search and add tags"
                type="search"
                value={addTagQuery}
              />
              {focusedAdd && addSuggestions.length ? (
                <div className="autocomplete-dropdown">
                  {addSuggestions.map((suggestion) => (
                    <button
                      className="autocomplete-item"
                      key={suggestion.id}
                      onMouseDown={(event) => {
                        event.preventDefault();
                        queueAddTag(suggestion.name_normalized);
                        setFocusedAdd(true);
                      }}
                      type="button"
                    >
                      <span>{suggestion.display_name}</span>
                      <small>
                        {suggestion.category} · {suggestion.usage_count}
                      </small>
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
          </label>
          {pendingAddTags.length ? (
            <div className="tag-edit-list">
              <strong>Queued additions</strong>
              <div className="tag-edit-grid">
                {pendingAddTags.map((tagName) => (
                  <button
                    className="tag-edit-chip is-adding"
                    key={tagName}
                    onClick={() => removePendingAddTag(tagName)}
                    type="button"
                  >
                    Remove add: {tagName}
                  </button>
                ))}
              </div>
            </div>
          ) : null}
          <div className="tag-edit-list">
            <strong>
              Existing tags
              <span className="muted-inline"> · showing {visibleTags.length} of {tags.length}</span>
            </strong>
            <div className="tag-edit-grid">
              {visibleTags.length ? (
                visibleTags.map((tag) => {
                  const tagName = tag.name_normalized;
                  const removing = selectedForRemoval.includes(tagName);
                  return (
                    <button
                      className={`tag-edit-chip${removing ? " is-removing" : ""}`}
                      key={tagName}
                      onClick={() => toggleRemoveTag(tagName)}
                      type="button"
                    >
                      <span>{removing ? "Undo remove: " : "Remove: "}{tag.display_name}</span>
                      <small>
                        {tag.category} · {tag.source}
                        {tag.confidence !== null ? ` · ${(tag.confidence * 100).toFixed(0)}%` : ""}
                      </small>
                    </button>
                  );
                })
              ) : (
                <span className="muted-inline">No tags match the current filter.</span>
              )}
            </div>
          </div>
          <button className="primary-button" disabled={saving} type="submit">
            Save tags
          </button>
        </form>
      </section>

      <section className="panel">
        <h2>Moderation</h2>
        <form className="stack-form" onSubmit={handleModerationSave}>
          <label>
            Rating
            <select
              className="stack-select"
              onChange={(event) => setModerationRating(event.target.value as ModerationImageActionsProps["rating"])}
              value={moderationRating}
            >
              <option value="general">general</option>
              <option value="sensitive">sensitive</option>
              <option value="questionable">questionable</option>
              <option value="explicit">explicit</option>
            </select>
          </label>
          <label>
            Visibility
            <select
              className="stack-select"
              onChange={(event) =>
                setModerationVisibility(event.target.value as ModerationImageActionsProps["visibilityStatus"])
              }
              value={moderationVisibility}
            >
              <option value="visible">visible</option>
              <option value="hidden">hidden</option>
            </select>
          </label>
          <button className="primary-button" disabled={saving} type="submit">
            Save moderation
          </button>
        </form>
        <button className="danger-button" disabled={saving} onClick={handleDelete} type="button">
          Delete post
        </button>
      </section>

      {statusMessage ? <p className="form-success">{statusMessage}</p> : null}
      {errorMessage ? <p className="form-error">{errorMessage}</p> : null}
    </>
  );
}
