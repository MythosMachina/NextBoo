"use client";

import { ReactNode } from "react";
import { useAuthState } from "./auth";

export function ShellAccessGate({ children }: { children: ReactNode }) {
  const { isTosDeactivated, requiresTosAcceptance } = useAuthState();
  if (isTosDeactivated || requiresTosAcceptance) {
    return null;
  }
  return <>{children}</>;
}
