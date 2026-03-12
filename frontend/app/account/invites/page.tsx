"use client";

import { AccountInvitesPanel } from "../../components/account-data";
import { AccountShell } from "../../components/account-shell";

export default function AccountInvitesPage() {
  return (
    <AccountShell title="Invites" description="Manage your invite quota and track who entered through your account.">
      <AccountInvitesPanel />
    </AccountShell>
  );
}
