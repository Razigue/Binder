import { useEffect, useRef, useState } from "react"
import { CameraIcon, CircleNotchIcon } from "@phosphor-icons/react"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { useT } from "@/i18n"
import { agent as messages } from "@/i18n/messages/agent"

export function CameraDialog({
  open,
  onOpenChange,
  onCapture,
  onFallback,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCapture: (file: File) => void
  onFallback: () => void
}) {
  const t = useT(messages)
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="gap-4 sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{t("cameraTitle")}</DialogTitle>
          <DialogDescription>{t("cameraDescription")}</DialogDescription>
        </DialogHeader>
        {/* Mounted while the dialog is shown: the camera is released when it closes. */}
        <CameraView
          onClose={() => onOpenChange(false)}
          onCapture={(file) => {
            onCapture(file)
            onOpenChange(false)
          }}
          onFallback={() => {
            onOpenChange(false)
            onFallback()
          }}
        />
      </DialogContent>
    </Dialog>
  )
}

function CameraView({
  onClose,
  onCapture,
  onFallback,
}: {
  onClose: () => void
  onCapture: (file: File) => void
  onFallback: () => void
}) {
  const t = useT(messages)
  const video = useRef<HTMLVideoElement>(null)
  const [stream, setStream] = useState<MediaStream | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let active: MediaStream | null = null
    let cancelled = false
    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: "environment", width: { ideal: 1920 }, height: { ideal: 1080 } } })
      .then((s) => {
        if (cancelled) return s.getTracks().forEach((track) => track.stop())
        active = s
        setStream(s)
      })
      .catch(() => !cancelled && setFailed(true))
    return () => {
      cancelled = true
      active?.getTracks().forEach((track) => track.stop())
    }
  }, [])

  useEffect(() => {
    if (video.current) video.current.srcObject = stream
  }, [stream])

  const capture = () => {
    const v = video.current
    if (!v || !v.videoWidth) return
    const canvas = document.createElement("canvas")
    canvas.width = v.videoWidth
    canvas.height = v.videoHeight
    canvas.getContext("2d")?.drawImage(v, 0, 0)
    canvas.toBlob(
      (blob) => {
        if (!blob) return
        const stamp = new Date().toISOString().slice(0, 19).replace(/[T:]/g, "-")
        onCapture(new File([blob], `photo-${stamp}.jpg`, { type: "image/jpeg" }))
      },
      "image/jpeg",
      0.92,
    )
  }

  if (failed)
    return (
      <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed px-4 py-10 text-center text-sm text-muted-foreground">
        <CameraIcon className="size-6" />
        {t("cameraUnavailable")}
        <Button variant="outline" size="sm" onClick={onFallback}>
          {t("chooseImage")}
        </Button>
      </div>
    )

  return (
    <>
      <div className="relative flex aspect-video items-center justify-center overflow-hidden rounded-lg bg-black">
        <video ref={video} autoPlay playsInline muted className="size-full object-contain" />
        {!stream && <CircleNotchIcon className="absolute size-6 animate-spin text-white/70" />}
      </div>
      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>
          {t("cancel")}
        </Button>
        <Button onClick={capture} disabled={!stream}>
          <CameraIcon /> {t("capture")}
        </Button>
      </div>
    </>
  )
}
