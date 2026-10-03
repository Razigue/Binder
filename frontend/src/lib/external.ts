/** Opens an official or customer website in the user's own browser, where they are signed in:
 * through the desktop window when there is one (its web view would keep the page inside), else
 * a new tab. */
export function openExternal(url: string) {
  if (!url.startsWith("https://")) return
  const desktop = window.pywebview?.api?.open_external
  if (desktop) void desktop(url)
  else window.open(url, "_blank", "noopener,noreferrer")
}
