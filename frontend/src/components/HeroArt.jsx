import React from 'react';

// Decorative inventory/evidence motif, never a chart of invented business data.
export default function HeroArt() {
  return <svg className="hero-art" viewBox="0 0 360 220" fill="none" aria-hidden="true">
    <circle cx="235" cy="108" r="94" fill="var(--hero-orbit)" />
    <circle cx="235" cy="108" r="72" stroke="var(--hero-line)" strokeDasharray="3 9" />
    <path d="M30 184h300 M57 172V80l80-40 80 40v92" stroke="var(--hero-line)" strokeWidth="2" />
    <path d="M57 80l80 43 80-43 M137 123v49" stroke="var(--hero-line)" strokeWidth="2" />
    <rect x="75" y="136" width="44" height="36" rx="4" fill="var(--accent)" /><path d="M97 136v12" stroke="var(--hero-ink)" strokeWidth="3" />
    <rect x="142" y="122" width="57" height="50" rx="4" fill="var(--gold)" /><path d="M170 122v15" stroke="var(--hero-ink)" strokeWidth="3" />
    <rect x="231" y="42" width="85" height="61" rx="12" fill="var(--hero-card)" stroke="var(--hero-line)" />
    <path d="M247 71l12 12 25-25 M291 62h10 M291 73h10 M247 93h54" stroke="var(--gold)" strokeWidth="2" />
    <circle cx="254" cy="157" r="21" fill="var(--secondary)" /><path d="M246 158l6 6 11-12" stroke="var(--hero-ink)" strokeWidth="2" />
  </svg>;
}
