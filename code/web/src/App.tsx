import { useEffect, useState } from 'react'
import { Header } from './components/Header'
import { Overview } from './pages/Overview'
import { ZoneDetail } from './pages/ZoneDetail'
import { useLive, usePoll } from './lib/api'
import type { Health } from './lib/api'

export function App() {
  const [path, setPath] = useState(location.pathname)
  useEffect(() => {
    const onNav = () => setPath(location.pathname)
    addEventListener('popstate', onNav)
    return () => removeEventListener('popstate', onNav)
  }, [])
  const [health] = usePoll<Health>('/healthz', 5000)
  const { points, connected } = useLive()
  const go = (to: string) => { history.pushState({}, '', to); setPath(to) }

  const m = path.match(/^\/zone\/([^/]+)\/([^/]+)/)
  return (
    <>
      <Header health={health} connected={connected} />
      {m
        ? <ZoneDetail zone={m[1]} drive={m[2]} live={points} health={health} onBack={() => go('/')} />
        : <Overview live={points} health={health} onOpen={(z, d) => go(`/zone/${z}/${d}`)} />}
    </>
  )
}
