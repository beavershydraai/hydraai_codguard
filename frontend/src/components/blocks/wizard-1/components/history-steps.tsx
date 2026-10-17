import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { type ColumnDef, useTable } from '@tanstack/react-table'
import { CheckCircle2Icon, CircleAlertIcon, PartyPopperIcon, SparklesIcon, UploadIcon } from 'lucide-react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import type { HistoryCountry, HistoryImportResult, ModelHealth } from '@/api/gen'
import {
  getModelHealthOptions,
  importHistoryMutation,
  updateModelsMutation,
} from '@/api/gen/@tanstack/react-query.gen'
import { CsvDropzone } from '@/components/orders/csv-dropzone'
import { Alert, AlertDescription, AlertTitle } from '@/components/reui/alert'
import { Badge } from '@/components/reui/badge'
import { DataGrid, type DataGridFeatures, dataGridFeatures } from '@/components/reui/data-grid/data-grid'
import { DataGridTable } from '@/components/reui/data-grid/data-grid-table'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { useFileUpload } from '@/hooks/use-file-upload'
import { isProblem, problemMessage } from '@/lib/api'
import { COUNTRY_LABELS, formatPercent } from '@/lib/labels'

// Onboarding steps 3 and 4: the shop uploads its past orders with their delivery results
// (POST /shop/history, checked row by row), then the risk models learn from them
// (POST /dashboard/model-health/update, progress from GET /dashboard/model-health).

export function HistoryStep({ onDone }: { onDone: (result: HistoryImportResult | null) => void }) {
  const [picked, actions] = useFileUpload({
    maxFiles: 1,
    maxSize: 20 * 1024 * 1024,
    accept: '.csv,text/csv',
    multiple: false,
  })
  const file = picked.files[0]?.file instanceof File ? picked.files[0].file : null
  const upload = useMutation({
    ...importHistoryMutation(),
    onSuccess: (result) => onDone(result),
    onError: (error) => toast.error('Could not import the file', { description: problemMessage(error) }),
  })
  const result = upload.data

  return (
    <div className="flex flex-col gap-4">
      <p className="text-muted-foreground">
        Upload your past orders with their delivery results. COD Guard checks every row, keeps the valid ones
        and learns from them which orders end in a failed delivery.
      </p>
      <div className="flex flex-col gap-1.5">
        <CsvDropzone state={picked} actions={actions} />
        <p className="text-xs text-muted-foreground">
          The columns of the order import, plus branch_id, delivery_result and outcome_at. Up to 20,000
          orders.
        </p>
      </div>
      {picked.errors.length > 0 && (
        <Alert variant="destructive">
          <CircleAlertIcon />
          <AlertDescription>{picked.errors.join(' ')}</AlertDescription>
        </Alert>
      )}
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          onClick={() => file && upload.mutate({ body: { file } })}
          disabled={!file || upload.isPending}
        >
          {upload.isPending ? <Spinner data-icon="inline-start" /> : <UploadIcon aria-hidden="true" />}
          {upload.isPending ? 'Checking and importing…' : 'Upload and check'}
        </Button>
        {!result && (
          <Button type="button" variant="ghost" onClick={() => onDone(null)}>
            Skip: no past orders yet
          </Button>
        )}
      </div>
      {result && <HistoryReport result={result} />}
    </div>
  )
}

const failureRate = (c: HistoryCountry) =>
  c.delivered + c.failed ? formatPercent(c.failed / (c.delivered + c.failed), 1) : '—'

const number = (n: number) => n.toLocaleString('en-US')

const right = { headerClassName: 'text-right', cellClassName: 'text-right tabular-nums' }

const countryColumns: ColumnDef<DataGridFeatures, HistoryCountry>[] = [
  {
    id: 'country',
    accessorFn: (c) => COUNTRY_LABELS[c.country] ?? c.country,
    header: 'Country',
    size: 140,
  },
  { id: 'orders', accessorFn: (c) => number(c.orders), header: 'Orders', meta: right, size: 90 },
  { id: 'delivered', accessorFn: (c) => number(c.delivered), header: 'Delivered', meta: right, size: 90 },
  { id: 'failed', accessorFn: (c) => number(c.failed), header: 'Failed', meta: right, size: 90 },
  { id: 'failure_rate', accessorFn: failureRate, header: 'Failure rate', meta: right, size: 100 },
]

