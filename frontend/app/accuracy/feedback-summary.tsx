'use client';

import { useEffect, useRef, useState } from 'react';

type Metrics = { count: number; mean_absolute_error_years: number | null };
type Summary = Metrics & { by_source: Record<'camera' | 'upload', Metrics>; self_reported: true };
const formatError = (value: number | null) => value === null ? 'No data' : `${value.toFixed(2)} years`;

export default function FeedbackSummary() {
  const [data, setData] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const generation = useRef(0);
  useEffect(() => {
    const token = ++generation.current;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    setLoading(true); setError(''); setData(null);
    async function load() {
      try {
        const response = await fetch('/api/feedback/summary', { cache: 'no-store', signal: controller.signal });
        if (!response.ok) throw new Error('Feedback summary is unavailable. Please try again.');
        const result: Summary = await response.json();
        if (token === generation.current) setData(result);
      } catch {
        if (token === generation.current) setError('Feedback summary is unavailable. Please try again.');
      } finally {
        clearTimeout(timeout);
        if (token === generation.current) setLoading(false);
      }
    }
    void load();
    return () => { generation.current++; clearTimeout(timeout); controller.abort(); };
  }, [revision]);

  return <section id="feedback" className="accuracy-panel feedback-summary" aria-labelledby="feedback-summary-heading">
    <div className="accuracy-toolbar"><div><div className="eyebrow">SELF-REPORTED FEEDBACK</div><h2 id="feedback-summary-heading">What users shared</h2></div><button className="feedback-refresh" disabled={loading} onClick={() => setRevision(value => value + 1)}>Refresh feedback</button></div>
    <p>These ages and estimates were submitted by users and have not been verified. Submissions can include repeat users and different model versions; they do not measure test-set or webcam accuracy.</p>
    <div role="status">{loading ? <p>Loading feedback...</p> : error ? <p className="error">{error}</p> : data?.count === 0 ? <p>No feedback yet. After an estimate, share your actual age to contribute.</p> : null}</div>
    {data && <>
      <div className="accuracy-metrics feedback-metrics"><article><h3>Feedback submissions</h3><strong>{data.count.toLocaleString('en-US')}</strong><p>All saved submissions, across camera and uploads.</p></article><article><h3>Average reported difference</h3><strong>{data.mean_absolute_error_years === null ? '—' : data.mean_absolute_error_years.toFixed(2)} <small>years</small></strong><p>Average absolute difference between the displayed estimate and the age users entered.</p></article></div>
      <table className="accuracy-table"><caption>Feedback by input method</caption><thead><tr><th scope="col">Input method</th><th scope="col">Average difference</th><th scope="col">Submissions</th></tr></thead><tbody>{(['camera', 'upload'] as const).map(source => <tr key={source}><th scope="row">{source === 'camera' ? 'Camera' : 'Upload'}</th><td>{formatError(data.by_source[source].mean_absolute_error_years)}</td><td>{data.by_source[source].count.toLocaleString('en-US')}</td></tr>)}</tbody></table>
      <p>Updated when this page opens or you select Refresh feedback. Empty groups show “No data”.</p>
    </>}
  </section>;
}
