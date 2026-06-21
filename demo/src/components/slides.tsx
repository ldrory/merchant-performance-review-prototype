import React from 'react';
import {AbsoluteFill, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {COLORS, FONT} from '../theme';
import {Card} from './Card';
import {SlideFrame} from './SlideFrame';
import {EXEC_BULLETS, EXEC_CARDS, Kpi, META, NOTES} from '../data/deck';

// Small helper: a value that eases in over the first ~18 frames of a slide.
const useEnter = (delay = 0) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  return spring({frame: frame - delay, fps, config: {damping: 200}});
};

export const TitleSlide: React.FC = () => {
  const e = useEnter();
  const y = interpolate(e, [0, 1], [30, 0]);
  return (
    <SlideFrame showLogo={false}>
      <Img src={staticFile('logo.png')} style={{position: 'absolute', top: 70, left: 72, height: 74}} />
      <div style={{position: 'absolute', top: 320, left: 80, opacity: e, transform: `translateY(${y}px)`}}>
        <div style={{fontSize: 96, fontWeight: 800, color: COLORS.navy}}>{META.merchant}</div>
        <div style={{fontSize: 44, color: COLORS.blue, marginTop: 10}}>{META.subtitle}</div>
        <div style={{width: 280, height: 6, background: COLORS.teal, margin: '26px 0 18px'}} />
        <div style={{fontSize: 26, color: COLORS.grey}}>{META.profile}</div>
      </div>
      <div
        style={{
          position: 'absolute',
          bottom: 0,
          left: 0,
          right: 0,
          height: 70,
          background: COLORS.navy,
          display: 'flex',
          alignItems: 'center',
          paddingLeft: 80,
        }}
      >
        <span style={{color: COLORS.white, fontSize: 22, fontFamily: FONT}}>{META.prepared}</span>
      </div>
    </SlideFrame>
  );
};

export const ExecSummarySlide: React.FC = () => {
  return (
    <SlideFrame title="Executive Summary">
      <div style={{position: 'absolute', top: 170, left: 64, right: 64, display: 'flex', gap: 24}}>
        {EXEC_CARDS.map((c, i) => {
          const e = useEnter(i * 4);
          return (
            <div key={c.label} style={{flex: 1, opacity: e, transform: `translateY(${interpolate(e, [0, 1], [24, 0])}px)`}}>
              <Card label={c.label} value={c.value} sub={c.delta} accent={c.accent} arrow={c.up ? 'up' : 'down'} height={160} />
            </div>
          );
        })}
      </div>
      <div style={{position: 'absolute', top: 380, left: 80, right: 80}}>
        {EXEC_BULLETS.map((b, i) => {
          const e = useEnter(16 + i * 5);
          return (
            <div
              key={i}
              style={{
                fontSize: 26,
                color: COLORS.navy,
                marginBottom: 18,
                lineHeight: 1.35,
                opacity: e,
                transform: `translateX(${interpolate(e, [0, 1], [20, 0])}px)`,
              }}
            >
              <span style={{color: COLORS.teal, fontWeight: 800}}>•</span> {b}
            </div>
          );
        })}
      </div>
    </SlideFrame>
  );
};

export const KpiSlide: React.FC<{kpi: Kpi}> = ({kpi}) => {
  return (
    <SlideFrame title={kpi.name} subtitle={kpi.direction}>
      <div style={{position: 'absolute', top: 165, left: 64, right: 64, display: 'flex', gap: 22}}>
        {kpi.cards.map((c, i) => {
          const e = useEnter(i * 3);
          return (
            <div key={c.label} style={{flex: 1, opacity: e}}>
              <Card label={c.label} value={c.value} sub={c.sub} accent={c.accent} height={140} />
            </div>
          );
        })}
      </div>
      <div style={{position: 'absolute', top: 340, left: 56, right: 56, display: 'flex', gap: 24}}>
        <Img src={staticFile(kpi.monthly)} style={{flex: 1, width: '50%', objectFit: 'contain'}} />
        <Img src={staticFile(kpi.quarterly)} style={{flex: 1, width: '50%', objectFit: 'contain'}} />
      </div>
      <div
        style={{
          position: 'absolute',
          bottom: 40,
          left: 72,
          right: 72,
          fontSize: 20,
          color: COLORS.grey,
          lineHeight: 1.4,
        }}
      >
        {kpi.analysis}
      </div>
    </SlideFrame>
  );
};

export const NotesSlide: React.FC = () => {
  return (
    <SlideFrame title="Notes & Methodology">
      <div style={{position: 'absolute', top: 230, left: 80, right: 80}}>
        {NOTES.map((b, i) => {
          const e = useEnter(i * 6);
          return (
            <div key={i} style={{fontSize: 30, color: COLORS.navy, marginBottom: 28, opacity: e}}>
              <span style={{color: COLORS.teal, fontWeight: 800}}>•</span> {b}
            </div>
          );
        })}
      </div>
    </SlideFrame>
  );
};
