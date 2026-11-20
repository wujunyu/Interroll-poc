import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'

type Props = { option: echarts.EChartsOption; height: number | string; onReady?: (c: echarts.ECharts) => void }

export function Chart({ option, height, onReady }: Props) {
  const el = useRef<HTMLDivElement>(null)
  const inst = useRef<echarts.ECharts | null>(null)

  useEffect(() => {
    if (!el.current) return
    const chart = echarts.init(el.current, undefined, { renderer: 'canvas' })
    inst.current = chart
    onReady?.(chart)
    const ro = new ResizeObserver(() => chart.resize())
    ro.observe(el.current)
    return () => { ro.disconnect(); chart.dispose(); inst.current = null }
  }, [onReady])

  useEffect(() => { inst.current?.setOption(option, true) }, [option])

  return <div ref={el} style={{ width: '100%', height }} />
}
