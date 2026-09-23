'use client';

import { useEffect, useRef, useState } from 'react';
import { FaceBox, RECOVERABLE, STABLE_FRAMES, SAMPLE_COUNT, isStable, median } from './camera-scan';
import ThemeToggle from './theme-toggle';
import ResultVoice from './result-voice';
import ResultFeedback from './result-feedback';
import CameraQuality, { CaptureQuality } from './camera-quality';

type Mode = 'camera' | 'upload';
type Phase = 'idle' | 'opening' | 'analyzing' | 'done' | 'error';
type Prediction = { estimated_age: number; ready?: boolean; face_box?: FaceBox; quality?: CaptureQuality; error?: { code: string; message: string } };

export default function Home() {
  const [mode, setMode] = useState<Mode>('camera');
  const [phase, setPhase] = useState<Phase>('idle');
  const [message, setMessage] = useState('Position yourself in good light, facing the camera.');
  const [age, setAge] = useState<number | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [faceBox, setFaceBox] = useState<FaceBox | null>(null);
  const [frameSize, setFrameSize] = useState({ width: 960, height: 720 });
  const [scanProgress, setScanProgress] = useState(0);
  const [quality, setQuality] = useState<CaptureQuality | null>(null);
  const [steady, setSteady] = useState(false);
  const lastBox = useRef<FaceBox | null>(null);
  const stableFrames = useRef(0);
  const samples = useRef<number[]>([]);
  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const request = useRef<AbortController | null>(null);
  const generation = useRef(0);
  const previewUrl = useRef<string | null>(null);

  function releaseCamera() { stream.current?.getTracks().forEach(track => track.stop()); stream.current = null; }
  function cancel() {
    generation.current += 1;
    if (timer.current) clearTimeout(timer.current);
    request.current?.abort(); releaseCamera();
    resetScan();
  }
  function resetScan(box: FaceBox | null = null) {
    lastBox.current = box; stableFrames.current = 0; samples.current = [];
    setFaceBox(box); setScanProgress(0);
    setQuality(null); setSteady(false);
  }
  function clearPreview() {
    if (previewUrl.current) URL.revokeObjectURL(previewUrl.current);
    previewUrl.current = null; setPreview(null);
  }
  useEffect(() => () => {
    generation.current += 1;
    if (timer.current) clearTimeout(timer.current);
    request.current?.abort(); stream.current?.getTracks().forEach(track => track.stop());
    if (previewUrl.current) URL.revokeObjectURL(previewUrl.current);
  }, []);

  function changeMode(next: Mode) {
    cancel(); clearPreview(); setMode(next); setPhase('idle'); setAge(null);
    setMessage(next === 'camera' ? 'Position yourself in good light, facing the camera.' : 'Choose a clear photo with one face.');
  }
  async function predict(blob: Blob, token: number, fromCamera: boolean) {
    const controller = new AbortController(); request.current = controller;
    const timeout = setTimeout(() => controller.abort(), 30000);
    try {
      const form = new FormData(); form.append('image', blob, 'portrait.jpg');
      const scanning = fromCamera && stableFrames.current < STABLE_FRAMES;
      if (fromCamera) form.append('source', 'camera');
      const response = await fetch(scanning ? '/api/scan' : '/api/predict', { method: 'POST', body: form, signal: controller.signal });
      const data: Prediction = await response.json().catch(() => {
        throw new Error('The age service is not reachable. Start the backend and try again.');
      });
      if (token !== generation.current) return;
      if (!response.ok) {
        if (fromCamera && RECOVERABLE.includes(data.error?.code || '')) {
          resetScan(data.face_box || null);
          setQuality(data.quality || null);
          setMessage(data.error!.message); timer.current = setTimeout(() => capture(token), 650); return;
        }
        throw new Error(data.error?.message || 'Analysis failed. Please try again.');
      }
      let finalAge = data.estimated_age;
      if (fromCamera) {
        if (!data.face_box) throw new Error('Face scan unavailable. Please restart the backend and try again.');
        setFaceBox(data.face_box);
        setQuality(data.quality || null);
        if (!isStable(lastBox.current, data.face_box)) {
          samples.current = []; stableFrames.current = 1;
        } else stableFrames.current += 1;
        lastBox.current = data.face_box;
        setSteady(stableFrames.current >= STABLE_FRAMES);
        if (!scanning && stableFrames.current > STABLE_FRAMES) {
          if (!Number.isFinite(data.estimated_age)) throw new Error('The server returned an invalid result.');
          samples.current.push(data.estimated_age);
        }
        setScanProgress(Math.min(100, (Math.min(stableFrames.current, STABLE_FRAMES) + samples.current.length) / (STABLE_FRAMES + SAMPLE_COUNT) * 100));
        if (samples.current.length < SAMPLE_COUNT) {
          setMessage(samples.current.length ? `Scanning your face — ${samples.current.length} of ${SAMPLE_COUNT} clear frames. Hold still.` : 'Face detected. Hold still while the scan prepares.');
          timer.current = setTimeout(() => capture(token), 450); return;
        }
        if (Math.max(...samples.current) - Math.min(...samples.current) > 8) {
          resetScan(data.face_box); setMessage('The estimate is changing. Hold still in even light for another scan.');
          timer.current = setTimeout(() => capture(token), 650); return;
        }
        finalAge = median(samples.current);
      }
      if (!Number.isFinite(finalAge)) throw new Error('The server returned an invalid result.');
      setAge(Math.round(finalAge)); setPhase('done'); setMessage('Your estimate is ready.');
      releaseCamera();
    } catch (error) {
      if (token !== generation.current) return;
      releaseCamera(); setPhase('error');
      setMessage(error instanceof Error && error.name !== 'AbortError' ? error.message : 'The request timed out. Please try again.');
    } finally { clearTimeout(timeout); }
  }
  async function capture(token: number) {
    if (token !== generation.current) return;
    const element = video.current;
    if (!element || !element.videoWidth) { timer.current = setTimeout(() => capture(token), 300); return; }
    const canvas = document.createElement('canvas');
    const scale = Math.min(1, 1280 / element.videoWidth);
    canvas.width = Math.round(element.videoWidth * scale); canvas.height = Math.round(element.videoHeight * scale);
    setFrameSize({ width: canvas.width, height: canvas.height });
    canvas.getContext('2d')!.drawImage(element, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise<Blob | null>(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.95));
    if (token !== generation.current || !blob) return;
    if (previewUrl.current) URL.revokeObjectURL(previewUrl.current);
    previewUrl.current = URL.createObjectURL(blob); setPreview(previewUrl.current);
    await predict(blob, token, true);
  }
  async function openCamera() {
    cancel(); clearPreview(); setAge(null); setPhase('opening'); setMessage('Allow camera access to begin.');
    const token = generation.current;
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error('Camera access requires localhost or HTTPS and a supported browser.');
      const media = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 960 } }, audio: false });
      if (token !== generation.current) { media.getTracks().forEach(track => track.stop()); return; }
      stream.current = media;
      if (video.current) { video.current.srcObject = media; await video.current.play(); }
      if (token !== generation.current) return;
      setPhase('analyzing'); setMessage('Looking for one clear face…');
      timer.current = setTimeout(() => capture(token), 1500);
    } catch (error) {
      if (token !== generation.current) return;
      releaseCamera(); setPhase('error');
      setMessage(error instanceof DOMException && error.name === 'NotAllowedError' ? 'Camera access was denied. Allow access in your browser or upload an image.' : error instanceof Error ? error.message : 'Could not open the camera.');
    }
  }
  async function upload(file?: File) {
    if (!file) return;
    cancel(); clearPreview(); setAge(null);
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 8 * 1024 * 1024) {
      setPhase('error'); setMessage('Choose a JPG, PNG or WebP image under 8 MB.'); return;
    }
    previewUrl.current = URL.createObjectURL(file); setPreview(previewUrl.current);
    setPhase('analyzing'); setMessage('Analyzing your photo…');
    await predict(file, generation.current, false);
  }
  const busy = phase === 'opening' || phase === 'analyzing';
  return <main>
    <header><div className="brand-group"><a className="brand" href="https://www.goobolabs.so/en" aria-label="Goobo Labs website"><img src="/brand/goobo-logo.svg" alt="Goobo Labs" width="120" height="34" /></a><span className="product-name">Da’qiyaas<span>Computer vision</span></span></div><nav aria-label="Main navigation"><ThemeToggle /><a className="site-link" href="https://www.goobolabs.so/en">Explore Goobo Labs <span aria-hidden="true">↗</span></a><a className="nav-cta" href="#workspace">Try the model <span aria-hidden="true">↗</span></a></nav></header>
    <section className="intro"><div><div className="eyebrow"><span /> COMPUTER VISION · INTERACTIVE DEMO</div><h1>A clearer look at<br /><span>age estimation.</span></h1></div><div className="intro-copy"><p>One face. A few clear frames.<br />Explore an age estimate with a live scan or upload a portrait to get started.</p><div className="hero-tags"><span>Live face scan</span><span>Image upload</span></div></div></section>
    <div className="workspace-heading"><span className="badge"><i /> TRY IT LIVE</span><span>A portrait in. A perspective out.</span></div>
    <section id="workspace" className="workspace" aria-label="Age estimation workspace">
      <div className="input-panel"><div className="tabs" role="group" aria-label="Input method"><button aria-pressed={mode === 'camera'} className={mode === 'camera' ? 'active' : ''} onClick={() => changeMode('camera')}>◎ &nbsp; Live camera</button><button aria-pressed={mode === 'upload'} className={mode === 'upload' ? 'active' : ''} onClick={() => changeMode('upload')}>↥ &nbsp; Upload image</button></div>
        <div className={`viewfinder ${busy ? 'scanning' : ''}`}>
          <video ref={video} muted playsInline className={mode === 'camera' && busy ? 'visible' : 'hidden'} />
          {mode === 'camera' && busy && faceBox && <svg className="face-scan-overlay" viewBox={`0 0 ${frameSize.width} ${frameSize.height}`} preserveAspectRatio="xMidYMid meet" aria-label="Detected face scan">
            <svg x={(1 - faceBox.x - faceBox.width) * frameSize.width} y={faceBox.y * frameSize.height} width={faceBox.width * frameSize.width} height={faceBox.height * frameSize.height} viewBox="0 0 100 100" preserveAspectRatio="none">
              <rect x="1" y="1" width="98" height="98" rx="8" fill="#78e8bc14" stroke="#98ffca" strokeWidth="1" />
              <path d="M 0 25 H 100 M 0 50 H 100 M 0 75 H 100 M 25 0 V 100 M 50 0 V 100 M 75 0 V 100" stroke="#98ffca" strokeWidth=".3" opacity=".5" />
              <path className="face-scan-line" d="M 2 5 H 98" stroke="#c9ffe0" strokeWidth="1.4" />
            </svg>
          </svg>}
          {preview && !busy && <img src={preview} alt="Portrait used for age estimation" />}
          {preview && mode === 'upload' && busy && <img src={preview} alt="Uploaded portrait" />}
          {!preview && !busy && <div className="placeholder"><div className="face-outline"><span /></div><h2>{mode === 'camera' ? 'Your moment in focus' : 'Bring your own portrait'}</h2><p>{mode === 'camera' ? 'Open your camera. We’ll take it from there.' : 'A front-facing photo works best.'}</p></div>}
          {busy && <div className="scan-label"><span className="pulse" /> {phase === 'opening' ? 'Opening camera' : mode === 'camera' ? (faceBox ? `Scanning face · ${Math.round(scanProgress)}%` : 'Looking for a clear face') : 'Analysis in progress'}</div>}
          <i className="corner tl"/><i className="corner tr"/><i className="corner bl"/><i className="corner br"/>
        </div>
        {mode === 'camera' && <CameraQuality quality={quality} stable={steady} />}<div className="actions">{mode === 'camera' ? <button className="primary" disabled={busy} onClick={openCamera}>{phase === 'done' || phase === 'error' ? 'Try Again' : 'Open Camera'} <span>↗</span></button> : <label className="primary upload">{preview ? 'Choose Another Image' : 'Upload Image'} <span>↥</span><input type="file" accept="image/jpeg,image/png,image/webp" onChange={event => { void upload(event.target.files?.[0]); event.target.value = ''; }} /></label>}{busy && <button className="cancel" onClick={() => { cancel(); setPhase('idle'); setMessage('Analysis cancelled. You can start again.'); }}>Cancel</button>}</div>
        <p className="input-hint">{mode === 'camera' ? 'Camera access starts only when you choose.' : 'JPG, PNG or WebP · Up to 8 MB'}</p>
      </div>
      <aside className="result-panel"><div className="eyebrow">THE OUTPUT</div><h2>Your age estimate.</h2><div className={`age-card ${phase === 'done' ? 'complete' : ''}`}><span className="result-label">ESTIMATED AGE</span><div className="age-number">{age ?? '—'}{age !== null && <span>years</span>}</div><span className="result-tag">{phase === 'done' ? 'Analysis complete' : 'Waiting for your portrait'}</span></div><p className={`status ${phase === 'error' ? 'error' : ''}`} role="status" aria-live="polite">{message}</p><ResultVoice age={age} />{phase === 'done' && age !== null && <ResultFeedback age={age} source={mode} preview={preview} />}<div className="tips"><h3>A little preparation. A clearer scan.</h3><p><span>01</span> Face forward in even lighting</p><p><span>02</span> Keep only one face in the frame</p><p><span>03</span> Remove anything covering your face</p></div><p className="disclaimer">An estimate, not a verified age. Results can vary with lighting, image quality and the model.</p></aside>
    </section><a className="accuracy-link" href="/accuracy">View accuracy dashboard →</a><footer><span><span className="privacy-dot" /> Photos are saved only with your separate training consent.</span><a href="https://www.goobolabs.so/en">Goobo Labs <span aria-hidden="true">↗</span></a></footer>
  </main>;
}
