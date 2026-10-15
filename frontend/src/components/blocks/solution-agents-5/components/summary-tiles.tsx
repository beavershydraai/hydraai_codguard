import { type ReactNode, useId } from 'react'

import { Frame, FramePanel } from '@/components/ui/frame'
import { IconTile } from '@/components/reui/icon-tile'

// Review queue summary tiles, adapted from ReUI card-2 (icon-tile cards with a faded dot pattern,
// in one Frame): each tile shows a live count instead of a feature link.

export type SummaryTileItem = {
  title: string
  value: ReactNode
  note: string
  icon: ReactNode
  badge?: ReactNode
}

export function SummaryTiles({ items }: { items: SummaryTileItem[] }) {
  return (
    <Frame className="@container w-full">
      <div className="grid gap-1 @2xl:grid-cols-2 @4xl:grid-cols-4">
        {items.map((item) => (
          <SummaryTile key={item.title} item={item} />
        ))}
      </div>
    </Frame>
  )
}

function SummaryTile({ item }: { item: SummaryTileItem }) {
  return (
    <FramePanel className="isolate">
      <CardDotPattern />

      <div className="relative z-10 flex flex-col">
        <IconTile variant="elevated" className="mb-6">
          {item.icon}
        </IconTile>
        <h3 className="text-sm leading-tight font-medium">{item.title}</h3>
        <div className="flex items-center gap-2.5 pt-2">
          <span className="text-2xl font-medium tracking-tight tabular-nums">{item.value}</span>
          {item.badge}
        </div>
        <p className="pt-1.5 text-xs leading-relaxed text-muted-foreground">{item.note}</p>
      </div>
    </FramePanel>
  )
}

