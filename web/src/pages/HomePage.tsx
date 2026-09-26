import type { Route } from '../App'

export function HomePage({ go }: { go: (r: Route) => void }) {
  return (
    <>
      <div className="page-header">
        <h1>Sightline</h1>
      </div>
      <div className="notice info" style={{ marginBottom: 16 }}>
        <strong>Your files stay on your computer.</strong> Sightline does all of its work inside this browser tab, on your own machine. Nothing is uploaded, no video or
        audio is sent to a server, and no outside service ever sees your files. You can even turn off your internet connection after the page loads and it keeps working.
      </div>
      <div className="grid-3" style={{ marginTop: 20 }}>
        <div className="card" onClick={() => go('blur')}>
          <div className="emoji">🛡️</div>
          <h2>Blur Faces</h2>
          <p className="muted">Finds faces in photos and videos and blurs them for you. Works on many files at once.</p>
        </div>
        <div className="card" onClick={() => go('smudge')}>
          <div className="emoji">🎨</div>
          <h2>Face Smudge</h2>
          <p className="muted">Paint a blur over anything you choose, frame by frame, then save a new copy of the video.</p>
        </div>
        <div className="card" onClick={() => go('transcribe')}>
          <div className="emoji">📝</div>
          <h2>Transcription</h2>
          <p className="muted">Turns recordings into written text and labels who is speaking.</p>
        </div>
      </div>
      <div className="panel" style={{ marginTop: 24 }}>
        <h3>How it works</h3>
        <p>
          The first time you use a tool, the app downloads the recognition software it needs (a few megabytes for face blurring, more for transcription) and keeps a copy in
          your browser. That download is the only time the app talks to the internet. Your photos, videos and recordings are opened and edited right here and are never sent
          anywhere. When a job finishes, you choose where to save the result.
        </p>
        <p className="muted small">Sightline can be installed like an app from your browser's menu.</p>
      </div>
    </>
  )
}
