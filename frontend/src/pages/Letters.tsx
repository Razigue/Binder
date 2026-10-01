import { useEffect, useMemo, useState } from "react"
import { useSearchParams } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { Copy, Download, FileSignature, Languages, MessageSquareWarning, Send } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectSeparator, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import { PageHeader } from "@/components/layout/AppLayout"
import { useDocuments } from "@/hooks/queries"
import { useLocale, useT } from "@/i18n"
import { common } from "@/i18n/messages/common"
import { letters as messages } from "@/i18n/messages/letters"
import { api, LETTER_KINDS, type Letter, type LetterKind, type Profile } from "@/lib/api"
import { cn } from "@/lib/utils"

const ICONS: Record<LetterKind, typeof Send> = {
  termination: FileSignature,
  complaint: MessageSquareWarning,
  request: Send,
}

// Select value for "no related document" (Select values are strings).
const NONE = "none"

function initialKind(value: string | null): LetterKind {
  return LETTER_KINDS.includes(value as LetterKind) ? (value as LetterKind) : "termination"
}

export function LettersPage() {
  const t = useT(messages)
  const { language } = useLocale()
  const [params] = useSearchParams()
  const [kind, setKind] = useState<LetterKind>(() => initialKind(params.get("kind")))
  const [documentId, setDocumentId] = useState<number | null>(params.get("document") ? Number(params.get("document")) : null)
  const [details, setDetails] = useState("")
  const [text, setText] = useState("")
  const [letter, setLetter] = useState<Letter | null>(null)
  const docs = useDocuments({ limit: 500 })
  const documentItems = useMemo<Record<string, string>>(
    () => ({
      [NONE]: t("noDocument"),
      ...Object.fromEntries(
        (docs.data ?? []).map((d) => [
          String(d.id),
          d.issuer && !d.title.includes(d.issuer) ? `${d.title} · ${d.issuer}` : d.title,
        ]),
      ),
    }),
    [docs.data, t],
  )
  const write = useMutation({
    mutationFn: () => api.writeLetter({ kind, document_id: documentId, details }),
    onSuccess: (result) => {
      setLetter(result)
      setText(result.body)
      if (result.registered) toast.info(t("registered"))
    },
    onError: (e) => toast.error(e.message),
  })

  const download = () => {
    const url = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }))
    const a = document.createElement("a")
    a.href = url
    a.download = t("fileName", { kind })
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <>
      <PageHeader title={t("title")} subtitle={t("subtitle")} />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        <div className="space-y-6">
          <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-1 xl:grid-cols-3">
            {LETTER_KINDS.map((k) => {
              const Icon = ICONS[k]
              return (
                <button
                  key={k}
                  aria-pressed={k === kind}
                  onClick={() => setKind(k)}
                  className={cn(
                    "flex flex-col items-start rounded-xl border bg-card p-4 text-left transition-colors hover:bg-muted/40",
                    k === kind && "border-primary ring-1 ring-primary",
                  )}
                >
                  <Icon className="mb-2 size-4 text-primary" />
                  <p className="text-sm font-medium">{t(`kind.${k}`)}</p>
                  <p className="text-xs text-muted-foreground">{t(`kind.${k}.hint`)}</p>
                </button>
              )
            })}
          </div>
          <Card className="gap-4 p-5">
            <div className="space-y-1.5">
              <Label htmlFor="letter-doc">{t("document")}</Label>
              <Select
                items={documentItems}
                value={documentId === null ? NONE : String(documentId)}
                onValueChange={(value) => setDocumentId(value && value !== NONE ? Number(value) : null)}
              >
                <SelectTrigger id="letter-doc" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="max-h-80">
                  <SelectItem value={NONE}>{documentItems[NONE]}</SelectItem>
                  {!!docs.data?.length && <SelectSeparator />}
                  {docs.data?.map((d) => (
                    <SelectItem key={d.id} value={String(d.id)}>
                      {documentItems[String(d.id)]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="letter-details">{t(`kind.${kind}.details`)}</Label>
              <Textarea id="letter-details" value={details} onChange={(e) => setDetails(e.target.value)} rows={3} />
            </div>
            <div>
              <Button onClick={() => write.mutate()} disabled={write.isPending}>
                {t("write")}
              </Button>
            </div>
          </Card>
          <ProfileCard />
        </div>
        <Card className="gap-0 p-0">
          <div className="flex items-center gap-2 border-b px-5 py-3">
            <h2 className="flex-1 font-semibold">{t("preview")}</h2>
            <Button
              variant="ghost"
              size="sm"
              disabled={!text}
              onClick={() => navigator.clipboard.writeText(text).then(() => toast.success(t("copied")))}
            >
              <Copy /> {t("copy")}
            </Button>
            <Button variant="ghost" size="sm" disabled={!text} onClick={download}>
              <Download /> {t("download")}
            </Button>
          </div>
          {text && letter && letter.language !== language && (
            <p className="flex items-center gap-2 border-b bg-muted/40 px-5 py-2 text-xs text-muted-foreground">
              <Languages className="size-3.5 shrink-0" />
              {t(`writtenIn.${letter.language}`)}
            </p>
          )}
          {text ? (
            <Textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              className="min-h-[560px] resize-y rounded-none border-0 leading-relaxed shadow-none focus-visible:ring-0"
            />
          ) : (
            <p className="px-5 py-16 text-center text-sm text-muted-foreground">{t("empty")}</p>
          )}
        </Card>
      </div>
    </>
  )
}

function ProfileCard() {
  const t = useT(messages)
  const tc = useT(common)
  const qc = useQueryClient()
  const profile = useQuery({ queryKey: ["profile"], queryFn: api.profile })
  const [form, setForm] = useState<Profile>({ name: "", address: "", city: "", email: "", phone: "" })
  useEffect(() => {
    if (profile.data) setForm(profile.data)
  }, [profile.data])
  const save = useMutation({
    mutationFn: () => api.saveProfile(form),
    onSuccess: (p) => {
      qc.setQueryData(["profile"], p)
      toast.success(t("profile.saved"))
    },
  })
  const set = (patch: Partial<Profile>) => setForm((f) => ({ ...f, ...patch }))
  return (
    <Card className="gap-3 p-5">
      <h2 className="font-semibold">{t("profile.title")}</h2>
      <p className="-mt-2 text-xs text-muted-foreground">{t("profile.hint")}</p>
      <div className="grid items-end gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="p-name">{t("profile.name")}</Label>
          <Input id="p-name" autoComplete="name" value={form.name} onChange={(e) => set({ name: e.target.value })} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="p-city">{t("profile.city")}</Label>
          <Input id="p-city" autoComplete="address-level2" value={form.city} onChange={(e) => set({ city: e.target.value })} />
        </div>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="p-address">{t("profile.address")}</Label>
        <Textarea id="p-address" rows={2} autoComplete="street-address" value={form.address} onChange={(e) => set({ address: e.target.value })} />
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="p-email">{t("profile.email")}</Label>
          <Input id="p-email" type="email" autoComplete="email" value={form.email} onChange={(e) => set({ email: e.target.value })} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="p-phone">{t("profile.phone")}</Label>
          <Input id="p-phone" type="tel" autoComplete="tel" value={form.phone} onChange={(e) => set({ phone: e.target.value })} />
        </div>
      </div>
      <div>
        <Button variant="outline" onClick={() => save.mutate()} disabled={save.isPending}>
          {tc("action.save")}
        </Button>
      </div>
    </Card>
  )
}
