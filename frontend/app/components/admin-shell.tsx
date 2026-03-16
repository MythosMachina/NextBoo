"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect } from "react";
import { fetchCurrentUser, storeUser, useAuthState } from "./auth";

type AdminShellProps = {
  children: ReactNode;
  title: string;
  description: string;
};

function AdminMenuLink({ href, label }: { href: string; label: string }) {
  const pathname = usePathname();
  const isActive = pathname === href;

  return (
    <Link className={isActive ? "admin-menu-link active" : "admin-menu-link"} href={href}>
      {label}
    </Link>
  );
}

export function AdminShell({ children, title, description }: AdminShellProps) {
  const router = useRouter();
  const { authenticated, isAdmin, isModerator, loading, setSession, user } = useAuthState();

  useEffect(() => {
    async function resolveSession() {
      if (isAdmin || isModerator) {
        return;
      }

      const nextUser = await fetchCurrentUser();
      if (!nextUser) {
        setSession(null);
        router.replace("/login");
        return;
      }

      storeUser(nextUser);
      setSession(nextUser);

      if (nextUser.role !== "admin" && nextUser.role !== "moderator") {
        router.replace("/");
      }
    }

    resolveSession();
  }, [authenticated, isAdmin, isModerator, router, setSession]);

  if (loading) {
    return (
      <section className="panel">
        <h2>Admin</h2>
        <div className="empty-state">
          <strong>Loading admin session.</strong>
          <p>Checking permissions.</p>
        </div>
      </section>
    );
  }

  if (!user || (user.role !== "admin" && user.role !== "moderator")) {
    return (
      <section className="panel">
        <h2>Moderation</h2>
        <div className="empty-state">
          <strong>Access denied.</strong>
          <p>This section is only available to moderators and administrators.</p>
        </div>
      </section>
    );
  }

  return (
    <div className="admin-layout">
      <aside className="admin-sidebar">
        <section className="panel">
          <h2>{user.role === "admin" ? "Admin" : "Moderation"}</h2>
          <div className="admin-menu-group">
            <h3>Overview</h3>
            <div className="admin-menu-list">
              <AdminMenuLink href="/admin" label="Dashboard" />
            </div>
          </div>
          <div className="admin-menu-group">
            <h3>Moderation</h3>
            <div className="admin-menu-list">
              <AdminMenuLink href="/admin/reports" label="Reports" />
              <AdminMenuLink href="/admin/content" label="Content" />
              <AdminMenuLink href="/admin/comments" label="Comments" />
              <AdminMenuLink href="/admin/near-duplicates" label="Near Duplicates" />
              <AdminMenuLink href="/admin/tags" label="Tags" />
              <AdminMenuLink href="/admin/danger-tags" label="Danger Tags" />
              <AdminMenuLink href="/admin/rating-rules" label="Rating Rules" />
              <AdminMenuLink href="/admin/strikes" label="Strikes" />
            </div>
          </div>
          <div className="admin-menu-group">
            <h3>Operations</h3>
            <div className="admin-menu-list">
              <AdminMenuLink href="/admin/jobs" label="Jobs" />
              <AdminMenuLink href="/admin/imports" label="Imports" />
              <AdminMenuLink href="/admin/board-imports" label="Board Importer" />
              <AdminMenuLink href="/admin/worker-scaling" label="Worker Scaling" />
              <AdminMenuLink href="/admin/tagger-settings" label="Tagger Maintenance" />
              <AdminMenuLink href="/admin/sidebar-settings" label="Sidebar Settings" />
              <AdminMenuLink href="/admin/rate-limits" label="Rate Limits" />
              {user.role === "admin" ? <AdminMenuLink href="/admin/tos" label="Terms of Service" /> : null}
            </div>
          </div>
          {user.role === "admin" ? (
          <div className="admin-menu-group">
            <h3>Accounts</h3>
            <div className="admin-menu-list">
              <AdminMenuLink href="/admin/users" label="Users" />
              <AdminMenuLink href="/admin/upload-requests" label="Upload Requests" />
              <AdminMenuLink href="/admin/upload-audit" label="Upload Audit" />
            </div>
          </div>
          ) : null}
        </section>
      </aside>

      <section className="admin-main">
        <section className="panel admin-heading">
          <h2>{title}</h2>
          <div className="admin-heading-body">
            <p>{description}</p>
          </div>
        </section>
        {children}
      </section>
    </div>
  );
}
