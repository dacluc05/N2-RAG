import { useMemo, useState } from "react";
import { displayDate, roles, verification, type Report } from "./data";
import { ClaimCard } from "./Finding";
import type { Selection } from "./Evidence";
import { Section, State } from "./ui";

export function Explorer({
  report,
  open,
}: {
  report: Report;
  open: (selection: Selection) => void;
}) {
  const [query, setQuery] = useState(""),
    [status, setStatus] = useState(""),
    [role, setRole] = useState(""),
    [kind, setKind] = useState(""),
    [period, setPeriod] = useState(""),
    [from, setFrom] = useState(""),
    [view, setView] = useState("claims"),
    [order, setOrder] = useState("newest"),
    [page, setPage] = useState(0);
  const byId = useMemo(
    () => new Map(report.evidence.map((source) => [source.id, source])),
    [report.evidence],
  );
  const kinds = [
    ...new Set(report.evidence.map((source) => source.kind)),
  ].sort();
  const periods = [
    ...new Set(
      report.evidence.flatMap((source) =>
        source.report_end ? [source.report_end] : [],
      ),
    ),
  ]
    .sort()
    .reverse();
  const term = query.trim().toLowerCase();
  const filteredSources = report.evidence.filter(
    (source) =>
      (!kind || source.kind === kind) &&
      (!period || source.report_end === period) &&
      (!from || (!!source.published && source.published >= from)),
  );
  const ids = new Set(filteredSources.map((source) => source.id));
  const claims = report.claims.filter(
    (claim) =>
      (!status || claim.status === status) &&
      (!role || claim.role === role) &&
      (!(kind || period || from) ||
        [...claim.evidence_ids, ...claim.counter_ids].some((id) =>
          ids.has(id),
        )) &&
      (!term ||
        [
          claim.claim.text,
          claim.id,
          ...claim.evidence_ids.map((id) => byId.get(id)?.title),
        ]
          .join(" ")
          .toLowerCase()
          .includes(term)),
  );
  const sources = filteredSources
    .filter(
      (source) =>
        !term ||
        [source.title, source.id, source.locator]
          .join(" ")
          .toLowerCase()
          .includes(term),
    )
    .sort((a, b) =>
      order === "newest"
        ? (b.published ?? "").localeCompare(a.published ?? "")
        : (a.published ?? "").localeCompare(b.published ?? ""),
    );
  const count = view === "claims" ? claims.length : sources.length;
  return (
    <section className="panel">
      <Section
        title="Trung tâm bằng chứng"
        detail={
          report.scores.total_claims +
          " nhận định · " +
          report.scores.supported +
          " có bằng chứng · " +
          report.scores.contradicted_claims +
          " bị phản bác · " +
          report.scores.unresolved_conflicts +
          " mâu thuẫn chưa giải quyết"
        }
      />
      {report.retrieval && (
        <p className="muted">
          {report.retrieval.collected_chunks} đoạn thu thập · {report.retrieval.indexed_chunks} đoạn đủ điều kiện lập chỉ mục ·{" "}
          {report.retrieval.cited_documents}/{report.retrieval.indexed_documents} tài liệu đã được dẫn.
          {report.retrieval.sec_reused !== undefined && (
            <> Hồ sơ SEC: {report.retrieval.sec_reused} dùng lại · {report.retrieval.sec_fetched} tải mới.</>
          )}
        </p>
      )}
      <div className="filter-row">
        <label>
          Hiển thị
          <select
            value={view}
            onChange={(e) => {
              setView(e.target.value);
              setPage(0);
            }}
          >
            <option value="claims">Nhận định</option>
            <option value="sources">Tài liệu và số liệu</option>
          </select>
        </label>
        <label>
          Tìm kiếm
          <input
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(0);
            }}
            placeholder="Nhận định, tiêu đề, mã nguồn…"
          />
        </label>
        {view === "claims" && (
          <>
            <label>
              Kiểm chứng
              <select
                aria-label="Kiểm chứng"
                value={status}
                onChange={(e) => {
                  setStatus(e.target.value);
                  setPage(0);
                }}
              >
                <option value="">Tất cả</option>
                {Object.entries(verification).map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Nhóm phân tích
              <select
                value={role}
                onChange={(e) => {
                  setRole(e.target.value);
                  setPage(0);
                }}
              >
                <option value="">Tất cả</option>
                {[...new Set(report.claims.map((c) => c.role))].map((key) => (
                  <option key={key} value={key}>
                    {roles[key] ?? key}
                  </option>
                ))}
              </select>
            </label>
          </>
        )}
        <label>
          Loại nguồn
          <select
            value={kind}
            onChange={(e) => {
              setKind(e.target.value);
              setPage(0);
            }}
          >
            <option value="">Tất cả</option>
            {kinds.map((key) => (
              <option key={key} value={key}>{key === "news" ? "Báo chí" : key}</option>
            ))}
          </select>
        </label>
        <label>
          Kỳ báo cáo
          <select
            value={period}
            onChange={(e) => {
              setPeriod(e.target.value);
              setPage(0);
            }}
          >
            <option value="">Tất cả</option>
            {periods.map((key) => (
              <option key={key} value={key}>
                {displayDate(key)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Công bố từ ngày
          <input
            type="date"
            value={from}
            onChange={(e) => {
              setFrom(e.target.value);
              setPage(0);
            }}
          />
        </label>
        {view === "sources" && (
          <label>
            Sắp xếp
            <select
              value={order}
              onChange={(e) => {
                setOrder(e.target.value);
                setPage(0);
              }}
            >
              <option value="newest">Mới nhất</option>
              <option value="oldest">Cũ nhất</option>
            </select>
          </label>
        )}
      </div>
      {!count ? (
        <State title="Không tìm thấy dữ liệu phù hợp" />
      ) : view === "claims" ? (
        <div className="findings">
          {claims.slice(page * 10, (page + 1) * 10).map((claim) => (
            <ClaimCard key={claim.id} claim={claim} open={open} />
          ))}
        </div>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Tài liệu</th>
                <th>Loại</th>
                <th>Công bố</th>
                <th>Kết thúc kỳ</th>
                <th>Chi tiết</th>
              </tr>
            </thead>
            <tbody>
              {sources.slice(page * 10, (page + 1) * 10).map((source) => (
                <tr key={source.id}>
                  <td>{source.title}</td>
                  <td>{source.kind}</td>
                  <td>{displayDate(source.published)}</td>
                  <td>{displayDate(source.report_end)}</td>
                  <td>
                    <button className="button" onClick={() => open({ source })}>
                      Mở nguồn
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {!!count && (
        <div className="pagination">
          <span>{count} kết quả</span>
          <button
            className="button"
            disabled={!page}
            onClick={() => setPage(page - 1)}
          >
            Trang trước
          </button>
          <button
            className="button"
            disabled={(page + 1) * 10 >= count}
            onClick={() => setPage(page + 1)}
          >
            Trang sau
          </button>
        </div>
      )}
    </section>
  );
}
