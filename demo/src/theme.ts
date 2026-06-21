// Brand palette — mirrors src/presentation/theme.py so the demo matches the real deck.
export const COLORS = {
  navy: '#0B2545',
  blue: '#2E6FB7',
  teal: '#1B998B',
  amber: '#E8A33D',
  red: '#D7263D',
  grey: '#6B7280',
  light: '#EEF2F7',
  evidence: '#7C3AED',
  white: '#FFFFFF',
} as const;

export const FONT = 'Inter, Calibri, Helvetica, Arial, sans-serif';
export const MONO = '"SF Mono", "JetBrains Mono", Menlo, Consolas, monospace';

// Timing (frames @ 30fps)
export const FPS = 30;
export const TERMINAL_FRAMES = 165;
export const SLIDE_FRAMES = 72;
export const TRANSITION_FRAMES = 16;
export const N_SLIDES = 7;
export const DECK_FRAMES = N_SLIDES * SLIDE_FRAMES - (N_SLIDES - 1) * TRANSITION_FRAMES;
export const TOTAL_FRAMES = TERMINAL_FRAMES + DECK_FRAMES;
