import { create } from 'zustand';
import type { TurnState } from '../lib/ws';

export interface TurnSubmit {
  player_id: string;
  intent?: string;
}

export interface TurnWindowState {
  state: TurnState | 'IDLE';
  submitted: TurnSubmit[];
  total: number;
  countdownEndTs: number;
  setTurn: (t: Partial<Omit<TurnWindowState, 'setTurn' | 'reset'>>) => void;
  reset: () => void;
}

/** turn slice：回合 / 窗口状态 */
export const useTurnStore = create<TurnWindowState>()((set) => ({
  state: 'IDLE',
  submitted: [],
  total: 0,
  countdownEndTs: 0,
  setTurn: (t) => set(t),
  reset: () => set({ state: 'IDLE', submitted: [], total: 0, countdownEndTs: 0 }),
}));
