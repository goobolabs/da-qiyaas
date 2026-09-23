'use client';

import { useEffect, useRef, useState } from 'react';

export default function ResultFeedback({ age, source, preview }: { age: number; source: 'camera' | 'upload'; preview: string | null }) {
  const [actualAge, setActualAge] = useState('');
  const [consent, setConsent] = useState(false);
  const [trainingConsent, setTrainingConsent] = useState(false);
  const [status, setStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [message, setMessage] = useState('');
  const [toast, setToast] = useState('');
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(''), 6000);
    return () => clearTimeout(timer);
  }, [toast]);
  const submission = useRef<string | null>(null);
  const pending = useRef<AbortController | null>(null);
  const locked = useRef(false);
  useEffect(() => () => pending.current?.abort(), []);
  const actual = Number(actualAge);
  const valid = actualAge.trim() !== '' && Number.isInteger(actual) && actual >= 0 && actual <= 120;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!valid || !consent || locked.current || status === 'saved') return;
    locked.current = true;
    setStatus('saving'); setMessage('Saving feedback...');
    const controller = new AbortController(); pending.current = controller;
    const timeout = setTimeout(() => controller.abort(), 15000);
    try {
      submission.current ??= crypto.randomUUID();
      const metadata = { submission_id: submission.current, estimated_age: age, actual_age: actual, source, consent: true, training_consent: trainingConsent };
      let body: string | FormData = JSON.stringify(metadata);
      if (trainingConsent) {
        if (!preview) throw new Error('The photo is unavailable. Please run a new estimate.');
        const photoResponse = await fetch(preview, { signal: controller.signal });
        if (!photoResponse.ok) throw new Error('The photo is unavailable. Please run a new estimate.');
        body = new FormData();
        body.append('metadata', JSON.stringify(metadata));
        body.append('image', await photoResponse.blob(), 'training-photo');
      }
      const response = await fetch('/api/feedback', {
        method: 'POST', headers: trainingConsent ? undefined : { 'Content-Type': 'application/json' }, signal: controller.signal, body,
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error?.message || 'Feedback could not be saved. Please try again.');
      setStatus('saved'); setMessage(data.training_saved ? 'Thank you. Your feedback and photo were saved for review before future model training.' : 'Thank you. Your feedback has been saved.');
      setToast(data.training_saved ? 'Your feedback and photo have been saved for review.' : 'Your feedback has been saved successfully.');
    } catch (error) {
      setStatus('error');
      setMessage(error instanceof Error && error.name !== 'AbortError' ? error.message : 'The request timed out. Please try again.');
    } finally { clearTimeout(timeout); locked.current = false; }
  }

  return <section className="result-feedback" aria-labelledby="feedback-heading">
    <h3 id="feedback-heading">How close was the estimate?</h3>
    <p>Optional: enter your age in this photo to compare it with the estimate.</p>
    <form onSubmit={submit}>
      <label htmlFor="actual-age">Actual age (years)</label>
      <input id="actual-age" type="number" min="0" max="120" step="1" required value={actualAge} disabled={status === 'saving' || status === 'saved'} onChange={event => setActualAge(event.target.value)} aria-describedby="feedback-comparison" />
      <p id="feedback-comparison" aria-live="polite">{valid ? `The estimate is ${Math.abs(age - actual)} years ${age === actual ? 'away — an exact match' : age > actual ? 'older than your age' : 'younger than your age'}.` : 'Enter a whole-number age from 0 to 120.'}</p>
      <label className="feedback-consent"><input type="checkbox" checked={consent} disabled={status === 'saving' || status === 'saved'} onChange={event => setConsent(event.target.checked)} /><span>I agree to save these two ages and the input method for feedback analysis.</span></label>
      <label className="feedback-consent"><input type="checkbox" checked={trainingConsent} disabled={!preview || status === 'saving' || status === 'saved'} onChange={event => setTrainingConsent(event.target.checked)} /><span>I also agree to save this photo and my stated age to improve the age-estimation model through future training. This is optional.</span></label>
      <p>Your photo is saved only if you select the separate training option. Contributions are reviewed before training; submitting does not immediately change the model.</p>
      <button type="submit" disabled={!valid || !consent || status === 'saving' || status === 'saved'}>{status === 'saved' ? 'Feedback saved' : status === 'saving' ? 'Saving...' : 'Share feedback'}</button>
      <p role={status === 'saved' ? undefined : 'status'} className={status === 'error' ? 'error' : ''}>{message}</p>
    </form>
    <div className="feedback-toast-region" role="status" aria-live="polite" aria-atomic="true">
      {toast && <div className="feedback-toast"><span className="feedback-toast-check" aria-hidden="true">✓</span><div><strong>Feedback saved</strong><p>{toast}</p></div><button type="button" aria-label="Dismiss notification" onClick={() => setToast('')}>×</button></div>}
    </div>
  </section>;
}
