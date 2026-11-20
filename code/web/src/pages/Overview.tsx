import { useMemo } from 'react'
import { Chart } from '../components/Chart'
import { useHistory, usePoll } from '../lib/api'
import type { Health, Point, Zone } from '../lib/api'

type AlertItem = { id: string; zone: string; drive: string; rule: string; level: string; state: string; since: string; message: string }
type AlertsPayload = { active: AlertItem[]; history: AlertItem[]; rules: { for_seconds: number; offline_seconds: number } }

type Props = { live: Point[]; health: Health | null; onOpen: (zone: string, drive: string) => void }

const STATE_COLOR: Record<string, string> = { run: 'var(--c-ok)', warn: 'var(--c-warn)', off: 'var(--c-off)' }

function zoneState(z: Zone): 'run' | 'warn' | 'off' {
  if (z.online === 0) return 'off'
  if (z.online < z.drives) return 'warn'
  return 'run'
}

export function Overview({ live, health, onOpen }: Props) {
  const [zones] = usePoll<Zone[]>('/api/zones', 2000)
  const [alerts] = usePoll<AlertsPayload>('/api/alerts', 2000)

  const kpi = useMemo(() => {
    const list = zones ?? []
    const online = list.reduce((a, z) => a + z.online, 0)
    const drives = list.reduce((a, z) => a + z.drives, 0)
    const speed = list.length ? list.reduce((a, z) => a + z.speed_avg, 0) / list.length : 0
    const lastTs = health?.db.watermark ? new Date(health.db.watermark) : null
    const lagMs = lastTs ? Math.max(0, Date.now() - lastTs.getTime()) : null
    const lag = lagMs === null ? null : Math.round(lagMs / 1000)
    // 吞吐是估算：在线驱动 × 单驱动名义产能 40 件/时，界面上标「估算」
    return { online, drives, speed, lag, tps: online * 40 }
  }, [zones, health])

  const hist = useHistory(live, 'Z1', 'D01', 120)
  const spark = useMemo(() => {
    const pts = hist
    return {
      animation: false,
      grid: { left: 8, right: 8, top: 8, bottom: 8 },
      xAxis: { type: 'category' as const, show: false, data: pts.map((p) => p.ts) },
      yAxis: { type: 'value' as const, show: false, min: 0, max: 1.2 },
      series: [{ type: 'line' as const, data: pts.map((p) => p.v), showSymbol: false, lineStyle: { width: 2, color: '#38BDF8' }, areaStyle: { opacity: 0.15, color: '#38BDF8' } }],
    }
  }, [hist])

  return (
    <main className="page">
      <section className="kpis">
        <div className="card kpi">
          <div className="kpi-label">吞吐量 · 件/时（估算）</div>
          <div className="kpi-value">{kpi.tps.toLocaleString()}</div>
          <div className="kpi-foot">在线驱动 × 40 件/时</div>
        </div>
        <div className="card kpi">
          <div className="kpi-label">在线驱动 · 台</div>
          <div className="kpi-value">{kpi.online}/{kpi.drives || 36}</div>
          <div className="kpi-foot">{kpi.online === kpi.drives ? '全部在线' : `${(kpi.drives || 36) - kpi.online} 台离线`}</div>
        </div>
        <div className="card kpi">
          <div className="kpi-label">平均速度 · m/s</div>
          <div className="kpi-value">{kpi.speed.toFixed(2)}</div>
          <div className="kpi-foot">六区均值</div>
        </div>
        <div className="card kpi">
          <div className="kpi-label">端到端延迟 · s</div>
          <div className="kpi-value">{kpi.lag === null ? '—' : kpi.lag > 600 ? '>600' : kpi.lag}</div>
          <div className="kpi-foot">库水位到现在（无新数据时会涨）</div>
        </div>
      </section>

      <section className="grid-main">
        <div className="card panel">
          <div className="panel-hd">
            <span>分区状态</span>
            <span className="legend">
              <i className="dot ok" />运行 <i className="dot warn" />积压 <i className="dot off" />离线
            </span>
          </div>
          <div className="zones">
            {(zones ?? []).map((z) => {
              const st = zoneState(z)
              return (
                <button key={z.zone} className={`zone z-${st}`} onClick={() => onOpen(z.zone, 'D01')}>
                  <div className="zone-name">{z.zone}</div>
                  <div className="zone-state" style={{ color: STATE_COLOR[st] }}>
                    {st === 'run' ? '运行' : st === 'warn' ? '积压' : '离线'}
                  </div>
                  <div className="zone-meta">{z.online}/{z.drives} 驱动 · {z.speed_avg.toFixed(2)} m/s</div>
                  <div className="zone-dots">
                    {Array.from({ length: z.drives }).map((_, i) => (
                      <i key={i} className="zdot" style={{ background: i < z.online ? STATE_COLOR[st] : 'var(--c-off)', opacity: i < z.online ? 1 : 0.35 }} />
                    ))}
                  </div>
                </button>
              )
            })}
            {!zones && <div className="empty">等待数据…（ingest 与 api 是否在跑？）</div>}
          </div>
        </div>

        <div className="card panel">
          <div className="panel-hd">
            <span>告警 · {alerts?.active.length ?? 0}</span>
            <span className="dim">去抖 {alerts?.rules.for_seconds ?? 30}s · 离线 {alerts?.rules.offline_seconds ?? 15}s</span>
          </div>
          <div className="alerts">
            {(alerts?.active ?? []).map((a) => (
              <div key={a.id} className={`alert-item lv-${a.level}`}>
                <div className="dim">{a.since} · {a.zone}/{a.drive} · {a.rule}</div>
                <div>{a.message}</div>
              </div>
            ))}
            {!alerts?.active.length && (
              <div className="alert-item"><div className="dim">当前没有触发中的告警（抖动不满 {alerts?.rules.for_seconds ?? 30}s 不会报）</div></div>
            )}
            {(alerts?.history ?? []).filter((h) => h.state === 'resolved').slice(-3).reverse().map((h) => (
              <div key={h.id} className="alert-item lv-resolved"><div className="dim">{h.since} · 已恢复 · {h.rule}</div></div>
            ))}
          </div>
        </div>
      </section>

      <section className="card panel">
        <div className="panel-hd"><span>实时速度 · Z1/D01</span><span className="dim">WS 10fps</span></div>
        {hist.length > 1 ? <Chart option={spark} height={180} /> : <div className="empty">等待实时帧…（模拟器是否在发数？）</div>}
      </section>
    </main>
  )
}
