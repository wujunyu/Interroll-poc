import { useCallback, useMemo } from 'react'
import { Chart } from '../components/Chart'
import { usePoll } from '../lib/api'
import type { Health, Point, Series } from '../lib/api'

type Props = { zone: string; drive: string; live: Point[]; health: Health | null; onBack: () => void }

export function ZoneDetail({ zone, drive, live, health, onBack }: Props) {
  const [series, err] = usePoll<Series>(`/api/series?zone=${zone}&drive=${drive}&window=60s`, 3000)
  // 双击复位：ECharts 没有内置双击，绑在 canvas 的 zrender 上（与设计稿「双击复位」一致）
  const bindReset = useCallback((chart: import('echarts').ECharts) => {
    chart.getZr().on('dblclick', () => {
      chart.dispatchAction({ type: 'dataZoom', start: 0, end: 100 })
    })
  }, [])

  const option = useMemo(() => {
    const pts = series?.points ?? []
    return {
      animation: false,
      backgroundColor: 'transparent',
      textStyle: { color: '#8B9AAB' },
      grid: { left: 48, right: 16, top: 16, bottom: 56 },
      xAxis: {
        type: 'category' as const,
        data: pts.map((p) => new Date(p.ts).toLocaleTimeString('zh-CN', { hour12: false })),
        axisLine: { lineStyle: { color: '#1F2A36' } },
        axisLabel: { color: '#5C6B7A', fontSize: 10, interval: Math.max(0, Math.floor(pts.length / 8)) },
      },
      yAxis: { type: 'value' as const, min: 0, max: 1.2, splitLine: { lineStyle: { color: '#1F2A36' } }, axisLabel: { color: '#5C6B7A', fontSize: 10 }, name: 'm/s', nameTextStyle: { color: '#5C6B7A', fontSize: 10 } },
      tooltip: { trigger: 'axis' as const },
      // 缩放：滚轮/拖选走 inside，底部概览条走 slider，双击复位走 toolbox
      dataZoom: [
        { type: 'inside' as const, filterMode: 'none' as const, zoomOnMouseWheel: true, moveOnMouseMove: true },
        { type: 'slider' as const, height: 18, bottom: 8, borderColor: '#1F2A36', fillerColor: 'rgba(56,189,248,0.15)', handleStyle: { color: '#38BDF8' }, textStyle: { color: '#5C6B7A', fontSize: 9 } },
      ],
      toolbox: {
        right: 8, top: 0,
        iconStyle: { borderColor: '#5C6B7A' },
        feature: { restore: { title: '复位', show: true }, dataZoom: { title: { zoom: '框选缩放', back: '撤销' }, show: true } },
      },
      series: [{
        type: 'line' as const,
        data: pts.map((p) => p.speed_mps),
        showSymbol: false,
        lineStyle: { width: 1.6, color: '#38BDF8' },
        areaStyle: { opacity: 0.12, color: '#38BDF8' },
      }],
    }
  }, [series])

  const rows = live.filter((p) => p.zone === zone).sort((a, b) => a.drive.localeCompare(b.drive))

  return (
    <main className="page">
      <div className="crumbs">
        <button className="link" onClick={onBack}>← 总览</button>
        <span className="dim"> / {zone} / {drive}</span>
        <span className="dim" style={{ marginLeft: 'auto' }}>
          {series ? `${series.source} · ${series.point_count} 点（原始 ${series.raw_count}）` : '加载中…'}
        </span>
      </div>

      <section className="grid-detail">
        <div className="card panel">
          <div className="panel-hd">
            <span>速度趋势 · {zone}/{drive} · 10Hz</span>
            <span className="dim">滚轮/框选缩放 · 双击或 ⟲ 复位</span>
          </div>
          <Chart option={option} height={420} onReady={bindReset} />
          {err && <div className="empty">{err}</div>}
        </div>

        <div className="card panel">
          <div className="panel-hd"><span>点位明细</span><span className="dim">{zone}</span></div>
          <table className="tbl">
            <thead><tr><th>驱动</th><th>速度</th><th>电流</th><th>温度</th><th>状态</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.drive}>
                  <td>{r.drive}</td>
                  <td>{(r.speed_mps ?? 0).toFixed(2)} m/s</td>
                  <td>{(r.current_a ?? 0).toFixed(1)} A</td>
                  <td>{(r.temp_c ?? 0).toFixed(1)} °C</td>
                  <td><i className={`dot ${r.state === 'running' ? 'ok' : 'off'}`} />{r.state === 'running' ? '运行' : '停止'}</td>
                </tr>
              ))}
              {!rows.length && <tr><td colSpan={5} className="dim">等待实时帧…</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card panel">
        <div className="panel-hd"><span>补传水位线</span><span className="dim">{health?.mqtt.connected ? 'Broker 已连接' : 'Broker 断开'}</span></div>
        <div className="watermark">
          <div className="dim">库水位</div>
          <div>{health?.db.watermark ? new Date(health.db.watermark).toLocaleString('zh-CN', { hour12: false }) : '—'}</div>
          <div className="dim">MQTT 帧数</div>
          <div>{health?.mqtt.frames?.toLocaleString() ?? '—'}</div>
          <div className="dim">版本</div>
          <div>{health?.version ?? '—'}</div>
        </div>
      </section>
    </main>
  )
}
