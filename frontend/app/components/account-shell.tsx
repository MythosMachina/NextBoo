"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect } from "react";
import { fetchCurrentUser, storeUser, useAuthState } from "./auth";

type AccountShellProps = {
  children: ReactNode;
  title: string;
  description: string;
};

function AccountMenuLink({ href, label }: { href: string; label: string }) {
  const pathname = usePathname();
  const isActive = pathname === href;

  return (
    <Link className={isActive ? "admin-menu-link active" : "admin-menu-link"} href={href}>
      {label}
    </Link>
  );
}

export function AccountShell({ children, title, description }: AccountShellProps) {
  const router = useRouter();
  const { authenticated, loading, setSession, user } = useAuthState();

  useEffect(() => {
    async function resolveSession() {
      if (authenticated && user) {
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
    }

    resolveSession();
  }, [authenticated, router, setSession, user]);

  if (loading) {
    return (
      <section className="panel">
        <h2>Account</h2>
        <div className="empty-state">
          <strong>Loading account.</strong>
          <p>Checking your session.</p>
        </div>
      </section>
    );
  }

  if (!user) {
    return (
      <section className="panel">
        <h2>Account</h2>
        <div className="empty-state">
          <strong>Login required.</strong>
          <p>Sign in to access your account area.</p>
        </div>
      </section>
    );
  }

  return (
    <div className="admin-layout">
      <aside className="admin-sidebar">
        <section className="panel">
          <h2>Account</h2>
          <div className="admin-menu-group">
            <h3>Overview</h3>
            <div className="admin-menu-list">
              <AccountMenuLink href="/account" label="Summary" />
            </div>
          </div>
          <div className="admin-menu-group">
            <h3>Preferences</h3>
            <div className="admin-menu-list">
              <AccountMenuLink href="/account/preferences" label="Content" />
              <AccountMenuLink href="/account/security" label="Security" />
            </div>
          </div>
          <div className="admin-menu-group">
            <h3>Activity</h3>
            <div className="admin-menu-list">
              <AccountMenuLink href="/account/invites" label="Invites" />
              <AccountMenuLink href="/account/access" label="Upload Access" />
              <AccountMenuLink href="/account/uploads" label="My Uploads" />
            </div>
          </div>
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
