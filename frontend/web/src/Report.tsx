import { lazy, Suspense, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  BarChart3,
  CircleAlert,
  Download,
  FileCheck2,
  FileSearch,
  Landmark,
  Layers3,
  RefreshCw,
  ShieldCheck,
  TrendingUp,
} from "lucide-react";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import {
  api,
  dimensions,
  displayDate,
  displayTime,
  factKey,
  metricNames,
  number,
  post,
  roles,
  validSource,
  valueText,
  type Report,
  type Signal,
  type Investment,
} from "./data";
import { Drawer, EvidenceButton, SourceLink, type Selection } from "./Evidence";
import { sourceTarget } from "./excerpt";
import { Explorer } from "./Explorer";
import { ClaimCard } from "./Finding";
const Finance = lazy(() => import("./Finance"));
import { Badge, Loading, Section, State, Stat } from "./ui";

const tabs = [
  ["overview", "Tổng quan"],
  ["finance", "Tài chính"],
  ["topics", "Chủ đề phân tích"],
  ["valuation", "Luận điểm và định giá"],
  ["agents", "Nhóm phân tích"],
  ["context", "Báo chí và mạng xã hội"],
  ["evidence", "Bằng chứng"],
  ["export", "Xuất báo cáo"],
];
const reportRoute = (id: string) => "/reports/" + encodeURIComponent(id);

export default function ReportPage() {
  const { id = "" } = useParams();
  const query = useQuery({
    queryKey: ["report", id],
    queryFn: ({ signal }) => api<Report>(reportRoute(id), { signal }),
    staleTime: 300_000,
  });
  if (query.isPending) return <Loading />;
  if (query.isError)
    return (
      <State
        error
        title="Chưa tải được báo cáo"
        retry={() => void query.refetch()}
      >
        {query.error.message}
      </State>
    );
  return <ReportView key={id} report={query.data} />;
}

function ReportView({ report }: { report: Report }) {
  const [params, setParams] = useSearchParams(),
    [selection, setSelection] = useState<Selection | null>(null);
  const tab = params.get("tab") ?? "overview";
  const selectTab = (key: string) =>
    setParams(key === "overview" ? {} : { tab: key }, { replace: true });
  const { company, scores } = report;
  const nav = useNavigate();
  const rerun = useMutation({
    mutationFn: () => post<{ id: string }>(reportRoute(report.id) + "/rerun"),
    onSuccess: (data) => nav("/nghien-cuu?run=" + data.id),
  });
  const market = report.market.observations ?? [];
  const last = market.at(-1),
    previous = market.at(-2);
  return (
    <>
      <div className="report-back">
        <Link to="/lich-su">
          <ArrowLeft size={16} /> Lịch sử báo cáo
        </Link>
        <span className="muted">
          Tạo lúc {displayTime(report.created_at)} · Bản phân tích{" "}
          {report.version}
        </span>
      </div>
      <section className="company-header">
        <div>
          <div className="company-top">
            <span className="company-symbol">{company.ticker}</span>
            <Badge status={report.status} />
          </div>
          <h1>{company.name}</h1>
          <p>
            {[company.exchange, company.industry, "CIK " + company.cik]
              .filter(Boolean)
              .join(" · ")}
          </p>
          <p>
            Chốt dữ liệu {displayDate(report.request.as_of)}
            {last &&
              " · Giá đóng cửa " +
                valueText(last.close, report.market.currency ?? "") +
                " (" +
                displayDate(last.date) +
                ")"}
            {last &&
              previous &&
              previous.close > 0 &&
              " · Thay đổi " +
                valueText(100 * (last.close / previous.close - 1), "%")}
          </p>
          {report.market.market_cap != null && (
            <p>
              Vốn hóa{" "}
              {valueText(
                report.market.market_cap,
                report.market.currency ?? "",
                true,
              )}
            </p>
          )}
        </div>
        <div className="company-actions">
          <button className="button" onClick={() => selectTab("evidence")}>
            <FileSearch size={16} /> Xem nguồn
          </button>
          <button className="button" onClick={() => selectTab("export")}>
            <Download size={16} /> Xuất báo cáo
          </button>
          <button
            className="button primary"
            disabled={rerun.isPending}
            onClick={() => {
              if (window.confirm("Tạo phiên phân tích mới với cùng tham số?"))
                rerun.mutate();
            }}
          >
            <RefreshCw size={16} /> Phân tích lại
          </button>
        </div>
      </section>
      {rerun.isError && (
        <p role="alert" className="error-text">
          {rerun.error.message}
        </p>
      )}
      <div className="stats four">
        <Stat
          label="Có bằng chứng hỗ trợ"
          value={scores.supported + " / " + scores.total_claims}
          detail={
            scores.total_claims
              ? number(scores.supported_rate * 100) + "% số nhận định"
              : "Chưa có nhận định"
          }
          icon={<ShieldCheck size={18} />}
        />
        <Stat
          label="Khía cạnh có bằng chứng"
          value={
            scores.covered_dimensions.length + " / " + scores.total_dimensions
          }
          icon={<Layers3 size={18} />}
        />
        <Stat
          label="Đoạn nguồn sơ cấp đã lập chỉ mục"
          value={number(scores.primary_evidence)}
          icon={<FileCheck2 size={18} />}
        />
        <Stat
          label="Nhận định bị phản bác"
          value={number(scores.contradicted_claims)}
          detail={scores.unresolved_conflicts + " mâu thuẫn chưa giải quyết"}
          icon={<CircleAlert size={18} />}
        />
      </div>
      <nav className="tabs" aria-label="Mục báo cáo">
        {tabs.map(([key, label]) => (
          <button
            key={key}
            aria-current={tab === key ? "page" : undefined}
            onClick={() => selectTab(key)}
          >
            {label}
          </button>
        ))}
      </nav>
      {tab === "finance" ? (
        <Suspense fallback={<Loading />}>
          <Finance report={report} open={setSelection} />
        </Suspense>
      ) : tab === "topics" ? (
        <Topics report={report} open={setSelection} />
      ) : tab === "agents" ? (
        <Agents report={report} open={setSelection} />
      ) : tab === "evidence" ? (
        <Explorer report={report} open={setSelection} />
      ) : tab === "context" ? (
        <ExternalContext report={report} open={setSelection} />
      ) : tab === "valuation" ? (
        <ReportValuation report={report} open={setSelection} />
      ) : tab === "export" ? (
        <Export report={report} />
      ) : (
        <Overview report={report} open={setSelection} />
      )}
      {selection && (
        <Drawer
          selection={selection}
          report={report}
          close={() => setSelection(null)}
        />
      )}
    </>
  );
}

