import type { DocDetail, DocPatch } from "@/lib/api"

/** The fields the user can correct, as edited before saving. */
export type Draft = Required<Omit<DocPatch, "validated" | "keep_forever">>

export function toDraft(doc: DocDetail): Draft {
  return {
    title: doc.title,
    category: doc.category,
    issuer: doc.issuer,
    amount: doc.amount,
    issue_date: doc.issue_date,
    due_date: doc.due_date,
    expiry_date: doc.expiry_date,
    reference: doc.reference,
    doc_type: doc.doc_type,
    person: doc.person,
  }
}
