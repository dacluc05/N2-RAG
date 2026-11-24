import { useEffect, useRef, useState, type ReactNode } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ExternalLink, FileCheck2, X } from "lucide-react";
import {
  api,
  claimText,
  claimVerificationLabel,
  displayDate,
  evidenceId,
  factKey,
  formulaText,
  metricNames,
  post,
  validSource,
  valueText,
  type Claim,
  type Evidence,
  type Fact,
  type Report,
} from "./data";
import { Link, useLocation, useParams, useSearchParams } from "react-router-dom";
import { matchExcerpt, sourceTarget } from "./excerpt";
import { Badge, Loading, Section, State } from "./ui";

export type Selection =
  | { claim: Claim; only?: string }
  | {
      title: string;
      facts: Fact[];
      urls?: string[];
      formula?: string;
      detail?: string;
    }
  | { source: Evidence };

export function EvidenceButton({
  children,
  onClick,
}: {
  children?: ReactNode;
  onClick: () => void;
}) {
  return (
    <button type="button" className="button evidence-button" onClick={onClick}>
      <FileCheck2 size={16} />
      {children ?? "Xem bằng chứng"}
    </button>
  );
}

export function Drawer({
  selection,
  report,
  close,
}: {
  selection: Selection;
  report: Report;
  close: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const panel = dialog.current;
    panel?.showModal();
    return () => panel?.close();
  }, []);
  return (
    <dialog
      ref={dialog}
      className="drawer"
      aria-labelledby="evidence-heading"
      onCancel={close}
      onClick={(event) => {
        if (event.target === event.currentTarget) close();
      }}
    >
      <div className="drawer-content">
        <header className="drawer-heading">
          <div>
            <span className="muted">
              {report.company.ticker} · {displayDate(report.request.as_of)}
            </span>
            <h2 id="evidence-heading">Bằng chứng</h2>
          </div>
          <button
            className="icon-button"
            aria-label="Đóng bằng chứng"
            onClick={close}
          >
            <X size={21} />
          </button>
        </header>
        <div className="drawer-body">
          {"claim" in selection ? (
            <ClaimSources selection={selection} report={report} />
          ) : "source" in selection ? (
            <SelectedSource source={selection.source} report={report} />
          ) : (
            <>
              <h3>{selection.title}</h3>
              {selection.detail && <p>{selection.detail}</p>}
              {selection.formula && (
                <div className="formula">{formulaText(selection.formula)}</div>
              )}
              {selection.facts.length ? (
                selection.facts.map((fact) => (
                  <FactSource
                    key={factKey(fact)}
                    reportId={report.id}
                    fact={fact}
                  />
                ))
              ) : !selection.urls?.length ? (
                <State title="Chưa có nguồn đầu vào trong báo cáo này" />
              ) : null}
              {selection.urls?.map((url) => (
                <SourceLink key={url} href={url}>
                  Nguồn đối chứng
                </SourceLink>
              ))}
              {!!selection.urls?.length && (
                <p className="muted">
                  Nguồn thị trường chưa lưu vị trí chính xác trong trang.
                </p>
              )}
            </>
          )}
        </div>
      </div>
    </dialog>
  );
}

