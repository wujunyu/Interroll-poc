#!/usr/bin/env node
/**
 * 生成 Penpot 看板 spec（docs/design/screens/poc-dashboard.json）。
 *
 * 为什么用脚本生成而不是手写 JSON：
 *   - 色板只在 tokens.json 一处定义，改一处全稿生效；
 *   - 6 个区、36 个驱动点、60 根柱子都是循环出来的，手写必然对不齐；
 *   - 生成物是纯文本，能 diff、能 review、能进 CI 校验。
 *
 * 用法：node docs/design/gen-spec.mjs
 */
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const T = JSON.parse(readFileSync(resolve(HERE, 'tokens.json'), 'utf8')).color

const R = (x, y, w, h, fill, r = 0, extra = {}) => ({ k: 'rect', x: Math.round(x), y: Math.round(y), w: Math.round(w), h: Math.round(h), fill, r, ...extra })
const TX = (x, y, s, o = {}) => ({
  k: 'text', x: Math.round(x), y: Math.round(y), s: String(s),
  size: o.size ?? 14, color: o.color ?? T.text, weight: o.weight ?? 400,
  ...(o.w ? { w: Math.round(o.w) } : {}), ...(o.align ? { align: o.align } : {}),
})

const header = (W, right = []) => [
  R(0, 0, W, 64, T.panel), R(0, 63, W, 1, T.line),
  R(24, 20, 26, 26, T.brand, 7),
  TX(58, 18, '英特诺 · 产线遥测', { size: 16, weight: 600 }),
  TX(58, 41, 'PoC 单机 · 6 区 / 36 驱动 · v0.3.1', { size: 11, color: T.sub }),
  ...right,
]

const statusChip = (x, y, text, color) => [
  R(x, y, 8, 8, color, 4),
  TX(x + 14, y - 5, text, { size: 12, color: T.sub }),
]

const kpi = (x, y, w, label, value, unit, delta, deltaColor) => [
  R(x, y, w, 96, T.card, 12, { strokeColor: T.line }),
  TX(x + 20, y + 16, `${label} · ${unit}`, { size: 12, color: T.sub }),
  TX(x + 20, y + 40, value, { size: 28, weight: 600 }),
  TX(x + w - 20 - String(delta).length * 7, y + 74, delta, { size: 12, color: deltaColor }),
]

const panel = (x, y, w, h, title, extra = []) => [
  R(x, y, w, h, T.panel, 12, { strokeColor: T.line }),
  TX(x + 20, y + 16, title, { size: 14, weight: 600 }),
  ...extra,
]

const zones = [
  { id: 'Z1', name: '上包段', st: 'run', on: 6, tps: 216 },
  { id: 'Z2', name: '扫码段', st: 'run', on: 6, tps: 214 },
  { id: 'Z3', name: '分流 A', st: 'warn', on: 6, tps: 198 },
  { id: 'Z4', name: '分流 B', st: 'run', on: 6, tps: 206 },
  { id: 'Z5', name: '合流段', st: 'run', on: 6, tps: 232 },
  { id: 'Z6', name: '出货段', st: 'off', on: 0, tps: 0 },
]
const stColor = { run: T.ok, warn: T.warn, off: T.off }
const stText = { run: '运行', warn: '积压', off: '离线' }

const alerts = [
  { t: '21:35', zone: 'Z6 出货段', msg: '驱动 D03 电流超限 4.8A，已降速', lv: T.bad },
  { t: '21:34', zone: 'Z3 分流 A', msg: '积压 8 件，持续 42s（阈值 30s）', lv: T.warn },
  { t: '21:31', zone: '边缘机', msg: '网络抖动 8s，已切本地缓存并补传', lv: T.warn },
]

const bars = Array.from({ length: 60 }, (_, i) => {
  if (i >= 24 && i < 32) return 0
  return 40 + Math.round(28 * Math.sin(i / 4.2) + 18 * Math.sin(i / 1.7) + 26)
})

