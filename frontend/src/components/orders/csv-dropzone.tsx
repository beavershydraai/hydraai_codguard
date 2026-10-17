import { UploadIcon, XIcon } from 'lucide-react'

import { FileType } from '@/components/reui/file-type'
import { Button } from '@/components/ui/button'
import { type FileUploadActions, type FileUploadState, formatBytes } from '@/hooks/use-file-upload'
import { cn } from '@/lib/utils'

/**
 * The drag-and-drop area of ReUI c-file-upload-3 for one CSV file. The caller owns the
 * `useFileUpload` state, so it can read the file and clear it.
 */
export function CsvDropzone({
  state: { files, isDragging },
  actions,
}: {
  state: FileUploadState
  actions: FileUploadActions
}) {
  const file = files[0]?.file instanceof File ? files[0].file : null
  return (
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
      <input {...actions.getInputProps()} className="sr-only" aria-label="Choose a CSV file" />
      <FileType type="csv" variant={file ? 'solid' : 'light'} size="lg" aria-hidden="true" />
      {file ? (
        <div className="flex items-center gap-2 text-sm">
          <span className="font-medium">{file.name}</span>
          <span className="text-muted-foreground">{formatBytes(file.size)}</span>
          <Button
            size="icon-xs"
            variant="ghost"
            aria-label="Remove file"
            onClick={() => actions.clearFiles()}
          >
            <XIcon />
          </Button>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">Drag and drop a CSV file here, or</p>
      )}
      <Button size="sm" variant={file ? 'outline' : 'default'} onClick={actions.openFileDialog}>
        <UploadIcon aria-hidden="true" />
        {file ? 'Choose another file' : 'Choose file'}
      </Button>
    </div>
  )
}
