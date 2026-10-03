import { useEffect } from "react"

/** The window and tab title names the page, so screen readers announce where a link led. */
export function useDocumentTitle(title: string | undefined) {
  useEffect(() => {
    if (title) document.title = `${title} · Binder`
  }, [title])
}