// ---------- 01 总览 ----------
const b1 = (() => {
  const W = 1440
  const c = []
  c.push(...header(W, [
    ...statusChip(1136, 28, 'Broker 已连接', T.ok),
    ...statusChip(1246, 28, '补传 0', T.ok),
    TX(1372, 22, '21:36:12', { size: 14, color: T.sub, w: 44, align: 'right' }),
  ]))
  const kpis = [
    ['吞吐量', '1,284', '件/时', '▲ 3.2%', T.ok],
    ['线体在制品', '12', '件', '▼ 4', T.ok],
    ['在线驱动', '30/36', '台', 'Z6 离线', T.bad],
    ['端到端延迟', '180', 'ms', 'P95 240ms', T.sub],
  ]
  kpis.forEach((k, i) => c.push(...kpi(24 + i * 352, 88, 336, ...k)))

  const px = 24, py = 200, pw = 900, ph = 344
  c.push(...panel(px, py, pw, ph, '分区状态', [
    ...statusChip(px + 640, py + 25, '运行', T.ok),
    ...statusChip(px + 700, py + 25, '积压', T.warn),
    ...statusChip(px + 760, py + 25, '离线', T.off),
    TX(px + pw - 84, py + 16, '实时', { size: 11, color: T.dim }),
  ]))
  zones.forEach((z, i) => {
    const col = i % 3, row = Math.floor(i / 3)
    const x = px + 20 + col * (277 + 14)
    const y = py + 48 + row * (134 + 14)
    c.push(R(x, y, 277, 134, z.st === 'off' ? '#141A21' : T.card, 10, { strokeColor: z.st === 'off' ? '#2A1F24' : T.line }))
    c.push(TX(x + 14, y + 12, `${z.id} · ${z.name}`, { size: 12, color: T.sub }))
    c.push(TX(x + 14, y + 32, stText[z.st], { size: 16, weight: 600, color: stColor[z.st] }))
    c.push(TX(x + 76, y + 36, z.tps ? `${z.tps} 件/时` : '无数据', { size: 12, color: T.dim }))
    for (let d = 0; d < 6; d++) {
      const on = d < z.on
      c.push(R(x + 14 + d * 28, y + 70, 24, 24, on ? stColor[z.st] : T.off, 6, { opacity: on ? 1 : 0.35 }))
    }
    c.push(TX(x + 14, y + 106, `${z.on}/6 驱动 · ${z.st === 'off' ? '断网 8s' : '同步 21:36'}`, { size: 11, color: T.dim }))
  })

  const ax = px + pw + 20, aw = 472, ah = ph
  c.push(...panel(ax, py, aw, ah, '告警 · 3', [TX(ax + aw - 84, py + 16, '最近 5 分钟', { size: 11, color: T.dim })]))
  alerts.forEach((a, i) => {
    const y = py + 48 + i * (84 + 8)
    c.push(R(ax + 20, y, aw - 40, 84, T.card, 10, { strokeColor: T.line }))
    c.push(R(ax + 20, y, 3, 84, a.lv, 2))
    c.push(TX(ax + 34, y + 12, `${a.t} · ${a.zone}`, { size: 12, color: T.sub }))
    c.push(TX(ax + 34, y + 34, a.msg, { size: 13, color: T.text, w: aw - 74 }))
  })

  const cy = 568, ch = 308
  c.push(...panel(24, cy, 1392, ch, '吞吐趋势 · 最近 5 分钟', [TX(24 + 1290, cy + 16, '件 / 10s', { size: 11, color: T.dim })]))
  for (let g = 0; g < 5; g++) c.push(R(84, 620 + g * 40, 1300, 1, T.line))
  bars.forEach((v, i) => {
    if (!v) return
    const h = Math.round(v * 1.1)
    const inGap = i >= 24 && i < 32
    c.push(R(84 + i * 21, 820 - h, 12, h, inGap ? T.warn : T.accent, 2, { opacity: 0.85 }))
  })
  c.push(TX(84 + 24 * 21 + 4, 690, '断网 8s', { size: 11, color: T.bad }))
  c.push(TX(24, 838, '−5m', { size: 11, color: T.dim }))
  c.push(TX(1330, 838, 'now', { size: 11, color: T.dim }))
  return { name: 'pages.poc.overview#dashboard', x: 0, y: 170, w: 1440, h: 900, fill: T.bg, title: '总览 · 六区状态与吞吐', source: 'src/App.tsx · Overview', note: '面试 30 秒：哪条线卡住、卡了多久、断网有没有丢数', children: c }
})()

