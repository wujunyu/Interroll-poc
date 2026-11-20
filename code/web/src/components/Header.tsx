import type { Health } from '../lib/api'

export function Header({ health, connected }: { health: Health | null; connected: boolean }) {
  const mqttOk = health?.mqtt.connected ?? false
  return (
    <header className="hdr">
      <div className="hdr-brand">
        <span className="logo" />
        <div>
          <div className="hdr-title">英特诺 · 产线遥测</div>
          <div className="hdr-sub">PoC 单机 · 6 区 / 36 驱动 · {health?.version ?? '—'}</div>
        </div>
      </div>
      <div className="hdr-right">
        <span className="chip"><i className={mqttOk ? 'dot ok' : 'dot off'} />{mqttOk ? 'Broker 已连接' : 'Broker 断开'}</span>
        <span className="chip"><i className={connected ? 'dot ok' : 'dot off'} />{connected ? 'WS 10fps' : 'WS 断开'}</span>
        <span className="clock">{new Date().toLocaleTimeString('zh-CN', { hour12: false })}</span>
      </div>
    </header>
  )
}
