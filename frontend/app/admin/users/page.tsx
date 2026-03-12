"use client";

import { FormEvent, useEffect, useState } from "react";
import { AdminShell } from "../../components/admin-shell";
import { authFetch, useAuthState } from "../../components/auth";

type User = {
  id: number;
  username: string;
  email: string | null;
  role: "admin" | "moderator" | "uploader";
  is_active: boolean;
  is_banned: boolean;
  can_upload: boolean;
  invite_quota: number;
  invite_slots_used: number;
  invite_slots_remaining: number;
  invited_by_username: string | null;
  strike_count: number;
  can_view_explicit: boolean;
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

type ModalMode = "create" | "edit" | "reset" | "ban" | "invites" | null;

export default function AdminUsersPage() {
  const { isAdmin } = useAuthState();
  const [users, setUsers] = useState<User[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [modalMode, setModalMode] = useState<ModalMode>(null);
  const [selectedUser, setSelectedUser] = useState<User | null>(null);
  const [saving, setSaving] = useState(false);
  const [formState, setFormState] = useState({
    username: "",
    email: "",
    password: "",
    role: "uploader",
    can_upload: false,
    invite_quota: 2,
    is_active: true,
    can_view_explicit: false
  });
  const [reviewNote, setReviewNote] = useState("");
  const [resetPassword, setResetPassword] = useState("");
  const [inviteHistory, setInviteHistory] = useState<InviteItem[]>([]);
  const [inviteHistoryMeta, setInviteHistoryMeta] = useState<{ used: number; quota: number; remaining: number }>({
    used: 0,
    quota: 0,
    remaining: 0
  });

  async function loadUsers() {
    if (!isAdmin) {
      return;
    }
    const response = await authFetch("/api/v1/users");
    if (!response.ok) {
      setError("Failed to load users.");
      return;
    }
    const payload = await response.json();
    setUsers(payload.data);
  }

  useEffect(() => {
    loadUsers();
  }, [isAdmin]);

  function openCreateModal() {
    setSelectedUser(null);
    setFormState({
      username: "",
      email: "",
      password: "",
      role: "uploader",
      can_upload: false,
      invite_quota: 2,
      is_active: true,
      can_view_explicit: false
    });
    setModalMode("create");
  }

  function openEditModal(user: User) {
    setSelectedUser(user);
    setFormState({
      username: user.username,
      email: user.email ?? "",
      password: "",
      role: user.role,
      can_upload: user.can_upload,
      invite_quota: user.invite_quota,
      is_active: user.is_active,
      can_view_explicit: user.can_view_explicit
    });
    setModalMode("edit");
  }

  async function openInviteHistoryModal(user: User) {
    setSelectedUser(user);
    setSaving(true);
    setError(null);
    setSuccess(null);
    const response = await authFetch(`/api/v1/invites/admin/user/${user.id}`);
    setSaving(false);
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      setError(payload?.detail ?? "Failed to load invite history.");
      return;
    }
    const payload = await response.json();
    setInviteHistory(payload.data.invites);
    setInviteHistoryMeta({
      used: payload.data.used,
      quota: payload.data.quota,
      remaining: payload.data.remaining
    });
    setModalMode("invites");
  }

  async function submitCreateOrEdit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!isAdmin) {
      return;
    }
    setSaving(true);
    setError(null);
    setSuccess(null);
    const isCreate = modalMode === "create";
    const response = await authFetch(
      `/api/v1/users${isCreate ? "" : `/${selectedUser?.id}`}`,
      {
        method: isCreate ? "POST" : "PATCH",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify(
          isCreate
            ? {
                username: formState.username,
                email: formState.email,
                password: formState.password,
                role: formState.role
              }
            : {
                email: formState.email,
                role: formState.role,
                can_upload: formState.can_upload,
                invite_quota: formState.invite_quota,
                is_active: formState.is_active,
                can_view_explicit: formState.can_view_explicit
              }
        )
      }
    );
    setSaving(false);
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      setError(payload?.detail ?? "Failed to save user.");
      return;
    }
    setModalMode(null);
    setSuccess(isCreate ? "User created." : "User updated.");
    await loadUsers();
  }

  async function resetUserPassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedUser) {
      return;
    }
    setSaving(true);
    setError(null);
    setSuccess(null);
    const response = await authFetch(`/api/v1/users/${selectedUser.id}/reset-password`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ new_password: resetPassword || null })
    });
    setSaving(false);
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      setError(payload?.detail ?? "Failed to reset password.");
      return;
    }
    const payload = await response.json();
    setSuccess(`Temporary password: ${payload.data.temporary_password}`);
    setModalMode(null);
  }

  async function banUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedUser) {
      return;
    }
    setSaving(true);
    setError(null);
    setSuccess(null);
    const response = await authFetch(`/api/v1/users/${selectedUser.id}/ban`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ reason: reviewNote || null })
    });
    setSaving(false);
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      setError(payload?.detail ?? "Failed to ban user.");
      return;
    }
    setModalMode(null);
    setSuccess("User banned.");
    await loadUsers();
  }

  async function removeUser(user: User) {
    if (!window.confirm(`Remove user ${user.username}? This cannot be undone.`)) {
      return;
    }
    setError(null);
    setSuccess(null);
    const response = await authFetch(`/api/v1/users/${user.id}`, {
      method: "DELETE"
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      setError(payload?.detail ?? "Failed to remove user.");
      return;
    }
    setSuccess("User removed.");
    await loadUsers();
  }

  async function purgeUserContent(user: User) {
    if (!window.confirm(`Really remove all posts, thumbs and tag remnants for ${user.username}?`)) {
      return;
    }
    setError(null);
    setSuccess(null);
    const response = await authFetch(`/api/v1/users/${user.id}/purge-content`, {
      method: "POST"
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      setError(payload?.detail ?? "Failed to purge account content.");
      return;
    }
    const payload = await response.json();
    setSuccess(`Removed ${payload.data.removed_images} images from ${user.username}.`);
    await loadUsers();
  }

  async function deletePendingInvite(invite: InviteItem) {
    if (!window.confirm(`Delete pending invite for ${invite.email}?`)) {
      return;
    }
    setSaving(true);
    setError(null);
    setSuccess(null);
    const response = await authFetch(`/api/v1/invites/admin/${invite.id}`, {
      method: "DELETE"
    });
    setSaving(false);
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      setError(payload?.detail ?? "Failed to delete pending invite.");
      return;
    }
    setSuccess("Pending invite deleted.");
    if (selectedUser) {
      await openInviteHistoryModal(selectedUser);
      await loadUsers();
    }
  }

  async function rehabInvite(invite: InviteItem) {
    if (!window.confirm(`Rehab revoked invite for ${invite.email} and free the slot again?`)) {
      return;
    }
    setSaving(true);
    setError(null);
    setSuccess(null);
    const response = await authFetch(`/api/v1/invites/admin/${invite.id}/rehab`, {
      method: "POST"
    });
    setSaving(false);
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      setError(payload?.detail ?? "Failed to rehab invite.");
      return;
    }
    setSuccess("Invite rehabilitated. Slot released.");
    if (selectedUser) {
      await openInviteHistoryModal(selectedUser);
      await loadUsers();
    }
  }

  return (
    <AdminShell title="Users" description="Admin account management with create, edit, remove, ban and password reset actions.">
      {!isAdmin ? (
        <section className="panel">
          <h2>Users</h2>
          <div className="empty-state">
            <strong>Administrator access required.</strong>
            <p>Only admins can manage accounts.</p>
          </div>
        </section>
      ) : null}

      {isAdmin ? (
        <>
          {error ? <p className="form-error">{error}</p> : null}
          {success ? <p className="form-success">{success}</p> : null}

          <section className="panel">
            <h2>User List</h2>
            <div className="admin-toolbar">
              <button className="primary-button" onClick={openCreateModal} type="button">
                Create User
              </button>
            </div>
            <div className="table-wrap">
              <table className="simple-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Username</th>
                    <th>Email</th>
                    <th>Role</th>
                    <th>Invited by</th>
                    <th>Strikes</th>
                    <th>Invites</th>
                    <th>Upload</th>
                    <th>State</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((user) => (
                    <tr key={user.id}>
                      <td>{user.id}</td>
                      <td>{user.username}</td>
                      <td>{user.email ?? "-"}</td>
                      <td>{user.role}</td>
                      <td>{user.invited_by_username ?? "-"}</td>
                      <td>{user.strike_count}</td>
                      <td>{user.invite_slots_remaining}/{user.invite_quota}</td>
                      <td>{user.can_upload ? "yes" : "no"}</td>
                      <td>{user.is_banned ? "banned" : user.is_active ? "active" : "inactive"}</td>
                      <td>
                        <div className="row-actions">
                          <button aria-label={`Edit ${user.username}`} className="icon-action" onClick={() => openEditModal(user)} title="Edit" type="button">✎</button>
                          <button aria-label={`Invite history for ${user.username}`} className="icon-action" onClick={() => openInviteHistoryModal(user)} title="Invite History" type="button">⌁</button>
                          <button aria-label={`Purge content for ${user.username}`} className="icon-action" onClick={() => purgeUserContent(user)} title="Purge Content" type="button">⌦</button>
                          <button aria-label={`Remove ${user.username}`} className="icon-action" onClick={() => removeUser(user)} title="Remove" type="button">✖</button>
                          <button
                            aria-label={`Ban ${user.username}`}
                            className="icon-action"
                            onClick={() => {
                              setSelectedUser(user);
                              setReviewNote("");
                              setModalMode("ban");
                            }}
                            title="Ban"
                            type="button"
                          >
                            ⛔
                          </button>
                          <button
                            aria-label={`Reset password for ${user.username}`}
                            className="icon-action"
                            onClick={() => {
                              setSelectedUser(user);
                              setResetPassword("");
                              setModalMode("reset");
                            }}
                            title="Reset Password"
                            type="button"
                          >
                            ↺
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {modalMode ? (
            <div className="modal-backdrop" onClick={() => setModalMode(null)}>
              <div className={modalMode === "invites" ? "modal-panel modal-panel-wide" : "modal-panel"} onClick={(event) => event.stopPropagation()}>
                {modalMode === "create" || modalMode === "edit" ? (
                  <>
                    <h2>{modalMode === "create" ? "Create User" : `Edit ${selectedUser?.username}`}</h2>
                    <form className="stack-form" onSubmit={submitCreateOrEdit}>
                      {modalMode === "create" ? (
                        <label>
                          Username
                          <input onChange={(event) => setFormState((current) => ({ ...current, username: event.target.value }))} type="text" value={formState.username} />
                        </label>
                      ) : null}
                      <label>
                        Email
                        <input onChange={(event) => setFormState((current) => ({ ...current, email: event.target.value }))} type="email" value={formState.email} />
                      </label>
                      {modalMode === "create" ? (
                        <label>
                          Password
                          <input onChange={(event) => setFormState((current) => ({ ...current, password: event.target.value }))} type="password" value={formState.password} />
                        </label>
                      ) : null}
                      <label>
                        Role
                        <select className="stack-select" onChange={(event) => setFormState((current) => ({ ...current, role: event.target.value }))} value={formState.role}>
                          <option value="uploader">Uploader</option>
                          <option value="moderator">Moderator</option>
                          <option value="admin">Admin</option>
                        </select>
                      </label>
                      {modalMode === "edit" ? (
                        <>
                          <label className="toggle-row">
                            <span>Upload access</span>
                            <input checked={formState.can_upload} onChange={(event) => setFormState((current) => ({ ...current, can_upload: event.target.checked }))} type="checkbox" />
                          </label>
                          <label>
                            Invite quota
                            <input
                              min={0}
                              onChange={(event) => setFormState((current) => ({ ...current, invite_quota: Number(event.target.value) }))}
                              type="number"
                              value={formState.invite_quota}
                            />
                          </label>
                          <label className="toggle-row">
                            <span>Active</span>
                            <input checked={formState.is_active} onChange={(event) => setFormState((current) => ({ ...current, is_active: event.target.checked }))} type="checkbox" />
                          </label>
                          <label className="toggle-row">
                            <span>Can view explicit</span>
                            <input checked={formState.can_view_explicit} onChange={(event) => setFormState((current) => ({ ...current, can_view_explicit: event.target.checked }))} type="checkbox" />
                          </label>
                        </>
                      ) : null}
                      <div className="row-actions">
                        <button className="primary-button" disabled={saving} type="submit">{saving ? "Saving..." : "Save"}</button>
                        <button className="theme-toggle" onClick={() => setModalMode(null)} type="button">Close</button>
                      </div>
                    </form>
                  </>
                ) : null}

                {modalMode === "reset" ? (
                  <>
                    <h2>Reset Password</h2>
                    <form className="stack-form" onSubmit={resetUserPassword}>
                      <p>Leave empty to generate a temporary password automatically.</p>
                      <label>
                        New password
                        <input onChange={(event) => setResetPassword(event.target.value)} type="text" value={resetPassword} />
                      </label>
                      <div className="row-actions">
                        <button className="primary-button" disabled={saving} type="submit">{saving ? "Resetting..." : "Reset password"}</button>
                        <button className="theme-toggle" onClick={() => setModalMode(null)} type="button">Close</button>
                      </div>
                    </form>
                  </>
                ) : null}

                {modalMode === "ban" ? (
                  <>
                    <h2>Ban User</h2>
                    <form className="stack-form" onSubmit={banUser}>
                      <p>This disables login and blocks future account creation with the same email address.</p>
                      <label>
                        Ban reason
                        <textarea className="stack-textarea" onChange={(event) => setReviewNote(event.target.value)} rows={4} value={reviewNote} />
                      </label>
                      <div className="row-actions">
                        <button className="danger-button" disabled={saving} type="submit">Ban user</button>
                        <button className="theme-toggle" onClick={() => setModalMode(null)} type="button">Close</button>
                      </div>
                    </form>
                  </>
                ) : null}

                {modalMode === "invites" ? (
                  <>
                    <h2>Invite History: {selectedUser?.username}</h2>
                    <div className="account-card">
                      <div className="account-row">
                        <strong>Quota</strong>
                        <span>{inviteHistoryMeta.quota}</span>
                      </div>
                      <div className="account-row">
                        <strong>Used</strong>
                        <span>{inviteHistoryMeta.used}</span>
                      </div>
                      <div className="account-row">
                        <strong>Remaining</strong>
                        <span>{inviteHistoryMeta.remaining}</span>
                      </div>
                    </div>
                    <div className="table-wrap">
                      <table className="simple-table">
                        <thead>
                          <tr>
                            <th>Email</th>
                            <th>Status</th>
                            <th>Code</th>
                            <th>Accepted by</th>
                            <th>Action</th>
                          </tr>
                        </thead>
                        <tbody>
                          {inviteHistory.map((invite) => (
                            <tr key={invite.id}>
                              <td>{invite.email}</td>
                              <td>{invite.status}{invite.rehabilitated_at ? " (rehab)" : ""}</td>
                              <td><code>{invite.code}</code></td>
                              <td>{invite.invited_username ?? "-"}</td>
                              <td>
                                <div className="row-actions">
                                  {invite.status === "pending" ? (
                                    <button className="danger-button compact-danger" disabled={saving} onClick={() => deletePendingInvite(invite)} type="button">
                                      Delete
                                    </button>
                                  ) : null}
                                  {invite.status === "revoked" && !invite.rehabilitated_at ? (
                                    <button className="primary-button" disabled={saving} onClick={() => rehabInvite(invite)} type="button">
                                      Rehab
                                    </button>
                                  ) : null}
                                  {invite.status === "accepted" || (invite.status === "revoked" && invite.rehabilitated_at) ? "-" : null}
                                </div>
                              </td>
                            </tr>
                          ))}
                          {!inviteHistory.length ? (
                            <tr>
                              <td colSpan={5}>No invite records for this account.</td>
                            </tr>
                          ) : null}
                        </tbody>
                      </table>
                    </div>
                    <div className="row-actions">
                      <button className="theme-toggle" onClick={() => setModalMode(null)} type="button">Close</button>
                    </div>
                  </>
                ) : null}
              </div>
            </div>
          ) : null}
        </>
      ) : null}
    </AdminShell>
  );
}
