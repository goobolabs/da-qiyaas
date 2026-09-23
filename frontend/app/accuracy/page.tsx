import Link from 'next/link';
import ThemeToggle from '../theme-toggle';
import Dashboard from './dashboard';

export const metadata = { title: 'Accuracy dashboard | Da’qiyaas' };

export default function AccuracyPage() {
  return <main className="accuracy-page">
    <header><Link href="/" className="product-name">Da’qiyaas<span>Model evaluation</span></Link><nav aria-label="Main navigation"><ThemeToggle /><Link className="nav-cta" href="/">Try the model</Link></nav></header>
    <section className="intro"><div><div className="eyebrow">MEASURED PERFORMANCE</div><h1>Accuracy,<br /><span>with context.</span></h1></div><div className="intro-copy"><p>Explore how far age estimates were from known ages on this project’s UTKFace evaluation splits.</p></div></section>
    <Dashboard />
  </main>;
}
