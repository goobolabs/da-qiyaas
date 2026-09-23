'use client';

import { useState } from 'react';
import FeedbackSummary from './feedback-summary';
import report from '../../../docs/model-detector-comparison.json';

const number = (value: number) => value.toLocaleString('en-US');
// Keep one scale across both splits so switching cannot exaggerate differences.
const scale = Math.ceil(Math.max(...[report.test, report.validation].flatMap(split =>
  Object.values(split.full_coverage_crop_mae.yunet.age_bands).map(band => band.mae))));

export default function Dashboard() {
  const [split, setSplit] = useState<'test' | 'validation'>('test');
  const data = report[split];
  const metrics = data.full_coverage_crop_mae.yunet;
  const total = data.single_face_coverage.images;
  const bands = Object.entries(metrics.age_bands);
  return <section aria-label="Accuracy dashboard" className="accuracy-dashboard">
    <div className="accuracy-toolbar"><div><h2>Recorded evaluation</h2><p>YuNet face crops · Recorded {report.recorded.slice(0, 10)} (UTC)</p></div>
      <div className="tabs" role="group" aria-label="Evaluation split">{(['test', 'validation'] as const).map(value => <button key={value} className={split === value ? 'active' : ''} aria-pressed={split === value} onClick={() => setSplit(value)}>{value === 'test' ? 'Test' : 'Validation'}</button>)}</div>
    </div>
    <div aria-live="polite" aria-atomic="true" className="accuracy-metrics">
      <article><h3>Mean absolute error</h3><strong>{metrics.mae_years.toFixed(2)} <small>years</small></strong><p>Average distance from the known age. Lower is better.</p></article>
      <article><h3>Evaluated portraits</h3><strong>{number(metrics.count)}</strong><p>Of {number(total)} images in the {split} split.</p></article>
      <article><h3>Single-face coverage</h3><strong>{(metrics.count / total * 100).toFixed(2)}<small>%</small></strong><p>{number(total - metrics.count)} images excluded without exactly one detected face. Coverage measures detection, not age accuracy.</p></article>
    </div>
    <section className="accuracy-panel" aria-labelledby="age-band-heading"><h2 id="age-band-heading">Error by age group</h2><p>Mean absolute error in years · Lower is better · Bar scale: 0–{scale} years</p>
      <table className="accuracy-table"><caption>{split === 'test' ? 'Test' : 'Validation'} split: detected-face crops</caption><thead><tr><th scope="col">Age group</th><th scope="col">Average error (years)</th><th scope="col">Images</th></tr></thead><tbody>{bands.map(([label, band]) => <tr key={label}><th scope="row">{label}</th><td><div className="accuracy-bar-cell"><div className="accuracy-track" aria-hidden="true"><div style={{ width: `${band.mae / scale * 100}%` }} /></div><span>{band.mae.toFixed(2)}</span></div></td><td>{number(band.count)}</td></tr>)}</tbody></table>
      <p>Groups with fewer images have less evidence behind their results. These averages do not describe every individual prediction.</p>
    </section>
    <section className="accuracy-panel"><h2>How to read these results</h2><ul>
      <li>A mean absolute error of {metrics.mae_years.toFixed(2)} years means estimates differed from known ages by that amount on average. It is not a confidence interval or an accuracy percentage.</li>
      <li>Validation was used to choose the detector and crop settings; the test split was evaluated afterwards. This test split has been reused and is not an external holdout.</li>
      <li>UTKFace contains tightly cropped portraits. Physical-webcam accuracy has not been measured.</li>
      <li>This is a saved evaluation snapshot, not a live measurement of your uploads or a check of the currently loaded model.</li>
    </ul><details><summary>Evaluation source</summary><p>Model: {report.model_evaluated}. Detector: {report.detector.current}. Crop margin: {report.detector.crop_margin}.</p><p>Source: docs/model-detector-comparison.json. Refresh this report and rebuild the frontend after a new evaluation.</p></details></section>
    <FeedbackSummary />
  </section>;
}
