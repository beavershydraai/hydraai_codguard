import { CircleAlertIcon, DownloadIcon, FileSpreadsheetIcon, UploadIcon, XIcon } from 'lucide-react'
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
import { formatBytes, useFileUpload } from '@/hooks/use-file-upload'
import { problemMessage } from '@/lib/api'
import { cn } from '@/lib/utils'

export type ImportSummary = {
  /** Label and count pairs, e.g. ["Đã nhập", 120]. */
  counts: [string, number][]
  rejected: ImportRowError[]
}

/**
 * CSV import with the drag-and-drop area of ReUI c-file-upload-3: pick or drop one file,
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
  const [{ files, isDragging, errors }, actions] = useFileUpload({
    maxFiles: 1,
    maxSize: 10 * 1024 * 1024,
    accept: '.csv,text/csv',
    multiple: false,
  })
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
                  <dd className="text-xl font-semibold tabular-nums">{value.toLocaleString('vi-VN')}</dd>
                </div>
              ))}
            </dl>
            {summary.rejected.length > 0 && (
              <Alert variant="destructive">
                <CircleAlertIcon />
                <AlertTitle>{summary.rejected.length} dòng bị bỏ qua</AlertTitle>
                <AlertDescription>
                  <ul className="max-h-40 overflow-y-auto">
                    {summary.rejected.slice(0, 50).map((r) => (
                      <li key={`${r.row}-${r.field}`}>
                        Dòng {r.row}
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
            <div
              className={cn(
                'flex flex-col items-center gap-3 rounded-lg border border-dashed p-6 text-center transition-colors',
                isDragging
                  ? 'border-primary bg-primary/5'
                  : 'border-muted-foreground/25 hover:border-muted-foreground/50',
              )}
              onDragEnter={actions.handleDragEnter}
              onDragLeave={actions.handleDragLeave}
              onDragOver={actions.handleDragOver}
              onDrop={actions.handleDrop}
            >
              <input {...actions.getInputProps()} className="sr-only" aria-label="Chọn file CSV" />
              <FileSpreadsheetIcon className="size-8 text-muted-foreground" aria-hidden="true" />
              {file ? (
                <div className="flex items-center gap-2 text-sm">
                  <span className="font-medium">{file.name}</span>
                  <span className="text-muted-foreground">{formatBytes(file.size)}</span>
                  <Button
                    size="icon-xs"
                    variant="ghost"
                    aria-label="Bỏ file"
                    onClick={() => actions.clearFiles()}
                  >
                    <XIcon />
                  </Button>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">Kéo thả file CSV vào đây, hoặc</p>
              )}
              <Button size="sm" variant={file ? 'outline' : 'default'} onClick={actions.openFileDialog}>
                <UploadIcon aria-hidden="true" />
                {file ? 'Chọn file khác' : 'Chọn file'}
              </Button>
            </div>
            <Button variant="link" size="sm" className="self-start p-0" onClick={downloadTemplate}>
              <DownloadIcon aria-hidden="true" />
              Tải file mẫu ({template[0]!.length} cột)
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
                Nhập file khác
              </Button>
              <Button onClick={() => onOpenChange(false)}>Xong</Button>
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
                  setError(problemMessage(err, 'Không đọc được file. Kiểm tra lại định dạng CSV.'))
                } finally {
                  setPending(false)
                }
              }}
            >
              {pending && <Spinner data-icon="inline-start" />}
              Nhập
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
