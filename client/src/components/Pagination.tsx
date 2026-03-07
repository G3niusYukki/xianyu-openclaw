import React from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

interface PaginationProps {
  current: number;
  total: number;
  pageSize: number;
  onChange: (page: number) => void;
}

export default function Pagination({ current, total, pageSize, onChange }: PaginationProps) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  if (totalPages <= 1) return null;

  const pages: (number | '...')[] = [];
  if (totalPages <= 7) {
    for (let i = 1; i <= totalPages; i++) pages.push(i);
  } else {
    pages.push(1);
    if (current > 3) pages.push('...');
    const start = Math.max(2, current - 1);
    const end = Math.min(totalPages - 1, current + 1);
    for (let i = start; i <= end; i++) pages.push(i);
    if (current < totalPages - 2) pages.push('...');
    pages.push(totalPages);
  }

  return (
    <div className="flex items-center justify-between px-4 py-3">
      <p className="text-sm text-xy-text-secondary">
        共 <span className="font-medium text-xy-text-primary">{total}</span> 条
      </p>
      <div className="flex items-center gap-1">
        <button
          onClick={() => onChange(Math.max(1, current - 1))}
          disabled={current <= 1}
          aria-label="上一页"
          className="p-1.5 rounded-lg border border-xy-border text-xy-text-secondary hover:bg-xy-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>
        {pages.map((p, i) =>
          p === '...' ? (
            <span key={`e${i}`} className="px-2 text-xy-text-muted text-sm">...</span>
          ) : (
            <button
              key={p}
              onClick={() => onChange(p as number)}
              aria-label={`第 ${p} 页`}
              aria-current={p === current ? 'page' : undefined}
              className={`min-w-[32px] h-8 text-sm font-medium rounded-lg transition-colors ${
                p === current
                  ? 'bg-xy-brand-500 text-white'
                  : 'text-xy-text-secondary hover:bg-xy-gray-50 border border-xy-border'
              }`}
            >
              {p}
            </button>
          )
        )}
        <button
          onClick={() => onChange(Math.min(totalPages, current + 1))}
          disabled={current >= totalPages}
          aria-label="下一页"
          className="p-1.5 rounded-lg border border-xy-border text-xy-text-secondary hover:bg-xy-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
