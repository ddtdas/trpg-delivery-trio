import React from 'react';

interface ShellProps {
  title: string;
  note?: string;
}

// UI-R2: 灰白黑令牌适配（仅视觉）
export function Shell({ title, note }: ShellProps): React.ReactElement {
  return (
    <div className="rounded border border-gray-300 bg-white p-4 shadow-sm">
      <h2 className="text-lg font-semibold text-gray-900">{title}</h2>
      <p className="mt-1 text-sm text-gray-500">{note ?? 'M0 占位壳 —— 视觉后续任务完善。'}</p>
    </div>
  );
}
