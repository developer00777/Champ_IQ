/**
 * useB2BPulseExtension — the browser-side coordinator for LinkedIn scraping.
 *
 * Single Responsibility: coordinate the scrape lifecycle between:
 *   ChampIQ backend (task queue) ↔ Chrome extension (actual scraping) ↔ canvas UI
 *
 * Full flow:
 *   1. Poll /extension/tasks every 10s
 *   2. For each task: postMessage SCRAPE_POSTS to extension via content.js
 *   3. Receive SCRAPE_POSTS_RESULT back from extension
 *   4. Submit posts to /extension/posts (backend stores in Redis)
 *   5. Update the canvas node's runtime state directly so the UI shows posts
 *      without waiting for a full re-execution (list_posts is async by design)
 *
 * Only activates when a lakeb2b credential exists in the store.
 */
import { useEffect, useRef } from 'react'
import { useCredentialStore } from '@/store/credentialStore'
import { useCanvasStore } from '@/store/canvasStore'
import { api } from '@/lib/api'

const POLL_INTERVAL_MS = 10_000   // poll every 10 seconds
const SCRAPE_TIMEOUT_MS = 90_000  // 90s max per scrape before error

interface ScrapeTask {
  task_id: string
  action: string
  page_url: string
  limit?: number
}

interface ScrapeResult {
  task_id: string
  posts: Record<string, unknown>[]
  status: 'ok' | 'error'
  error?: string
}

// Map task_id → canvas node_id so we can update the right node when result arrives
const taskToNodeId = new Map<string, string>()

export function useB2BPulseExtension() {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const activeTasksRef = useRef<Set<string>>(new Set())
  const credentials = useCredentialStore((s) => s.credentials)

  useEffect(() => {
    const lakeb2bCred = credentials.find((c) => c.type === 'lakeb2b')
    const credId = lakeb2bCred ? Number(lakeb2bCred.fields.credential_id) : null
    if (!credId || isNaN(credId)) return

    let cancelled = false

    // ── Handle SCRAPE_POSTS_RESULT from extension ────────────────────────────
    function onExtensionMessage(ev: MessageEvent) {
      if (!ev.data || ev.data.type !== 'SCRAPE_POSTS_RESULT') return
      const result = ev.data as ScrapeResult & { type: string }
      if (!activeTasksRef.current.has(result.task_id)) return

      activeTasksRef.current.delete(result.task_id)

      const posts = result.posts ?? []
      const status = result.status

      // Submit to backend so canvas execution polling can read it
      api.submitExtensionPosts({
        task_id: result.task_id,
        credential_id: credId!,
        posts,
        status,
        error: result.error,
      }).catch((e: unknown) => {
        console.error('[b2bpulse] Failed to submit extension posts:', e)
      })

      // Update canvas node UI directly — the node already returned "queued"
      // so without this the canvas would show empty output forever.
      const nodeId = taskToNodeId.get(result.task_id)
      if (nodeId) {
        taskToNodeId.delete(result.task_id)
        const store = useCanvasStore.getState()
        if (status === 'ok') {
          store.setNodeRuntime(nodeId, {
            status: 'success',
            output: { data: { status: 'ok', posts, task_id: result.task_id } },
          })
          store.addLog({
            nodeId,
            nodeName: 'B2B Pulse',
            status: 'success',
            message: `Scraped ${posts.length} post${posts.length !== 1 ? 's' : ''} from LinkedIn`,
          })
        } else {
          store.setNodeRuntime(nodeId, {
            status: 'error',
            error: result.error ?? 'Extension scrape failed',
          })
          store.addLog({
            nodeId,
            nodeName: 'B2B Pulse',
            status: 'error',
            message: result.error ?? 'Extension scrape failed',
          })
        }
      }
    }

    window.addEventListener('message', onExtensionMessage)

    // ── Poll backend for pending tasks ───────────────────────────────────────
    async function poll() {
      if (cancelled) return
      try {
        const { tasks } = await api.getExtensionTasks(credId!)

        for (const raw of tasks) {
          const task = raw as unknown as ScrapeTask
          if (!task.task_id || activeTasksRef.current.has(task.task_id)) continue

          activeTasksRef.current.add(task.task_id)

          // Find the canvas node that owns this task so we can update its status
          const canvasNodes = useCanvasStore.getState().nodes
          const ownerNode = canvasNodes.find((n) => {
            const runtime = useCanvasStore.getState().nodeRuntimeStates[n.id]
            const output = runtime?.output as Record<string, unknown> | undefined
            const data = output?.data as Record<string, unknown> | undefined
            return data?.task_id === task.task_id
          })
          if (ownerNode) {
            taskToNodeId.set(task.task_id, ownerNode.id)
            // Mark as running while extension scrapes
            useCanvasStore.getState().setNodeRuntime(ownerNode.id, { status: 'running' })
          }

          // Timeout guard — if extension goes silent, fail fast
          setTimeout(() => {
            if (!activeTasksRef.current.has(task.task_id)) return
            activeTasksRef.current.delete(task.task_id)
            taskToNodeId.delete(task.task_id)
            const nid = ownerNode?.id
            if (nid) {
              useCanvasStore.getState().setNodeRuntime(nid, {
                status: 'error',
                error: 'Extension scrape timed out. Make sure the ChampIQ extension is installed and LinkedIn is open in this browser.',
              })
            }
            api.submitExtensionPosts({
              task_id: task.task_id,
              credential_id: credId!,
              posts: [],
              status: 'error',
              error: 'Extension timed out',
            }).catch(() => {})
          }, SCRAPE_TIMEOUT_MS)

          // Send task to extension
          window.postMessage({
            type: 'SCRAPE_POSTS',
            task_id: task.task_id,
            page_url: task.page_url,
            limit: task.limit ?? 20,
          }, '*')
        }
      } catch {
        // Silently ignore network errors
      }

      if (!cancelled) {
        timerRef.current = setTimeout(poll, POLL_INTERVAL_MS)
      }
    }

    poll()

    return () => {
      cancelled = true
      if (timerRef.current) clearTimeout(timerRef.current)
      window.removeEventListener('message', onExtensionMessage)
    }
  }, [credentials])
}
