import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** `value` when it is one of `options` (a search parameter, a stored choice), else undefined. */
export function oneOf<const T extends string>(options: readonly T[], value: string | null | undefined): T | undefined {
  return options.find((option) => option === value)
}
