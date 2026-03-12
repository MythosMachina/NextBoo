"use client";

import { useEffect, useState } from "react";
import { authFetch, fetchCurrentUser, storeUser, useAuthState } from "./auth";

type UploadRequestItem = {
  id: number;
  content_focus: string;
  reason: string;
  status: "pending" | "approved" | "rejected";
  review_note: string | null;
  created_at: string;
};

type InviteItem = {
  id: number;
  code: string;
  email: string;
  note: string | null;
  status: "pending" | "accepted" | "revoked";
  invited_username: string | null;
  created_at: string;
  accepted_at: string | null;
  revoked_at: string | null;
  rehabilitated_at: string | null;
};

export function useAccountData() {
  const { user, setSession } = useAuthState();
  const [canViewQuestionable, setCanViewQuestionable] = useState(true);
  const [canViewExplicit, setCanViewExplicit] = useState(false);
  const [tagBlacklist, setTagBlacklist] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [passwordForm, setPasswordForm] = useState({
    currentPassword: "",
    newPassword: "",
    confirmPassword: ""
  });
  const [passwordSaving, setPasswordSaving] = useState(false);
  const [passwordMessage, setPasswordMessage] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [requestForm, setRequestForm] = useState({ contentFocus: "", reason: "" });
  const [requestState, setRequestState] = useState<{ loading: boolean; saving: boolean; items: UploadRequestItem[]; error: string | null }>({
    loading: true,
    saving: false,
    items: [],
    error: null
  });
  const [inviteForm, setInviteForm] = useState({ email: "", note: "" });
  const [inviteState, setInviteState] = useState<{
    loading: boolean;
    saving: boolean;
    quota: number;
    used: number;
    remaining: number;
    invited_by_username: string | null;
    items: InviteItem[];
    error: string | null;
  }>({
    loading: true,
    saving: false,
    quota: 0,
    used: 0,
    remaining: 0,
    invited_by_username: null,
    items: [],
    error: null
  });

  useEffect(() => {
    if (user) {
      setCanViewQuestionable(user.can_view_questionable);
      setCanViewExplicit(user.can_view_explicit);
      setTagBlacklist(user.tag_blacklist.join("\n"));
      return;
    }

    async function loadUser() {
      const nextUser = await fetchCurrentUser();
      if (!nextUser) {
        return;
      }
      storeUser(nextUser);
      setSession(nextUser);
      setCanViewQuestionable(nextUser.can_view_questionable);
      setCanViewExplicit(nextUser.can_view_explicit);
      setTagBlacklist(nextUser.tag_blacklist.join("\n"));
    }

    loadUser();
  }, [setSession, user]);

  useEffect(() => {
    async function loadInvites() {
      if (!user) {
        return;
      }
      const response = await authFetch("/api/v1/invites/me");
      if (!response.ok) {
        setInviteState((current) => ({ ...current, loading: false, error: "Failed to load invites." }));
        return;
      }
      const payload = await response.json();
      setInviteState({
        loading: false,
        saving: false,
        quota: payload.data.quota,
        used: payload.data.used,
        remaining: payload.data.remaining,
        invited_by_username: payload.data.invited_by_username,
        items: payload.data.invites,
        error: null
      });
    }

    loadInvites();
  }, [user]);

  useEffect(() => {
    async function loadRequests() {
      if (!user || user.can_upload || user.role === "admin" || user.role === "moderator") {
        setRequestState((current) => ({ ...current, loading: false }));
        return;
      }
      const response = await authFetch("/api/v1/upload-requests/me");
      if (!response.ok) {
        setRequestState({ loading: false, saving: false, items: [], error: "Failed to load upload request status." });
        return;
      }
      const payload = await response.json();
      setRequestState({ loading: false, saving: false, items: payload.data, error: null });
    }

    loadRequests();
  }, [user]);

  async function refreshInvites() {
    const response = await authFetch("/api/v1/invites/me");
    if (!response.ok) {
      return;
    }
    const payload = await response.json();
    setInviteState({
      loading: false,
      saving: false,
      quota: payload.data.quota,
      used: payload.data.used,
      remaining: payload.data.remaining,
      invited_by_username: payload.data.invited_by_username,
      items: payload.data.invites,
      error: null
    });
  }

  async function savePreferences(nextQuestionable: boolean, nextExplicit: boolean, nextBlacklist: string) {
    setSaving(true);
    setError(null);
    setMessage(null);
    const response = await authFetch("/api/v1/users/me", {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        can_view_questionable: nextQuestionable,
        can_view_explicit: nextExplicit,
        tag_blacklist: nextBlacklist.split("\n").map((item) => item.trim()).filter(Boolean)
      })
    });

    if (!response.ok) {
      setSaving(false);
      setError("Failed to save account settings.");
      return;
    }

    const payload = await response.json();
    storeUser(payload.data);
    setSession(payload.data);
    setCanViewQuestionable(payload.data.can_view_questionable);
    setCanViewExplicit(payload.data.can_view_explicit);
    setTagBlacklist(payload.data.tag_blacklist.join("\n"));
    setSaving(false);
    setMessage("Settings saved.");
  }

  async function handleQuestionableToggle(nextValue: boolean) {
    await savePreferences(nextValue, canViewExplicit, tagBlacklist);
  }

  async function handleExplicitToggle(nextValue: boolean) {
    await savePreferences(canViewQuestionable, nextValue, tagBlacklist);
  }

  async function handleBlacklistSave() {
    await savePreferences(canViewQuestionable, canViewExplicit, tagBlacklist);
  }

  async function handlePasswordChange(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (passwordForm.newPassword !== passwordForm.confirmPassword) {
      setPasswordError("New passwords do not match.");
      return;
    }

    setPasswordSaving(true);
    setPasswordError(null);
    setPasswordMessage(null);

    const response = await authFetch("/api/v1/users/me/password", {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        current_password: passwordForm.currentPassword,
        new_password: passwordForm.newPassword
      })
    });

    if (!response.ok) {
      let detail = "Failed to change password.";
      try {
        const payload = await response.json();
        detail = payload.detail ?? detail;
      } catch {}
      setPasswordSaving(false);
      setPasswordError(detail);
      return;
    }

    setPasswordForm({ currentPassword: "", newPassword: "", confirmPassword: "" });
    setPasswordSaving(false);
    setPasswordMessage("Password updated.");
  }

  async function handleUploadRequestSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setRequestState((current) => ({ ...current, saving: true, error: null }));
    const response = await authFetch("/api/v1/upload-requests/me", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        content_focus: requestForm.contentFocus,
        reason: requestForm.reason
      })
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      setRequestState((current) => ({
        ...current,
        saving: false,
        error: payload?.detail ?? "Failed to submit request."
      }));
      return;
    }
    const refreshResponse = await authFetch("/api/v1/upload-requests/me");
    const refreshPayload = refreshResponse.ok ? await refreshResponse.json() : { data: [] };
    setRequestForm({ contentFocus: "", reason: "" });
    setRequestState({ loading: false, saving: false, items: refreshPayload.data, error: null });
  }

  async function handleInviteSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setInviteState((current) => ({ ...current, saving: true, error: null }));
    const response = await authFetch("/api/v1/invites/me", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(inviteForm)
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      setInviteState((current) => ({
        ...current,
        saving: false,
        error: payload?.detail ?? "Failed to create invite."
      }));
      return;
    }
    setInviteForm({ email: "", note: "" });
    await refreshInvites();
  }

  async function deletePendingInvite(inviteId: number) {
    if (!window.confirm("Delete this pending invite?")) {
      return;
    }
    setInviteState((current) => ({ ...current, saving: true, error: null }));
    const response = await authFetch(`/api/v1/invites/me/${inviteId}`, { method: "DELETE" });
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      setInviteState((current) => ({
        ...current,
        saving: false,
        error: payload?.detail ?? "Failed to delete invite."
      }));
      return;
    }
    await refreshInvites();
  }

  return {
    user,
    canViewQuestionable,
    canViewExplicit,
    tagBlacklist,
    setTagBlacklist,
    saving,
    message,
    error,
    passwordForm,
    setPasswordForm,
    passwordSaving,
    passwordMessage,
    passwordError,
    requestForm,
    setRequestForm,
    requestState,
    inviteForm,
    setInviteForm,
    inviteState,
    handleQuestionableToggle,
    handleExplicitToggle,
    handleBlacklistSave,
    handlePasswordChange,
    handleUploadRequestSubmit,
    handleInviteSubmit,
    deletePendingInvite
  };
}

