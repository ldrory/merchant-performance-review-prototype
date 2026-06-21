import React from 'react';
import {AbsoluteFill, Composition, Sequence} from 'remotion';
import {loadFont} from '@remotion/google-fonts/Inter';
import {DECK_FRAMES, FPS, TERMINAL_FRAMES, TOTAL_FRAMES} from './theme';
import {Terminal} from './scenes/Terminal';
import {Deck} from './scenes/Deck';

loadFont();

const ProductDemo: React.FC = () => {
  return (
    <AbsoluteFill style={{background: '#0a1626'}}>
      <Sequence durationInFrames={TERMINAL_FRAMES}>
        <Terminal />
      </Sequence>
      <Sequence from={TERMINAL_FRAMES} durationInFrames={DECK_FRAMES}>
        <Deck />
      </Sequence>
    </AbsoluteFill>
  );
};

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="ProductDemo"
      component={ProductDemo}
      durationInFrames={TOTAL_FRAMES}
      fps={FPS}
      width={1920}
      height={1080}
    />
  );
};
