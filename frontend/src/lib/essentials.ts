import type { Profile } from "./api"

// The three questions of the first launch, asked again in Settings.
export type Question = "situation" | "housing" | "vehicle"
export const QUESTIONS: Question[] = ["situation", "housing", "vehicle"]
// Each answer and its label.
export const OPTIONS = {
  situation: [
    ["student", "situation.student"],
    ["employee", "situation.employee"],
    ["self_employed", "situation.self_employed"],
    ["job_seeker", "situation.job_seeker"],
    ["retired", "situation.retired"],
  ],
  housing: [
    ["tenant", "housing.tenant"],
    ["owner", "housing.owner"],
    ["hosted", "housing.hosted"],
  ],
  vehicle: [
    ["yes", "vehicle.yes"],
    ["no", "vehicle.no"],
  ],
} as const

/** Whether the three questions of the first launch were answered. */
export function answered(profile: Profile | undefined) {
  return !!profile && QUESTIONS.every((q) => !!profile[q])
}
