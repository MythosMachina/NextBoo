"use client";

import Link from "next/link";
import { useAuthState } from "./auth";

export function HeaderNav() {
  const { authenticated, canUpload, isTosDeactivated, requiresTosAcceptance } = useAuthState();
  if (authenticated && (isTosDeactivated || requiresTosAcceptance)) {
    return null;
  }

  return (
    <nav className="board-nav" aria-label="Primary">
      <Link href="/">Posts</Link>
      {authenticated && canUpload ? <Link href="/upload">Upload</Link> : null}
      <Link href={authenticated ? (isTosDeactivated ? "/account/backup" : "/account") : "/login"}>Account</Link>
    </nav>
  );
}

export function SidebarNav() {
  const { authenticated, canUpload, isTosDeactivated, requiresTosAcceptance } = useAuthState();
  if (authenticated && (isTosDeactivated || requiresTosAcceptance)) {
    return null;
  }

  return (
    <ul className="link-list">
      <li><Link href="/">Posts</Link></li>
      {authenticated && canUpload ? <li><Link href="/upload">Upload</Link></li> : null}
      {authenticated ? <li><Link href={isTosDeactivated ? "/account/backup" : "/account"}>Settings</Link></li> : <li><Link href="/login">Login</Link></li>}
    </ul>
  );
}
