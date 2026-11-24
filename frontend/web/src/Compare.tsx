import { useState } from "react";
import { useQueries } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  api,
  displayDate,
  displayTime,
  metricNames,
  number,
  readable,
  valueText,
  type Report,
} from "./data";
import { useHistory } from "./Workspace";
import { Heading, Loading, OpenReport, Section, State } from "./ui";

const keys = [
  "revenue",
  "revenue_growth",
  "net_income",
  "gross_margin",
  "ocf",
  "fcf",
  "roe",
  "roic",
  "net_debt",
  "pe",
];
const raw = ["revenue", "net_income", "ocf"];
const dollars = ["revenue", "net_income", "ocf", "fcf", "net_debt"];
export default function Compare() {
  const history = useHistory();
  const [ids, setIds] = useState(["", ""]);
  const queries = useQueries({
    queries: ids.filter(Boolean).map((id) => ({
      queryKey: ["report", id],
      queryFn: ({ signal }: { signal: AbortSignal }) =>
        api<Report>("/reports/" + id, { signal }),
      staleTime: 300_000,
    })),
  });
  const reports = queries.flatMap((query) => (query.data ? [query.data] : []));
  const ends = reports.map((report) =>
    report.facts
      .filter(
        (fact) =>
          fact.key === "revenue" && fact.unit === "USD" && fact.period === "FY",
      )
      .map((fact) => fact.end)
      .sort()
      .at(-1),
  );
  const dates = ends.flatMap((end) => (end ? [Date.parse(end)] : []));
  const aligned =
    dates.length === reports.length &&
    dates.length >= 2 &&
    Math.max(...dates) - Math.min(...dates) <= 92 * 86_400_000;
  const rows = keys.map((key) => ({
    key,
    values: reports.map((report, index) => {
      const end = ends[index];
      return end
        ? raw.includes(key)
          ? report.facts.find(
              (fact) =>
                fact.key === key &&
                fact.end === end &&
                fact.period === "FY" &&
                fact.unit === "USD",
            )
          : report.ratios.find(
              (ratio) =>
                ratio.key === key &&
                ratio.end === end &&
                (ratio.period ?? "FY") === "FY" &&
                (!dollars.includes(key) || ratio.unit === "USD"),
            )
        : undefined;
    }),
  }));
  const plot = rows
    .filter(
      (row) =>
        dollars.includes(row.key) &&
        row.values.every((value) => value?.value != null),
    )
    .map((row) => ({
      label: metricNames[row.key],
      ...Object.fromEntries(
        row.values.map((value, index) => [
          "series" + index,
          value!.value! / 1e9,
        ]),
      ),
    }));
  const options = (history.data ?? []).filter((run) => readable(run.status));
  return (
    <>
      <Heading
        title="So sánh doanh nghiệp"
        detail="Đối chiếu từ hai đến bốn báo cáo đã lưu theo cùng định nghĩa chỉ tiêu."
      />
      <section className="panel">
        <Section
          title="Chọn báo cáo"
          action={
            ids.length < 4 ? (
              <button className="button" onClick={() => setIds([...ids, ""])}>
                Thêm doanh nghiệp
              </button>
            ) : undefined
          }
        />
        {history.isPending ? (
          <Loading />
        ) : history.isError ? (
          <State
            error
            title="Chưa tải được báo cáo"
            retry={() => void history.refetch()}
          >
            {history.error.message}
          </State>
        ) : (
          <div className="filter-row">
            {ids.map((id, index) => (
              <label key={index}>
                Báo cáo {index + 1}
                <select
                  value={id}
                  onChange={(e) =>
                    setIds(
                      ids.map((existing, i) =>
                        i === index ? e.target.value : existing,
                      ),
                    )
                  }
                >
                  <option value="">Chọn báo cáo</option>
                  {options
                    .filter((run) => run.id === id || !ids.includes(run.id))
                    .map((run) => (
                      <option key={run.id} value={run.id}>
                        {run.ticker} · {displayTime(run.created_at)}
                      </option>
                    ))}
                </select>
              </label>
            ))}
          </div>
        )}
      </section>
      {queries.some((q) => q.isPending) ? (
        <Loading />
      ) : queries.some((q) => q.isError) ? (
        <State error title="Chưa tải được một hoặc nhiều báo cáo" />
      ) : (
        reports.length >= 2 && (
          <>
            <section className="panel">
              <Section
                title="Đối chiếu số liệu"
                detail="Số liệu năm gần nhất trong từng báo cáo. Chênh lệch tối đa 92 ngày để vẽ biểu đồ đối chiếu."
              />
              {!aligned && (
                <p className="notice">
                  Ngày kết thúc năm tài chính khác nhau quá 92 ngày hoặc thiếu
                  kỳ đối chiếu. Các cột dưới đây chỉ dùng để tra cứu từng báo
                  cáo.
                </p>
              )}
              {new Set(reports.map((report) => report.company.ticker)).size <
                reports.length && (
                <p className="notice">
                  Có nhiều phiên của cùng một doanh nghiệp. So sánh theo mốc và
                  thời điểm tạo báo cáo.
                </p>
              )}
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Chỉ tiêu</th>
                      {reports.map((report, index) => (
                        <th key={report.id}>
                          {report.company.ticker}
                          <small className="table-note">
                            {displayDate(ends[index])}
                          </small>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr key={row.key}>
                        <td>{metricNames[row.key]}</td>
                        {row.values.map((value, index) => (
                          <td className="numeric" key={index}>
                            {value
                              ? valueText(value.value, value.unit, true)
                              : "—"}
                          </td>
                        ))}
                      </tr>
                    ))}
                    <tr>
                      <td>Nguồn</td>
                      {reports.map((report) => (
                        <td key={report.id}>
                          <OpenReport id={report.id} />
                        </td>
                      ))}
                    </tr>
                  </tbody>
                </table>
              </div>
            </section>
            {aligned && !!plot.length && (
              <section className="panel">
                <Section
                  title="Quy mô tài chính"
                  detail="Tỷ USD · Nguồn: báo cáo SEC đã lưu."
                />
                <div className="chart">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={plot}>
                      <CartesianGrid vertical={false} stroke="var(--border)" />
                      <XAxis
                        dataKey="label"
                        tick={{ fill: "var(--muted)", fontSize: 11 }}
                      />
                      <YAxis tick={{ fill: "var(--muted)", fontSize: 11 }} />
                      <Tooltip
                        formatter={(value) => number(Number(value)) + " tỷ USD"}
                        contentStyle={{
                          background: "var(--panel)",
                          borderColor: "var(--border)",
                        }}
                      />
                      <Legend />
                      {reports.map((report, index) => (
                        <Bar
                          key={report.id}
                          dataKey={"series" + index}
                          name={
                            report.company.ticker +
                            " · " +
                            displayDate(report.request.as_of)
                          }
                          fill={
                            ["#5593ff", "#26b6ae", "#a78bfa", "#e6a252"][index]
                          }
                          isAnimationActive={false}
                        />
                      ))}
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </section>
            )}
            <section className="panel">
              <Section title="Lợi thế cạnh tranh và rủi ro" />
              <div className="signal-grid">
                {reports.map((report) => (
                  <div className="signal" key={report.id}>
                    <strong>{report.company.ticker}</strong>
                    <p>
                      {
                        report.claims.filter(
                          (claim) =>
                            ["moat", "risk"].includes(claim.claim.dimension) &&
                            claim.status === "SUPPORTED",
                        ).length
                      }{" "}
                      nhận định có bằng chứng trong hai nhóm.
                    </p>
                    <OpenReport id={report.id} />
                  </div>
                ))}
              </div>
            </section>
          </>
        )
      )}
    </>
  );
}
