"use client";

import { FormEvent, useState } from "react";
import { authFetch } from "./auth";

type ModerationImageActionsProps = {
  imageId: string;
  rating: "general" | "sensitive" | "questionable" | "explicit";
  visibilityStatus: "visible" | "hidden" | "deleted";
  tagNames: string[];
  onUpdated: () => void | Promise<void>;
};

export function ModerationImageActions({
  imageId,
  rating,
  visibilityStatus,
  tagNames,
  onUpdated
}: ModerationImageActionsProps) {
  const [addTags, setAddTags] = useState("");
  const [selectedForRemoval, setSelectedForRemoval] = useState<string[]>([]);
  const [moderationRating, setModerationRating] = useState(rating);
  const [moderationVisibility, setModerationVisibility] = useState(visibilityStatus);
  const [saving, setSaving] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  function parseCommaSeparatedTags(value: string) {
    return value
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function toggleRemoveTag(tagName: string) {
    setSelectedForRemoval((current) =>
      current.includes(tagName) ? current.filter((item) => item !== tagName) : [...current, tagName]
    );
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
    const addTagNames = parseCommaSeparatedTags(addTags);
    if (!addTagNames.length && !selectedForRemoval.length) {
      setStatusMessage("No tag changes queued.");
      setErrorMessage(null);
      return;
    }
    const ok = await sendJson(`/api/v1/images/${imageId}/metadata`, "PATCH", {
      add_tag_names: addTagNames,
      remove_tag_names: selectedForRemoval
    });
    if (ok) {
      setStatusMessage("Tags updated.");
      setAddTags("");
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
          <label>
            Add tags
            <textarea
              className="stack-textarea"
              onChange={(event) => setAddTags(event.target.value)}
              placeholder="tag_one, tag_two, character_name_(series)"
              rows={4}
              value={addTags}
            />
          </label>
          <div className="tag-edit-list">
            <strong>Existing tags</strong>
            <div className="tag-edit-grid">
              {tagNames.length ? (
                tagNames.map((tagName) => {
                  const removing = selectedForRemoval.includes(tagName);
                  return (
                    <button
                      className={`tag-edit-chip${removing ? " is-removing" : ""}`}
                      key={tagName}
                      onClick={() => toggleRemoveTag(tagName)}
                      type="button"
                    >
                      {removing ? "Undo remove: " : "Remove: "}
                      {tagName}
                    </button>
                  );
                })
              ) : (
                <span className="muted-inline">No tags on this post.</span>
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
