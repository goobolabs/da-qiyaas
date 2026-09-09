'use client';

import { useEffect, useRef, useState } from 'react';

export default function ResultVoice({ age }: { age: number | null }) {
  const [enabled, setEnabled] = useState(false);
  const [notice, setNotice] = useState('Read the result aloud in Somali.');
  const [playing, setPlaying] = useState(false);
  const stop = useRef<() => void>(() => {});
  const play = useRef<() => void>(() => {});

  useEffect(() => {
    try { setEnabled(localStorage.getItem('da-qiyaas-sound') === 'on'); } catch { /* Optional storage. */ }
  }, []);

  useEffect(() => {
    let current = true;
    let audio: HTMLAudioElement | null = null;
    let url: string | null = null;
    let utterance: SpeechSynthesisUtterance | null = null;
    let sequence = 0;
    let controller: AbortController | null = null;
    let voiceTimeout: ReturnType<typeof setTimeout> | null = null;
    const synth = typeof window.speechSynthesis === 'undefined' ? null : window.speechSynthesis;
    synth?.getVoices(); // Start asynchronous voice discovery before a result arrives.
    const cleanup = () => {
      sequence++;
      if (voiceTimeout) clearTimeout(voiceTimeout);
      controller?.abort();
      if (audio) { audio.pause(); audio.removeAttribute('src'); audio.load(); audio = null; }
      if (url) { URL.revokeObjectURL(url); url = null; }
      if (utterance) { synth?.cancel(); utterance = null; }
    };
    stop.current = () => { cleanup(); setPlaying(false); };
    const speak = async () => {
      cleanup();
      if (!enabled || age === null) return;
      const token = sequence;
      const active = () => current && token === sequence;
      const failed = () => { if (active()) { setPlaying(false); setNotice('Audio could not play. Select Listen again to retry.'); } };
      setPlaying(true);
      setNotice('Preparing Somali audio…');
      // Voice availability varies by device; never read Somali with an English voice.
      const voice = synth?.getVoices().find(item => /^so(?:-|$)/i.test(item.lang));
      if (voice && synth) {
        utterance = new SpeechSynthesisUtterance(`Da’daada waxaa lagu qiyaasay ${age} sano.`);
        utterance.voice = voice; utterance.lang = voice.lang;
        voiceTimeout = setTimeout(() => { if (active()) { cleanup(); setPlaying(false); setNotice('Select Listen again to allow audio playback.'); } }, 15000);
        utterance.onstart = () => { if (active()) setNotice('Reading your estimate in Somali.'); };
        utterance.onend = () => { if (voiceTimeout) clearTimeout(voiceTimeout); if (active()) { setPlaying(false); setNotice('Select Listen again to replay.'); } };
        utterance.onerror = failed;
        try { synth.speak(utterance); } catch { failed(); }
        return;
      }
      const pending = new AbortController();
      controller = pending;
      const timeout = setTimeout(() => pending.abort(), 15000);
      try {
        const response = await fetch('/api/speech', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ age }), signal: pending.signal });
        if (!active()) return;
        if (response.status === 503 || response.status === 404) {
          setPlaying(false); setNotice('Somali audio is unavailable on this device. Your estimate is still shown above.'); return;
        }
        if (!response.ok) throw new Error('Speech unavailable');
        const blob = await response.blob();
        if (!active()) return;
        url = URL.createObjectURL(blob);
        audio = new Audio(url);
        audio.onended = () => { if (active()) { setPlaying(false); setNotice('Select Listen again to replay.'); } };
        audio.onerror = failed;
        await audio.play();
        if (active()) setNotice('Reading your estimate in Somali.');
      } catch { failed(); }
      finally { clearTimeout(timeout); }
    };
    play.current = () => { void speak(); };
    setPlaying(false);
    setNotice(enabled ? 'The completed estimate will be read in Somali.' : 'Read the result aloud in Somali.');
    if (enabled && age !== null) void speak();
    return () => { current = false; cleanup(); };
  }, [age, enabled]);

  function toggle() {
    stop.current();
    const next = !enabled;
    setEnabled(next);
    try { localStorage.setItem('da-qiyaas-sound', next ? 'on' : 'off'); } catch { /* Optional storage. */ }
  }

  return <div className="result-voice">
    <div className="voice-actions">
      <button type="button" aria-pressed={enabled} onClick={toggle}>Sound {enabled ? 'on' : 'off'}</button>
      {enabled && age !== null && <button type="button" onClick={() => playing ? stop.current() : play.current()}>{playing ? 'Stop audio' : 'Listen again'}</button>}
    </div>
    {age !== null && <p lang="so">Da’daada waxaa lagu qiyaasay {age} sano.</p>}
    <p className="voice-notice" aria-live="polite">{notice}</p>
  </div>;
}
