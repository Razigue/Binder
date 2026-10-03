import { useEffect } from "react"
import { useMutation } from "@tanstack/react-query"
import { toast } from "sonner"
import { ArrowsClockwiseIcon } from "@phosphor-icons/react"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { PageHeader } from "@/components/layout/PageHeader"
import { TabList, TabPanel } from "@/components/Tabs"
import { useImportSettings, useInvalidateAll } from "@/hooks/queries"
import { useSearchTab } from "@/hooks/useSearchTab"
import { useT } from "@/i18n"
import { localAi } from "@/i18n/messages/localAi"
import { settings as messages } from "@/i18n/messages/settings"
import { api } from "@/lib/api"
import { DataCard, LocalAiCard, RecoveryCard, RemindersCard } from "./settings/AppCards"
import { FolderCard, MailCard } from "./settings/ImportCards"
import { Section } from "./settings/parts"
import { PersonalSettings } from "./settings/PersonalSettings"
import { AppearanceCard, RegionCard } from "./settings/RegionCards"

// Personal settings (who you are, your household) apart from how the app works.
const TABS = ["you", "app"] as const

export function SettingsPage() {
  const t = useT(messages)
  const [tab, setTab] = useSearchTab(TABS, "you")

  // "Correct" on the household card lands on it.
  useEffect(() => {
    const id = window.location.hash.slice(1)
    if (id) document.getElementById(id)?.scrollIntoView({ block: "start" })
  }, [tab])

  return (
    <>
      <PageHeader title={t("title")} subtitle={t("subtitle")} />
      <TabList id="settings" label={t("tab.label")} tabs={TABS} value={tab} onChange={setTab} labelOf={(key) => t(`tab.${key}`)} className="mb-2" />
      <TabPanel id="settings" value={tab} className="divide-y pt-6">
        {tab === "you" ? <PersonalSettings /> : <AppSettings />}
      </TabPanel>
    </>
  )
}

/** How the app works: language and look, automatic import, reminders, local AI, security, data. */
function AppSettings() {
  const t = useT(messages)
  const ai = useT(localAi)
  const imports = useImportSettings()
  const invalidate = useInvalidateAll()
  const run = useMutation({
    mutationFn: api.runImports,
    onSuccess: (r) => {
      void invalidate()
      const errors = [r.folder?.error, r.mail?.error].filter(Boolean)
      const imported = (r.folder?.imported ?? 0) + (r.mail?.imported ?? 0)
      if (errors.length) toast.error(errors.join(" · "))
      else if (!r.folder && !r.mail) toast.info(t("import.noSource"))
      else toast.success(imported ? t("import.imported", { count: imported }) : t("import.nothing"))
    },
  })
  const anySource = imports.data && (imports.data.folder.enabled || imports.data.mail.enabled)

  return (
    <>
      <Section title={t("region.title")} description={t("region.description")}>
        {/* Side by side only when there is room: a container query, so that it follows the text
            size (media queries do not). */}
        <div className="@container">
          <div className="grid items-start gap-6 @3xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
            <RegionCard />
            <AppearanceCard />
          </div>
        </div>
      </Section>
      <Section
        title={t("import.title")}
        description={t("import.description")}
        action={
          anySource && (
            <Button variant="outline" onClick={() => run.mutate()} disabled={run.isPending}>
              <ArrowsClockwiseIcon className={run.isPending ? "animate-spin" : ""} /> {t("import.check")}
            </Button>
          )
        }
      >
        {imports.data ? (
          <div className="grid items-start gap-6 2xl:grid-cols-2">
            {/* Remounted when the server's values change, so the form starts from them. */}
            <FolderCard key={`${imports.data.folder.enabled}:${imports.data.folder.path}`} settings={imports.data} />
            <MailCard settings={imports.data} />
          </div>
        ) : (
          <Skeleton className="h-64 w-full" />
        )}
      </Section>
      <Section title={t("reminders.title")} description={t("reminders.description")}>
        <RemindersCard />
      </Section>
      <Section title={ai("card.title")} description={ai("card.description")}>
        <LocalAiCard />
      </Section>
      <Section title={t("security.title")} description={t("security.description")}>
        <RecoveryCard />
      </Section>
      <Section title={t("data.title")} description={t("data.description")}>
        <DataCard />
      </Section>
    </>
  )
}