function CardDotPattern() {
  const id = useId().replace(/:/g, '')
  const width = 240
  const height = 136
  const patternId = `${id}-pattern`
  const maskId = `${id}-mask`
  const gradientId = `${id}-gradient`

  return (
    <div
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 z-0 [--card-dot-pattern-fill:var(--color-foreground)] [--card-dot-pattern-opacity:0.12] dark:[--card-dot-pattern-opacity:0.2]"
    >
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="size-full"
        fill="none"
        preserveAspectRatio="none"
        shapeRendering="crispEdges"
        xmlns="http://www.w3.org/2000/svg"
        style={{ opacity: 'var(--card-dot-pattern-opacity)' }}
      >
        <defs>
          <mask
            id={maskId}
            style={{ maskType: 'alpha' }}
            maskUnits="userSpaceOnUse"
            x="0"
            y="0"
            width={width}
            height={height}
          >
            <rect width={width} height={height} fill={`url(#${gradientId})`} />
          </mask>

          <linearGradient
            id={gradientId}
            x1="0"
            y1="0"
            x2="83.8613"
            y2="95.7483"
            gradientUnits="userSpaceOnUse"
          >
            <stop stopColor="white" />
            <stop offset="0.538873" stopColor="white" />
            <stop offset="1" stopColor="white" stopOpacity="0" />
          </linearGradient>

          <pattern
            id={patternId}
            patternUnits="userSpaceOnUse"
            patternTransform="matrix(48 0 0 48 0 0)"
            preserveAspectRatio="none"
            viewBox="0 0 48 48"
            width="1"
            height="1"
          >
            <g fill="var(--card-dot-pattern-fill)">
              <rect x="0" y="0" width="2" height="2" fillOpacity="0.216" />
              <rect x="4" y="0" width="2" height="2" fillOpacity="0.489" />
              <rect x="8" y="0" width="2" height="2" fillOpacity="0.366" />
              <rect x="12" y="0" width="2" height="2" fillOpacity="0.305" />
              <rect x="16" y="0" width="2" height="2" fillOpacity="0.514" />
              <rect x="20" y="0" width="2" height="2" fillOpacity="0.129" />
              <rect x="24" y="0" width="2" height="2" fillOpacity="0.431" />
              <rect x="28" y="0" width="2" height="2" fillOpacity="0.142" />
              <rect x="32" y="0" width="2" height="2" fillOpacity="0.288" />
              <rect x="36" y="0" width="2" height="2" fillOpacity="0.144" />
              <rect x="40" y="0" width="2" height="2" fillOpacity="0.313" />
              <rect x="44" y="0" width="2" height="2" fillOpacity="0.214" />
              <rect x="0" y="4" width="2" height="2" fillOpacity="0.4" />
              <rect x="4" y="4" width="2" height="2" fillOpacity="0.13" />
              <rect x="8" y="4" width="2" height="2" fillOpacity="0.498" />
              <rect x="12" y="4" width="2" height="2" fillOpacity="0.473" />
              <rect x="16" y="4" width="2" height="2" fillOpacity="0.386" />
              <rect x="20" y="4" width="2" height="2" fillOpacity="0.248" />
              <rect x="24" y="4" width="2" height="2" fillOpacity="0.168" />
              <rect x="28" y="4" width="2" height="2" fillOpacity="0.193" />
              <rect x="32" y="4" width="2" height="2" fillOpacity="0.528" />
              <rect x="36" y="4" width="2" height="2" fillOpacity="0.307" />
              <rect x="40" y="4" width="2" height="2" fillOpacity="0.314" />
              <rect x="44" y="4" width="2" height="2" fillOpacity="0.444" />
              <rect x="0" y="8" width="2" height="2" fillOpacity="0.33" />
              <rect x="4" y="8" width="2" height="2" fillOpacity="0.438" />
              <rect x="8" y="8" width="2" height="2" fillOpacity="0.477" />
              <rect x="12" y="8" width="2" height="2" fillOpacity="0.434" />
              <rect x="16" y="8" width="2" height="2" fillOpacity="0.47" />
              <rect x="20" y="8" width="2" height="2" fillOpacity="0.383" />
              <rect x="24" y="8" width="2" height="2" fillOpacity="0.514" />
              <rect x="28" y="8" width="2" height="2" fillOpacity="0.287" />
              <rect x="32" y="8" width="2" height="2" fillOpacity="0.346" />
              <rect x="36" y="8" width="2" height="2" fillOpacity="0.52" />
              <rect x="40" y="8" width="2" height="2" fillOpacity="0.524" />
              <rect x="44" y="8" width="2" height="2" fillOpacity="0.126" />
              <rect x="0" y="12" width="2" height="2" fillOpacity="0.259" />
              <rect x="4" y="12" width="2" height="2" fillOpacity="0.281" />
              <rect x="8" y="12" width="2" height="2" fillOpacity="0.311" />
              <rect x="12" y="12" width="2" height="2" fillOpacity="0.212" />
              <rect x="16" y="12" width="2" height="2" fillOpacity="0.524" />
              <rect x="20" y="12" width="2" height="2" fillOpacity="0.353" />
              <rect x="24" y="12" width="2" height="2" fillOpacity="0.34" />
              <rect x="28" y="12" width="2" height="2" fillOpacity="0.417" />
              <rect x="32" y="12" width="2" height="2" fillOpacity="0.258" />
              <rect x="36" y="12" width="2" height="2" fillOpacity="0.158" />
              <rect x="40" y="12" width="2" height="2" fillOpacity="0.388" />
              <rect x="44" y="12" width="2" height="2" fillOpacity="0.184" />
              <rect x="0" y="16" width="2" height="2" fillOpacity="0.491" />
              <rect x="4" y="16" width="2" height="2" fillOpacity="0.417" />
              <rect x="8" y="16" width="2" height="2" fillOpacity="0.231" />
              <rect x="12" y="16" width="2" height="2" fillOpacity="0.209" />
              <rect x="16" y="16" width="2" height="2" fillOpacity="0.305" />
              <rect x="20" y="16" width="2" height="2" fillOpacity="0.287" />
              <rect x="24" y="16" width="2" height="2" fillOpacity="0.353" />
              <rect x="28" y="16" width="2" height="2" fillOpacity="0.513" />
              <rect x="32" y="16" width="2" height="2" fillOpacity="0.483" />
              <rect x="36" y="16" width="2" height="2" fillOpacity="0.455" />
              <rect x="40" y="16" width="2" height="2" fillOpacity="0.483" />
              <rect x="44" y="16" width="2" height="2" fillOpacity="0.189" />
              <rect x="0" y="20" width="2" height="2" fillOpacity="0.264" />
              <rect x="4" y="20" width="2" height="2" fillOpacity="0.295" />
              <rect x="8" y="20" width="2" height="2" fillOpacity="0.51" />
              <rect x="12" y="20" width="2" height="2" fillOpacity="0.305" />
              <rect x="16" y="20" width="2" height="2" fillOpacity="0.438" />
              <rect x="20" y="20" width="2" height="2" fillOpacity="0.289" />
              <rect x="24" y="20" width="2" height="2" fillOpacity="0.322" />
              <rect x="28" y="20" width="2" height="2" fillOpacity="0.196" />
              <rect x="32" y="20" width="2" height="2" fillOpacity="0.486" />
              <rect x="36" y="20" width="2" height="2" fillOpacity="0.388" />
              <rect x="40" y="20" width="2" height="2" fillOpacity="0.489" />
              <rect x="44" y="20" width="2" height="2" fillOpacity="0.208" />
              <rect x="0" y="24" width="2" height="2" fillOpacity="0.239" />
              <rect x="4" y="24" width="2" height="2" fillOpacity="0.463" />
              <rect x="8" y="24" width="2" height="2" fillOpacity="0.539" />
              <rect x="12" y="24" width="2" height="2" fillOpacity="0.408" />
              <rect x="16" y="24" width="2" height="2" fillOpacity="0.527" />
              <rect x="20" y="24" width="2" height="2" fillOpacity="0.357" />
              <rect x="24" y="24" width="2" height="2" fillOpacity="0.362" />
              <rect x="28" y="24" width="2" height="2" fillOpacity="0.151" />
              <rect x="32" y="24" width="2" height="2" fillOpacity="0.324" />
              <rect x="36" y="24" width="2" height="2" fillOpacity="0.347" />
              <rect x="40" y="24" width="2" height="2" fillOpacity="0.299" />
              <rect x="44" y="24" width="2" height="2" fillOpacity="0.127" />
              <rect x="0" y="28" width="2" height="2" fillOpacity="0.476" />
              <rect x="4" y="28" width="2" height="2" fillOpacity="0.461" />
              <rect x="8" y="28" width="2" height="2" fillOpacity="0.377" />
              <rect x="12" y="28" width="2" height="2" fillOpacity="0.415" />
              <rect x="16" y="28" width="2" height="2" fillOpacity="0.217" />
              <rect x="20" y="28" width="2" height="2" fillOpacity="0.297" />
              <rect x="24" y="28" width="2" height="2" fillOpacity="0.258" />
              <rect x="28" y="28" width="2" height="2" fillOpacity="0.296" />
              <rect x="32" y="28" width="2" height="2" fillOpacity="0.276" />
              <rect x="36" y="28" width="2" height="2" fillOpacity="0.182" />
              <rect x="40" y="28" width="2" height="2" fillOpacity="0.422" />
              <rect x="44" y="28" width="2" height="2" fillOpacity="0.392" />
              <rect x="0" y="32" width="2" height="2" fillOpacity="0.273" />
              <rect x="4" y="32" width="2" height="2" fillOpacity="0.143" />
              <rect x="8" y="32" width="2" height="2" fillOpacity="0.338" />
              <rect x="12" y="32" width="2" height="2" fillOpacity="0.264" />
              <rect x="16" y="32" width="2" height="2" fillOpacity="0.218" />
              <rect x="20" y="32" width="2" height="2" fillOpacity="0.29" />
              <rect x="24" y="32" width="2" height="2" fillOpacity="0.336" />
              <rect x="28" y="32" width="2" height="2" fillOpacity="0.313" />
              <rect x="32" y="32" width="2" height="2" fillOpacity="0.514" />
              <rect x="36" y="32" width="2" height="2" fillOpacity="0.289" />
              <rect x="40" y="32" width="2" height="2" fillOpacity="0.25" />
              <rect x="44" y="32" width="2" height="2" fillOpacity="0.507" />
              <rect x="0" y="36" width="2" height="2" fillOpacity="0.346" />
              <rect x="4" y="36" width="2" height="2" fillOpacity="0.208" />
              <rect x="8" y="36" width="2" height="2" fillOpacity="0.313" />
              <rect x="12" y="36" width="2" height="2" fillOpacity="0.365" />
              <rect x="16" y="36" width="2" height="2" fillOpacity="0.491" />
              <rect x="20" y="36" width="2" height="2" fillOpacity="0.121" />
              <rect x="24" y="36" width="2" height="2" fillOpacity="0.472" />
              <rect x="28" y="36" width="2" height="2" fillOpacity="0.281" />
              <rect x="32" y="36" width="2" height="2" fillOpacity="0.297" />
              <rect x="36" y="36" width="2" height="2" fillOpacity="0.33" />
              <rect x="40" y="36" width="2" height="2" fillOpacity="0.463" />
              <rect x="44" y="36" width="2" height="2" fillOpacity="0.447" />
              <rect x="0" y="40" width="2" height="2" fillOpacity="0.217" />
              <rect x="4" y="40" width="2" height="2" fillOpacity="0.467" />
              <rect x="8" y="40" width="2" height="2" fillOpacity="0.297" />
              <rect x="12" y="40" width="2" height="2" fillOpacity="0.303" />
              <rect x="16" y="40" width="2" height="2" fillOpacity="0.497" />
              <rect x="20" y="40" width="2" height="2" fillOpacity="0.201" />
              <rect x="24" y="40" width="2" height="2" fillOpacity="0.5" />
              <rect x="28" y="40" width="2" height="2" fillOpacity="0.458" />
              <rect x="32" y="40" width="2" height="2" fillOpacity="0.165" />
              <rect x="36" y="40" width="2" height="2" fillOpacity="0.36" />
              <rect x="40" y="40" width="2" height="2" fillOpacity="0.329" />
              <rect x="44" y="40" width="2" height="2" fillOpacity="0.419" />
              <rect x="0" y="44" width="2" height="2" fillOpacity="0.47" />
              <rect x="4" y="44" width="2" height="2" fillOpacity="0.161" />
              <rect x="8" y="44" width="2" height="2" fillOpacity="0.191" />
              <rect x="12" y="44" width="2" height="2" fillOpacity="0.341" />
              <rect x="16" y="44" width="2" height="2" fillOpacity="0.279" />
              <rect x="20" y="44" width="2" height="2" fillOpacity="0.387" />
              <rect x="24" y="44" width="2" height="2" fillOpacity="0.173" />
              <rect x="28" y="44" width="2" height="2" fillOpacity="0.537" />
              <rect x="32" y="44" width="2" height="2" fillOpacity="0.218" />
              <rect x="36" y="44" width="2" height="2" fillOpacity="0.368" />
              <rect x="40" y="44" width="2" height="2" fillOpacity="0.5" />
              <rect x="44" y="44" width="2" height="2" fillOpacity="0.414" />
            </g>
          </pattern>
        </defs>
        <g mask={`url(#${maskId})`}>
          <rect width={width} height={height} fill={`url(#${patternId})`} />
        </g>
      </svg>
    </div>
  )
}
