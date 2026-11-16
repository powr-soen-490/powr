// Source-File AI Declaration
// AI contribution: 50% or more AI-generated

import { Button } from './Button'
import { Icon } from './Icon'

// Last-sync line with a "Sync now" button, or a progress bar while a sync is running.
export function SyncStatus({ text, onSync, progress }: { text: string; onSync?: () => void; progress?: number }) {
  if (progress !== undefined) {
    return (
      <div className="sync-status running">
        <span className="sync-text"><Icon name="refresh" />{text}</span>
        <div className="progress" role="progressbar" aria-label={text} aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}>
          <div style={{ width: `${progress}%` }} />
        </div>
      </div>
    )
  }
  return (
    <div className="sync-status">
      <span className="sync-text"><Icon name="check" />{text}</span>
      {onSync && <Button size="sm" icon="refresh" onClick={onSync}>Sync now</Button>}
    </div>
  )
}
