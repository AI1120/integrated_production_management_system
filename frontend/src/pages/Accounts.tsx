import { useEffect, useMemo, useState, type FormEvent } from 'react'

import { errorMessage } from '../api/client'
import { useChangeOwnPassword, useCreateUser, useUpdateUser, useUsers } from '../api/hooks'
import type { Role, User } from '../api/types'
import { Layout } from '../components/Layout'
import { Alert, Badge, Card, Empty, Field, Loading, Modal } from '../components/ui'
import { useAuth } from '../lib/auth'
import { dateTime, roleLabel, since } from '../lib/format'

/** Hold a fast-changing value still, so typing does not fire a request per keystroke. */
function useDebounced<T>(value: T, delay = 250): T {
  const [settled, setSettled] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return settled
}

const ROLES: { key: Role; what: string }[] = [
  { key: 'ADMIN', what: 'Everything, including accounts' },
  { key: 'PLANNER', what: 'Master data, orders, scheduling' },
  { key: 'OPERATOR', what: 'Shop floor terminal, downtime' },
  { key: 'QC', what: 'Inspections, dispositions, NCRs' },
  { key: 'WAREHOUSE', what: 'Receipts, issues, transfers' },
  { key: 'VIEWER', what: 'Read only' },
]

const ROLE_TONE: Record<Role, 'good' | 'warn' | 'info' | 'neutral'> = {
  ADMIN: 'warn',
  PLANNER: 'info',
  OPERATOR: 'neutral',
  QC: 'good',
  WAREHOUSE: 'neutral',
  VIEWER: 'neutral',
}

