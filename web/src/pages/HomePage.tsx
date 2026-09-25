import type { Route } from '../App'

export function HomePage({ go }: { go: (r: Route) => void }) {
  return (
    <>
      <div className="page-header">
        <h1>Sightline</h1>
      </div>
      <p className="muted">Privacy-first media tools. Every file is processed on this device and never uploaded.</p>
      <div className="grid-3" style={{ marginTop: 20 }}>
        <div className="card" onClick={() => go('blur')}>
          <div className="emoji">🛡️</div>
          <h2>Blur Faces</h2>
          <p className="muted">Automatically detect and blur faces in images and videos, in batches.</p>
        </div>
        <div className="card" onClick={() => go('smudge')}>
          <div className="emoji">🎨</div>
          <h2>Face Smudge</h2>
          <p className="muted">Manually blur faces or sensitive details frame by frame, then export.</p>
        </div>
        <div className="card" onClick={() => go('transcribe')}>
          <div className="emoji">📝</div>
          <h2>Transcription</h2>
          <p className="muted">Speech to text with speaker labels, entirely in the browser.</p>
        </div>
      </div>
      <div className="panel" style={{ marginTop: 24 }}>
        <h3>How it works</h3>
        <p>
          Models download once and stay cached, so the app keeps working offline. Install it from your browser menu to get a desktop-style window. Heavy jobs can optionally be
          sent to a server you control from <a href="#/settings">Settings</a>.
        </p>
      </div>
    </>
  )
}