// ---------- 02 单线详情 ----------
const b2 = (() => {
  const W = 1440
  const c = []
  c.push(...header(W, [
    ...statusChip(1136, 28, '10Hz 采集中', T.ok),
    TX(1372, 22, '21:36:12', { size: 14, color: T.sub, w: 44, align: 'right' }),
  ]))
  c.push(R(0, 64, W, 44, T.bg), TX(24, 76, '总览  /  Z3 分流 A  /  D02', { size: 12, color: T.sub }))
  c.push(R(1104, 72, 132, 28, T.card, 14, { strokeColor: T.line }), TX(1120, 78, '切换区 ▾', { size: 12, color: T.sub }))

  // 缩放：− / 百分比 / + / 复位；滚轮与双击也走同一条路径（ADR-0003 的抽样策略在这里生效）
  c.push(...panel(24, 128, 900, 420, '速度趋势 · D02 · 10Hz', [
    R(516, 144, 52, 28, T.card2, 14), TX(530, 150, '1m', { size: 12, color: T.text }),
    R(574, 144, 52, 28, null, 14), TX(588, 150, '5m', { size: 12, color: T.dim }),
    R(632, 144, 52, 28, null, 14), TX(646, 150, '1h', { size: 12, color: T.dim }),
    R(716, 144, 28, 28, T.card, 8, { strokeColor: T.line }), TX(725, 148, '−', { size: 15, color: T.text }),
    R(748, 144, 56, 28, null, 8), TX(757, 150, '100%', { size: 12, color: T.sub }),
    R(808, 144, 28, 28, T.card, 8, { strokeColor: T.line }), TX(817, 148, '+', { size: 15, color: T.text }),
    R(844, 144, 56, 28, null, 8), TX(852, 150, '复位', { size: 11, color: T.dim }),
    TX(716, 178, '滚轮缩放 · 双击复位 · 缩放后按可见窗口重新抽样', { size: 10, color: T.dim }),
  ]))
  // 10Hz 的证据是一个「波形」，不是柱状图：600 个点、1.37px/点，画成面积图；
  // 中间空 8 秒 = 断网，曲线断开但恢复后补齐——这一屏就是给「抗不抗得住 10Hz」看的。
  const chartX = 64, chartW = 820, baseY = 450, chartH = 235, nPts = 600
  for (let g = 0; g < 4; g++) c.push(R(chartX, 200 + g * 62, chartW, 1, T.line))
  for (let i = 0; i < nPts; i++) {
    if (i >= 240 && i < 320) continue
    const t = i / nPts
    const v = 0.55 + 0.18 * Math.sin(t * Math.PI * 2 * 2.5) + 0.05 * Math.sin(t * Math.PI * 2 * 23) + 0.035 * Math.sin(i * 1.7)
    const h = Math.max(8, v * chartH)
    c.push(R(chartX + i * 1.37, baseY - h, 1.6, h, T.accent, 0))
  }
  c.push(R(chartX, baseY, chartW, 1, T.dim))
  c.push(R(chartX + 240 * 1.37, 206, 80 * 1.37, chartH + 4, T.bad, 0, { opacity: 0.1 }))
  c.push(TX(chartX + 240 * 1.37 + 6, 224, '断网 8s', { size: 11, color: T.bad }))
  c.push(TX(chartX - 6, 196, '0.8', { size: 10, color: T.dim }))
  c.push(TX(chartX - 6, baseY - 8, '0.0', { size: 10, color: T.dim }))
  ;['−60s', '−45s', '−30s', '−15s', 'now'].forEach((t, i) => c.push(TX(chartX + i * 200, 460, t, { size: 10, color: T.dim })))
  // 指标条：把「10Hz 扛得住」变成四个可核对的数
  const metric = (x, label, val, color) => [TX(x, 486, label, { size: 10, color: T.dim }), TX(x, 502, val, { size: 16, weight: 600, color: color || T.text })]
  c.push(...metric(chartX, '采样率', '10 Hz'))
  c.push(...metric(chartX + 150, '窗口点数', '600'))
  c.push(...metric(chartX + 300, '缩放 · 60s 窗口', '100%'))
  c.push(...metric(chartX + 490, '渲染', '58 fps', T.ok))
  c.push(...metric(chartX + 640, '帧耗时 P95', '12 ms', T.ok))

  const rx = 944, rw = 472
  c.push(...panel(rx, 128, rw, 420, '点位明细'))
  c.push(TX(rx + 20, 164, '驱动', { size: 11, color: T.dim }), TX(rx + 200, 164, '速度', { size: 11, color: T.dim }), TX(rx + 290, 164, '电流', { size: 11, color: T.dim }), TX(rx + 370, 164, '状态', { size: 11, color: T.dim }))
  for (let i = 0; i < 6; i++) {
    const y = 188 + i * 56
    c.push(R(rx + 20, y, rw - 40, 48, T.card, 8))
    c.push(TX(rx + 34, y + 14, `D0${i + 1}`, { size: 13, weight: 500 }))
    c.push(TX(rx + 200, y + 14, `${(0.8 - i * 0.01).toFixed(2)} m/s`, { size: 12, color: T.sub }))
    c.push(TX(rx + 290, y + 14, `${(2.1 + i * 0.2).toFixed(1)} A`, { size: 12, color: i === 2 ? T.warn : T.sub }))
    c.push(R(rx + 362, y + 16, 8, 8, i === 2 ? T.warn : T.ok, 4))
    c.push(TX(rx + 376, y + 11, i === 2 ? '降速' : '运行', { size: 11, color: i === 2 ? T.warn : T.sub }))
  }

  c.push(...panel(24, 568, 1392, 280, '补传水位线', [TX(24 + 1290, 584, '已恢复', { size: 11, color: T.ok })]))
  c.push(TX(44, 612, '本地缓存 → 边缘库 → 中心库', { size: 12, color: T.sub }))
  c.push(R(44, 644, 900, 10, T.card2, 5), R(44, 644, 702, 10, T.ok, 5))
  c.push(TX(44, 666, '水位 21:35:58 · 滞后 14s', { size: 11, color: T.dim }), TX(804, 666, '补传 1,284 条', { size: 11, color: T.dim }))
  const stat = (x, label, val, color) => [TX(x, 704, label, { size: 11, color: T.dim }), TX(x, 722, val, { size: 22, weight: 600, color: color || T.text })]
  c.push(...stat(44, '待补条数', '0', T.ok))
  c.push(...stat(260, '断网次数 · 今日', '1'))
  c.push(...stat(476, '最大滞后', '42s'))
  c.push(...stat(692, '幂等冲突', '0', T.ok))
  c.push(R(944, 636, 452, 196, T.card, 10, { strokeColor: '#2A1F24' }))
  c.push(R(944, 636, 3, 196, T.warn, 2))
  c.push(TX(960, 656, '断网演练', { size: 12, color: T.warn, weight: 600 }))
  c.push(TX(960, 682, '21:31:04 边缘机与中心失联 8s，', { size: 12, color: T.sub, w: 420 }))
  c.push(TX(960, 702, 'Broker 本地保留，恢复后按', { size: 12, color: T.sub, w: 420 }))
  c.push(TX(960, 722, 'device+ts 幂等键补齐，零丢点。', { size: 12, color: T.sub, w: 420 }))
  c.push(TX(960, 762, '讲法：先落本地，再谈一致。', { size: 11, color: T.dim }))
  return { name: 'pages.poc.zone-detail#zone', x: 1520, y: 170, w: 1440, h: 900, fill: T.bg, title: '单线详情 · 10Hz 与聚合切换', source: 'src/pages/ZoneDetail.tsx', note: '现场演示：切窗口不卡、断网 8s 后曲线无空洞', children: c }
})()

