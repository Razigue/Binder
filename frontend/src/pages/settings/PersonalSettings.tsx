import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { PencilSimpleIcon, UserMinusIcon, UserPlusIcon } from "@phosphor-icons/react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { Textarea } from "@/components/ui/textarea"
import { keys, useHousehold, useInvalidateAll, useProfile, useSaveSituation } from "@/hooks/queries"
import { useT } from "@/i18n"
import { essentials } from "@/i18n/messages/essentials"
import { settings as messages } from "@/i18n/messages/settings"
import { api, type Member, type MemberEdit, type Profile } from "@/lib/api"
import { OPTIONS, QUESTIONS } from "@/lib/essentials"
import { Field, Section } from "./parts"

/** Who the user is: their details, their situation, their household. */
export function PersonalSettings() {
  const t = useT(messages)
  return (
    <>
      <Section title={t("you.title")} description={t("you.description")}>
        <ProfileCard />
      </Section>
      <Section title={t("situation.title")} description={t("situation.description")}>
        <SituationCard />
      </Section>
      <Section id="household" title={t("household.title")} description={t("household.description")}>
        <HouseholdCard />
      </Section>
    </>
  )
}

// --- About you ---------------------------------------------------------------------------------

const EMPTY_PROFILE: Profile = { name: "", address: "", city: "", email: "", phone: "", notes: "", auto: [] }

function ProfileCard() {
  const profile = useProfile({ fresh: true })
  if (!profile.data) return <Skeleton className="h-80 w-full" />
  // Remounted when Binder or the agent changes the details, so the form shows them.
  return <ProfileForm key={JSON.stringify(profile.data)} initial={{ ...EMPTY_PROFILE, ...profile.data }} />
}

function ProfileForm({ initial }: { initial: Profile }) {
  const t = useT(messages)
  const [form, setForm] = useState<Profile>(initial)
  const queryClient = useQueryClient()
  const save = useMutation({
    mutationFn: () => api.saveProfile(form),
    onSuccess: (saved) => {
      queryClient.setQueryData(keys.profile, saved)
      toast.success(t("saved"))
    },
    onError: (e) => toast.error(e.message),
  })
  const set = (patch: Partial<Profile>) => setForm((f) => ({ ...f, ...patch }))
  // Filled by Binder from the documents, and not changed since.
  const found = (field: "name" | "address" | "city" | "email" | "phone") =>
    initial.auto.includes(field) && form[field] === initial[field] ? t("you.found") : undefined

  return (
    <Card className="gap-5 p-6">
      <div className="grid gap-x-6 gap-y-4 md:grid-cols-2">
        <Field id="profile-name" label={t("you.name")} hint={found("name")}>
          <Input id="profile-name" value={form.name} onChange={(e) => set({ name: e.target.value })} autoComplete="name" />
        </Field>
        <Field id="profile-city" label={t("you.city")} hint={found("city")}>
          <Input id="profile-city" value={form.city} onChange={(e) => set({ city: e.target.value })} />
        </Field>
        <Field id="profile-address" label={t("you.address")} hint={found("address")} className="md:row-span-2">
          <Textarea
            id="profile-address"
            value={form.address}
            onChange={(e) => set({ address: e.target.value })}
            rows={4}
            autoComplete="street-address"
            className="min-h-[7.5rem]"
          />
        </Field>
        <Field id="profile-email" label={t("you.email")} hint={found("email")}>
          <Input id="profile-email" type="email" value={form.email} onChange={(e) => set({ email: e.target.value })} autoComplete="email" />
        </Field>
        <Field id="profile-phone" label={t("you.phone")} hint={found("phone")}>
          <Input id="profile-phone" type="tel" value={form.phone} onChange={(e) => set({ phone: e.target.value })} autoComplete="tel" />
        </Field>
        <Field id="profile-notes" label={t("you.notes")} hint={t("you.notesHint")} className="md:col-span-2">
          <Textarea
            id="profile-notes"
            value={form.notes}
            onChange={(e) => set({ notes: e.target.value })}
            placeholder={t("you.notesPlaceholder")}
            maxLength={2000}
            rows={4}
          />
        </Field>
      </div>
      <div>
        <Button onClick={() => save.mutate()} disabled={save.isPending}>
          {t("save")}
        </Button>
      </div>
    </Card>
  )
}

// --- Situation: the three answers of the first launch, to change at any time ----------------

