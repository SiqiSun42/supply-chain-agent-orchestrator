import type { ReactNode } from "react";

export function PageHeader({
  title,
  subtitle,
  tabs,
  actions,
}: {
  title: string;
  subtitle?: ReactNode;
  tabs?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div
      className={
        actions
          ? "flex flex-wrap items-end justify-between gap-4 border-b border-slate-200 bg-white px-8 py-6"
          : "border-b border-slate-200 bg-white px-8 py-6"
      }
    >
      <div className={actions ? "min-w-0" : undefined}>
        <h1 className="text-xl font-semibold tracking-tight text-slate-900">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
        {tabs && <div className="mt-3 w-fit max-w-full">{tabs}</div>}
      </div>
      {actions}
    </div>
  );
}