export function AccountSummaryPanel() {
  const { user, inviteState } = useAccountData();

  if (!user) {
    return null;
  }

  return (
    <section className="panel">
      <h2>Account Summary</h2>
      <div className="account-card">
        <div className="account-row">
          <strong>Username</strong>
          <span>{user.username}</span>
        </div>
        <div className="account-row">
          <strong>Role</strong>
          <span>{user.role}</span>
        </div>
        <div className="account-row">
          <strong>Uploads</strong>
          <span>{user.can_upload || user.role === "admin" || user.role === "moderator" ? <a href="/account/uploads">Manage your uploads</a> : "Upload access not granted"}</span>
        </div>
        <div className="account-row">
          <strong>Invited by</strong>
          <span>{inviteState.invited_by_username ?? user.invited_by_username ?? "-"}</span>
        </div>
        <div className="account-row">
          <strong>Strikes</strong>
          <span>{user.strike_count}</span>
        </div>
        <div className="account-row">
          <strong>Invites remaining</strong>
          <span>{inviteState.loading ? "..." : inviteState.remaining}</span>
        </div>
      </div>
    </section>
  );
}

export function AccountPreferencesPanel() {
  const { canViewQuestionable, canViewExplicit, saving, message, error, tagBlacklist, setTagBlacklist, handleQuestionableToggle, handleExplicitToggle, handleBlacklistSave } = useAccountData();

  return (
    <>
      <section className="panel">
        <h2>Content Preferences</h2>
        <div className="account-card">
          <label className="toggle-row">
            <span>
              <strong>Questionable content</strong>
              <small>Questionable posts are member-only. Turn this off to hide them from your view.</small>
            </span>
            <input checked={canViewQuestionable} disabled={saving} onChange={(event) => handleQuestionableToggle(event.target.checked)} type="checkbox" />
          </label>
          <label className="toggle-row">
            <span>
              <strong>NSFW / explicit content</strong>
              <small>Allows explicit posts to appear in search results and post pages. Explicit content stays opt-in.</small>
            </span>
            <input checked={canViewExplicit} disabled={saving} onChange={(event) => handleExplicitToggle(event.target.checked)} type="checkbox" />
          </label>
          {message ? <p className="form-success">{message}</p> : null}
          {error ? <p className="form-error">{error}</p> : null}
        </div>
      </section>

      <section className="panel">
        <h2>Tag Blacklist</h2>
        <div className="stack-form narrow-panel">
          <label>
            Hidden tags
            <textarea className="stack-textarea" onChange={(event) => setTagBlacklist(event.target.value)} placeholder={"one_tag_per_line\nanother_tag"} rows={8} value={tagBlacklist} />
          </label>
          <button className="primary-button" disabled={saving} onClick={handleBlacklistSave} type="button">
            {saving ? "Saving..." : "Save blacklist"}
          </button>
          <p className="account-help">Right-click any tag in the interface to add it here quickly. Blacklisted tags are filtered out of post listings for your account.</p>
        </div>
      </section>
    </>
  );
}

