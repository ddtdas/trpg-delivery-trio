import { create } from 'zustand';

export interface NarrItem {
  id: string;
  text: string;
  status: 'pending' | 'approved' | 'rejected';
}

export interface NarrState {
  items: NarrItem[];
  pushNarr: (item: NarrItem) => void;
  markNarr: (id: string, status: NarrItem['status']) => void;
  clear: () => void;
}

/** narr slice：叙事流（propose→approve 待批队列的本地投影） */
export const useNarrStore = create<NarrState>()((set) => ({
  items: [],
  pushNarr: (item) => set((s) => ({ items: [...s.items, item] })),
  markNarr: (id, status) =>
    set((s) => ({ items: s.items.map((it) => (it.id === id ? { ...it, status } : it)) })),
  clear: () => set({ items: [] }),
}));
