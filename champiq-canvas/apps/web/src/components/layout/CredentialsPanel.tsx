import { useState } from 'react'
import { Plus, Trash2, ChevronDown, ChevronUp, Eye, EyeOff } from '@/lib/icons'
import {
  useCredentialStore,
  CREDENTIAL_TYPE_FIELDS,
  type CredentialType,
  type Credential,
} from '@/store/credentialStore'

const TYPE_LABELS: Record<CredentialType, string> = {
  champmail: 'ChampMail',
  champgraph: 'ChampGraph',
  champvoice: 'ChampVoice',
  lakeb2b: 'LakeB2B Pulse',
  http: 'HTTP / Bearer',
  generic: 'Generic Secret',
}

const CREDENTIAL_TYPES: CredentialType[] = [
  'champmail', 'champgraph', 'champvoice', 'lakeb2b', 'http', 'generic',
]

// ── Add Credential Form ───────────────────────────────────────────────────────

function AddCredentialForm({ onDone }: { onDone: () => void }) {
  const { addCredential } = useCredentialStore()
  const [name, setName] = useState('')
  const [type, setType] = useState<CredentialType>('champmail')
  const [fields, setFields] = useState<Record<string, string>>({})
  const [showSecrets, setShowSecrets] = useState(false)
  const [error, setError] = useState('')

  const fieldDefs = CREDENTIAL_TYPE_FIELDS[type]

  function handleTypeChange(t: CredentialType) {
    setType(t)
    setFields({})
  }

  function handleSubmit() {
    if (!name.trim()) { setError('Name is required'); return }
    addCredential(name.trim(), type, fields)
    onDone()
  }

  return (
    <div className="flex flex-col gap-2 p-3 rounded-md" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
      <p className="text-xs font-semibold" style={{ color: 'var(--text-2)' }}>New credential</p>

      <div className="flex flex-col gap-1">
        <label className="text-xs" style={{ color: 'var(--text-3)' }}>Name (used in node config)</label>
        <input
          autoFocus
          className="text-xs p-1.5 rounded-md focus:outline-none"
          style={{ background: 'var(--bg-sidebar)', border: '1px solid var(--border)', color: 'var(--text-1)' }}
          placeholder="e.g. champmail-prod"
          value={name}
          onChange={(e) => { setName(e.target.value); setError('') }}
        />
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-xs" style={{ color: 'var(--text-3)' }}>Type</label>
        <select
          className="text-xs p-1.5 rounded-md focus:outline-none"
          style={{ background: 'var(--bg-sidebar)', border: '1px solid var(--border)', color: 'var(--text-1)' }}
          value={type}
          onChange={(e) => handleTypeChange(e.target.value as CredentialType)}
        >
          {CREDENTIAL_TYPES.map((t) => (
            <option key={t} value={t}>{TYPE_LABELS[t]}</option>
          ))}
        </select>
      </div>

      {fieldDefs.map((f) => (
        <div key={f.key} className="flex flex-col gap-1">
          <label className="text-xs" style={{ color: 'var(--text-3)' }}>{f.label}</label>
          <div className="flex gap-1">
            <input
              type={f.secret && !showSecrets ? 'password' : 'text'}
              className="flex-1 text-xs p-1.5 rounded-md focus:outline-none"
              style={{ background: 'var(--bg-sidebar)', border: '1px solid var(--border)', color: 'var(--text-1)' }}
              value={fields[f.key] ?? ''}
              onChange={(e) => setFields((prev) => ({ ...prev, [f.key]: e.target.value }))}
            />
          </div>
        </div>
      ))}

      <div className="flex items-center gap-1">
        <button
          className="text-xs flex items-center gap-1"
          style={{ color: 'var(--text-3)' }}
          onClick={() => setShowSecrets((v) => !v)}
        >
          {showSecrets ? <EyeOff size={11} /> : <Eye size={11} />}
          {showSecrets ? 'Hide' : 'Show'} secrets
        </button>
      </div>

      {error && <p className="text-xs" style={{ color: '#f87171' }}>{error}</p>}

      <div className="flex gap-2 mt-1">
        <button
          onClick={handleSubmit}
          className="flex-1 text-xs py-1.5 rounded-md font-medium"
          style={{ background: '#6366f1', color: '#fff' }}
        >
          Save
        </button>
        <button
          onClick={onDone}
          className="flex-1 text-xs py-1.5 rounded-md"
          style={{ background: 'var(--bg-sidebar)', border: '1px solid var(--border)', color: 'var(--text-2)' }}
        >
          Cancel
        </button>
      </div>
    </div>
  )
}

// ── Credential Card ───────────────────────────────────────────────────────────

function CredentialCard({ cred }: { cred: Credential }) {
  const { deleteCredential } = useCredentialStore()
  const fieldKeys = Object.keys(cred.fields).filter((k) => cred.fields[k])

  return (
    <div
      className="group flex items-center justify-between gap-2 px-2 py-1.5 rounded-md"
      style={{ border: '1px solid var(--border)', background: 'var(--bg-surface)' }}
    >
      <div className="min-w-0 flex-1">
        <p className="text-xs font-medium truncate" style={{ color: 'var(--text-1)' }}>{cred.name}</p>
        <p className="text-xs" style={{ color: 'var(--text-3)' }}>
          {TYPE_LABELS[cred.type]}
          {fieldKeys.length > 0 && ` · ${fieldKeys.join(', ')}`}
        </p>
      </div>
      <button
        onClick={() => deleteCredential(cred.id)}
        className="opacity-0 group-hover:opacity-100 shrink-0 p-0.5 rounded hover:text-red-400"
        style={{ color: 'var(--text-3)' }}
        aria-label={`Delete credential ${cred.name}`}
      >
        <Trash2 size={11} />
      </button>
    </div>
  )
}

// ── CredentialsPanel ──────────────────────────────────────────────────────────

export function CredentialsPanel() {
  const { credentials } = useCredentialStore()
  const [open, setOpen] = useState(false)
  const [adding, setAdding] = useState(false)

  return (
    <div>
      {/* Section header */}
      <div className="p-3">
        <div className="flex items-center justify-between mb-2">
          <button
            className="flex items-center gap-1 text-xs font-semibold uppercase tracking-wide"
            style={{ color: 'var(--text-3)' }}
            onClick={() => setOpen((v) => !v)}
          >
            {open ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
            Credentials {credentials.length > 0 && `(${credentials.length})`}
          </button>
          <button
            onClick={() => { setOpen(true); setAdding(true) }}
            className="p-0.5 rounded hover:opacity-70"
            style={{ color: 'var(--text-2)' }}
            aria-label="Add credential"
          >
            <Plus size={14} />
          </button>
        </div>

        {open && (
          <div className="flex flex-col gap-1.5">
            {adding && (
              <AddCredentialForm onDone={() => setAdding(false)} />
            )}
            {credentials.length === 0 && !adding && (
              <p className="text-xs" style={{ color: 'var(--text-3)' }}>
                No credentials yet. Click + to add one.
              </p>
            )}
            {credentials.map((c) => <CredentialCard key={c.id} cred={c} />)}
          </div>
        )}
      </div>

      <div style={{ borderTop: '1px solid var(--border)' }} />
    </div>
  )
}
