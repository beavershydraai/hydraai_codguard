import { CircleAlertIcon, DownloadIcon } from 'lucide-react'
import { useState } from 'react'

import type { ImportRowError } from '@/api/gen'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Spinner } from '@/components/ui/spinner'
import { useFileUpload } from '@/hooks/use-file-upload'
import { problemMessage } from '@/lib/api'

import { CsvDropzone } from './csv-dropzone'

export type ImportSummary = {
  /** Label and count pairs, e.g. ["Imported", 120]. */
  counts: [string, number][]
  rejected: ImportRowError[]
}

/**
 * CSV import with the drag-and-drop area of ReUI c-file-upload-3 (`CsvDropzone`): pick or drop one file,
 * download a template, import, then see what was imported and which rows were rejected.
 */
export function CsvImportDialog({
  open,
  onOpenChange,
  title,
  description,
  template,
  templateName,
  onImport,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description: string
  /** Header and example rows of the downloadable template. */
  template: string[][]
  templateName: string
  onImport: (file: File) => Promise<ImportSummary>
}) {
  const [summary, setSummary] = useState<ImportSummary | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const [upload, actions] = useFileUpload({
    maxFiles: 1,
    maxSize: 10 * 1024 * 1024,
    accept: '.csv,text/csv',
    multiple: false,
  })
  const { files, errors } = upload
  const file = files[0]?.file instanceof File ? files[0].file : null

  const reset = () => {
    setSummary(null)
    setError(null)
    actions.clearFiles()
  }

  const downloadTemplate = () => {
    const csv =
      '﻿' +
      template
        .map((row) => row.map((c) => (/[",\n]/.test(c) ? `"${c.replace(/"/g, '""')}"` : c)).join(','))
        .join('\r\n')
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
    const link = document.createElement('a')
    link.href = url
    link.download = templateName
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) reset()
        onOpenChange(next)
      }}
    >
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>

        {summary ? (
          <div className="flex flex-col gap-4">
            <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {summary.counts.map(([label, value]) => (
                <div key={label} className="rounded-lg border p-3">
                  <dt className="text-xs text-muted-foreground">{label}</dt>
                  <dd className="text-xl font-semibold tabular-nums">{value.toLocaleString('en-US')}</dd>
                </div>
              ))}
            </dl>
            {summary.rejected.length > 0 && (
              <Alert variant="destructive">
                <CircleAlertIcon />
                <AlertTitle>
                  {summary.rejected.length} {summary.rejected.length === 1 ? 'row' : 'rows'} skipped
                </AlertTitle>
                <AlertDescription>
                  <ul className="max-h-40 overflow-y-auto">
                    {summary.rejected.slice(0, 50).map((r) => (
                      <li key={`${r.row}-${r.field}`}>
                        Row {r.row}
                        {r.field && ` (${r.field})`}: {r.message}
                      </li>
                    ))}
                  </ul>
                </AlertDescription>
              </Alert>
            )}
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            <CsvDropzone state={upload} actions={actions} />
            <Button variant="link" size="sm" className="self-start p-0" onClick={downloadTemplate}>
              <DownloadIcon aria-hidden="true" />
              Download template ({template[0]!.length} columns)
            </Button>
            {(errors.length > 0 || error) && (
              <Alert variant="destructive">
                <CircleAlertIcon />
                <AlertDescription>{error ?? errors.join(' ')}</AlertDescription>
              </Alert>
            )}
          </div>
        )}

        <DialogFooter>
          {summary ? (
            <>
              <Button variant="outline" onClick={reset}>
                Import another file
              </Button>
              <Button onClick={() => onOpenChange(false)}>Done</Button>
            </>
          ) : (
            <Button
              disabled={!file || pending}
              onClick={async () => {
                if (!file) return
                setPending(true)
                setError(null)
                try {
                  setSummary(await onImport(file))
                } catch (err) {
                  setError(problemMessage(err, 'Could not read the file. Check that it is a valid CSV.'))
                } finally {
                  setPending(false)
                }
              }}
            >
              {pending && <Spinner data-icon="inline-start" />}
              Import
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
