import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ClaimStatusCard } from './ClaimStatusCard';
import { makeClaim } from '../../test/factories';

describe('ClaimStatusCard', () => {
  it('renders claim fields and a formatted currency amount', () => {
    render(<ClaimStatusCard claim={makeClaim()} />);

    expect(screen.getByText('CLM-8821')).toBeInTheDocument();
    expect(screen.getByText('POL-1092')).toBeInTheDocument();
    expect(screen.getByText('Water Damage')).toBeInTheDocument();
    expect(screen.getByText('$3,500.00')).toBeInTheDocument();
    expect(screen.getByText('Approved')).toBeInTheDocument();
  });

});