function Overview({
  report,
  open,
}: {
  report: Report;
  open: (selection: Selection) => void;
}) {
  const findings = useMemo(
    () => new Map(report.claims.map((claim) => [claim.id, claim])),
    [report.claims],
  );
  const summary = report.summary_ids.flatMap((id) => {
    const claim = findings.get(id);
    return claim?.status === "SUPPORTED" ? [claim] : [];
  });
  const editorial = summary.filter((claim) => claim.role !== "computed");
  const main = editorial.slice(0, 6);
  const hasSpecialistFindings = report.claims.some(
    (claim) => claim.role !== "computed" && claim.status === "SUPPORTED",
  );
  const risks = report.claims.filter(
    (claim) =>
      claim.claim.dimension === "risk" &&
      claim.status === "SUPPORTED" &&
      !main.includes(claim),
  );
  const gaps = Object.entries(dimensions).filter(
    ([key]) => !report.scores.covered_dimensions.includes(key),
  );
  const signals = useQuery({
    queryKey: ["signals", report.id],
    queryFn: ({ signal }) =>
      api<Signal[]>(reportRoute(report.id) + "/signals", { signal }),
    staleTime: 300_000,
  });
  const selectedMetrics = [
    "revenue",
    "revenue_growth",
    "ocf",
    "fcf",
    "fcf_margin",
    "operating_margin",
    "roic",
    "interest_coverage",
    "net_debt",
  ];
  const currency =
    report.facts.find(
      (fact) =>
        fact.key === "revenue" && fact.period === "FY" && fact.unit === "USD",
    )?.unit ?? "USD";
  const annualEnd = report.facts
    .filter(
      (fact) =>
        fact.key === "revenue" &&
        fact.period === "FY" &&
        fact.unit === currency,
    )
    .map((fact) => fact.end)
    .sort()
    .at(-1);
  const factMap = new Map(report.facts.map((fact) => [factKey(fact), fact]));
  return (
    <>
      {!!report.warnings.length && (
        <details className="notice">
          <summary>
            <CircleAlert size={17} /> Các bước chưa hoàn tất (
            {report.warnings.length})
          </summary>
          <p>Một số bước chưa tạo được kết quả hợp lệ. Các phần này chưa đủ để xem là một đánh giá hoàn chỉnh.</p>
          <ul>
            {report.warnings.map((message, index) => (
              <li key={index}>{message.replace(/^market: /, "Chuyên gia định giá: ").replace(/^financial: /, "Chuyên gia tài chính: ").replace(/^business: /, "Mô hình kinh doanh: ").replace(/^risk: /, "Rủi ro và quản trị: ")}</li>
            ))}
          </ul>
        </details>
      )}
      {!!report.lead_assessment?.length && <LeadSummary report={report} open={open} />}
      {!hasSpecialistFindings && (
        <State title="Phân tích chuyên môn chưa hoàn tất">
          Báo cáo hiện có thể hiển thị số liệu đã chuẩn hóa. Chưa có nhận định chuyên môn đã kiểm chứng để tổng hợp.
        </State>
      )}
      <section className="panel">
        <Section
          title="Tóm tắt điều hành"
          detail="Kết quả và xu hướng từ số liệu tài chính đã chuẩn hóa."
          action={
            <Link className="button" to={"?tab=valuation"}>
              <Landmark size={16} /> Luận điểm đầu tư
            </Link>
          }
        />
        {signals.isPending ? (
          <Loading />
        ) : signals.isError ? (
          <State
            error
            title="Chưa tải được tóm tắt số liệu"
            retry={() => void signals.refetch()}
          >
            {signals.error.message}
          </State>
        ) : signals.data.length ? (
          <div className="signal-grid">
            {signals.data.map((signal) => (
              <article className="signal" key={signal.period}>
                <div className="finding-meta">
                  <strong>
                    <TrendingUp size={17} /> {signal.title}
                  </strong>
                  <span>{displayDate(signal.end)}</span>
                </div>
                <p>{signal.text}</p>
                <EvidenceButton
                  onClick={() =>
                    open({
                      title: signal.title,
                      facts: signal.inputs,
                      detail: signal.text,
                    })
                  }
                />
              </article>
            ))}
          </div>
        ) : (
          <State title="Chưa đủ dữ liệu để đối chiếu hai kỳ" />
        )}
      </section>
      <section className="panel">
        <Section
          title="Chỉ số tài chính trọng yếu"
          detail={
            annualEnd
              ? "Năm tài chính kết thúc " + displayDate(annualEnd)
              : "Chưa xác định được kỳ tài chính"
          }
        />
        <div className="financial-grid">
          {selectedMetrics.map((metric) => {
            const key = metric === "net_debt" &&
              !report.ratios.some((row) => row.key === metric && row.end === annualEnd && row.value != null) &&
              report.ratios.some((row) => row.key === "reported_debt_less_cash" && row.end === annualEnd && row.value != null)
              ? "reported_debt_less_cash" : metric;
            const fact = annualEnd
              ? report.facts.find(
                  (item) =>
                    item.key === key &&
                    item.end === annualEnd &&
                    item.period === "FY" &&
                    item.unit === currency,
                )
              : undefined;
            const ratio = annualEnd
              ? report.ratios.find(
                  (item) =>
                    item.key === key &&
                    item.end === annualEnd &&
                    (item.period ?? "FY") === "FY",
                )
              : undefined;
            const row = fact ?? ratio;
            const inputs = fact
              ? [fact]
              : (ratio?.inputs.flatMap((id) => {
                  const item = factMap.get(id);
                  return item ? [item] : [];
                }) ?? []);
            return (
              <article key={key} className="financial-card">
                <span>{metricNames[key] ?? (key === "interest_coverage" ? "Khả năng trả lãi" : key)}</span>
                <strong>
                  {row?.value != null
                    ? valueText(row.value, row.unit, true)
                    : "—"}
                </strong>
                  {inputs.length || ratio?.inputs.some((input) => !!validSource(input)) ? (
                  <EvidenceButton
                    onClick={() =>
                      open({
                        title: metricNames[key] ?? (key === "interest_coverage" ? "Khả năng trả lãi" : key),
                        facts: inputs,
                        urls: ratio?.inputs.filter(
                          (input) => !!validSource(input),
                        ),
                        formula: ratio?.formula,
                        detail: valueText(row?.value, row?.unit ?? ""),
                      })
                    }
                  />
                ) : (
                  <small className="muted">Chưa có dữ liệu</small>
                )}
                {!!ratio?.reason && <small className="muted">{ratio.reason}</small>}
              </article>
            );
          })}
        </div>
      </section>
      {!(hasSpecialistFindings && report.lead_assessment?.length) && <section className="panel">
        <Section
          title="Kết luận chính"
          detail="Nhận định được lựa chọn trong báo cáo đã lưu."
        />
        {main.length ? (
          <div className="findings">
            {main.map((claim) => (
              <ClaimCard key={claim.id} claim={claim} open={open} />
            ))}
          </div>
        ) : (
          <State title="Chưa đủ bằng chứng cho kết luận chính" />
        )}
      </section>}
      {!!risks.length && (
        <section className="panel">
          <Section title="Rủi ro đáng theo dõi" />
          <div className="findings">
            {risks.map((claim) => (
              <ClaimCard key={claim.id} claim={claim} open={open} />
            ))}
          </div>
        </section>
      )}
      {!!gaps.length && (
        <section className="panel">
          <Section title="Khía cạnh cần thêm bằng chứng" />
          <div className="tags">
            {gaps.map(([key, label]) => (
              <span key={key}>{label}</span>
            ))}
          </div>
        </section>
      )}
      <p className="muted">
        Kết quả phản ánh bằng chứng trong phạm vi phiên nghiên cứu. Báo cáo phục
        vụ tham khảo.
      </p>
    </>
  );
}

