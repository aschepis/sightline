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
        <a className="nav-item nav-link" href="https://github.com/aschepis/sightline" target="_blank" rel="noopener noreferrer">
          <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" fill="currentColor">
            <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z" />
          </svg>
          Source on GitHub
        </a>
        <div className="spacer" />
        <a className="kofi" href="https://ko-fi.com/N4N8U0J6M" target="_blank" rel="noopener noreferrer">
          ♥ Support Sightline on Ko-fi
        </a>
        <div className="small muted">
          {caps ? (
            <>
              {engine.activeBackend() === 'remote' ? 'Sending files to your server' : 'Working on this computer'}
              <br />
              {engine.activeBackend() === 'webgpu' ? 'Using the graphics card' : engine.activeBackend() === 'wasm' ? 'Using the main processor' : ''}
              <br />
              {caps.webcodecs ? 'Video editing available' : 'Video needs a newer browser'}
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
