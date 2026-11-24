import type { ReactNode } from "react";
import {
  AlertCircle,
  ArrowUpRight,
  Database,
  FileSearch,
  Search,
  Server,
  Sparkles,
} from "lucide-react";
import { Link } from "react-router-dom";
import { runStates, verification, type System } from "./data";

export function Badge({
  status,
  claim = false,
  label,
}: {
  status: string;
  claim?: boolean;
  label?: string;
}) {
  const tone = ["SUPPORTED", "completed", "ready"].includes(status)
    ? "positive"
    : ["failed", "CONTRADICTED"].includes(status)
      ? "negative"
      : ["partial", "PARTIALLY_SUPPORTED", "UNVERIFIED"].includes(status)
        ? "warning"
        : "neutral";
  return (
    <span className={"badge " + tone}>
      <i />
      {label ??
        (claim ? verification : runStates)[status] ??
        ({ ready: "Đã xử lý", insufficient: "Thiếu bằng chứng" }[status] ||
          status)}
    </span>
  );
}

export function Stat({
  label,
  value,
  detail,
  icon,
}: {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  icon: ReactNode;
}) {
  return (
    <article className="stat">
      <div className="stat-label">
        <span>{label}</span>
        <span className="stat-icon">{icon}</span>
      </div>
      <strong>{value}</strong>
      {detail && <div className="muted stat-detail">{detail}</div>}
    </article>
  );
}

export function Heading({
  title,
  detail,
  action,
}: {
  title: string;
  detail?: string;
  action?: ReactNode;
}) {
  return (
    <header className="page-heading">
      <div>
        <h1>{title}</h1>
        {detail && <p>{detail}</p>}
      </div>
      {action}
    </header>
  );
}

export function Section({
  title,
  detail,
  action,
}: {
  title: string;
  detail?: string;
  action?: ReactNode;
}) {
  return (
    <header className="section-heading">
      <div>
        <h2>{title}</h2>
        {detail && <p>{detail}</p>}
      </div>
      {action}
    </header>
  );
}

export function State({
  error,
  title,
  children,
  retry,
}: {
  error?: boolean;
  title: string;
  children?: ReactNode;
  retry?: () => void;
}) {
  const Icon = error ? AlertCircle : FileSearch;
  return (
    <section
      className={"empty " + (error ? "state-error" : "")}
      role={error ? "alert" : undefined}
    >
      <Icon size={25} />
      <h3>{title}</h3>
      {children && <p>{children}</p>}
      {retry && (
        <button className="button" onClick={retry}>
          Thử lại
        </button>
      )}
    </section>
  );
}

export function Loading() {
  return (
    <div className="loading" role="status" aria-label="Đang tải dữ liệu">
      <span />
      <span />
      <span />
    </div>
  );
}

export function ConnectionList({ state }: { state?: System }) {
  const items = [
    {
      icon: Database,
      name: "MySQL",
      ready: state?.mysql === "ready",
      label: "Đã kết nối",
    },
    {
      icon: Server,
      name: "SEC EDGAR",
      ready: state?.sec_configured,
      label: "Đã cấu hình",
    },
    {
      icon: Search,
      name: "Brave Search",
      ready: state?.brave_configured,
      label: "Đã cấu hình",
    },
    {
      icon: Sparkles,
      name: "Gemini",
      ready: state?.gemini_configured,
      label: "Đã cấu hình",
    },
  ];
  return (
    <div className="connection-list">
      {items.map(({ icon: Icon, name, ready, label }) => (
        <div key={name}>
          <span>
            <Icon size={16} />
            {name}
          </span>
          <span className={state && ready ? "ready-label" : "muted"}>
            {!state ? "Chưa kiểm tra" : ready ? label : "Cần kiểm tra"}
          </span>
        </div>
      ))}
    </div>
  );
}
export const OpenReport = ({
  id,
  label = "Mở báo cáo",
}: {
  id: string;
  label?: string;
}) => (
  <Link className="button subtle" to={"/bao-cao/" + id}>
    {label}
    <ArrowUpRight size={15} />
  </Link>
);