export function AccountSecurityPanel() {
  const { passwordForm, setPasswordForm, passwordSaving, passwordMessage, passwordError, handlePasswordChange } = useAccountData();

  return (
    <section className="panel">
      <h2>Password</h2>
      <form className="stack-form narrow-panel" onSubmit={handlePasswordChange}>
        <label>
          Current password
          <input onChange={(event) => setPasswordForm((current) => ({ ...current, currentPassword: event.target.value }))} type="password" value={passwordForm.currentPassword} />
        </label>
        <label>
          New password
          <input onChange={(event) => setPasswordForm((current) => ({ ...current, newPassword: event.target.value }))} type="password" value={passwordForm.newPassword} />
        </label>
        <label>
          Confirm new password
          <input onChange={(event) => setPasswordForm((current) => ({ ...current, confirmPassword: event.target.value }))} type="password" value={passwordForm.confirmPassword} />
        </label>
        <button className="primary-button" disabled={passwordSaving} type="submit">
          {passwordSaving ? "Updating..." : "Change password"}
        </button>
        {passwordMessage ? <p className="form-success">{passwordMessage}</p> : null}
        {passwordError ? <p className="form-error">{passwordError}</p> : null}
      </form>
    </section>
  );
}

export function AccountInvitesPanel() {
  const { inviteForm, setInviteForm, inviteState, handleInviteSubmit, deletePendingInvite } = useAccountData();

  return (
    <section className="panel">
      <h2>Invites</h2>
      <div className="account-card">
        <div className="account-row">
          <strong>Invite quota</strong>
          <span>{inviteState.loading ? "..." : `${inviteState.used}/${inviteState.quota} used`}</span>
        </div>
        <div className="account-row">
          <strong>Remaining</strong>
          <span>{inviteState.loading ? "..." : inviteState.remaining}</span>
        </div>
      </div>
      <form className="stack-form narrow-panel" onSubmit={handleInviteSubmit}>
        <label>
          Invite email
          <input onChange={(event) => setInviteForm((current) => ({ ...current, email: event.target.value }))} type="email" value={inviteForm.email} />
        </label>
        <label>
          Invite note
          <textarea className="stack-textarea" onChange={(event) => setInviteForm((current) => ({ ...current, note: event.target.value }))} rows={3} value={inviteForm.note} />
        </label>
        <button className="primary-button" disabled={inviteState.loading || inviteState.saving || inviteState.remaining <= 0} type="submit">
          {inviteState.saving ? "Creating..." : "Create invite"}
        </button>
        {inviteState.remaining <= 0 ? <p className="account-help">No invite slots remaining on this account.</p> : null}
        {inviteState.error ? <p className="form-error">{inviteState.error}</p> : null}
      </form>
      {inviteState.items.length ? (
        <div className="table-wrap">
          <table className="simple-table">
            <thead>
              <tr>
                <th>Email</th>
                <th>Status</th>
                <th>Invite code</th>
                <th>Accepted by</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {inviteState.items.map((invite) => (
                <tr key={invite.id}>
                  <td>{invite.email}</td>
                  <td>{invite.status}</td>
                  <td><code>{invite.code}</code></td>
                  <td>{invite.invited_username ?? "-"}</td>
                  <td>
                    {invite.status === "pending" ? (
                      <button
                        className="danger-button compact-danger"
                        disabled={inviteState.saving}
                        onClick={() => deletePendingInvite(invite.id)}
                        type="button"
                      >
                        Delete
                      </button>
                    ) : (
                      "-"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="empty-state compact-empty">
          <strong>No invites created.</strong>
          <p>Invite-only registration is now the only account entry path.</p>
        </div>
      )}
    </section>
  );
}

export function AccountAccessPanel() {
  const { user, requestForm, setRequestForm, requestState, handleUploadRequestSubmit } = useAccountData();

  if (!user) {
    return null;
  }

  return (
    <section className="panel">
      <h2>Upload Access</h2>
      {user.can_upload || user.role === "admin" || user.role === "moderator" ? (
        <div className="empty-state compact-empty">
          <strong>Upload enabled.</strong>
          <p>Your account already has upload access.</p>
        </div>
      ) : (
        <div className="stack-form narrow-panel">
          <p className="account-help">Upload is disabled for your account until an administrator approves your request.</p>
          {requestState.items.some((item) => item.status === "pending") ? (
            <div className="empty-state compact-empty">
              <strong>Request pending.</strong>
              <p>Your upload request is waiting for admin review.</p>
            </div>
          ) : (
            <form className="stack-form" onSubmit={handleUploadRequestSubmit}>
              <label>
                Primary content
                <input onChange={(event) => setRequestForm((current) => ({ ...current, contentFocus: event.target.value }))} type="text" value={requestForm.contentFocus} />
              </label>
              <label>
                Why do you want upload access?
                <textarea className="stack-textarea" onChange={(event) => setRequestForm((current) => ({ ...current, reason: event.target.value }))} rows={5} value={requestForm.reason} />
              </label>
              <button className="primary-button" disabled={requestState.saving} type="submit">
                {requestState.saving ? "Submitting..." : "Request upload access"}
              </button>
            </form>
          )}
          {requestState.error ? <p className="form-error">{requestState.error}</p> : null}
          {requestState.items.length ? (
            <div className="request-history">
              {requestState.items.slice(0, 5).map((item) => (
                <div className="request-history-item" key={item.id}>
                  <strong>{item.status}</strong>
                  <p>{item.content_focus}</p>
                  {item.review_note ? <small>{item.review_note}</small> : null}
                </div>
              ))}
            </div>
          ) : null}
        </div>
      )}
    </section>
  );
}
