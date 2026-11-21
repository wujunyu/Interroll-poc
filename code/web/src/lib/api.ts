import { useEffect, useRef, useState } from 'react'

export type Zone = { zone: string; drives: number; online: number; speed_avg: number; last_ts: string | null }
export type Point = { zone: string; drive: string; speed_mps: number; current_a: number; temp_c?: number; state?: string; ts: string }
export type Health = {
  ok: boolean
  version: string
  mqtt: { connected: boolean; frames: number; last_ts: string | null }
  db: { ok: boolean; watermark?: string; error?: string }
  ws_fps: number
}
export type Series = {
  zone: string
  drive: string
  window: string
  source: 'raw' | '1m-agg'
  points: { ts: string; speed_mps: number; current_a: number }[]
  point_count: number
  raw_count: number
}

export async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`${url} → ${res.status}`)
  return res.json() as Promise<T>
}

export function usePoll<T>(url: string, ms: number): [T | null, string | null] {
  const [data, setData] = useState<T | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => {
    let alive = true
    const tick = async () => {
      try {
        const d = await getJson<T>(url)
        if (alive) { setData(d); setErr(null) }
      } catch (e) {
        if (alive) setErr(String(e))
      }
    }
    tick()
    const id = setInterval(tick, ms)
    return () => { alive = false; clearInterval(id) }
  }, [url, ms])
  return [data, err]
}

export function useLive(): { points: Point[]; frames: number; connected: boolean } {
  const [points, setPoints] = useState<Point[]>([])
  const [frames, setFrames] = useState(0)
  const [connected, setConnected] = useState(false)
  const last = useRef(0)

  useEffect(() => {
    let ws: WebSocket | null = null
    let closed = false
    let attempt = 0
    let timer: number | undefined

    const connect = (): void => {
      if (closed) return
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      ws = new WebSocket(`${proto}://${location.host}/ws/live`)

      ws.onopen = () => {
        attempt = 0
        setConnected(true)
      }
      // 服务端每帧都发全量快照，重连后的第一帧就能补齐状态
      ws.onmessage = (ev) => {
        try {
          const frame = JSON.parse(ev.data) as { points: Point[]; frames?: number }
          const now = performance.now()
          if (now - last.current < 90) return
          last.current = now
          setPoints(frame.points ?? [])
          if (frame.frames) setFrames(frame.frames)
        } catch {
          /* ignore */
        }
      }
      ws.onerror = () => ws?.close()
      ws.onclose = () => {
        setConnected(false)
        if (closed) return
        attempt += 1
        // 指数退避 + 抖动，避免所有看板同一时刻重连
        const delay = Math.min(30000, 500 * 2 ** attempt) * (0.5 + Math.random())
        timer = window.setTimeout(connect, delay)
      }
    }

    connect()
    return () => {
      closed = true
      if (timer) window.clearTimeout(timer)
      ws?.close()
    }
  }, [])

  return { points, frames, connected }
}

export function useHistory(points: Point[], zone: string, drive: string, max = 120) {
  const [hist, setHist] = useState<{ ts: string; v: number }[]>([])
  const lastTs = useRef('')
  useEffect(() => {
    const p = points.find((x) => x.zone === zone && x.drive === drive)
    if (!p || !p.ts || p.ts === lastTs.current) return
    lastTs.current = p.ts
    setHist((h) => [...h.slice(Math.max(0, h.length - max + 1)), { ts: p.ts, v: p.speed_mps }])
  }, [points, zone, drive, max])
  return hist
}
