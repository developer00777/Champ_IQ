import { useEffect, useRef } from 'react'
import type { Node, Edge } from '@xyflow/react'
import { api } from '@/lib/api'
import { useCanvasStore } from '@/store/canvasStore'
import type { CanvasMeta } from '@/types'

// ── localStorage key scheme ───────────────────────────────────────────────────
//   champiq:canvas:list      → CanvasMeta[]       (index of all canvases)
//   champiq:canvas:{id}      → { nodes, edges }   (per-canvas state)

/** Saves the current canvas to localStorage and best-effort syncs to the API. */
export function saveCurrentCanvas() {
  const { nodes, edges, currentCanvasId, canvasName, canvasList } = useCanvasStore.getState()

  localStorage.setItem(`champiq:canvas:${currentCanvasId}`, JSON.stringify({ nodes, edges }))

  const meta: CanvasMeta = { id: currentCanvasId, name: canvasName, updatedAt: new Date().toISOString() }
  const updated = canvasList.some((c) => c.id === currentCanvasId)
    ? canvasList.map((c) => (c.id === currentCanvasId ? meta : c))
    : [...canvasList, meta]
  useCanvasStore.setState({ canvasList: updated })
  localStorage.setItem('champiq:canvas:list', JSON.stringify(updated))

  api.saveCanvasState(nodes, edges).catch(() => {})
}

function loadCanvasFromStorage(id: string): { nodes: Node[]; edges: Edge[] } | null {
  const raw = localStorage.getItem(`champiq:canvas:${id}`)
  if (!raw) return null
  try {
    const { nodes, edges } = JSON.parse(raw) as { nodes: Node[]; edges: Edge[] }
    // Deduplicate and strip orphan edges
    const uniqueNodes = nodes.filter((n, i, arr) => arr.findIndex(x => x.id === n.id) === i)
    const nodeIds = new Set(uniqueNodes.map(n => n.id))
    const uniqueEdges = edges
      .filter((e, i, arr) => arr.findIndex(x => x.id === e.id) === i)
      .filter(e => nodeIds.has(e.source) && nodeIds.has(e.target))
    return { nodes: uniqueNodes, edges: uniqueEdges }
  } catch {
    return null
  }
}

export function usePersistence() {
  const { setNodes, setEdges } = useCanvasStore()
  const currentCanvasId = useCanvasStore((s) => s.currentCanvasId)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // 1. Initialise canvas list from localStorage (runs once on mount).
  useEffect(() => {
    const raw = localStorage.getItem('champiq:canvas:list')
    const list: CanvasMeta[] = raw ? (JSON.parse(raw) as CanvasMeta[]) : []

    if (list.length > 0) {
      const first = list[0]
      useCanvasStore.setState({ canvasList: list, currentCanvasId: first.id, canvasName: first.name })
    } else {
      const id = crypto.randomUUID()
      const meta: CanvasMeta = { id, name: 'My Canvas', updatedAt: new Date().toISOString() }
      useCanvasStore.setState({ canvasList: [meta], currentCanvasId: id })
      localStorage.setItem('champiq:canvas:list', JSON.stringify([meta]))
    }
  }, [])

  // 2. Load canvas state whenever active canvas ID changes.
  //    Clear first to avoid flashing stale content from previous canvas.
  useEffect(() => {
    setNodes([])
    setEdges([])

    const saved = loadCanvasFromStorage(currentCanvasId)
    if (saved) {
      setNodes(saved.nodes)
      setEdges(saved.edges)
      return
    }

    // Fallback: try the API.
    api.getCanvasState().then((s) => {
      if (s.nodes.length > 0 || s.edges.length > 0) {
        const uniqueNodes = (s.nodes as Node[]).filter((n, i, arr) => arr.findIndex(x => x.id === n.id) === i)
        const nodeIds = new Set(uniqueNodes.map(n => n.id))
        const uniqueEdges = (s.edges as Edge[])
          .filter((e, i, arr) => arr.findIndex(x => x.id === e.id) === i)
          .filter(e => nodeIds.has(e.source) && nodeIds.has(e.target))
        setNodes(uniqueNodes)
        setEdges(uniqueEdges)
      }
    }).catch(() => {})
  }, [currentCanvasId, setNodes, setEdges])

  // 3. Debounced save on ANY store change (nodes, edges, or config updates).
  //    1s debounce — short enough to capture config changes before Run All.
  useEffect(() => {
    const unsub = useCanvasStore.subscribe(
      (s) => [s.nodes, s.edges] as const,
      () => {
        if (debounceRef.current) clearTimeout(debounceRef.current)
        debounceRef.current = setTimeout(saveCurrentCanvas, 1_000)
      }
    )
    return () => {
      unsub()
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [])
}