function ClaimSources({
  selection,
  report,
}: {
  selection: { claim: Claim; only?: string };
  report: Report;
}) {
  const { claim, only } = selection;
  const numbers = [claim.claim.numeric, ...(claim.claim.comparisons ?? [])];
  const checks = numbers.flatMap((number) => {
    if (!number) return [];
    const matching = report.ratios.filter(
      (row) =>
        row.key === number.key &&
        row.end === number.end &&
        row.unit === number.unit &&
        row.value != null &&
        (!number.period || (row.period ?? "FY") === number.period),
    );
    return matching.length === 1 ? [{ number, ratio: matching[0] }] : [];
  });
  const lookup = useQuery({
    queryKey: ["fact-id-map", report.id],
    queryFn: async () =>
      new Map(
        await Promise.all(
          report.facts.map(
            async (fact) => [await evidenceId(fact), fact] as const,
          ),
        ),
      ),
    enabled: [...claim.evidence_ids, ...claim.counter_ids].some((id) =>
      id.startsWith("X:"),
    ),
    staleTime: Infinity,
  });
  const sources = new Map(report.evidence.map((source) => [source.id, source]));
  const sections = [
    [
      claim.status === "SUPPORTED" ? "Nguồn hỗ trợ" : "Nguồn được trích dẫn",
      claim.evidence_ids,
    ],
    ["Nguồn trái chiều", claim.counter_ids],
  ] as const;
  return (
    <>
      <Badge
        status={claim.status}
        claim
        label={claimVerificationLabel(claim)}
      />
      <h3>{claimText(claim)}</h3>
      {claim.reason && <p className="muted">{claim.reason}</p>}
      {checks.map(({ number, ratio }) => (
        <div
          className="formula"
          key={[number.key, number.period, number.end].join("/")}
        >
          <div>Đối chiếu kỳ {displayDate(number.end)}</div>
          <div>
            {formulaText(ratio.formula)} = {valueText(ratio.value, ratio.unit)}
          </div>
        </div>
      ))}
      {sections.map(([label, ids]) => {
        const available = ids.filter((id) => !only || id === only);
        return available.length ? (
          <section key={label}>
            <h4>{label}</h4>
            {available.map((id) => {
              const source = sources.get(id);
              const fact = lookup.data?.get(id);
              if (fact)
                return (
                  <FactSource
                    key={id}
                    fact={fact}
                    reportId={report.id}
                    sourceId={id}
                  />
                );
              if (id.startsWith("X:") && lookup.isPending)
                return (
                  <p key={id} className="muted">
                    Đang đối chiếu số liệu…
                  </p>
                );
              return source ? (
                <TextSource
                  key={id}
                  source={source}
                  reportId={report.id}
                  claimId={claim.id}
                  quote={
                    claim.claim.references.find((ref) => ref.evidence_id === id)
                      ?.quote
                  }
                />
              ) : (
                <p key={id} className="muted">
                  Bằng chứng này chưa có trong báo cáo đã lưu.
                </p>
              );
            })}
          </section>
        ) : null;
      })}
      {!claim.evidence_ids.length && !claim.counter_ids.length && (
        <State title="Chưa có bằng chứng liên kết" />
      )}
    </>
  );
}

interface FactLocation {
  url: string | null;
  located: boolean;
  source_row?: {
    anchor: string;
    rendered: string;
    cells: string[];
    selected_cell: number | null;
    text_fragment?: string | null;
  };
}

function useFactLocation(reportId: string, fact: Fact) {
  return useQuery({
    queryKey: ["sec-anchor", reportId, factKey(fact)],
    queryFn: async ({ signal }) => {
      const id = await evidenceId(fact);
      return api<FactLocation>(
        "/analysis/" +
          reportId +
          "/evidence/" +
          encodeURIComponent(id) +
          "/location",
        { signal },
      );
    },
    retry: (count, error) => count < 1 && (
      error instanceof TypeError || error.message === "Tạm thời chưa tải được hồ sơ SEC."
    ),
    retryDelay: 400,
    staleTime: (query) => query.state.data?.located ? 300_000 : 0,
  });
}

function FactSource({
  fact,
  reportId,
  sourceId,
}: {
  fact: Fact;
  reportId: string;
  sourceId?: string;
}) {
  const params = new URLSearchParams({ fact: factKey(fact) });
  const { search } = useLocation();
  const tab = new URLSearchParams(search).get("tab");
  if (tab) params.set("tab", tab);
  return (
    <article className="source-card">
      <span className="source-kind">SEC EDGAR · {fact.form || "XBRL"}</span>
      <h4>{metricNames[fact.key] ?? fact.key}</h4>
      <p className="muted">
        Kỳ kết thúc {displayDate(fact.end)} · Công bố {displayDate(fact.filed)}
      </p>
      <blockquote>
        <mark>{valueText(fact.value, fact.unit)}</mark>
      </blockquote>
      <Link
        className="button source-link"
        to={"/so-lieu/" + reportId + "?" + params}
      >
        Nguồn đối chứng
      </Link>
      {sourceId && <SourceCheck reportId={reportId} sourceId={sourceId} />}
    </article>
  );
}

