/** Placeholders the letter leaves for the user to fill in: "[your customer number]". */
export const BLANK = /\[[^\]\n]{2,80}\]/g

/** Width over height of an A4 sheet. */
export const A4 = 297 / 210

/** Splits a letter into its blocks, laid out like its PDF: sender, then recipient and date on
 * the right, the subject in bold. Shared by the sheet on screen and printing. */
export function letterBlocks(body: string) {
  return body.split("\n\n").map((block, i) => ({
    style: /^(Objet|Subject)/.test(block) ? "subject" : i === 1 || i === 2 ? "right" : "",
    lines: block.split("\n"),
  }))
}

const ENTITIES: Record<string, string> = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }
const escape = (text: string) => text.replace(/[&<>"]/g, (c) => ENTITIES[c] ?? c)

/** Prints the letter laid out like its PDF (sender, then recipient and date on the right). The
 * PDF itself cannot be framed (`guard.py` denies it), so the text is printed from a blank frame. */
export function printLetter(body: string, title: string) {
  const blocks = letterBlocks(body).map(
    (block) => `<p class="${block.style}">${block.lines.map(escape).join("<br>")}</p>`,
  )
  const frame = document.createElement("iframe")
  frame.style.cssText = "position:fixed;width:0;height:0;border:0;visibility:hidden"
  frame.srcdoc = `<!doctype html><html><head><meta charset="utf-8"><title>${escape(title)}</title><style>
@page { size: A4; margin: 2cm; }
* { font-family: sans-serif; font-size: 10.5pt; line-height: 1.45; color: #111827; }
p { margin: 0 0 9pt 0; } .right { margin-left: 52%; } .subject { font-weight: bold; }
</style></head><body>${blocks.join("")}</body></html>`
  frame.onload = () => {
    frame.contentWindow?.focus()
    frame.contentWindow?.print()
    // The print dialog blocks until closed; the frame is no longer needed after that.
    setTimeout(() => frame.remove(), 1000)
  }
  document.body.appendChild(frame)
}
