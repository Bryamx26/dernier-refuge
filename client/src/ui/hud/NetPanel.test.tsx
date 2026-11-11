import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { NetPanel } from './NetPanel';

describe('NetPanel', () => {
  it('affiche ping, tick et zone quand la liaison est ouverte', () => {
    render(
      <NetPanel
        view={{
          state: 'open',
          zoneId: 'valcendre',
          zoneName: 'Valcendre',
          rttMs: 41.6,
          serverTick: 1234,
          tickRate: 20,
          closeCode: null,
          closeLabel: '',
        }}
      />,
    );
    expect(screen.getByTestId('net-state')).toHaveTextContent('En ligne');
    expect(screen.getByText('42 ms')).toBeInTheDocument();
    expect(screen.getByText('1234')).toBeInTheDocument();
    expect(screen.getByText('Valcendre')).toBeInTheDocument();
  });

  it('affiche la cause de fermeture', () => {
    render(
      <NetPanel
        view={{
          state: 'closed',
          zoneId: 'valcendre',
          zoneName: null,
          rttMs: null,
          serverTick: null,
          tickRate: null,
          closeCode: 4003,
          closeLabel: 'Zone pleine.',
        }}
      />,
    );
    expect(screen.getByTestId('net-state')).toHaveTextContent('Hors ligne');
    expect(screen.getByText('Zone pleine.')).toBeInTheDocument();
  });
});
