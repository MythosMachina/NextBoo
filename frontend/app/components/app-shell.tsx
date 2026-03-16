import type { ReactNode } from "react";
import { Suspense } from "react";
import Link from "next/link";
import { AuthStatus } from "./auth-status";
import { BoardSearch } from "./board-search";
import { HeaderNav } from "./shell-nav";
import { ShellAccessGate } from "./shell-access-gate";
import { SidebarTagPanels } from "./sidebar-tag-panels";
import { ThemeToggle } from "./theme-toggle";

export async function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="board-shell">
      <header className="board-header">
        <div className="board-title-row">
          <div>
            <Link className="board-title" href="/">
              NextBoo
            </Link>
            <p className="board-subtitle">Like Booru. Reimagined.</p>
          </div>
          <div className="board-header-actions">
            <HeaderNav />
            <AuthStatus />
            <ThemeToggle />
          </div>
        </div>

        <ShellAccessGate>
          <Suspense
            fallback={
              <form action="/" className="search-form">
                <div className="search-input-wrap">
                  <input aria-label="Search posts" name="q" placeholder="Search tags" type="search" />
                  <div className="search-help">
                    <button aria-label="Show search syntax help" className="search-help-trigger" type="button">
                      ?
                    </button>
                  </div>
                </div>
                <button type="submit">Search</button>
              </form>
            }
          >
            <BoardSearch />
          </Suspense>
        </ShellAccessGate>
      </header>

      <div className="board-main">
        <ShellAccessGate>
          <aside className="left-column">
            <Suspense
              fallback={
                <section className="panel">
                  <h2>Tag Browser</h2>
                  <div className="tag-browser-groups">
                    <div className="empty-state compact-empty-state">
                      <strong>Loading tags.</strong>
                    </div>
                  </div>
                </section>
              }
            >
              <SidebarTagPanels />
            </Suspense>
          </aside>
        </ShellAccessGate>

        <section className="center-column board-content">{children}</section>
      </div>
    </div>
  );
}