function Topics({
  report,
  open,
}: {
  report: Report;
  open: (selection: Selection) => void;
}) {
  const [params, setParams] = useSearchParams();
  const topic = params.get("topic") ?? "company";
  const matching = report.claims.filter(
    (claim) => claim.claim.dimension === topic,
  );
  const results = matching;
  const remaining = matching.filter(claim => claim.status !== "SUPPORTED").length;
  return (
    <section className="panel">
      <Section title="Phân tích theo chủ đề" />
      <div className="topic-grid">
        {Object.entries(dimensions).map(([key, title]) => (
          <button
            key={key}
            className={"button " + (topic === key ? "selected" : "")}
            onClick={() =>
              setParams({ tab: "topics", topic: key }, { replace: true })
            }
          >
            {title}
          </button>
        ))}
      </div>
      {results.length ? (
        <div className="findings">
          {results.map((claim) => (
            <ClaimCard key={claim.id} claim={claim} open={open} />
          ))}
        </div>
      ) : (
        <State title="Chưa có nhận định cho chủ đề này">Trạng thái agent: {report.topic_coverage?.[topic]?.agent_status ?? "chưa xác định"}. Điều này không đồng nghĩa doanh nghiệp không có dữ liệu; phiên có thể chưa truy xuất hoặc phân tích đủ.</State>
      )}
      {remaining > 0 && (
        <p className="muted">
          {remaining} nhận định còn cần kiểm chứng, đã được hiển thị phía trên.{" "}
          <Link to="?tab=evidence">Xem tại Trung tâm bằng chứng</Link>
        </p>
      )}
      {topic === "industry" && !!report.peers.length && (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Doanh nghiệp đối chiếu</th>
                <th>Kỳ kết thúc</th>
                <th>Doanh thu</th>
                <th>Tăng trưởng</th>
                <th>Biên hoạt động</th>
                <th>Biên dòng tiền tự do</th>
                <th>ROIC</th>
                <th>P/E</th>
                <th>Ngày giá</th>
                <th>Hồ sơ</th>
              </tr>
            </thead>
            <tbody>
              {report.peers.map((peer) => (
                <tr key={peer.ticker}>
                  <td>
                    {peer.ticker} · {peer.name}
                    {peer.same_sic === false && <small className="muted"> · Khác mã ngành SEC</small>}
                  </td>
                  <td>{displayDate(peer.end)}</td>
                  <td>{valueText(peer.revenue, peer.unit, true)}</td>
                  {["revenue_growth", "operating_margin", "fcf_margin", "roic", "pe"].map((key) => (
                    <td key={key}>{peer.ratios[key] == null ? "—" : valueText(peer.ratios[key], key === "pe" ? "x" : "%")}</td>
                  ))}
                  <td>{peer.price_date ? displayDate(peer.price_date) : "—"}</td>
                  <td>
                    {validSource(peer.url) && (
                      <SourceLink href={peer.url}>Mở hồ sơ</SourceLink>
                    )}
                    {peer.market_url && validSource(peer.market_url) && (
                      <SourceLink href={peer.market_url}>Nguồn giá</SourceLink>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function ExternalContext({ report, open }: { report: Report; open: (selection: Selection) => void }) {
  const [group, setGroup] = useState<"news" | "social">("news");
  const label = group === "news" ? "Báo chí" : "Mạng xã hội";
  const saved = report.external_context?.[group];
  const statusLabels: Record<string, string> = {
    disabled: "Brave Web Search chưa được bật hoặc chưa có khóa.",
    search_budget: "Phiên đã dùng hết lượt tìm kiếm trước khi đến nhóm này.",
    search_failed: "Chưa truy vấn được nguồn.",
    empty: "Brave chưa trả về bài phù hợp.",
    unreadable: "Tìm được liên kết, chưa có nội dung đủ điều kiện để agent phân tích.",
    agent_failed: "Agent gặp lỗi khi đọc nguồn.",
    agent_unavailable: "Agent chưa sẵn sàng.",
    partial: "Một phần nguồn đã được phân tích; các nguồn còn lại được giữ kèm lý do.",
    no_observations: "Agent chưa tạo được nhận xét có trích dẫn phù hợp.",
  };
  const citedNews = [...new Map(report.evidence
    .filter((source) => source.kind === "news")
    .map((source) => [source.url, source])).values()];
  const results = useQuery({
    queryKey: ["external-context", report.id, group],
    queryFn: ({ signal }) =>
      api<{ results: { url: string; title: string }[]; unavailable?: string[] }>(
        reportRoute(report.id) + "/context/" + group, { signal },
      ),
    staleTime: 120_000,
    gcTime: 180_000,
    retry: false,
    enabled: !saved,
  });
  return (
    <section className="panel">
      <Section title="Báo chí và mạng xã hội"
        detail={saved ? "Kết quả agent phân tích trong phiên đã lưu." : "Phiên cũ · Nguồn tra cứu có thể mới hơn ngày chốt báo cáo."} />
      {!saved && group === "news" && citedNews.length === 0 && (
        <p className="muted">Phiên này chưa trích dẫn bài báo. Danh sách tra cứu bên dưới chỉ dùng để tham khảo.</p>
      )}
      {!!citedNews.length && group === "news" && (
        <div className="findings">
          <h3>Bài báo được dẫn trong báo cáo</h3>
          {citedNews.map((source) => <article className="finding" key={source.url}>
            <p>{source.title}</p>
            <EvidenceButton onClick={() => open({ source })} />
          </article>)}
        </div>
      )}
      <div className="filter-row">
        <label>Nhóm nguồn
          <select value={group} onChange={(event) => setGroup(event.target.value === "news" ? "news" : "social")}>
            <option value="news">Báo chí</option>
            <option value="social">Mạng xã hội</option>
          </select>
        </label>
        <button className="button primary" type="button" disabled={results.isFetching}
          onClick={() => void results.refetch()}>
          {results.isFetching ? "Đang tìm…" : "Tra cứu thêm " + label.toLowerCase()}
        </button>
      </div>
      {saved && (
        <div className="findings">
          <h3>Kết quả agent trong phiên</h3>
          <p className="muted">Tìm thấy {saved.found} liên kết · Đọc được {saved.read} nguồn gốc · {saved.excerpts ?? 0} trích đoạn tìm kiếm · {saved.analyzed ?? saved.observations.length} nguồn đã phân tích · {saved.pending ?? 0} nguồn chờ xử lý.</p>
          {saved.status !== "ready" && <p>{statusLabels[saved.status] ?? "Chưa có kết quả phân tích."}</p>}
          {saved.error && <p className="muted">{saved.error}</p>}
          {Object.entries(saved.unreadable_reasons ?? {}).map(([reason, count]) => (
            <p className="muted" key={reason}>{count} nguồn · {reason}</p>
          ))}
          {!!saved.links?.length && <details><summary>Liên kết tìm được trong phiên</summary>{saved.links.filter(item => validSource(item.url)).map(item => <p key={item.url}><SourceLink href={item.url}>{item.title || new URL(item.url).hostname}</SourceLink></p>)}</details>}
          {saved.observations.map((item) => (
            <article className="finding" key={item.id}>
              <strong>{item.title}</strong>
              <p className="muted">{displayDate(item.published)} · {group === "social" ? "Ý kiến cộng đồng chưa kiểm chứng" : "Bối cảnh báo chí"}</p>
              <p>{item.observation}</p>
              <p className="muted">Mức tin cậy: {({moderate:"Vừa",low:"Thấp",insufficient:"Chưa đủ căn cứ"} as Record<string,string>)[item.confidence ?? ""] ?? "Chưa kiểm chứng"}. {item.reason}</p>
              <p className="muted">{item.source_type === "search_excerpt" ? "Trích đoạn từ công cụ tìm kiếm · Chưa đọc bài gốc · Cần kiểm chứng" : "Đã đọc nội dung trang gốc"}</p>
              <details><summary>Trích dẫn nguyên văn (ngôn ngữ nguồn)</summary><blockquote><mark>{item.quote}</mark></blockquote></details>
              {validSource(item.url) && (
                <SourceLink href={sourceTarget(item.url, group, "", item.quote).href}>Nguồn đối chứng</SourceLink>
              )}
            </article>
          ))}
        </div>
      )}
      {saved && results.data && <p className="muted">Kết quả tra cứu thêm không thay đổi báo cáo đã lưu. Chọn Phân tích lại để tạo bản đánh giá mới.</p>}
      {!!results.data?.unavailable?.length && (
        <p className="muted">Chưa truy vấn được {results.data.unavailable.join(", ")}.</p>
      )}
      {results.isFetching ? <Loading /> : results.isError ? (
        <State error title="Chưa tìm được nguồn">{results.error.message}</State>
      ) : results.data?.results.length ? (
        <div className="findings">
          {results.data.results.filter((item) => validSource(item.url)).map((item) => (
            <article className="finding" key={item.url}>
              <p>{item.title || new URL(item.url).hostname}</p>
              <p className="muted">{group === "social" ? "Bài đăng chưa kiểm chứng" : "Kết quả tra cứu · Mở bài gốc để đối chiếu"}</p>
              <SourceLink href={item.url}>Mở {group === "news" ? "bài báo" : "bài đăng"}</SourceLink>
            </article>
          ))}
        </div>
      ) : results.data && <State title={group === "social" ? "Brave chưa tìm thấy bài đăng công khai phù hợp" : "Brave chưa tìm thấy bài báo phù hợp"} />}
    </section>
  );
}

function LeadSummary({ report, open }: { report: Report; open: (selection: Selection) => void }) {
  const labels: Record<string, string> = {
    overall: "Đánh giá tổng thể", financial: "Tài chính và tăng trưởng",
    competition: "Vị thế cạnh tranh", risk: "Rủi ro và quản trị", valuation: "Mức giá và định giá",
    business: "Mô hình, lợi thế và ngành", gaps: "Độ tin cậy và việc cần kiểm chứng",
    health: "Sức khỏe doanh nghiệp", conditions: "Điều kiện làm thay đổi luận điểm",
  };
  const points = report.lead_assessment ?? [];
  return (
    <section className="panel">
      <Section title="Đánh giá tổng hợp của Lead" />
      {points.length ? points.map((point) => (
        <article className="finding" key={point.topic}>
          <h3>{labels[point.topic] ?? point.topic}</h3>
          <p>{point.text}</p>
          <p className="muted">Mức tin cậy: {({high:"Cao",moderate:"Vừa",low:"Thấp",insufficient:"Chưa đủ căn cứ",conflicted:"Có mâu thuẫn"} as Record<string,string>)[point.confidence ?? ""] ?? "Chưa phân loại"} · {point.mode === "fallback" ? "Bản kê tự động, chưa có tổng hợp của mô hình" : point.basis}</p>
          {!!point.context_ids?.length && <p className="muted">Có sử dụng bối cảnh bên ngoài chưa kiểm chứng. <Link to="?tab=context">Xem nhận xét và nguồn bối cảnh</Link></p>}
          <div className="finding-actions">
            {point.claim_ids.map((id) => {
              const claim = report.claims.find((item) => item.id === id);
              return claim && <EvidenceButton key={id} onClick={() => open({ claim })}>
                Xem bằng chứng ({id})
              </EvidenceButton>;
            })}
            {point.context_ids?.map(id => {
              const source = Object.values(report.external_context ?? {}).flatMap(group => group.observations).find(item => item.id === id);
              return source && validSource(source.url) ? <SourceLink key={id} href={source.url}>Nguồn bối cảnh: {source.title}</SourceLink> : null;
            })}
          </div>
        </article>
      )) : <State title="Phiên này chưa có đánh giá tổng hợp của Lead" />}
      {!!points.length && !points.some((point) => point.topic === "valuation") && (
        <p className="muted">Chưa đủ bằng chứng để Lead đánh giá mức giá.</p>
      )}
      {points.some((point) => point.topic === "health") && !points.some((point) => point.topic === "conditions") && (
        <p className="muted">Chưa đủ bằng chứng về điều kiện làm thay đổi luận điểm.</p>
      )}
    </section>
  );
}

function Agents({
  report,
  open,
}: {
  report: Report;
  open: (selection: Selection) => void;
}) {
  const entries = Object.entries(report.agents);
  const [selected, setSelected] = useState(entries[0]?.[0] ?? "");
  const claims = report.claims.filter(
    (claim) => selected === "verification" || claim.role === selected,
  );
  return (
    <section className="panel">
      <Section
        title="Kết quả theo nhóm phân tích"
        detail="Xem kết luận, trạng thái kiểm chứng và nguồn của từng nhóm."
      />
      {!entries.length ? (
        <State title="Chưa có kết quả từ các nhóm phân tích" />
      ) : (
        <>
          <div className="agent-grid">
            {entries.map(([role, meta]) => (
              <button
                className={"agent " + (selected === role ? "selected" : "")}
                key={role}
                onClick={() => setSelected(role)}
                aria-pressed={selected === role}
              >
                <strong>{roles[role] ?? role}</strong>
                <span>
                  <Badge status={meta.status} />
                  <small>{meta.count} mục</small>
                </span>
              </button>
            ))}
          </div>
          {selected === "lead" ? <LeadSummary report={report} open={open} /> : selected === "external_context" ? (
            <Link className="button" to="?tab=context">Xem nhận xét và nguồn đối chứng</Link>
          ) : claims.length ? (
            <div className="findings">
              {claims.map((claim) => (
                <ClaimCard key={claim.id} claim={claim} open={open} />
              ))}
            </div>
          ) : (
            <State title="Nhóm này không có nhận định riêng đã lưu" />
          )}
        </>
      )}
    </section>
  );
}

function InvestmentThesis({
  report,
  open,
}: {
  report: Report;
  open: (selection: Selection) => void;
}) {
  const thesis = useQuery({
    queryKey: ["investment", report.id],
    queryFn: ({ signal }) =>
      api<Investment>(reportRoute(report.id) + "/investment", { signal }),
    staleTime: 300_000,
  });
  const [multiples, setMultiples] = useState(["", "", ""]);
  const [manualPrice, setManualPrice] = useState("");
  if (thesis.isPending) return <Loading />;
  if (thesis.isError)
    return <State error title="Chưa tải được luận điểm đầu tư" retry={() => void thesis.refetch()} />;

  const { signals, driver_ids, risk_ids, eps, price } = thesis.data;
  const latest = signals[0];
  const currency = eps?.unit.split("/")[0];
  const enteredPrice = Number(manualPrice);
  const referencePrice = price && price.currency === currency
    ? price.close
    : Number.isFinite(enteredPrice) && enteredPrice > 0 ? enteredPrice : null;
  const observedMultiple = referencePrice !== null && eps ? referencePrice / eps.value : null;
  const priceLabel = price && price.currency === currency && report.market.source !== "manual"
    ? "Giá tại mốc báo cáo" : "Giá tham chiếu đã nhập";
  const scenarioValues = multiples.map((value) => value.trim() ? Number(value) : 0);
  const ordered = scenarioValues.every((value, index) =>
    Number.isFinite(value) && value > 0 && (index === 0 || value >= scenarioValues[index - 1]),
  );
  return (
    <section className="panel">
      <Section title="Luận điểm đầu tư và định giá" />
      {latest && (
        <article className="signal">
          <strong>{latest.title} · {displayDate(latest.end)}</strong>
          <p>{latest.text}</p>
          <EvidenceButton onClick={() => open({ title: latest.title, facts: latest.inputs })} />
        </article>
      )}
      {([["Động lực", driver_ids], ["Rủi ro cần theo dõi", risk_ids]] as const).map(([label, ids]) => (
        <div key={label}>
          <h3>{label}</h3>
          <div className="findings">
            {report.claims.filter((claim) => ids.includes(claim.id)).map((claim) =>
              <ClaimCard key={claim.id} claim={claim} open={open} />,
            )}
            {!ids.length && <p className="muted">Chưa có nhận định đủ bằng chứng cho mục này.</p>}
          </div>
        </div>
      ))}
      <h3>Giá và định giá theo kịch bản</h3>
      {price && <p>{report.market.source === "manual" ? "Giá tham chiếu đã nhập" : "Giá đóng cửa"} {displayDate(price.date)} · {valueText(price.close, price.currency)}{" "}
        {price.url && validSource(price.url) && <SourceLink href={price.url}>Nguồn thị trường</SourceLink>}
      </p>}
      {observedMultiple === null ? (
        <p><strong>Chưa đủ dữ liệu để đánh giá mức giá tại mốc báo cáo.</strong></p>
      ) : (
        <p>{priceLabel} tương ứng P/E {valueText(observedMultiple, "x")} trên EPS năm gần nhất.</p>
      )}
      {eps && (
        <>
          <p>EPS pha loãng năm kết thúc {displayDate(eps.end)} · {valueText(eps.value, eps.unit)}{" "}
            <EvidenceButton onClick={() => open({ title: "EPS pha loãng", facts: [eps] })} />
          </p>
          <p className="muted">Nhập P/E bạn muốn thử cho mỗi kịch bản. Giá theo giả định bằng EPS năm gần nhất nhân P/E.</p>
          {(!price || price.currency !== currency) && (
            <div className="research-form">
              <label>Giá tham chiếu tự nhập ({currency})
                <input type="number" min="0.01" step="any" value={manualPrice}
                  onChange={(event) => setManualPrice(event.target.value)} />
              </label>
            </div>
          )}
          <div className="financial-grid research-form">
            {["Thận trọng", "Cơ sở", "Tích cực"].map((label, index) => (
              <label key={label}>{label} · P/E
                <input type="number" min="0.01" step="any" value={multiples[index]}
                  onChange={(event) => setMultiples(multiples.map((value, i) => i === index ? event.target.value : value))}
                />
                {ordered && Number.isFinite(eps.value * scenarioValues[index]) && (
                  <strong>{valueText(eps.value * scenarioValues[index], currency ?? "")}
                    {referencePrice !== null && " · " + valueText((eps.value * scenarioValues[index] / referencePrice - 1) * 100, "%")}
                  </strong>
                )}
              </label>
            ))}
          </div>
          {multiples.every((value) => value.trim()) && !ordered && (
            <p className="muted">Nhập ba hệ số dương theo thứ tự tăng dần.</p>
          )}
          {observedMultiple !== null && ordered && (
            <p>{priceLabel}{observedMultiple > scenarioValues[2]
              ? " cao hơn cả ba kịch bản."
              : observedMultiple < scenarioValues[0]
                ? " thấp hơn cả ba kịch bản."
                : " nằm trong khoảng định giá theo giả định."}</p>
          )}
        </>
      )}
    </section>
  );
}

function ReportValuation({
  report,
  open,
}: {
  report: Report;
  open: (selection: Selection) => void;
}) {
  const values = report.ratios.filter((row) =>
    ["pe", "pb", "p_fcf", "ev_ebitda"].includes(row.key),
  );
  const lookup = new Map(report.facts.map((fact) => [factKey(fact), fact]));
  return (
    <>
      <InvestmentThesis report={report} open={open} />
      <section className="panel">
      <Section
        title="Định giá thị trường"
        detail={report.market.market_cap_date
          ? (report.market.source === "manual" ? "Giá do người dùng nhập ngày " : "Giá đóng cửa ngày ")
            + displayDate(report.market.market_cap_date) + " · Bội số dựa trên năm tài chính gần nhất."
          : "Chỉ số quan sát tại mốc dữ liệu của báo cáo."}
        action={
          <Link className="button" to="/dinh-gia">
            <Landmark size={16} /> Mở mô hình DCF
          </Link>
        }
      />
      {values.length ? (
        <div className="financial-grid">
          {values.map((row) => (
            <article className="financial-card" key={row.key}>
              <span>
                {metricNames[row.key]} · {displayDate(row.end)}
              </span>
              <strong>
                {row.value == null ? "—" : valueText(row.value, row.unit)}
              </strong>
              {row.value == null ? (
                <small className="muted">
                  {row.reason || "Chưa có dữ liệu"}
                </small>
              ) : (
                <EvidenceButton
                  onClick={() =>
                    open({
                      title: metricNames[row.key],
                      facts: row.inputs.flatMap((id) => {
                        const fact = lookup.get(id);
                        return fact ? [fact] : [];
                      }),
                      urls: row.inputs.filter((input) => !!validSource(input)),
                      formula: row.formula,
                      detail: valueText(row.value, row.unit),
                    })
                  }
                />
              )}
              {row.inputs
                .filter((input) => validSource(input))
                .map((input) => (
                  <SourceLink key={input} href={input}>
                    Nguồn thị trường
                  </SourceLink>
                ))}
            </article>
          ))}
        </div>
      ) : (
        <State title="Chưa có chỉ số định giá tại mốc này" />
      )}
      <div className="findings">
        {report.claims
          .filter((claim) => claim.claim.dimension === "valuation")
          .map((claim) => (
            <ClaimCard key={claim.id} claim={claim} open={open} />
          ))}
      </div>
      </section>
    </>
  );
}

function Export({ report }: { report: Report }) {
  const nav = useNavigate(),
    cache = useQueryClient();
  const [format, setFormat] = useState("pdf"),
    [score, setScore] = useState(5),
    [note, setNote] = useState("");
  const feedback = useMutation({
    mutationFn: () =>
      post(reportRoute(report.id) + "/feedback", { score, note }),
  });
  const remove = useMutation({
    mutationFn: () => api(reportRoute(report.id), { method: "DELETE" }),
    onSuccess: () => {
      void cache.invalidateQueries({ queryKey: ["reports"] });
      void cache.invalidateQueries({ queryKey: ["history"] });
      void cache.invalidateQueries({ queryKey: ["dashboard"] });
      nav("/lich-su");
    },
  });
  return (
    <div className="dashboard-grid">
      <section className="panel">
        <Section title="Tải báo cáo" action={<Download size={19} />} />
        <div className="search-inline">
          <label>
            Định dạng
            <select value={format} onChange={(e) => setFormat(e.target.value)}>
              <option value="pdf">PDF</option>
              <option value="md">Markdown</option>
              <option value="json">JSON</option>
            </select>
          </label>
          <a
            className="button primary"
            href={
              "/api/v1" + reportRoute(report.id) + "/export?format=" + format
            }
            download
          >
            <Download size={16} /> Tải xuống
          </a>
        </div>
        <div className="details">
          <p>
            Thời gian xử lý:{" "}
            {report.elapsed_seconds == null
              ? "—"
              : number(report.elapsed_seconds) + " giây"}
          </p>
          <p>
            Chi phí ước tính:{" "}
            {report.estimated_cost_usd == null
              ? "Chưa có đơn giá"
              : valueText(report.estimated_cost_usd, "USD")}
          </p>
        </div>
        <details className="notice">
          <summary>
            <BarChart3 size={17} /> Mức sử dụng dịch vụ
          </summary>
          <dl>
            {[
              ["Lượt gọi mô hình", "model"],
              ["Lượt tìm kiếm", "search"],
              ["Token đầu vào Gemini", "gemini_input_tokens"],
              ["Token đầu ra Gemini", "gemini_output_tokens"],
            ].map(([label, key]) =>
              report.usage[key] != null ? (
                <div key={key}>
                  <dt>{label}</dt>
                  <dd>{number(report.usage[key])}</dd>
                </div>
              ) : null,
            )}
          </dl>
        </details>
        <details className="notice">
          <summary>Quản lý báo cáo</summary>
          <button
            className="button danger"
            disabled={remove.isPending}
            onClick={() => {
              if (
                window.confirm(
                  "Xóa vĩnh viễn báo cáo " + report.company.ticker + " này?",
                )
              )
                remove.mutate();
            }}
          >
            Xóa báo cáo
          </button>
          {remove.isError && (
            <p role="alert" className="error-text">
              {remove.error.message}
            </p>
          )}
        </details>
      </section>
      <section className="panel">
        <Section title="Gửi phản hồi" />
        <form
          className="research-form"
          onSubmit={(e) => {
            e.preventDefault();
            feedback.mutate();
          }}
        >
          <label>
            Mức độ hữu ích
            <select
              value={score}
              onChange={(e) => setScore(Number(e.target.value))}
            >
              {[1, 2, 3, 4, 5].map((value) => (
                <option key={value} value={value}>
                  {value} / 5
                </option>
              ))}
            </select>
          </label>
          <label>
            Ghi chú
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              maxLength={2000}
              rows={4}
            />
          </label>
          <button className="button primary" disabled={feedback.isPending}>
            Lưu phản hồi
          </button>
          {feedback.isSuccess && (
            <p role="status" className="ready-label">
              Đã lưu phản hồi.
            </p>
          )}
          {feedback.isError && (
            <p role="alert" className="error-text">
              {feedback.error.message}
            </p>
          )}
        </form>
      </section>
    </div>
  );
}
