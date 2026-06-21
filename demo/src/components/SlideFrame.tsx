import React from 'react';
import {AbsoluteFill, Img, staticFile} from 'remotion';
import {COLORS, FONT} from '../theme';

// A 16:9 white deck slide: title (top-left), optional subtitle, and the logo top-right.
// Mirrors the slide chrome produced by src/presentation/deck_generator.py.
export const SlideFrame: React.FC<{
  title?: string;
  subtitle?: string;
  showLogo?: boolean;
  children: React.ReactNode;
}> = ({title, subtitle, showLogo = true, children}) => {
  return (
    <AbsoluteFill style={{background: COLORS.white, fontFamily: FONT}}>
      {showLogo ? (
        <Img
          src={staticFile('logo.png')}
          style={{position: 'absolute', top: 44, right: 56, height: 46}}
        />
      ) : null}
      {title ? (
        <div style={{position: 'absolute', top: 48, left: 64}}>
          <div style={{fontSize: 50, fontWeight: 800, color: COLORS.navy}}>{title}</div>
          {subtitle ? (
            <div style={{fontSize: 22, color: COLORS.grey, marginTop: 6}}>{subtitle}</div>
          ) : null}
        </div>
      ) : null}
      {children}
    </AbsoluteFill>
  );
};
