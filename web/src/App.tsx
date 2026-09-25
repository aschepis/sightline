import { useEffect, useState } from 'react'
import { useCapabilities } from './engine/hooks'
import { engine } from './engine'
import { FaceBlurPage } from './pages/FaceBlurPage'
import { HomePage } from './pages/HomePage'
import { ModelsPage } from './pages/ModelsPage'
import { SettingsPage } from './pages/SettingsPage'
import { SmudgePage } from './pages/SmudgePage'
import { TranscribePage } from './pages/TranscribePage'

export type Route = 'home' | 'blur' | 'smudge' | 'transcribe' | 'models' | 'settings'

const NAV: Array<{ route: Route; label: string }> = [
  { route: 'home', label: 'Home' },
  { route: 'blur', label: 'Blur Faces' },
  { route: 'smudge', label: 'Face Smudge' },
  { route: 'transcribe', label: 'Transcription' },
  { route: 'models', label: 'Models' },
  { route: 'settings', label: 'Settings' },
]

function routeFromHash(): Route {
  const hash = location.hash.replace('#/', '').replace('#', '') as Route
  return NAV.some((n) => n.route === hash) ? hash : 'home'
}

export default function App() {
  const [route, setRoute] = useState<Route>(routeFromHash)
  const caps = useCapabilities()
  useEffect(() => {
    const onHash = () => setRoute(routeFromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])
  const go = (r: Route) => {
    window.location.assign(`#/${r}`)
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <img src={`${import.meta.env.BASE_URL}icon.png`} alt="" />
          <span>Sightline</span>
        </div>
        {NAV.map((n) => (
          <button key={n.route} className={`nav-item ${route === n.route ? 'active' : ''}`} onClick={() => go(n.route)}>
            {n.label}
          </button>
        ))}
        <div className="spacer" />
        <div className="small muted">
          {caps ? (
            <>
              Compute: <strong>{engine.activeBackend()}</strong>
              <br />
              {caps.webcodecs ? 'WebCodecs ready' : 'No WebCodecs: video disabled'}
              <br />
              {caps.crossOriginIsolated ? 'Multi-threaded' : 'Single-threaded'}
            </>
          ) : (
            'Probing device…'
          )}
        </div>
      </aside>
      <main className="main">
        {route === 'home' && <HomePage go={go} />}
        {route === 'blur' && <FaceBlurPage />}
        {route === 'smudge' && <SmudgePage />}
        {route === 'transcribe' && <TranscribePage />}
        {route === 'models' && <ModelsPage />}
        {route === 'settings' && <SettingsPage />}
      </main>
    </div>
  )
}