export function FactReader() {
  const { reportId = "" } = useParams();
  const [params] = useSearchParams();
  const report = useQuery({
    queryKey: ["report", reportId],
    queryFn: ({ signal }) =>
      api<Report>("/reports/" + encodeURIComponent(reportId), { signal }),
  });
  if (report.isPending) return <Loading />;
  if (report.isError)
    return (
      <State
        title="Không tải được số liệu"
        error
        retry={() => void report.refetch()}
      >
        {report.error.message}
      </State>
    );
  const key = params.get("fact");
  const fact =
    report.data.facts.find((item) => factKey(item) === key) ??
    report.data.changes
      .flatMap((change) => [change.prior, change.current])
      .find((item) => factKey(item) === key);
  if (!fact) return <State title="Không tìm thấy số liệu trong báo cáo này" />;
  return (
    <FactDocument
      key={key}
      reportId={reportId}
      fact={fact}
      ticker={report.data.company.ticker}
      returnTab={params.get("tab")}
    />
  );
}

function FactDocument({
  reportId,
  fact,
  ticker,
  returnTab,
}: {
  reportId: string;
  fact: Fact;
  ticker: string;
  returnTab: string | null;
}) {
  const anchor = useFactLocation(reportId, fact);
  const row = anchor.data?.source_row;
  const target = validSource(anchor.data?.url ?? fact.url);
  const original =
    target && row?.text_fragment
      ? target + ":~:text=" + row.text_fragment
      : target;
  const title = metricNames[fact.key] ?? fact.key;
  return (
    <>
      <div className="report-back">
        <Link to={"/bao-cao/" + reportId + (returnTab ? "?" + new URLSearchParams({ tab: returnTab }) : "")}>
          ← Quay lại báo cáo {ticker}
        </Link>
      </div>
      <section className="panel">
        <Section
          title={title}
          detail={ticker + " · SEC EDGAR · " + (fact.form || "XBRL")}
        />
        <p className="muted">
          Kỳ kết thúc {displayDate(fact.end)} · Công bố{" "}
          {displayDate(fact.filed)}
        </p>
        <article className="source-card">
          <h4>Số liệu theo đơn vị gốc</h4>
          <blockquote>
            <mark>{valueText(fact.value, fact.unit)}</mark>
          </blockquote>
          {anchor.isFetching && !row && (
            <p role="status" className="muted">
              Đang tìm vị trí số liệu trong hồ sơ SEC…
            </p>
          )}
          {row && (
            <section className="sec-fact-row">
              <h4>Dòng trích từ hồ sơ SEC</h4>
              {row.selected_cell === null ? (
                <blockquote>
                  <mark>{row.rendered}</mark>
                </blockquote>
              ) : (
                <div className="sec-fact-scroll">
                  <table aria-label="Dòng số liệu trong hồ sơ SEC">
                    <tbody>
                      <tr>
                        {row.cells.map(
                          (cell, index) =>
                            (cell || index === row.selected_cell) && (
                              <td key={index}>
                                {index === row.selected_cell ? (
                                  <mark>{cell || row.rendered}</mark>
                                ) : (
                                  cell
                                )}
                              </td>
                            ),
                        )}
                      </tr>
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          )}
          {!anchor.isFetching && !row && (
            <>
              <p role="status" className="muted">
                {anchor.isError
                  ? "Tạm thời chưa tải được dòng gốc. Bạn vẫn có thể đọc số liệu đã lưu ở trên."
                  : "Chưa định vị được dòng gốc trong hồ sơ SEC."}
              </p>
              <button className="button subtle" type="button" onClick={() => void anchor.refetch()}>
                Thử lại đối chiếu
              </button>
              {target && <SourceLink href={target}>Mở hồ sơ gốc</SourceLink>}
            </>
          )}
          {original && anchor.data?.located && (
            <SourceLink href={original}>Mở hồ sơ gốc tại dòng số liệu</SourceLink>
          )}
          {anchor.data?.located && !row?.text_fragment && (
            <p className="muted">
              Hồ sơ gốc mở tại vị trí đã xác định. Ô đối chiếu được đánh dấu ở bảng trên.
            </p>
          )}
        </article>
      </section>
    </>
  );
}

export function SourceReader() {
  const { reportId = "" } = useParams();
  const [params] = useSearchParams();
  const sourceId = params.get("id");
  const report = useQuery({
    queryKey: ["report", reportId],
    queryFn: ({ signal }) =>
      api<Report>("/reports/" + encodeURIComponent(reportId), { signal }),
  });
  if (report.isPending) return <Loading />;
  if (report.isError)
    return (
      <State
        title="Không tải được dẫn chứng"
        error
        retry={() => void report.refetch()}
      >
        {report.error.message}
      </State>
    );
  const source = report.data.evidence.find((item) => item.id === sourceId)
    ?? report.data.leadership_updates?.find((item) => item.id === sourceId);
  if (!source) return <State title="Không tìm thấy nguồn trong báo cáo này" />;
  const claimId = params.get("claim");
  const claim = report.data.claims.find((item) => item.id === claimId);
  const quote = claim
    ? claim.claim.references.find((ref) => ref.evidence_id === source.id)?.quote
    : savedQuote(report.data, source);
  return (
    <>
      <div className="report-back">
        <Link to={"/bao-cao/" + reportId + "?" + new URLSearchParams({ tab: params.get("tab") || "evidence" })}>
          ← Quay lại báo cáo
        </Link>
      </div>
      <section className="panel">
        <Section
          title="Đối chiếu dẫn chứng"
          detail="Đoạn nguyên văn đã lưu từ nguồn khi tạo báo cáo."
        />
        {claim && <p>{claimText(claim)}</p>}
        <TextSource
          source={source}
          quote={quote}
          reportId={reportId}
          claimId={claim?.id}
          reader
        />
      </section>
    </>
  );
}

function savedQuote(report: Report, source: Evidence) {
  return report.claims
    .flatMap((claim) => claim.claim.references)
    .find(
      (ref) =>
        ref.evidence_id === source.id && matchExcerpt(source.text, ref.quote),
    )?.quote;
}

function TextSource({
  source,
  quote,
  reportId,
  claimId,
  reader = false,
}: {
  source: Evidence;
  quote?: string;
  reportId: string;
  claimId?: string;
  reader?: boolean;
}) {
  const [expanded, setExpanded] = useState(reader);
  const marker = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!reader || !marker.current) return;
    const bounds = marker.current.getBoundingClientRect();
    if (bounds.top < 70 || bounds.top >= window.innerHeight - 60) {
      marker.current.scrollIntoView({ block: "center" });
    }
  }, [reader, source.id, quote]);
  const match = matchExcerpt(source.text, quote);
  const hasText = !!source.text.trim();
  const start = match?.start ?? 0;
  const end = match?.end ?? source.text.length;
  const left = expanded ? 0 : Math.max(0, start - 240);
  const right = expanded
    ? source.text.length
    : match
      ? Math.min(source.text.length, end + 380)
      : Math.min(source.text.length, 420);
  const base = validSource(source.url);
  const link = base
    ? sourceTarget(
        base,
        source.kind,
        source.locator,
        source.text.slice(start, end),
      )
    : undefined;
  const readerParams = new URLSearchParams({ id: source.id });
  if (claimId) readerParams.set("claim", claimId);
  const { search } = useLocation();
  const tab = new URLSearchParams(search).get("tab");
  if (tab) readerParams.set("tab", tab);
  return (
    <article className="source-card">
      <span className="source-kind">
        {source.kind.toUpperCase()} ·{" "}
        {source.quality === "primary"
          ? "Nguồn sơ cấp"
          : source.quality === "approved"
            ? "Nguồn được duyệt"
            : "Nguồn bên ngoài"}
      </span>
      <h4>{source.title}</h4>
      <p className="muted">
        Công bố {displayDate(source.published)} · Kỳ kết thúc{" "}
        {displayDate(source.report_end)}
      </p>
      {source.locator && <p className="muted">{source.locator}</p>}
      {hasText && (
        <>
          {!match && (
            <p className="muted">
              Tô sáng đoạn nguồn đã lưu.{" "}
              {quote
                ? "Chưa đối chiếu được câu trích dẫn riêng."
                : "Nguồn này chưa có câu trích dẫn riêng."}
            </p>
          )}
          <blockquote className={reader ? "source-reader-excerpt" : undefined}>
            {left > 0 ? "…" : ""}
            {source.text.slice(left, start)}
            <mark ref={marker}>
              {source.text.slice(start, Math.min(end, right))}
            </mark>
            {source.text.slice(Math.min(end, right), right)}
            {right < source.text.length ? "…" : ""}
          </blockquote>
        </>
      )}
      {!reader && (left > 0 || right < source.text.length || expanded) && (
        <button
          className="button subtle"
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? "Thu gọn" : "Xem thêm ngữ cảnh"}
        </button>
      )}
      {link?.mode === "page" && (
        <PdfCounterproof
          path={
            "/analysis/" +
            reportId +
            "/evidence/" +
            encodeURIComponent(source.id) +
            "/pdf" +
            (claimId ? "?claim_id=" + encodeURIComponent(claimId) : "")
          }
        />
      )}
      {!reader && hasText && (
        <Link className="button source-link" to={"/nguon/" + reportId + "?" + readerParams.toString()}>
          Đối chiếu đoạn tô sáng
        </Link>
      )}
      {link && (
        <SourceLink href={link.href}>
          {link.mode === "page" ? "Mở PDF gốc tại trang trích" :
            link.mode === "text" ? "Mở nguồn gốc tại đoạn trích" : "Mở tài liệu gốc"}
        </SourceLink>
      )}
      {link?.mode === "document" && (
        <p className="muted">Nguồn gốc chưa có vị trí trích dẫn. Xem phần tô sáng trong FinSight.</p>
      )}
      {base && <SourceCheck reportId={reportId} sourceId={source.id} />}
    </article>
  );
}

