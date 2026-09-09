export type CaptureQuality = { lighting: 'good' | 'low' | 'harsh'; face_size: 'good' | 'too_small'; sharpness: 'good' | 'blurry' };

export default function CameraQuality({ quality, stable }: { quality: CaptureQuality | null; stable: boolean }) {
  const indicators = [
    { label: 'Lighting', value: !quality ? 'Waiting' : quality.lighting === 'good' ? 'Good' : quality.lighting === 'low' ? 'Add light' : 'Too bright', good: quality?.lighting === 'good' },
    { label: 'Face size', value: !quality ? 'Waiting' : quality.face_size === 'good' ? 'Good' : 'Move closer', good: quality?.face_size === 'good' },
    { label: 'Sharpness', value: !quality ? 'Waiting' : quality.sharpness === 'good' ? 'Clear' : 'Focus needed', good: quality?.sharpness === 'good' },
    { label: 'Position', value: !quality ? 'Waiting' : stable ? 'Steady' : 'Hold still', good: stable },
  ];
  return <div className="quality-indicators" aria-label="Camera capture quality">{indicators.map(item => <div key={item.label} className={`quality-item ${!quality ? 'waiting' : item.good ? 'good' : 'needs-work'}`}><span>{item.label}</span><strong><i />{item.value}</strong></div>)}</div>;
}