export function Accounts() {
  const { user: me, can } = useAuth()
  const isAdmin = can('ADMIN')

  const [search, setSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState<Role | ''>('')
  const [statusFilter, setStatusFilter] = useState<'' | 'active' | 'disabled'>('')
  const debouncedSearch = useDebounced(search)

  const filters = useMemo(
    () => ({
      q: debouncedSearch.trim() || undefined,
      role: roleFilter || undefined,
      active: statusFilter === '' ? undefined : statusFilter === 'active',
    }),
    [debouncedSearch, roleFilter, statusFilter],
  )
  const filtered = !!(filters.q || filters.role || filters.active !== undefined)

  const { data: users, isLoading } = useUsers(isAdmin, filters)
  // The role summary counts the whole plant, so narrowing the table above it
  // does not silently change what the permissions table appears to say.
  const { data: everyone } = useUsers(isAdmin)

  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<User | null>(null)
  const [ownPassword, setOwnPassword] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const update = useUpdateUser()

  async function toggleActive(target: User) {
    setError(null)
    setNotice(null)
    try {
      await update.mutateAsync({ id: target.id, body: { is_active: !target.is_active } })
      setNotice(`${target.full_name} ${target.is_active ? 'deactivated' : 'reactivated'}.`)
    } catch (exception) {
      setError(errorMessage(exception))
    }
  }

  return (
    <Layout
      title="Accounts"
      subtitle={isAdmin ? 'Who can sign in, and what each of them may do' : 'Your account'}
      actions={
        <>
          <button onClick={() => setOwnPassword(true)}>Change my password</button>
          {isAdmin && (
            <button className="primary" onClick={() => setCreating(true)}>
              + New account
            </button>
          )}
        </>
      }
    >
      <div className="stack">
        {notice && <Alert tone="ok">{notice}</Alert>}
        {error && <Alert tone="error">{error}</Alert>}

        {!isAdmin && (
          <Card title="Your account">
            <div className="row" style={{ gap: 28 }}>
              <div>
                <div className="muted small">Name</div>
                <div className="strong">{me?.full_name}</div>
              </div>
              <div>
                <div className="muted small">Username</div>
                <div className="code">{me?.username}</div>
              </div>
              <div>
                <div className="muted small">Role</div>
                <Badge tone={ROLE_TONE[me?.role ?? 'VIEWER']}>{roleLabel(me?.role ?? '')}</Badge>
              </div>
              <div>
                <div className="muted small">Badge</div>
                <div className="code">{me?.badge_no ?? '—'}</div>
              </div>
            </div>
            <div className="muted small" style={{ marginTop: 14 }}>
              Only an administrator can change roles or create accounts.
            </div>
          </Card>
        )}

        {isAdmin && (
          <>
            {isLoading && <Loading />}
            {users && (
              <Card
                title="People"
                hint={
                  filtered
                    ? `${users.length} of ${everyone?.length ?? users.length} accounts match`
                    : "Deactivating keeps the person's production history intact — accounts are never deleted"
                }
                actions={
                  <>
                    <input
                      className="sm"
                      type="search"
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                      placeholder="Search name, username, badge"
                      aria-label="Search accounts"
                      style={{ minWidth: 210 }}
                    />
                    <select
                      className="sm"
                      value={roleFilter}
                      onChange={(e) => setRoleFilter(e.target.value as Role | '')}
                      aria-label="Filter by role"
                    >
                      <option value="">All roles</option>
                      {ROLES.map((role) => (
                        <option key={role.key} value={role.key}>
                          {roleLabel(role.key)}
                        </option>
                      ))}
                    </select>
                    <select
                      className="sm"
                      value={statusFilter}
                      onChange={(e) => setStatusFilter(e.target.value as '' | 'active' | 'disabled')}
                      aria-label="Filter by state"
                    >
                      <option value="">Any state</option>
                      <option value="active">Active</option>
                      <option value="disabled">Disabled</option>
                    </select>
                    {filtered && (
                      <button
                        className="sm"
                        onClick={() => {
                          setSearch('')
                          setRoleFilter('')
                          setStatusFilter('')
                        }}
                      >
                        Clear
                      </button>
                    )}
                  </>
                }
                flush
              >
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Name</th>
                        <th>Username</th>
                        <th>Role</th>
                        <th>Badge</th>
                        <th>Last signed in</th>
                        <th>State</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {users.length === 0 && (
                        <tr>
                          <td colSpan={7}>
                            <Empty>{filtered ? 'No accounts match those filters' : 'No accounts'}</Empty>
                          </td>
                        </tr>
                      )}
                      {users.map((account) => (
                        <tr key={account.id}>
                          <td>
                            <span className="strong">{account.full_name}</span>
                            {account.id === me?.id && <span className="muted small"> · you</span>}
                          </td>
                          <td className="code">{account.username}</td>
                          <td>
                            <Badge tone={ROLE_TONE[account.role]}>{roleLabel(account.role)}</Badge>
                          </td>
                          <td className="code small">{account.badge_no ?? '—'}</td>
                          <td className="small">
                            {account.last_login_at ? (
                              <span className="secondary" title={dateTime(account.last_login_at)}>
                                {since(account.last_login_at)}
                              </span>
                            ) : (
                              <span className="muted">Never</span>
                            )}
                          </td>
                          <td>
                            {account.is_active ? (
                              <Badge tone="good">Active</Badge>
                            ) : (
                              <Badge tone="neutral">Disabled</Badge>
                            )}
                          </td>
                          <td className="num">
                            <div className="row tight" style={{ justifyContent: 'flex-end' }}>
                              <button className="sm" onClick={() => setEditing(account)}>
                                Edit
                              </button>
                              <button
                                className={account.is_active ? 'sm danger' : 'sm'}
                                onClick={() => toggleActive(account)}
                                disabled={update.isPending}
                              >
                                {account.is_active ? 'Disable' : 'Enable'}
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            )}

            <Card title="What each role may do" flush>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Role</th>
                      <th>Permissions</th>
                      <th className="num">People</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ROLES.map((role) => (
                      <tr key={role.key}>
                        <td>
                          <Badge tone={ROLE_TONE[role.key]}>{roleLabel(role.key)}</Badge>
                        </td>
                        <td className="secondary">{role.what}</td>
                        <td className="num">
                          {(everyone ?? []).filter((u) => u.role === role.key && u.is_active).length}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="muted small" style={{ padding: '10px 16px' }}>
                Administrators pass every permission check. The screens hide what a role cannot do,
                but the server is what enforces it.
              </div>
            </Card>
          </>
        )}
      </div>

      {creating && (
        <AccountModal
          onClose={() => setCreating(false)}
          onDone={(message) => {
            setCreating(false)
            setNotice(message)
          }}
        />
      )}
      {editing && (
        <AccountModal
          account={editing}
          onClose={() => setEditing(null)}
          onDone={(message) => {
            setEditing(null)
            setNotice(message)
          }}
        />
      )}
      {ownPassword && (
        <OwnPasswordModal
          onClose={() => setOwnPassword(false)}
          onDone={(message) => {
            setOwnPassword(false)
            setNotice(message)
          }}
        />
      )}
    </Layout>
  )
}

function AccountModal({
  account,
  onClose,
  onDone,
}: {
  account?: User
  onClose: () => void
  onDone: (message: string) => void
}) {
  const create = useCreateUser()
  const update = useUpdateUser()
  const editing = !!account

  const [form, setForm] = useState({
    username: account?.username ?? '',
    full_name: account?.full_name ?? '',
    badge_no: account?.badge_no ?? '',
    role: (account?.role ?? 'OPERATOR') as Role,
    password: '',
  })
  const [error, setError] = useState<string | null>(null)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    try {
      if (editing) {
        const body: Record<string, unknown> = {
          full_name: form.full_name,
          badge_no: form.badge_no || null,
          role: form.role,
        }
        if (form.password) body.password = form.password
        await update.mutateAsync({ id: account!.id, body })
        onDone(`${form.full_name} updated.`)
      } else {
        await create.mutateAsync({
          username: form.username,
          full_name: form.full_name,
          badge_no: form.badge_no || null,
          role: form.role,
          password: form.password,
        })
        onDone(`${form.full_name} can now sign in.`)
      }
    } catch (exception) {
      setError(errorMessage(exception))
    }
  }

  const busy = create.isPending || update.isPending

  return (
    <Modal
      title={editing ? `Edit ${account!.username}` : 'New account'}
      onClose={onClose}
      footer={
        <>
          <button onClick={onClose}>Cancel</button>
          <button className="primary" form="account-form" type="submit" disabled={busy}>
            {busy ? 'Saving...' : editing ? 'Save changes' : 'Create account'}
          </button>
        </>
      }
    >
      <form id="account-form" onSubmit={submit} className="stack" style={{ gap: 12 }}>
        {error && <Alert tone="error">{error}</Alert>}

        <Field label="Full name">
          <input
            value={form.full_name}
            onChange={(e) => setForm({ ...form, full_name: e.target.value })}
            required
            autoFocus
          />
        </Field>

        {!editing && (
          <Field label="Username" note="used to sign in">
            <input
              value={form.username}
              onChange={(e) => setForm({ ...form, username: e.target.value.toLowerCase() })}
              required
              minLength={3}
            />
          </Field>
        )}

        <div className="row">
          <div style={{ flex: 1 }}>
            <Field label="Role">
              <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>
                {ROLES.map((role) => (
                  <option key={role.key} value={role.key}>
                    {roleLabel(role.key)}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <div style={{ flex: 1 }}>
            <Field label="Badge number" note="scannable at the terminal">
              <input
                value={form.badge_no}
                onChange={(e) => setForm({ ...form, badge_no: e.target.value })}
                placeholder="B-1003"
              />
            </Field>
          </div>
        </div>

        <Field
          label={editing ? 'New password' : 'Password'}
          note={editing ? 'leave blank to keep the current one' : 'at least 4 characters'}
        >
          <input
            type="password"
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
            required={!editing}
            minLength={editing && !form.password ? undefined : 4}
            autoComplete="new-password"
          />
        </Field>

        <div className="muted small">
          {ROLES.find((r) => r.key === form.role)?.what}
        </div>
      </form>
    </Modal>
  )
}

function OwnPasswordModal({
  onClose,
  onDone,
}: {
  onClose: () => void
  onDone: (message: string) => void
}) {
  const change = useChangeOwnPassword()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    if (next !== confirm) {
      setError('The two new passwords do not match.')
      return
    }
    try {
      await change.mutateAsync({ current_password: current, new_password: next })
      onDone('Your password has been changed.')
    } catch (exception) {
      setError(errorMessage(exception))
    }
  }

  return (
    <Modal
      title="Change my password"
      onClose={onClose}
      footer={
        <>
          <button onClick={onClose}>Cancel</button>
          <button className="primary" form="pw-form" type="submit" disabled={change.isPending}>
            {change.isPending ? 'Changing...' : 'Change password'}
          </button>
        </>
      }
    >
      <form id="pw-form" onSubmit={submit} className="stack" style={{ gap: 12 }}>
        {error && <Alert tone="error">{error}</Alert>}
        <Field label="Current password">
          <input
            type="password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            required
            autoFocus
            autoComplete="current-password"
          />
        </Field>
        <Field label="New password" note="at least 4 characters">
          <input
            type="password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            required
            minLength={4}
            autoComplete="new-password"
          />
        </Field>
        <Field label="Confirm new password">
          <input
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            required
            autoComplete="new-password"
          />
        </Field>
      </form>
    </Modal>
  )
}