function PdfCounterproof({ path }: { path: string }) {
  const preview = useMutation({
    mutationFn: async () => {
      const response = await fetch("/api/v1" + path);
      if (
        !response.ok ||
        !response.headers.get("Content-Type")?.startsWith("application/pdf")
      ) {
        throw new Error(
          "Chưa đối chiếu được đoạn trích trên trang PDF. Bạn có thể mở trang gốc hoặc đọc đoạn đã lưu.",
        );
      }
      return response.blob();
    },
    onSuccess: (document) => {
      const url = URL.createObjectURL(document);
      window.location.assign(url);
    },
  });
  return (
    <>
      <button
        className="button source-link"
        type="button"
        disabled={preview.isPending}
        onClick={() => preview.mutate()}
      >
        {preview.isPending ? "Đang đối chiếu…" : "Nguồn đối chứng"}
      </button>
      {preview.isError && (
        <p role="alert" className="muted">
          {preview.error.message}
        </p>
      )}
    </>
  );
}

function SelectedSource({
  source,
  report,
}: {
  source: Evidence;
  report: Report;
}) {
  const numeric = source.kind === "xbrl";
  const lookup = useQuery({
    queryKey: ["fact-id-map", report.id],
    queryFn: async () =>
      new Map(
        await Promise.all(
          report.facts.map(
            async (fact) => [await evidenceId(fact), fact] as const,
          ),
        ),
      ),
    enabled: numeric,
    staleTime: Infinity,
  });
  if (numeric && lookup.isPending)
    return <p className="muted">Đang đối chiếu số liệu…</p>;
  const fact = numeric ? lookup.data?.get(source.id) : undefined;
  return fact ? (
    <FactSource fact={fact} reportId={report.id} sourceId={source.id} />
  ) : (
    <TextSource
      source={source}
      quote={savedQuote(report, source)}
      reportId={report.id}
    />
  );
}

function SourceCheck({
  reportId,
  sourceId,
}: {
  reportId: string;
  sourceId: string;
}) {
  const status = useMutation({
    mutationFn: () =>
      post<{ reachable: boolean; message: string }>(
        "/analysis/" +
          reportId +
          "/evidence/" +
          encodeURIComponent(sourceId) +
          "/check",
      ),
  });
  return (
    <div className="source-check">
      <button
        className="button subtle"
        disabled={status.isPending}
        onClick={() => status.mutate()}
      >
        {status.isPending ? "Đang kiểm tra…" : "Kiểm tra truy cập nguồn"}
      </button>
      {status.data && (
        <p
          role="status"
          className={status.data.reachable ? "ready-label" : "muted"}
        >
          {status.data.message}
        </p>
      )}
      {status.isError && (
        <p role="alert" className="error-text">
          {status.error.message}
        </p>
      )}
    </div>
  );
}

export function SourceLink({
  href,
  children,
}: {
  href: string;
  children: ReactNode;
}) {
  return (
    <a
      className="button source-link"
      href={href}
      target="_blank"
      rel="noopener noreferrer"
    >
      {children}
      <ExternalLink size={14} />
    </a>
  );
}
