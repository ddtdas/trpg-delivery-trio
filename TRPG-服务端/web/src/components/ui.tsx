import React from 'react';

/** 通用错误横幅：可关闭、danger 语义（灰白黑：红仅用于错误语义）。 */
export function ErrorBanner({ message, onClose }: { message: string; onClose?: () => void }): React.ReactElement {
  return (
    <div role="alert" className="flex items-start justify-between gap-3 rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800">
      <span>{message}</span>
      {onClose ? (
        <button className="rounded px-2 py-0.5 text-xs hover:bg-red-100" onClick={onClose} aria-label="关闭错误提示">
          关闭
        </button>
      ) : null}
    </div>
  );
}

/** 通用空状态。 */
export function EmptyState({ text }: { text: string }): React.ReactElement {
  return <div className="empty">{text}</div>;
}

/** 通用加载态（灰白黑）。 */
export function LoadingRow({ text }: { text: string }): React.ReactElement {
  return (
    <div className="flex items-center gap-2 text-sm text-gray-700" role="status" aria-live="polite" aria-atomic="true">
      <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-gray-400 border-t-black" aria-hidden="true" />
      {text}
    </div>
  );
}

/** 骨架屏块（UI-P2 增强）：animate-pulse 浅灰块。 */
export function SkeletonBlock({ className = '' }: { className?: string }): React.ReactElement {
  return <div className={`animate-pulse rounded-lg bg-gray-200 ${className}`} aria-hidden="true" />;
}

/** 骨架屏列表：标题行（可选）+ n 行占位，模拟内容区加载。 */
export function SkeletonRows({ rows = 3, title = false, label = '内容加载中' }: { rows?: number; title?: boolean; label?: string }): React.ReactElement {
  return (
    <div className="space-y-2" role="status" aria-live="polite" aria-atomic="true" aria-label={label}>
      {title ? <SkeletonBlock className="h-4 w-1/3" /> : null}
      {Array.from({ length: rows }).map((_, i) => (
        <SkeletonBlock key={i} className={i % 2 === 0 ? 'h-12 w-full' : 'h-12 w-5/6'} />
      ))}
    </div>
  );
}

/** 全局 toast 区：瞬态消息唯一落点（灰白黑）。 */
export function ToastZone({ items, onClose }: { items: Array<{ id: string; text: string }>; onClose: (id: string) => void }): React.ReactElement {
  return (
    <div aria-live="polite" aria-atomic="true" aria-label="通知" className="space-y-2">
      {items.map((t) => (
        <div key={t.id} role="status" className="flex items-start justify-between gap-3 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-800 shadow-sm">
          <span>{t.text}</span>
          <button className="min-h-[40px] rounded px-2 py-0.5 text-xs hover:bg-gray-100" onClick={() => onClose(t.id)} aria-label="关闭通知">
            关闭
          </button>
        </div>
      ))}
    </div>
  );
}