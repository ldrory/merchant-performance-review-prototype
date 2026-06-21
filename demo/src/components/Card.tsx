import React from 'react';
import {COLORS, FONT} from '../theme';

// Rounded metric card — grey label, large accent value, optional sub line.
// Mirrors _card() in src/presentation/deck_generator.py.
export const Card: React.FC<{
  label: string;
  value: string;
  sub?: string;
  accent?: string;
  arrow?: 'up' | 'down' | null;
  height?: number;
}> = ({label, value, sub, accent = COLORS.navy, arrow = null, height = 150}) => {
  return (
    <div
      style={{
        flex: 1,
        height,
        background: COLORS.light,
        borderRadius: 16,
        padding: '18px 22px',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        fontFamily: FONT,
      }}
    >
      <div style={{fontSize: 19, fontWeight: 700, color: COLORS.grey, letterSpacing: 0.2}}>
        {label}
      </div>
      <div style={{fontSize: 40, fontWeight: 800, color: accent, lineHeight: 1.1, marginTop: 6}}>
        {value}
      </div>
      {sub ? (
        <div style={{fontSize: 18, color: COLORS.grey, marginTop: 4}}>
          {arrow ? (arrow === 'up' ? '▲ ' : '▼ ') : ''}
          {sub}
        </div>
      ) : null}
    </div>
  );
};
