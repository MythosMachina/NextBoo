"use client";

import { ReactNode, useEffect, useState } from "react";
import { authFetch, storeUser, useAuthState } from "./auth";

type MenuState = {
  x: number;
  y: number;
  tagName: string;
} | null;

let openTagMenu: ((x: number, y: number, tagName: string) => void) | null = null;

export function showTagContextMenu(x: number, y: number, tagName: string) {
  openTagMenu?.(x, y, tagName);
}

export function TagContextMenuProvider({ children }: { children: ReactNode }) {
  const { authenticated, setSession, user } = useAuthState();
  const [menu, setMenu] = useState<MenuState>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    openTagMenu = (x, y, tagName) => setMenu({ x, y, tagName });
    return () => {
      openTagMenu = null;
    };
  }, []);

  useEffect(() => {
    function close() {
      setMenu(null);
    }
    window.addEventListener("click", close);
    window.addEventListener("scroll", close, true);
    return () => {
      window.removeEventListener("click", close);
      window.removeEventListener("scroll", close, true);
    };
  }, []);

  async function updateBlacklist(nextList: string[]) {
    if (!authenticated || !user) {
      setMenu(null);
      return;
    }
    setSaving(true);
    const response = await authFetch("/api/v1/users/me", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        can_view_explicit: user.can_view_explicit,
        tag_blacklist: nextList
      })
    });
    setSaving(false);
    if (!response.ok) {
      setMenu(null);
      return;
    }
    const payload = await response.json();
    storeUser(payload.data);
    setSession(payload.data);
    setMenu(null);
  }

  const currentBlacklist = user?.tag_blacklist ?? [];
  const currentTag = menu?.tagName ?? "";
  const isBlacklisted = currentBlacklist.includes(currentTag);

  return (
    <>
      {children}
      {menu && authenticated ? (
        <div className="tag-context-menu" style={{ left: menu.x, top: menu.y }}>
          <button
            className="tag-context-button"
            disabled={saving}
            onClick={() =>
              updateBlacklist(
                isBlacklisted
                  ? currentBlacklist.filter((item) => item !== currentTag)
                  : [...currentBlacklist, currentTag]
              )
            }
            type="button"
          >
            {isBlacklisted ? "Remove from blacklist" : "Add to blacklist"}
          </button>
          <a className="tag-context-button" href={`/account`}>
            Open account settings
          </a>
        </div>
      ) : null}
    </>
  );
}

