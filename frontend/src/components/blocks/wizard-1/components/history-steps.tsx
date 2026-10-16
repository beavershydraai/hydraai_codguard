import { useMutation, useQuery } from '@tanstack/react-query'
import { CheckCircle2Icon, SparklesIcon, UploadIcon } from 'lucide-react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import type { HistoryImportResult, ModelHealth } from '@/api/gen'
import {
  getModelHealthOptions,
  importHistoryMutation,
  updateModelsMutation,
} from '@/api/gen/@tanstack/react-query.gen'
import { Button } from '@/components/ui/button'
import { Field, FieldDescription, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { problemMessage } from '@/lib/api'
import { COUNTRY_LABELS, formatDateTime, formatPercent } from '@/lib/labels'

// Onboarding steps 3 and 4: the shop uploads its past orders with their delivery results
// (POST /shop/history, checked row by row), then the risk models learn from them
// (POST /dashboard/model-health/update, progress from GET /dashboard/model-health).

export function HistoryStep({ onDone }: { onDone: (result: HistoryImportResult | null) => void }) {
  const [file, setFile] = useState<File | null>(null)
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
      <Field>
        <FieldLabel htmlFor="onb-history">Order history (CSV)</FieldLabel>
        <Input
          id="onb-history"
          type="file"
          accept=".csv,text/csv"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
        />
        <FieldDescription>
          The columns of the order import, plus branch_id, delivery_result and outcome_at. Up to 20,000
          orders.
        </FieldDescription>
      </Field>
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

function HistoryReport({ result }: { result: HistoryImportResult }) {
  return (
    <div className="flex flex-col gap-3 rounded-lg border p-3">
      <p className="flex items-center gap-2 font-medium">
        <CheckCircle2Icon className="size-4 text-success" aria-hidden="true" />
        {result.imported.toLocaleString('en-US')} of {result.received.toLocaleString('en-US')} orders imported
        {result.rejected_count > 0 && `, ${result.rejected_count.toLocaleString('en-US')} rows rejected`}
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-xs tabular-nums">
          <thead className="text-muted-foreground">
            <tr>
              <th className="py-1 text-left font-normal">Country</th>
              <th className="py-1 text-right font-normal">Orders</th>
              <th className="py-1 text-right font-normal">Delivered</th>
              <th className="py-1 text-right font-normal">Failed</th>
              <th className="py-1 text-right font-normal">Failure rate</th>
            </tr>
          </thead>
          <tbody>
            {result.countries.map((c) => (
              <tr key={c.country} className="border-t">
                <td className="py-1">{COUNTRY_LABELS[c.country] ?? c.country}</td>
                <td className="py-1 text-right">{c.orders.toLocaleString('en-US')}</td>
                <td className="py-1 text-right">{c.delivered.toLocaleString('en-US')}</td>
                <td className="py-1 text-right">{c.failed.toLocaleString('en-US')}</td>
                <td className="py-1 text-right">
                  {c.delivered + c.failed ? formatPercent(c.failed / (c.delivered + c.failed), 1) : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {result.rejected.length > 0 && (
        <ul className="flex flex-col gap-0.5 text-xs text-muted-foreground">
          {result.rejected.slice(0, 5).map((r) => (
            <li key={`${r.row}-${r.field}`}>
              Row {r.row}
              {r.field && ` · ${r.field}`}: {r.message}
            </li>
          ))}
        </ul>
      )}
      <p className="text-xs text-muted-foreground">
        Failed counts refused and unreachable deliveries only: carrier and shop issues are not the buyer's.
      </p>
    </div>
  )
}

export function TrainStep({ onDone }: { onDone: () => void }) {
  const [startedAt, setStartedAt] = useState<string | null>(null)
  const health = useQuery({
    ...getModelHealthOptions(),
    refetchInterval: (q) => (startedAt && (q.state.data?.some((m) => m.updating) ?? true) ? 5_000 : false),
  })
  const train = useMutation({
    ...updateModelsMutation(),
    onSuccess: () => setStartedAt(new Date().toISOString()),
    onError: (error) => toast.error('Could not start learning', { description: problemMessage(error) }),
  })
  const models = health.data ?? []
  const learned = (m: ModelHealth) =>
    !!startedAt && !m.updating && !!m.trained_at && m.trained_at >= startedAt
  const done = models.length > 0 && models.every(learned)
  useEffect(() => {
    if (done) onDone()
  }, [done, onDone])

  return (
    <div className="flex flex-col gap-4">
      <p className="text-muted-foreground">
        COD Guard trains one risk model per country, on your history together with the orders it already
        knows. It takes about 2 to 3 minutes; you can keep this page open.
      </p>
      {!startedAt ? (
        <Button type="button" onClick={() => train.mutate({})} disabled={train.isPending} className="w-fit">
          {train.isPending ? <Spinner data-icon="inline-start" /> : <SparklesIcon aria-hidden="true" />}
          Train my risk model
        </Button>
      ) : (
        <ul className="flex flex-col divide-y rounded-lg border">
          {models.map((m) => (
            <li key={m.country} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2.5">
              <span className="font-medium">{COUNTRY_LABELS[m.country] ?? m.country}</span>
              {learned(m) ? (
                <span className="flex items-center gap-1.5 text-xs">
                  <CheckCircle2Icon className="size-4 text-success" aria-hidden="true" />
                  Learned from {(m.training_orders ?? 0).toLocaleString('en-US')} orders
                  {m.lift_top20 != null && ` · finds ${m.lift_top20.toFixed(1)}× more failed deliveries`}
                </span>
              ) : (
                <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Spinner className="size-3.5" /> Learning…
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
      {done && (
        <p className="rounded-lg bg-success/10 p-3 text-sm">
          <span className="font-medium">You're all set.</span> New orders are scored with your models from now
          on ({formatDateTime(models[0]!.trained_at!)}).
        </p>
      )}
    </div>
  )
}
