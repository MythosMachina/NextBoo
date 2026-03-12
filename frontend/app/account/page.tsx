"use client";

import { AccountSummaryPanel } from "../components/account-data";
import { AccountShell } from "../components/account-shell";

export default function AccountPage() {
  return (
    <AccountShell title="Summary" description="Core account status, invite chain and strike overview.">
      <AccountSummaryPanel />
    </AccountShell>
  );
}
