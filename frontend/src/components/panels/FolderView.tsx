import { DownloadSimpleIcon, FolderOpenIcon } from "@phosphor-icons/react"
import { Button } from "@/components/ui/button"
import { useT } from "@/i18n"
import { feed } from "@/i18n/messages/feed"
import { folderExportUrl, type Folder } from "@/lib/api"
import { cn } from "@/lib/utils"

/** A folder the agent put together: each piece, found or missing, and the folder to download. */
export function FolderView({ folder }: { folder: Folder }) {
  const t = useT(feed)
  return (
    <div className="overflow-hidden rounded-lg border">
      <div className="flex items-center gap-2 border-b bg-muted/40 px-3 py-2">
        <FolderOpenIcon className="size-4 text-muted-foreground" />
        <span className="min-w-0 flex-1 truncate text-sm font-medium">{folder.title}</span>
        <span className="text-xs text-muted-foreground">{t("folderReady", { ready: folder.ready, total: folder.total })}</span>
      </div>
      <ul className="divide-y">
        {folder.pieces.map((p) => (
          <li key={p.key} className="flex items-start gap-2 px-3 py-2 text-sm">
            <span
              className={cn(
                "mt-1.5 size-2 shrink-0 rounded-full",
                p.status === "ok" ? "bg-emerald-500" : p.status === "missing" ? "bg-red-500" : "bg-amber-500",
              )}
            />
            <span className="min-w-0 flex-1">
              <span className="block">{p.label}</span>
              {p.status !== "ok" && <span className="block text-xs text-muted-foreground">{p.note || p.hint}</span>}
            </span>
            <span className="text-xs text-muted-foreground">{t(`piece.${p.status}`)}</span>
          </li>
        ))}
      </ul>
      <div className="border-t px-3 py-2">
        <Button size="sm" variant="outline" render={<a href={folderExportUrl(folder.key)} download />} nativeButton={false}>
          <DownloadSimpleIcon /> {t("folderDownload")}
        </Button>
      </div>
    </div>
  )
}