// ---------- 03 诊断包 ----------
const b3 = (() => {
  const W = 1440
  const c = []
  c.push(...header(W, [
    ...statusChip(1136, 28, '可移交', T.ok),
    TX(1372, 22, '21:36:12', { size: 14, color: T.sub, w: 44, align: 'right' }),
  ]))
  c.push(R(0, 64, W, 44, T.bg), TX(24, 76, '运维  /  诊断包', { size: 12, color: T.sub }))
  c.push(R(1204, 72, 188, 28, T.card, 14, { strokeColor: T.line }), TX(1216, 78, '导出诊断包 .zip', { size: 12, color: T.text }))

  const cols = [24, 494, 964], cw = 450
  c.push(...panel(cols[0], 128, cw, 440, '服务状态'))
  const svc = [
    ['Mosquitto', '2.0.18', '运行 2d 04h', T.ok, '1884 · 36 连接'],
    ['TimescaleDB', 'pg17 · 2.17', '运行 2d 04h', T.ok, 'hypertable 1 / 聚合 3'],
    ['API', 'v0.3.1', '运行 2d 04h', T.ok, 'WS 会话 2'],
    ['Web', 'v0.3.1', '运行 2d 04h', T.ok, '静态资源 12'],
  ]
  svc.forEach((s, i) => {
    const y = 168 + i * 96
    c.push(R(cols[0] + 20, y, cw - 40, 84, T.card, 10))
    c.push(R(cols[0] + 36, y + 20, 8, 8, s[3], 4))
    c.push(TX(cols[0] + 54, y + 14, s[0], { size: 13, weight: 600 }))
    c.push(TX(cols[0] + 54, y + 36, `${s[1]} · ${s[2]}`, { size: 11, color: T.sub }))
    c.push(TX(cols[0] + 54, y + 56, s[4], { size: 11, color: T.dim }))
  })

  c.push(...panel(cols[1], 128, cw, 440, '补传与队列'))
  const big = (y, label, val, sub, color) => [
    TX(cols[1] + 20, y, label, { size: 11, color: T.dim }),
    TX(cols[1] + 20, y + 20, val, { size: 26, weight: 600, color: color || T.text }),
    TX(cols[1] + 20, y + 58, sub, { size: 11, color: T.sub }),
  ]
  c.push(...big(168, '待补条数', '0', '最近 24h 累计补传 3,842 条', T.ok))
  c.push(R(cols[1] + 20, 254, cw - 40, 1, T.line))
  c.push(...big(270, '最大滞后', '42s', '阈值 60s，未触发告警'))
  c.push(R(cols[1] + 20, 356, cw - 40, 1, T.line))
  c.push(...big(372, '幂等冲突', '0', '键 = device_id + ts(ms) + seq'))
  c.push(R(cols[1] + 20, 470, cw - 40, 10, T.card2, 5), R(cols[1] + 20, 470, (cw - 40) * 0.78, 10, T.ok, 5))
  c.push(TX(cols[1] + 20, 492, '队列水位 78% 已消费', { size: 11, color: T.dim }))

  c.push(...panel(cols[2], 128, cw, 440, '诊断包含什么'))
  const items = [
    'system.json — 版本 / 运行时长 / 端口',
    'config.redacted.yaml — 配置脱敏',
    'logs/ — 最近 2,000 行（按级别）',
    'mqtt-tail.ndjson — 最近 100 条消息',
    'db-stats.txt — 表大小 / 聚合新鲜度',
  ]
  items.forEach((t, i) => {
    const y = 168 + i * 46
    c.push(R(cols[2] + 20, y + 6, 14, 14, null, 3, { strokeColor: T.ok }))
    c.push(TX(cols[2] + 44, y, t, { size: 12, color: T.sub }))
  })
  c.push(R(cols[2] + 20, 404, cw - 40, 44, T.brand, 10))
  c.push(TX(cols[2] + 20, 418, '导出 .zip（约 2.1 MB）', { size: 13, weight: 600, w: cw - 40, align: 'center' }))
  c.push(TX(cols[2] + 20, 462, '集成商拿到就能发邮件，不用登机器。', { size: 11, color: T.dim }))

  c.push(...panel(24, 592, 1392, 284, '版本与回滚'))
  c.push(TX(44, 628, '当前版本', { size: 11, color: T.dim }), TX(44, 648, 'v0.3.1 · 镜像 tag sha-9f2c1', { size: 13 }))
  c.push(TX(44, 684, '上一版本', { size: 11, color: T.dim }), TX(44, 704, 'v0.3.0 · 保留 2 个历史 tag', { size: 13, color: T.sub }))
  c.push(TX(44, 750, '回滚：make rollback → 切 tag → 健康检查 → 无流量时 30s 内完成', { size: 12, color: T.sub }))
  c.push(R(900, 628, 476, 210, '#0A0E13', 10, { strokeColor: T.line }))
  c.push(TX(920, 644, '$ make diag', { size: 12, color: T.ok }))
  c.push(TX(920, 670, '$ make rollback TAG=v0.3.0', { size: 12, color: T.sub }))
  c.push(TX(920, 696, '$ make verify', { size: 12, color: T.ok }))
  c.push(TX(920, 730, '三条命令 = 面试里「可移交」的实物。', { size: 11, color: T.dim }))
  c.push(R(920, 760, 436, 1, T.line))
  c.push(TX(920, 774, '诊断包 2.1MB · 生成 1.4s', { size: 11, color: T.dim }))
  return { name: 'pages.poc.diagnostics#diag', x: 3040, y: 170, w: 1440, h: 900, fill: T.bg, title: '诊断包 · 可移交的那一面', source: 'src/pages/Diagnostics.tsx', note: '讲法：出问题不用登机器，集成商自己救', children: c }
})()

