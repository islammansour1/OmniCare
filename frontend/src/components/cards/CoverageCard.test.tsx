import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { CoverageCard } from './CoverageCard';
import { makeSources } from '../../test/factories';

describe('CoverageCard', () => {
  it('renders the answer and a "Covered" verdict badge', () => {
    render(
      <CoverageCard
        data={{ answer: 'Yes, burst pipes are covered.', verdict: 'covered' }}
        sources={makeSources()}
      />,
    );

    expect(screen.getByText('Yes, burst pipes are covered.')).toBeInTheDocument();
    expect(screen.getByText('Covered')).toBeInTheDocument();
  });

  it('renders citations with section and snippet', () => {
    render(
      <CoverageCard
        data={{ answer: 'Not covered.', verdict: 'excluded' }}
        sources={makeSources()}
      />,
    );

    expect(screen.getByText(/Citations \(1\)/)).toBeInTheDocument();
    expect(
      screen.getByText('Section 1 — Home Water Damage Coverage'),
    ).toBeInTheDocument();
    expect(screen.getByText(/Water damage caused by sudden pipe bursts/)).toBeInTheDocument();
  });

  it.each([
    ['covered', 'Covered'],
    ['excluded', 'Excluded'],
    ['conditional', 'Conditional'],
    ['unsupported', 'Unsupported'],
  ] as const)('maps verdict %s to label %s', (verdict, label) => {
    const { unmount } = render(
      <CoverageCard data={{ answer: 'x', verdict }} sources={[]} />,
    );
    expect(screen.getByText(label)).toBeInTheDocument();
    unmount();
  });
});
