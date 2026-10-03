import "react"

declare module "react" {
  interface CSSProperties {
    /** Position in a list, for the staggered `animate-rise` entrance (index.css). */
    "--i"?: number
  }
}
