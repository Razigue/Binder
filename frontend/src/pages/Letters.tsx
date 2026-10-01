import { useEffect, useState } from "react"
import { useSearchParams } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { Copy, Download, FileSignature, MessageSquareWarning, Send } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { PageHeader } from "@/components/layout/AppLayout"
import { useDocuments } from "@/hooks/queries"
import { api, type LetterKind, type Profile } from "@/lib/api"
import { cn } from "@/lib/utils"

const KINDS: { kind: LetterKind; title: string; hint: string; icon: typeof Send; details: string }[] = [
  {
    kind: "resiliation",
    title: "Résilier",
    hint: "Contrat, abonnement, assurance",
    icon: FileSignature,
    details: "Précision facultative (date souhaitée, motif…)",
  },
  {
    kind: "reclamation",
    title: "Contester",
    hint: "Facture erronée, prestation non fournie",
    icon: MessageSquareWarning,
    details: "Ce qui ne va pas",
  },
  {
    kind: "demande",
    title: "Demander un document",
    hint: "Attestation, duplicata, relevé",
    icon: Send,
    details: "Le document souhaité",
  },
]

export function LettersPage() {
  const [params] = useSearchParams()
  const [kind, setKind] = useState<LetterKind>((params.get("kind") as LetterKind) ?? "resiliation")
  const [documentId, setDocumentId] = useState<number | null>(params.get("document") ? Number(params.get("document")) : null)
  const [details, setDetails] = useState("")
  const [text, setText] = useState("")
  const docs = useDocuments({ limit: 500 })
  const write = useMutation({
    mutationFn: () => api.writeLetter({ kind, document_id: documentId, details }),
    onSuccess: (letter) => {
      setText(letter.body)
      if (letter.registered) toast.info("Conseil : envoyez ce courrier en recommandé avec accusé de réception.")
    },
    onError: (e) => toast.error(e.message),
  })
  const current = KINDS.find((k) => k.kind === kind)!

  const download = () => {
    const url = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }))
    const a = document.createElement("a")
    a.href = url
    a.download = `courrier-${kind}.txt`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <>
      <PageHeader title="Courriers" subtitle="Des courriers types préremplis avec les informations de vos documents." />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        <div className="space-y-6">
          <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-1 xl:grid-cols-3">
            {KINDS.map(({ kind: k, title, hint, icon: Icon }) => (
              <button
                key={k}
                onClick={() => setKind(k)}
                className={cn(
                  "rounded-xl border bg-card p-4 text-left transition-colors hover:bg-muted/40",
                  k === kind && "border-primary ring-1 ring-primary",
                )}
              >
                <Icon className="mb-2 size-4 text-primary" />
                <p className="text-sm font-medium">{title}</p>
                <p className="text-xs text-muted-foreground">{hint}</p>
              </button>
            ))}
          </div>
          <Card className="gap-4 p-5">
            <div className="space-y-1.5">
              <Label htmlFor="letter-doc">Document concerné</Label>
              <select
                id="letter-doc"
                value={documentId ?? ""}
                onChange={(e) => setDocumentId(e.target.value ? Number(e.target.value) : null)}
                className="h-9 w-full rounded-md border bg-background px-2 text-sm"
              >
                <option value="">Aucun (à compléter à la main)</option>
                {docs.data?.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.title}
                    {d.issuer && !d.title.includes(d.issuer) ? ` · ${d.issuer}` : ""}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="letter-details">{current.details}</Label>
              <Textarea id="letter-details" value={details} onChange={(e) => setDetails(e.target.value)} rows={3} />
            </div>
            <div>
              <Button onClick={() => write.mutate()} disabled={write.isPending}>
                Rédiger le courrier
              </Button>
            </div>
          </Card>
          <ProfileCard />
        </div>
        <Card className="gap-0 p-0">
          <div className="flex items-center gap-2 border-b px-5 py-3">
            <h2 className="flex-1 font-semibold">Aperçu</h2>
            <Button
              variant="ghost"
              size="sm"
              disabled={!text}
              onClick={() => navigator.clipboard.writeText(text).then(() => toast.success("Courrier copié"))}
            >
              <Copy /> Copier
            </Button>
            <Button variant="ghost" size="sm" disabled={!text} onClick={download}>
              <Download /> Télécharger
            </Button>
          </div>
          {text ? (
            <Textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              className="min-h-[560px] resize-y rounded-none border-0 font-mono text-[13px] leading-relaxed shadow-none focus-visible:ring-0"
            />
          ) : (
            <p className="px-5 py-16 text-center text-sm text-muted-foreground">
              Choisissez un type de courrier et un document, puis « Rédiger ». Le texte reste modifiable ;
              les passages entre crochets sont à compléter.
            </p>
          )}
        </Card>
      </div>
    </>
  )
}

function ProfileCard() {
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
      toast.success("Coordonnées enregistrées")
    },
  })
  const set = (patch: Partial<Profile>) => setForm((f) => ({ ...f, ...patch }))
  return (
    <Card className="gap-3 p-5">
      <h2 className="font-semibold">Vos coordonnées</h2>
      <p className="-mt-2 text-xs text-muted-foreground">Utilisées en en-tête des courriers. Stockées sur cette machine.</p>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="p-name">Prénom et nom</Label>
          <Input id="p-name" value={form.name} onChange={(e) => set({ name: e.target.value })} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="p-city">Ville (pour « À …, le … »)</Label>
          <Input id="p-city" value={form.city} onChange={(e) => set({ city: e.target.value })} />
        </div>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="p-address">Adresse</Label>
        <Textarea id="p-address" rows={2} value={form.address} onChange={(e) => set({ address: e.target.value })} />
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="p-email">E-mail</Label>
          <Input id="p-email" value={form.email} onChange={(e) => set({ email: e.target.value })} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="p-phone">Téléphone</Label>
          <Input id="p-phone" value={form.phone} onChange={(e) => set({ phone: e.target.value })} />
        </div>
      </div>
      <div>
        <Button variant="outline" onClick={() => save.mutate()} disabled={save.isPending}>
          Enregistrer
        </Button>
      </div>
    </Card>
  )
}
