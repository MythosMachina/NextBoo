"use client";

import { AccountAccessPanel } from "../../components/account-data";
import { AccountShell } from "../../components/account-shell";

export default function AccountAccessPage() {
  return (
    <AccountShell title="Upload Access" description="Request uploader rights and review the state of your access applications.">
      <AccountAccessPanel />
    </AccountShell>
  );
}
