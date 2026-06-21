import React from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {linearTiming, TransitionSeries} from '@remotion/transitions';
import {fade} from '@remotion/transitions/fade';
import {slide} from '@remotion/transitions/slide';
import {COLORS, SLIDE_FRAMES, TRANSITION_FRAMES} from '../theme';
import {ExecSummarySlide, KpiSlide, NotesSlide, TitleSlide} from '../components/slides';
import {KPIS} from '../data/deck';

// The deck "pops" in (scale + fade) as it hands off from the terminal, then the 7 slides
// advance with alternating fade / slide transitions.
export const Deck: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const pop = spring({frame, fps, config: {damping: 14, mass: 0.6}});
  const scale = interpolate(pop, [0, 1], [0.86, 1]);
  const opacity = interpolate(frame, [0, 10], [0, 1], {extrapolateRight: 'clamp'});

  const slides = [
    <TitleSlide key="title" />,
    <ExecSummarySlide key="exec" />,
    ...KPIS.map((k) => <KpiSlide key={k.id} kpi={k} />),
    <NotesSlide key="notes" />,
  ];

  return (
    <AbsoluteFill style={{background: COLORS.navy, justifyContent: 'center', alignItems: 'center'}}>
      <div
        style={{
          width: 1760,
          height: 990,
          transform: `scale(${scale})`,
          opacity,
          borderRadius: 14,
          overflow: 'hidden',
          boxShadow: '0 40px 120px rgba(0,0,0,0.5)',
        }}
      >
        <TransitionSeries>
          {slides.map((node, i) => (
            <React.Fragment key={i}>
              <TransitionSeries.Sequence durationInFrames={SLIDE_FRAMES}>
                {node}
              </TransitionSeries.Sequence>
              {i < slides.length - 1 ? (
                <TransitionSeries.Transition
                  presentation={i % 2 === 0 ? fade() : slide({direction: 'from-right'})}
                  timing={linearTiming({durationInFrames: TRANSITION_FRAMES})}
                />
              ) : null}
            </React.Fragment>
          ))}
        </TransitionSeries>
      </div>
    </AbsoluteFill>
  );
};
