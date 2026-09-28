import { create } from 'zustand';

export interface CharacterLite {
  id: string;
  name: string;
  online?: boolean;
}

export interface TableState {
  campaignId: string;
  tableId: string;
  characters: CharacterLite[];
  selectedCharacterId: string | null;
  setCampaign: (campaignId: string, tableId: string) => void;
  setCharacters: (chars: CharacterLite[]) => void;
  selectCharacter: (id: string | null) => void;
}

/** table slice：桌面 / 角色状态 */
export const useTableStore = create<TableState>()((set) => ({
  campaignId: '',
  tableId: '',
  characters: [],
  selectedCharacterId: null,
  setCampaign: (campaignId, tableId) => set({ campaignId, tableId }),
  setCharacters: (characters) => set({ characters }),
  selectCharacter: (selectedCharacterId) => set({ selectedCharacterId }),
}));
