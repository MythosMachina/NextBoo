"use client";

import { AccountSecurityPanel } from "../../components/account-data";
import { AccountShell } from "../../components/account-shell";

export default function AccountSecurityPage() {
  return (
    <AccountShell title="Security" description="Password management for your local account.">
      <AccountSecurityPanel />
    </AccountShell>
  );
}
