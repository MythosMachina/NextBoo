"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuthState } from "./auth";

const ALLOWED_REVIEW_PATHS = new Set(["/login", "/tos", "/tos/review"]);
const ALLOWED_BACKUP_PATHS = new Set(["/login", "/tos", "/account/backup"]);

export function TosGate() {
  const pathname = usePathname();
  const router = useRouter();
  const { loading, authenticated, user, isTosDeactivated, requiresTosAcceptance } = useAuthState();

  useEffect(() => {
    if (loading || !authenticated || !user) {
      return;
    }
    if (isTosDeactivated) {
      if (!ALLOWED_BACKUP_PATHS.has(pathname)) {
        router.replace("/account/backup");
      }
      return;
    }
    if (requiresTosAcceptance) {
      if (!ALLOWED_REVIEW_PATHS.has(pathname)) {
        router.replace("/tos/review");
      }
      return;
    }
    if (pathname === "/tos/review") {
      router.replace(user.role === "admin" || user.role === "moderator" ? "/admin" : "/account");
    }
  }, [authenticated, isTosDeactivated, loading, pathname, requiresTosAcceptance, router, user]);

  return null;
}
