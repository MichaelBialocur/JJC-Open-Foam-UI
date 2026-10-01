import { useEffect, useRef, useState } from 'react'

const deletable = new Set(['completed', 'not_converged', 'cancelled', 'failed', 'interrupted'])
const date = job => new Date(job.created_at * 1000).toLocaleString([], {
  month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
})
const label = job => `${job.inputs.name || `${job.inputs.mesh_level} pipe run`} · ${date(job)} · ${job.id.slice(0, 8)}`

function DeleteDialog({ jobs, busy, onCancel, onConfirm }) {
  const dialog = useRef(null)
  useEffect(() => {
    const previous = document.activeElement
    dialog.current.querySelector('button').focus()
    return () => { if (previous?.isConnected) previous.focus() }
  }, [])
  function keyDown(event) {
    if (event.key === 'Escape' && !busy) { event.preventDefault(); onCancel() }
    if (event.key === 'Tab') {
      const buttons = [...dialog.current.querySelectorAll('button:not(:disabled)')]
      if (!buttons.length) { event.preventDefault(); return }
      if (event.shiftKey && document.activeElement === buttons[0]) { event.preventDefault(); buttons.at(-1).focus() }
      else if (!event.shiftKey && document.activeElement === buttons.at(-1)) { event.preventDefault(); buttons[0].focus() }
    }
  }
  return <div className="editor-backdrop"><div className="property-editor delete-dialog" ref={dialog}
    role="dialog" aria-modal="true" aria-labelledby="delete-title" aria-describedby="delete-description" aria-busy={busy} onKeyDown={keyDown}>
    <h2 id="delete-title">Delete {jobs.length === 1 ? 'this saved run' : `${jobs.length} saved runs`}?</h2>
    <p id="delete-description">This permanently removes their results, logs, meshes and OpenFOAM case files. It cannot be undone. Your current inputs and geometry draft are kept.</p>
    <ul className="delete-run-names">{jobs.map(job => <li key={job.id}>{label(job)}</li>)}</ul>
    <div className="editor-actions"><button className="secondary" disabled={busy} onClick={onCancel}>Keep runs</button>
      <button className="danger" disabled={busy} onClick={onConfirm}>{busy ? 'Deleting…' : `Delete ${jobs.length === 1 ? 'run' : `${jobs.length} runs`} permanently`}</button></div>
  </div></div>
}

export default function RunHistory({ jobs, selectedId, onSelect, onDeleted, onDeletingChange, children }) {
  const [checked, setChecked] = useState([]), [pending, setPending] = useState(null)
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('')
  const allCheckbox = useRef(null)
  const finished = jobs.filter(job => deletable.has(job.status))
  const chosen = finished.filter(job => checked.includes(job.id))
  const allChecked = finished.length > 0 && chosen.length === finished.length
  useEffect(() => {
    if (allCheckbox.current) allCheckbox.current.indeterminate = chosen.length > 0 && !allChecked
  }, [chosen.length, allChecked])

  async function remove() {
    setBusy(true); onDeletingChange(true); setError(''); setNotice('')
    const removed = [], failures = []
    for (const job of pending) {
      try {
        const response = await fetch(`/api/jobs/${job.id}`, { method: 'DELETE' })
        // Another browser window may already have deleted the same run.
        if (!response.ok && response.status !== 404) {
          const data = await response.json()
          throw new Error(data.detail || `Server error ${response.status}`)
        }
        removed.push(job.id)
      } catch (exception) { failures.push(`${label(job)}: ${exception.message}`) }
    }
    onDeleted(removed)
    setChecked(ids => ids.filter(id => !removed.includes(id)))
    setPending(null); setBusy(false); onDeletingChange(false)
    if (removed.length) setNotice(`Deleted ${removed.length} saved run${removed.length === 1 ? '' : 's'}.`)
    if (failures.length) setError(`Could not delete ${failures.length} run${failures.length === 1 ? '' : 's'}. ${failures.join(' ')}`)
  }
  return <div className="run-history">
    {notice && <p className="notice" role="status">{notice}</p>}
    {error && <p className="error" role="alert">{error}</p>}
    {!!jobs.length && <><div className="run-history-actions">
      <label className="check-label"><input ref={allCheckbox} type="checkbox" aria-label="Select all stopped runs"
        checked={allChecked} disabled={busy || !finished.length} onChange={() => setChecked(allChecked ? [] : finished.map(job => job.id))}/><span>Select all stopped runs</span></label>
      <span className="muted">{chosen.length} selected · {jobs.length} saved</span>
      <button className="danger" disabled={busy || !chosen.length} onClick={() => setPending(chosen)}>Delete selected ({chosen.length})</button>
    </div><p className="muted">Queued and running jobs must be cancelled and stopped before deletion.</p></>}
    {!jobs.length ? <p className="muted">No saved runs in this workspace yet.</p> : <div className="run-list">{jobs.map(job => {
      const canDelete = deletable.has(job.status), name = label(job)
      return <div key={job.id} className={`run-card ${selectedId === job.id ? 'selected' : ''}`}>
        <button className="run-item" aria-pressed={selectedId === job.id} onClick={() => onSelect(job.id)}>
          <span className="muted">{date(job)}</span>{children(job)}<small>{job.id.slice(0, 8)}</small>
        </button>
        <div className="run-card-actions"><label className="check-label"><input type="checkbox" aria-label={`Select ${name}`}
          checked={canDelete && checked.includes(job.id)} disabled={busy || !canDelete}
          onChange={() => setChecked(ids => ids.includes(job.id) ? ids.filter(id => id !== job.id) : [...ids, job.id])}/><span>Select</span></label>
          <button className="danger" aria-label={`Delete ${name}`} disabled={busy || !canDelete}
            title={canDelete ? 'Delete this saved run and its files' : 'Cancel and wait for this run to stop first'} onClick={() => setPending([job])}>Delete</button></div>
      </div>
    })}</div>}
    {pending && <DeleteDialog jobs={pending} busy={busy} onCancel={() => setPending(null)} onConfirm={remove}/>}
  </div>
}
