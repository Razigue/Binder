import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { ActivityList } from "@/components/ActivityList"
import { PageHeader } from "@/components/layout/PageHeader"
import { useActivity } from "@/hooks/queries"
import { useT } from "@/i18n"
import { history } from "@/i18n/messages/history"

const PAGE = 100

export function HistoryPage() {
  const t = useT(history)
  const [limit, setLimit] = useState(PAGE)
  const activity = useActivity({ limit })
  const more = (activity.data?.length ?? 0) >= limit
  return (
    <>
      <PageHeader title={t("title")} subtitle={t("subtitle")} />
      <Card className="gap-0 overflow-hidden p-0">
        <ActivityList entries={activity.data} loading={activity.isPending} />
      </Card>
      {more && (
        <div className="mt-4 flex justify-center">
          <Button variant="outline" onClick={() => setLimit((l) => l + PAGE)} disabled={activity.isFetching}>
            {t("more")}
          </Button>
        </div>
      )}
    </>
  )
}