function SituationCard() {
  const t = useT(messages)
  const te = useT(essentials)
  const profile = useProfile({ fresh: true })
  const save = useSaveSituation(() => toast.success(t("saved")))
  if (!profile.data) return <Skeleton className="h-32 w-full" />
  const data = profile.data
  return (
    <Card className="p-6">
      <div className="grid gap-4 md:grid-cols-3">
        {QUESTIONS.map((question) => {
          const items = Object.fromEntries(OPTIONS[question].map(([value, label]) => [value, te(label)]))
          return (
            <Field key={question} id={`situation-${question}`} label={te(`${question}.question`)}>
              <Select
                items={items}
                value={data[question] || null}
                onValueChange={(value) => value && value !== data[question] && save.mutate({ [question]: value })}
                disabled={save.isPending}
              >
                <SelectTrigger id={`situation-${question}`} className="w-full">
                  <SelectValue placeholder="—" />
                </SelectTrigger>
                <SelectContent>
                  {OPTIONS[question].map(([value, label]) => (
                    <SelectItem key={value} value={value}>
                      {te(label)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
          )
        })}
      </div>
    </Card>
  )
}

// --- Household: the people Binder found in the documents, as the user corrects it -------------

function HouseholdCard() {
  const t = useT(messages)
  const queryClient = useQueryClient()
  const invalidate = useInvalidateAll()
  const members = useHousehold()
  const [renaming, setRenaming] = useState<string | null>(null)
  const [adding, setAdding] = useState("")
  const edit = useMutation({
    mutationFn: (body: MemberEdit) => api.editHousehold(body),
    onSuccess: (list) => {
      queryClient.setQueryData(keys.household, list)
      // Names change on the documents and the details may follow: everything is refreshed.
      void invalidate()
      setRenaming(null)
      setAdding("")
      toast.success(t("household.saved"))
    },
    onError: (e) => toast.error(e.message),
  })
  if (!members.data) return <Skeleton className="h-48 w-full" />
  const list = members.data

  return (
    <Card className="gap-0 p-0">
      {list.length === 0 ? (
        <p className="p-6 text-sm text-muted-foreground">{t("household.empty")}</p>
      ) : (
        <ul className="divide-y">
          {list.map((m) => (
            <li key={m.name} className="px-6 py-4">
              {renaming === m.name ? (
                <RenameMember
                  member={m}
                  others={list.filter((o) => o.name !== m.name)}
                  busy={edit.isPending}
                  onRename={(name) => edit.mutate({ action: "rename", name: m.name, new_name: name })}
                  onCancel={() => setRenaming(null)}
                />
              ) : (
                <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium">{m.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {m.added && m.documents === 0 ? t("household.added") : t("household.documents", { count: m.documents })}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    <Button size="sm" variant="outline" disabled={edit.isPending} onClick={() => setRenaming(m.name)}>
                      <PencilSimpleIcon /> {t("household.rename")}
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-muted-foreground"
                      aria-label={t("household.removeLabel", { name: m.name })}
                      disabled={edit.isPending}
                      onClick={() => edit.mutate({ action: "remove", name: m.name })}
                    >
                      <UserMinusIcon /> {t("household.remove")}
                    </Button>
                  </div>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      <form
        className="flex flex-wrap items-end gap-2 border-t p-6"
        onSubmit={(e) => {
          e.preventDefault()
          if (adding.trim()) edit.mutate({ action: "add", name: adding.trim() })
        }}
      >
        <Field id="member-add" label={t("household.addLabel")} className="min-w-0 flex-1">
          <Input
            id="member-add"
            value={adding}
            onChange={(e) => setAdding(e.target.value)}
            placeholder={t("household.addPlaceholder")}
            autoComplete="off"
            maxLength={120}
          />
        </Field>
        <Button type="submit" variant="outline" disabled={edit.isPending || !adding.trim()}>
          <UserPlusIcon /> {t("household.add")}
        </Button>
      </form>
    </Card>
  )
}

/** Renaming a person; another person's name merges the two. */
function RenameMember({
  member,
  others,
  busy,
  onRename,
  onCancel,
}: {
  member: Member
  others: Member[]
  busy: boolean
  onRename: (name: string) => void
  onCancel: () => void
}) {
  const t = useT(messages)
  const [name, setName] = useState(member.name)
  return (
    <form
      className="space-y-3"
      onSubmit={(e) => {
        e.preventDefault()
        if (name.trim() && name.trim() !== member.name) onRename(name.trim())
        else onCancel()
      }}
    >
      <Field id="member-rename" label={t("household.renameLabel", { name: member.name })} hint={others.length ? t("household.mergeHint") : undefined}>
        <Input
          id="member-rename"
          value={name}
          onChange={(e) => setName(e.target.value)}
          list="household-names"
          autoComplete="off"
          autoFocus
        />
      </Field>
      <datalist id="household-names">
        {others.map((o) => (
          <option key={o.name} value={o.name} />
        ))}
      </datalist>
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={busy || !name.trim()}>
          {t("household.save")}
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={onCancel}>
          {t("household.cancel")}
        </Button>
      </div>
    </form>
  )
}
