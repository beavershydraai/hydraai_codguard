import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

/** Placeholder for a screen whose sub-epic has not been built yet. */
export function ComingSoon({ epic, title }: { epic: string; title: string }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>Đang xây dựng ({epic}).</CardDescription>
      </CardHeader>
      <CardContent className="text-sm text-muted-foreground">
        Màn hình này sẽ được hoàn thiện trong sub-epic {epic}.
      </CardContent>
    </Card>
  )
}
