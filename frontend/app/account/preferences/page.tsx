"use client";

import { AccountPreferencesPanel } from "../../components/account-data";
import { AccountShell } from "../../components/account-shell";

export default function AccountPreferencesPage() {
  return (
    <AccountShell title="Content Preferences" description="Viewer filters, explicit opt-in and your tag blacklist.">
      <AccountPreferencesPanel />
    </AccountShell>
  );
}
