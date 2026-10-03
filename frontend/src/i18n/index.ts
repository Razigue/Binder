import { use, useMemo } from "react"
import { I18nContext, type I18nContextValue } from "./context"
import { translate, type Dict, type Messages, type Translate } from "./core"

export { defineMessages, type Language } from "./core"

export function useLocale(): I18nContextValue {
  const ctx = use(I18nContext)
  if (!ctx) throw new Error("useLocale must be used inside I18nProvider")
  return ctx
}

/** Translator for one namespace: `const t = useT(home)` then `t("title")`, `t("docs", { count })`. */
export function useT<E extends Dict>(messages: Messages<E>): Translate<E> {
  const { language } = useLocale()
  return useMemo(() => translate(messages, language), [messages, language])
}
