import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { ActivityList } from "@/components/ActivityList"
import { PageHeader } from "@/components/layout/AppLayout"
import { useActivity } from "@/hooks/queries"

const PAGE = 100

export function HistoryPage() {
  const [limit, setLimit] = useState(PAGE)
  const activity = useActivity({ limit })
  const more = (activity.data?.length ?? 0) >= limit
  return (
    <>
      <PageHeader title="Historique" subtitle="Tout ce que Binder et vous avez fait, du plus récent au plus ancien." />
      <Card className="gap-0 overflow-hidden p-0">
        <ActivityList entries={activity.data} loading={activity.isPending} />
      </Card>
      {more && (
        <div className="mt-4 flex justify-center">
          <Button variant="outline" onClick={() => setLimit((l) => l + PAGE)} disabled={activity.isFetching}>
            Afficher plus
          </Button>
        </div>
      )}
    </>
  )
}
