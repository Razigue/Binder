import { useRef, useState, type ChangeEvent, type ClipboardEvent, type RefObject } from "react"
import { ArrowUpIcon, CameraIcon, CircleNotchIcon, FileArrowUpIcon, FileTextIcon, PaperclipIcon, SquareIcon, XIcon } from "@phosphor-icons/react"
import { Button } from "@/components/ui/button"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { useT } from "@/i18n"
import { agent as messages } from "@/i18n/messages/agent"
import { previewUrl, type Doc } from "@/lib/api"
import { ACCEPT } from "@/lib/files"
import { cn } from "@/lib/utils"
import { Thumbnail } from "./actions"
import { CameraDialog } from "./CameraDialog"
import type { Viewing } from "./context"
import { isSubmit } from "./turns"
import type { Attachment, Attachments } from "./useAttachments"

/** Where the question is written, with its attachments and the document on screen it is about. */
export function Composer({
  inputRef,
  attachments,
  pending,
  onSend,
  onStop,
  viewing,
  onIgnoreViewing,
}: {
  inputRef: RefObject<HTMLTextAreaElement | null>
  attachments: Attachments
  pending: boolean
  onSend: (question: string, attachments: Doc[]) => void
  onStop: () => void
  viewing: Viewing | null
  onIgnoreViewing: () => void
}) {
  const t = useT(messages)
  const [text, setText] = useState("")
  const [camera, setCamera] = useState(false)
  const filePicker = useRef<HTMLInputElement>(null)
  const photoPicker = useRef<HTMLInputElement>(null)
  const { items, uploading, ready } = attachments
  const canSend = !pending && !uploading && (text.trim() !== "" || ready.length > 0)

  const submit = () => {
    if (!canSend) return
    onSend(text, ready)
    attachments.clear()
    setText("")
  }

  const onPaste = (e: ClipboardEvent) => {
    if (!e.clipboardData.files.length) return
    e.preventDefault()
    attachments.add(e.clipboardData.files)
  }

  const onPicked = (e: ChangeEvent<HTMLInputElement>) => {
    attachments.add(e.target.files ?? [])
    e.target.value = ""
  }

  const takePhoto = () => {
    // Without camera access from the page (some webviews), the system picker may offer the camera.
    if (typeof navigator.mediaDevices?.getUserMedia === "function") setCamera(true)
    else photoPicker.current?.click()
  }

  return (
    <div className="border-t p-3">
      <div className="rounded-xl border bg-card shadow-xs transition-colors focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/30">
        {viewing && <ViewingChip viewing={viewing} onIgnore={onIgnoreViewing} />}
        {items.length > 0 && (
          <div className="flex flex-wrap gap-1.5 px-2.5 pt-2.5">
            {items.map((item) => (
              <AttachmentChip key={item.key} item={item} onRemove={() => attachments.remove(item)} />
            ))}
          </div>
        )}
        <textarea
          ref={inputRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (!isSubmit(e)) return
            e.preventDefault()
            submit()
          }}
          onPaste={onPaste}
          placeholder={t("inputPlaceholder")}
          aria-label={t("inputPlaceholder")}
          rows={1}
          autoComplete="off"
          autoFocus
          className="field-sizing-content block max-h-48 min-h-11 w-full resize-none bg-transparent px-3.5 pt-3 pb-1 text-sm outline-none placeholder:text-muted-foreground"
        />
        <div className="flex items-center gap-1 px-2 pb-2">
          <DropdownMenu>
            <DropdownMenuTrigger
              disabled={attachments.full}
              render={
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label={t("attach")}
                  title={t("attach")}
                  className="text-muted-foreground"
                />
              }
            >
              <PaperclipIcon />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" side="top" className="w-52">
              <DropdownMenuItem onClick={() => filePicker.current?.click()}>
                <FileArrowUpIcon /> {t("attachFile")}
              </DropdownMenuItem>
              <DropdownMenuItem onClick={takePhoto}>
                <CameraIcon /> {t("takePhoto")}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <span className="flex-1 truncate px-1 text-[0.6875rem] text-muted-foreground max-sm:hidden">
            {t("keyboardHint")}
          </span>
          {pending ? (
            <Button size="icon-sm" onClick={onStop} aria-label={t("stop")} title={t("stop")} className="ml-auto rounded-full">
              <SquareIcon className="size-3 fill-current" />
            </Button>
          ) : (
            <Button
              size="icon-sm"
              onClick={submit}
              disabled={!canSend}
              aria-label={t("send")}
              title={t("send")}
              className="ml-auto rounded-full"
            >
              {uploading ? <CircleNotchIcon className="animate-spin" /> : <ArrowUpIcon />}
            </Button>
          )}
        </div>
      </div>
      <input ref={filePicker} type="file" accept={ACCEPT} multiple hidden onChange={onPicked} />
      <input ref={photoPicker} type="file" accept="image/jpeg,image/png" capture="environment" hidden onChange={onPicked} />
      <CameraDialog
        open={camera}
        onOpenChange={setCamera}
        onCapture={(file) => attachments.add([file])}
        onFallback={() => photoPicker.current?.click()}
      />
    </div>
  )
}

/** "About: <document>", the document on screen, with a way to unlink it from the questions. */
function ViewingChip({ viewing, onIgnore }: { viewing: Viewing; onIgnore: () => void }) {
  const t = useT(messages)
  return (
    <div className="flex px-2.5 pt-2.5">
      <span
        className="inline-flex max-w-full items-center gap-1.5 rounded-md border bg-background py-0.5 pr-0.5 pl-2 text-xs text-muted-foreground"
        title={t("viewingHint")}
      >
        <FileTextIcon className="size-3.5 shrink-0" />
        <span className="truncate">{t("viewing", { title: viewing.title })}</span>
        <button
          type="button"
          onClick={onIgnore}
          aria-label={t("ignoreViewing")}
          title={t("ignoreViewing")}
          className="relative flex size-5 shrink-0 items-center justify-center rounded-full after:absolute after:-inset-0.5 hover:bg-muted hover:text-foreground"
        >
          <XIcon className="size-3" />
        </button>
      </span>
    </div>
  )
}

function AttachmentChip({ item, onRemove }: { item: Attachment; onRemove: () => void }) {
  const t = useT(messages)
  return (
    <div
      className={cn(
        "group/draft relative flex max-w-48 items-center gap-2 rounded-lg border bg-background p-1 pr-6 text-xs",
        item.error && "border-destructive/40",
      )}
      title={item.error}
    >
      <span className="relative">
        <Thumbnail src={item.thumbnail ?? (item.doc ? previewUrl(item.doc.id) : undefined)} />
        {!item.doc && !item.error && (
          <span className="absolute inset-0 flex items-center justify-center rounded-md bg-background/60">
            <CircleNotchIcon className="size-3.5 animate-spin" />
          </span>
        )}
      </span>
      <span className="min-w-0">
        <span className="block truncate font-medium">{item.file.name}</span>
        <span className={cn("block truncate", item.error ? "text-destructive" : "text-muted-foreground")}>
          {item.error ?? (item.doc ? t("ready") : t("uploading"))}
        </span>
      </span>
      <button
        type="button"
        onClick={onRemove}
        aria-label={t("remove", { name: item.file.name })}
        className="absolute top-1 right-1 flex size-4 items-center justify-center rounded-full text-muted-foreground after:absolute after:-inset-1 hover:bg-muted hover:text-foreground"
      >
        <XIcon className="size-3" />
      </button>
    </div>
  )
}
