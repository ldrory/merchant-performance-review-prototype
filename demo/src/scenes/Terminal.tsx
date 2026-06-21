import React from 'react';
import {AbsoluteFill, interpolate, useCurrentFrame} from 'remotion';
import {COLORS, MONO} from '../theme';

const COMMAND = 'make decks';
const TYPE_START = 12;
const TYPE_SPEED = 3; // frames per char
const OUTPUT_START = TYPE_START + COMMAND.length * TYPE_SPEED + 12;

type Line = {text: string; color: string; bold?: boolean};
const OUTPUT: Line[] = [
  {text: 'Version: 20260621T235500Z', color: '#8aa0b6'},
  {text: '', color: '#8aa0b6'},
  {text: '  ✓ acme → data/output/decks/acme/acme_20260621T235500Z.pptx', color: COLORS.teal},
  {text: '  ✓ cyberdyne-systems → data/output/decks/cyberdyne-systems/cyberdyne-systems_…pptx', color: COLORS.teal},
  {text: '  ✓ vandelay-industries → data/output/decks/vandelay-industries/vandelay-industries_…pptx', color: COLORS.teal},
  {text: '', color: '#8aa0b6'},
  {text: 'Decks: data/output/decks/<merchant>/<merchant>_<version>.pptx', color: '#cfe3f7'},
];
const LINE_STEP = 9;

const Dot: React.FC<{color: string}> = ({color}) => (
  <div style={{width: 16, height: 16, borderRadius: 8, background: color}} />
);

export const Terminal: React.FC = () => {
  const frame = useCurrentFrame();
  const typed = Math.max(0, Math.min(COMMAND.length, Math.floor((frame - TYPE_START) / TYPE_SPEED)));
  const cursorOn = Math.floor(frame / 15) % 2 === 0;
  const appear = interpolate(frame, [0, 12], [0, 1], {extrapolateRight: 'clamp'});
  const scale = interpolate(frame, [0, 12], [0.96, 1], {extrapolateRight: 'clamp'});

  return (
    <AbsoluteFill style={{background: '#0a1626', justifyContent: 'center', alignItems: 'center'}}>
      <div
        style={{
          width: 1380,
          height: 720,
          background: '#0d1b2e',
          borderRadius: 18,
          boxShadow: '0 40px 120px rgba(0,0,0,0.55)',
          overflow: 'hidden',
          opacity: appear,
          transform: `scale(${scale})`,
          border: '1px solid rgba(255,255,255,0.08)',
        }}
      >
        <div
          style={{
            height: 56,
            background: '#13243b',
            display: 'flex',
            alignItems: 'center',
            padding: '0 22px',
            gap: 12,
          }}
        >
          <Dot color="#ff5f57" />
          <Dot color="#febc2e" />
          <Dot color="#28c840" />
          <div style={{flex: 1, textAlign: 'center', color: '#7e93a8', fontFamily: MONO, fontSize: 20, marginRight: 80}}>
            merchant-performance-review-prototype — zsh
          </div>
        </div>
        <div style={{padding: '34px 40px', fontFamily: MONO, fontSize: 30, lineHeight: 1.5}}>
          <div>
            <span style={{color: COLORS.teal, fontWeight: 700}}>❯ </span>
            <span style={{color: '#eaf2fb'}}>{COMMAND.slice(0, typed)}</span>
            {typed < COMMAND.length || cursorOn ? (
              <span style={{color: '#eaf2fb', opacity: cursorOn ? 1 : 0.15}}>▋</span>
            ) : null}
          </div>
          {OUTPUT.map((ln, i) => {
            const start = OUTPUT_START + i * LINE_STEP;
            const op = interpolate(frame, [start, start + 8], [0, 1], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
            });
            return (
              <div key={i} style={{color: ln.color, opacity: op, minHeight: 22, marginTop: i === 0 ? 18 : 2}}>
                {ln.text || ' '}
              </div>
            );
          })}
        </div>
      </div>
    </AbsoluteFill>
  );
};
