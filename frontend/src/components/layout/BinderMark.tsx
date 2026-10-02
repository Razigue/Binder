// The Binder mark: a binder seen from the front, its spine and four card sleeves. Same geometry
// as public/favicon.svg, the desktop loader (desktop.py), the splash (packaging/splash.py) and
// packaging/binder.png; the sleeves are holes, so the tile behind shows through in both themes.
const PATH =
  "M10.2 6h11.6a2.2 2.2 0 0 1 2.2 2.2v15.6a2.2 2.2 0 0 1-2.2 2.2H10.2A2.2 2.2 0 0 1 8 23.8V8.2A2.2 2.2 0 0 1 10.2 6z" +
  "M11 6h1.1v20H11z" +
  "M14.2 10h2.6a.6.6 0 0 1 .6.6v4.2a.6.6 0 0 1-.6.6h-2.6a.6.6 0 0 1-.6-.6v-4.2a.6.6 0 0 1 .6-.6z" +
  "M19.2 10h2.6a.6.6 0 0 1 .6.6v4.2a.6.6 0 0 1-.6.6h-2.6a.6.6 0 0 1-.6-.6v-4.2a.6.6 0 0 1 .6-.6z" +
  "M14.2 16.6h2.6a.6.6 0 0 1 .6.6v4.2a.6.6 0 0 1-.6.6h-2.6a.6.6 0 0 1-.6-.6v-4.2a.6.6 0 0 1 .6-.6z" +
  "M19.2 16.6h2.6a.6.6 0 0 1 .6.6v4.2a.6.6 0 0 1-.6.6h-2.6a.6.6 0 0 1-.6-.6v-4.2a.6.6 0 0 1 .6-.6z"

export function BinderMark({ className }: { className?: string }) {
  return (
    <svg viewBox="4 4 24 24" className={className} fill="currentColor" aria-hidden="true">
      <path fillRule="evenodd" d={PATH} />
    </svg>
  )
}