// ---------- 04 移动端 ----------
const b4 = (() => {
  const W = 390, H = 844
  const c = []
  c.push(R(0, 0, W, 56, T.panel), R(0, 55, W, 1, T.line))
  c.push(R(16, 16, 22, 22, T.brand, 6))
  c.push(TX(46, 16, '产线遥测', { size: 15, weight: 600 }))
  c.push(R(346, 20, 8, 8, T.ok, 4))
  c.push(TX(16, 34, 'v0.3.1 · 6 区', { size: 10, color: T.dim }))

  const mini = (x, y, w, label, val, color) => [
    R(x, y, w, 82, T.card, 10, { strokeColor: T.line }),
    TX(x + 12, y + 12, label, { size: 10, color: T.sub }),
    TX(x + 12, y + 32, val, { size: 22, weight: 600, color: color || T.text }),
  ]
  c.push(...mini(16, 72, 171, '吞吐', '1,284', T.text), ...mini(203, 72, 171, '在线驱动', '30/36', T.warn))
  c.push(...mini(16, 164, 171, '延迟', '180ms', T.text), ...mini(203, 164, 171, '告警', '3', T.warn))

  c.push(TX(16, 264, '分区', { size: 12, color: T.sub }))
  zones.forEach((z, i) => {
    const y = 288 + i * 62
    c.push(R(16, y, 358, 54, T.card, 10))
    c.push(R(28, y + 18, 8, 8, stColor[z.st], 4))
    c.push(TX(44, y + 12, `${z.id} · ${z.name}`, { size: 12, weight: 500 }))
    c.push(TX(44, y + 30, stText[z.st] + (z.st === 'off' ? ' · 断网 8s' : ''), { size: 10, color: stColor[z.st] }))
    c.push(TX(316, y + 19, z.tps ? `${z.tps}` : '—', { size: 14, weight: 600, color: z.tps ? T.text : T.dim, w: 44, align: 'right' }))
  })

  c.push(R(16, 672, 358, 96, T.card, 10, { strokeColor: '#2A1F24' }))
  c.push(R(16, 672, 3, 96, T.bad, 2))
  c.push(TX(32, 686, '21:35 · Z6 出货段', { size: 11, color: T.sub }))
  c.push(TX(32, 706, '驱动 D03 电流超限 4.8A', { size: 12 }))
  c.push(TX(32, 726, '已降速，等待人工确认', { size: 11, color: T.dim }))
  c.push(TX(16, 792, '下拉刷新 · 告警推送已开', { size: 10, color: T.dim, w: 358, align: 'center' }))
  return { name: 'pages.poc.mobile-overview#mobile', x: 4560, y: 170, w: 390, h: 844, fill: T.bg, title: '移动端 · 现场值班', source: 'src/pages/Mobile.tsx', note: '现场工程师拿手机看：先看红点，再点进区', children: c }
})()

const spec = {
  page: '设计 / 产线看板（PoC）',
  title: '英特诺 PoC · 产线看板',
  source: '原型：docs/design/screens/poc-dashboard.json（由 gen-spec.mjs 生成）',
  boards: [b1, b2, b3, b4],
  notes: {
    index: ['01 总览', '02 单线详情', '03 诊断包', '04 移动端'],
    notes: [
      '已定：深色工业风，绿=运行 / 黄=积压 / 灰=离线 / 红=故障，颜色即语义。',
      '已定：三屏各管一件事——看懂产线、讲清 10Hz、证明可移交。',
      '待确认：主色是否改成英特诺品牌红（现仅 logo 用红，数据用青）。',
      '未画：登录页、告警规则配置页（演示不需要）。',
    ],
  },
}

const out = resolve(HERE, 'screens/poc-dashboard.json')
mkdirSync(dirname(out), { recursive: true })
writeFileSync(out, JSON.stringify(spec, null, 2))
const n = spec.boards.reduce((a, b) => a + b.children.length, 0)
console.log(`✓ ${out}`)
console.log(`  boards=${spec.boards.length} children=${n}`)
