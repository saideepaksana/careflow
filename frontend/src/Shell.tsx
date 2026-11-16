import { ReactNode } from "react";

/** The product mark: a white cross on a green tile. */
export function BrandMark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="8" fill="#0f766e" />
      <path d="M13 7h6v6h6v6h-6v6h-6v-6H7v-6h6z" fill="#ffffff" />
    </svg>
  );
}

export function Shell({ sidebar, children }: { sidebar: ReactNode; children: ReactNode }) {
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <BrandMark />
          <div>
            <div className="brand-name">CareFlow</div>
            <div className="brand-sub">Post-discharge care coordination</div>
          </div>
        </div>
        {sidebar}
        <div className="sidebar-foot">Synthetic patients only. Not a medical device.</div>
      </aside>
      <main className="main">{children}</main>
    </div>
  );
}

export function Section({ title, aside, children }: { title: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <section className="section">
      <div className="section-title">
        <span>{title}</span>
        {aside}
      </div>
      {children}
    </section>
  );
}

export function Row({ label, value }: { label: ReactNode; value: ReactNode }) {
  return (
    <div className="row">
      <span className="row-label">{label}</span>
      <span className="row-value">{value}</span>
    </div>
  );
}

export function Dot({ tone }: { tone: string }) {
  return <span className={`dot ${tone}`} aria-hidden="true" />;
}
