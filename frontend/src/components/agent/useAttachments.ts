import { useState } from "react"
import { useInvalidateAll } from "@/hooks/queries"
import { api, type Doc } from "@/lib/api"
import { fileKey, isAccepted } from "@/lib/files"

// Same limit as the backend (attachments per message).
export const MAX_ATTACHMENTS = 10

/** A file attached to the next question, imported into Binder as soon as it is added. */
export interface Attachment {
  key: string
  file: File
  /** Local thumbnail of an image, until the document exists. */
  thumbnail?: string
  doc?: Doc
  error?: string
}

/** Files attached to the question being written: picked, pasted, dropped or photographed. */
export function useAttachments(onAdded?: () => void) {
  const [items, setItems] = useState<Attachment[]>([])
  const invalidate = useInvalidateAll()

  const patch = (key: string, change: Partial<Attachment>) =>
    setItems((prev) => prev.map((a) => (a.key === key ? { ...a, ...change } : a)))

  const add = (files: FileList | File[]) => {
    const list = Array.from(files).filter(isAccepted)
    if (!list.length) return
    const fresh: Attachment[] = list.map((file, i) => ({
      key: fileKey(file, i),
      file,
      thumbnail: file.type.startsWith("image/") ? URL.createObjectURL(file) : undefined,
    }))
    setItems((prev) => [...prev, ...fresh].slice(0, MAX_ATTACHMENTS))
    for (const item of fresh) {
      api
        .upload(item.file)
        .then((doc) => patch(item.key, { doc }))
        .catch((err: Error) => patch(item.key, { error: err.message }))
        .finally(invalidate)
    }
    onAdded?.()
  }

  const remove = (item: Attachment) => {
    if (item.thumbnail) URL.revokeObjectURL(item.thumbnail)
    setItems((prev) => prev.filter((a) => a.key !== item.key))
  }

  const clear = () => {
    for (const a of items) if (a.thumbnail) URL.revokeObjectURL(a.thumbnail)
    setItems([])
  }

  return {
    items,
    add,
    remove,
    clear,
    uploading: items.some((a) => !a.doc && !a.error),
    /** The documents imported so far, ready to send. */
    ready: items.flatMap((a) => (a.doc ? [a.doc] : [])),
    full: items.length >= MAX_ATTACHMENTS,
  }
}

export type Attachments = ReturnType<typeof useAttachments>
