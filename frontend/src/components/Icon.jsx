import React from 'react';

const paths = {
  overview: 'M3 3h6v6H3z M13 3h6v6h-6z M3 13h6v6H3z M13 13h6v6h-6z',
  data: 'M4 5h14v14H4z M7 2h8 M7 9h8 M7 13h8',
  insights: 'M3 19h16 M6 15V9 M11 15V4 M16 15v-6',
  ask: 'M3 4h16v11H9l-5 4v-4H3z M7 8h8 M7 11h5',
  decisions: 'M5 3h12v17H5z M8 8l2 2 4-4 M8 14h6 M8 17h4',
  simulator: 'M3 6h16 M3 16h16 M8 3v6 M14 13v6',
};
export default function Icon({ name, className = '' }) {
  return <svg className={`icon ${className}`} viewBox="0 0 22 22" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name] || paths.overview} /></svg>;
}
