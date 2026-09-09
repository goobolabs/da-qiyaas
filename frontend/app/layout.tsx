import type { Metadata } from 'next';
import './brand-fonts.css';
import './globals.css';
export const metadata: Metadata = { title: 'Da’qiyaas | Goobo Labs', description: 'Explore age estimation with a live face scan or uploaded portrait.', icons: { icon: '/brand/goobo-logo.svg' } };
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en" suppressHydrationWarning><head><script dangerouslySetInnerHTML={{ __html: "try{var t=localStorage.getItem('da-qiyaas-theme')||localStorage.getItem('agelens-theme');document.documentElement.dataset.theme=t==='dark'||(!t&&matchMedia('(prefers-color-scheme: dark)').matches)?'dark':'light'}catch(e){document.documentElement.dataset.theme='light'}" }} /></head><body>{children}</body></html>;
}
