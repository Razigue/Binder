/** Formats Binder imports, as the file pickers offer them. */
export const ACCEPT = ".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"

/** Whether a file can be imported (the type of a dropped file is sometimes empty). */
export function isAccepted(file: File) {
  return ACCEPT.split(",").includes(file.type) || /\.(pdf|jpe?g|png)$/i.test(file.name)
}

/** Key of a file picked or dropped, unique among those added together. */
export function fileKey(file: File, index: number) {
  return `${Date.now()}-${index}-${file.name}`
}
