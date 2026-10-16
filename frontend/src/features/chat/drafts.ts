import { ref, type Ref } from 'vue'

// Navigation drafts are scoped to the project and session, not a mounted page.
// They contain no credentials and are discarded when the desktop is closed.
const drafts = new Map<string, Ref<string>>()
export function useDraft(project: string, session: string, field: string): Ref<string> {
  const key = JSON.stringify([project, session, field])
  if (!drafts.has(key)) drafts.set(key, ref(''))
  return drafts.get(key)!
}
export function clearDrafts(project: string, session?: string) {
  for (const key of drafts.keys()) {
    const [p, s] = JSON.parse(key)
    if (p === project && (session === undefined || s === session)) drafts.delete(key)
  }
}
