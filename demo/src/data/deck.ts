// ACME deck content — extracted verbatim from deliverables/acme_performance_review.pptx.
import {COLORS} from '../theme';

export const META = {
  merchant: 'ACME',
  subtitle: 'Merchant Performance Review',
  profile: 'Post authorization   ·   Strategic   ·   2025-07 – 2026-06',
  prepared: 'Prepared by Riskified Customer Success',
};

export type ExecCard = {label: string; value: string; delta: string; up: boolean; accent: string};
export const EXEC_CARDS: ExecCard[] = [
  {label: 'Submission Volume', value: '4,876', delta: '+6.4% since start', up: true, accent: COLORS.navy},
  {label: 'Approval Rate', value: '98.15%', delta: '+1.3% since start', up: true, accent: COLORS.teal},
  {label: 'Accepted Chargeback Rate', value: '0.12%', delta: '-8.9% since start', up: false, accent: COLORS.teal},
  {label: 'Effective Fraud Rate', value: '1.80%', delta: '-4.9% since start', up: false, accent: COLORS.teal},
];

export const EXEC_BULLETS = [
  'Submission volume grew +6.4% by count and +6.0% by value over the review period, with a seasonal peak in December 2025.',
  'Approval rate improved +1.3% (count) and +1.4% (value), reaching near-period-high levels of 98.15% and 97.33% respectively by June 2026.',
  'Accepted chargeback rate declined meaningfully — down 8.9% by count and 18.8% by value — reflecting a healthier approved-order mix.',
  'Effective fraud rate trended in the right direction, falling 4.9% by count and 5.0% by value despite a noted high-fraud episode in January 2026.',
  "Overall, ACME's key risk and approval metrics moved favorably across the period, ending June 2026 at or near their best levels.",
];

export type Card = {label: string; value: string; sub: string; accent: string};
export type Kpi = {
  id: string;
  name: string;
  direction: string;
  cards: Card[];
  analysis: string;
  monthly: string;
  quarterly: string;
};

export const KPIS: Kpi[] = [
  {
    id: 'submission_volume',
    name: 'Submission Volume',
    direction: 'transaction volume',
    cards: [
      {label: 'Latest', value: '4,876', sub: '2026-06', accent: COLORS.navy},
      {label: 'Change since start', value: '+6.4%', sub: 'vs first month', accent: COLORS.navy},
      {label: 'Latest quarter', value: '12,846', sub: '2026-Q2', accent: COLORS.navy},
      {label: 'Submitted value', value: '$4,304,316', sub: '2026-06', accent: COLORS.blue},
    ],
    analysis:
      'Submission volume grew from 4,584 transactions ($4,061,436) in July 2025 to 4,876 transactions ($4,304,316) in June 2026, representing increases of +6.4% and +6.0% respectively. The count-based peak of 5,378 in December 2025 coincides with the noted Peak Season event, while the trough of 3,438 in February 2026 coincides with the Low Volume event flagged for that month.',
    monthly: 'charts/submission_volume_monthly.png',
    quarterly: 'charts/submission_volume_quarterly.png',
  },
  {
    id: 'approval_rate',
    name: 'Approval Rate',
    direction: 'higher is better',
    cards: [
      {label: 'Latest', value: '98.15%', sub: '2026-06', accent: COLORS.teal},
      {label: 'Change since start', value: '+1.3%', sub: 'vs first month', accent: COLORS.teal},
      {label: 'Latest quarter', value: '98.37%', sub: '2026-Q2', accent: COLORS.navy},
      {label: 'Amount-weighted latest', value: '97.33%', sub: '2026-06', accent: COLORS.blue},
    ],
    analysis:
      'Approval rate improved steadily over the review period, rising from 96.84% to 98.15% on a count basis (+1.3%) and from 96.00% to 97.33% on a value-weighted basis (+1.4%). The period low of 96.54% in January 2026 coincides with the High Fraud event. By April 2026, the count-based rate reached its period high of 98.66%, and June levels remain close to that peak.',
    monthly: 'charts/approval_rate_monthly.png',
    quarterly: 'charts/approval_rate_quarterly.png',
  },
  {
    id: 'accepted_chargeback_rate',
    name: 'Accepted Chargeback Rate',
    direction: 'lower is better',
    cards: [
      {label: 'Latest', value: '0.12%', sub: '2026-06', accent: COLORS.teal},
      {label: 'Change since start', value: '-8.9%', sub: 'vs first month', accent: COLORS.teal},
      {label: 'Latest quarter', value: '0.11%', sub: '2026-Q2', accent: COLORS.navy},
      {label: 'Amount-weighted latest', value: '0.08%', sub: '2026-06', accent: COLORS.blue},
    ],
    analysis:
      'The accepted chargeback rate declined from 0.13% to 0.12% by count (−8.9%) and from 0.10% to 0.08% by value (−18.8%), with the value-weighted improvement being particularly notable. The February 2026 period best of 0.09% (count-based) coincides with the Low Volume event. The overall downward direction across both views is a favorable outcome.',
    monthly: 'charts/accepted_chargeback_rate_monthly.png',
    quarterly: 'charts/accepted_chargeback_rate_quarterly.png',
  },
  {
    id: 'effective_fraud_rate',
    name: 'Effective Fraud Rate',
    direction: 'lower is better',
    cards: [
      {label: 'Latest', value: '1.80%', sub: '2026-06', accent: COLORS.teal},
      {label: 'Change since start', value: '-4.9%', sub: 'vs first month', accent: COLORS.teal},
      {label: 'Latest quarter', value: '2.23%', sub: '2026-Q2', accent: COLORS.navy},
      {label: 'Amount-weighted latest', value: '3.15%', sub: '2026-06', accent: COLORS.blue},
    ],
    analysis:
      'The effective fraud rate improved from 1.90% to 1.80% by count (−4.9%) and from 3.31% to 3.15% by value (−5.0%) over the review period. The count-based period high of 2.89% in January 2026 coincides with the High Fraud event. Despite that spike, the rate recovered and the period closed at its count-based low of 1.80%, suggesting the portfolio returned to a more favorable fraud profile by June 2026.',
    monthly: 'charts/effective_fraud_rate_monthly.png',
    quarterly: 'charts/effective_fraud_rate_quarterly.png',
  },
];

export const NOTES = [
  'Count-based view: KPIs by transaction volume (number of orders).',
  'Amount-weighted view: KPIs weighted by submitted order value (Submission Volume is shown in dollars).',
  'Charts annotate notable evidence events from the period.',
];
