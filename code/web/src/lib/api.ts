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
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${location.host}/ws/live`)
    ws.onopen = () => setConnected(true)
    ws.onclose = () => setConnected(false)
    ws.onmessage = (ev) => {
      try {
        const frame = JSON.parse(ev.data) as { points: Point[]; frames?: number }
        const now = performance.now()
        if (now - last.current < 90) return
        last.current = now
        setPoints(frame.points ?? [])
        if (frame.frames) setFrames(frame.frames)
      } catch { /* ignore */ }
    }
    return () => ws.close()
  }, [])
  return { points, frames, connected }
}

/** WS 只推「当前快照」，所以前端要自己攒一条时间线（按 ts 去重） */
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