function HistoryReport({ result }: { result: HistoryImportResult }) {
  const table = useTable({
    features: dataGridFeatures,
    columns: countryColumns,
    data: result.countries,
    getRowId: (c) => c.country,
  })

  return (
    <div className="flex flex-col gap-3">
      <Alert variant="success" role="status">
        <CheckCircle2Icon />
        <AlertTitle>
          {number(result.imported)} of {number(result.received)} orders imported
        </AlertTitle>
        <AlertDescription>
          Failed counts refused and unreachable deliveries only: carrier and shop issues are not the buyer's.
        </AlertDescription>
      </Alert>
      <DataGrid
        table={table}
        recordCount={result.countries.length}
        tableLayout={{ dense: true, width: 'auto', headerBackground: true }}
      >
        <div className="overflow-x-auto rounded-lg border">
          <DataGridTable />
        </div>
      </DataGrid>
      {result.rejected_count > 0 && (
        <Alert variant="warning">
          <CircleAlertIcon />
          <AlertTitle>
            {number(result.rejected_count)} {result.rejected_count === 1 ? 'row' : 'rows'} rejected
          </AlertTitle>
          <AlertDescription>
            <ul className="flex flex-col gap-0.5">
              {result.rejected.slice(0, 5).map((r) => (
                <li key={`${r.row}-${r.field}`}>
                  Row {r.row}
                  {r.field && ` · ${r.field}`}: {r.message}
                </li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}
    </div>
  )
}

export function TrainStep({ trained, onDone }: { trained: boolean; onDone: () => void }) {
  const [started, setStarted] = useState(trained)
  const queryClient = useQueryClient()
  // The server says when an update runs (`updating`) and how the last one ended (`last_update`),
  // also when it kept the current model because the new one was not better.
  const health = useQuery({
    ...getModelHealthOptions(),
    refetchInterval: (q) => (q.state.data?.some((m) => m.updating) ? 5_000 : false),
  })
  const models = health.data ?? []
  const running = models.some((m) => m.updating)
  // An update already running (started here before going back, or by another shop) is followed.
  if (running && !started) setStarted(true)
  const train = useMutation({
    ...updateModelsMutation(),
    onSuccess: (next) => {
      queryClient.setQueryData(getModelHealthOptions().queryKey, next)
      setStarted(true)
    },
    onError: (error) => {
      if (isProblem(error) && error.status === 409) void health.refetch()
      else toast.error('Could not start learning', { description: problemMessage(error) })
    },
  })
  const done = started && !running && models.length > 0
  useEffect(() => {
    if (done) onDone()
  }, [done, onDone])

  return (
    <div className="flex flex-col gap-4">
      <p className="text-muted-foreground">
        COD Guard trains one risk model per country, on your history together with the orders it already
        knows. It takes about 2 to 3 minutes; you can keep this page open.
      </p>
      {!started ? (
        <Button type="button" onClick={() => train.mutate({})} disabled={train.isPending} className="w-fit">
          {train.isPending ? <Spinner data-icon="inline-start" /> : <SparklesIcon aria-hidden="true" />}
          Train my risk model
        </Button>
      ) : (
        <ul className="flex flex-col divide-y rounded-lg border">
          {models.map((m) => (
            <li key={m.country} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2.5">
              <span className="font-medium">{COUNTRY_LABELS[m.country] ?? m.country}</span>
              {m.updating ? (
                <Badge variant="info-light">
                  <Spinner className="size-3" />
                  Learning…
                </Badge>
              ) : (
                <ModelResult model={m} />
              )}
            </li>
          ))}
        </ul>
      )}
      {done && (
        <Alert variant="success" role="status">
          <PartyPopperIcon />
          <AlertTitle>You're all set</AlertTitle>
          <AlertDescription>New orders are scored with these models from now on.</AlertDescription>
        </Alert>
      )}
    </div>
  )
}

function ModelResult({ model: m }: { model: ModelHealth }) {
  const finds = m.lift_top20 != null ? `finds ${m.lift_top20.toFixed(1)}× more failed deliveries` : null
  if (!m.last_update)
    return <span className="text-xs text-muted-foreground">No orders to learn from yet</span>
  return (
    <span className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
      <Badge variant="success-light">
        <CheckCircle2Icon aria-hidden="true" />
        {m.last_update.replaced ? 'Learned' : 'Checked'}
      </Badge>
      {m.last_update.replaced
        ? `from ${number(m.last_update.orders)} orders, yours included${finds ? ` · ${finds}` : ''}`
        : `on ${number(m.last_update.orders)} orders, yours included · the model in use stays: the new one was not better${finds ? ` (${finds})` : ''}`}
    </span>
  )
}
