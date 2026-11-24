import { useMutation } from "@tanstack/react-query";
import { Calculator, Landmark, Layers3 } from "lucide-react";
import { number, post, type DCFResult } from "./data";
import { Heading, Section, Stat } from "./ui";

const fields = [
  ["fcff", "Dòng tiền tự do năm cơ sở (FCFF)", "", "0.01"],
  ["shares", "Số cổ phiếu", "", "0.01"],
  ["net_debt", "Nợ ròng", "0", undefined],
  ["growth", "Tăng trưởng FCFF (%)", "5", "-99.99"],
  ["discount", "Chi phí vốn bình quân (WACC, %)", "10", "0.01"],
  ["terminal_growth", "Tăng trưởng dài hạn (%)", "2", "-99.99"],
  ["years", "Số năm dự phóng", "5", "1"],
] as const;
export default function Valuation() {
  const dcf = useMutation({
    mutationFn: (request: Record<string, number>) =>
      post<DCFResult>("/valuation/dcf", request),
  });
  return (
    <>
      <Heading
        title="Định giá DCF"
        detail="Tính giá trị theo giả định dòng tiền chiết khấu."
      />
      <div className="dashboard-grid">
        <section className="panel">
          <Section
            title="Giả định đầu vào"
            detail="Dùng cùng một đơn vị tiền tệ. Tỷ lệ nhập theo phần trăm."
          />
          <form
            className="research-form"
            onSubmit={(event) => {
              event.preventDefault();
              const values = new FormData(event.currentTarget);
              dcf.mutate(
                Object.fromEntries(
                  fields.map(([key]) => [
                    key,
                    Number(values.get(key)) /
                      (["growth", "discount", "terminal_growth"].includes(key)
                        ? 100
                        : 1),
                  ]),
                ),
              );
            }}
          >
            <div className="filter-row">
              {fields.map(([key, label, value, min]) => (
                <label key={key}>
                  {label}
                  <input
                    type="number"
                    name={key}
                    required
                    defaultValue={value}
                    min={min}
                    max={key === "years" ? 15 : undefined}
                    step={key === "years" ? 1 : "any"}
                  />
                </label>
              ))}
            </div>
            <button className="button primary" disabled={dcf.isPending}>
              <Calculator size={16} />{" "}
              {dcf.isPending ? "Đang tính…" : "Tính định giá"}
            </button>
            {dcf.isError && (
              <p className="error-text" role="alert">
                {dcf.error.message}
              </p>
            )}
          </form>
        </section>
        <section className="panel">
          <Section title="Đọc kết quả" />
          <p>
            Thay đổi WACC hoặc tăng trưởng dài hạn để xem giá trị biến động thế
            nào. Kết quả phụ thuộc vào giả định đầu vào.
          </p>
        </section>
      </div>
      {dcf.data && (
        <>
          <div className="stats three">
            <Stat
              label="Giá trị mỗi cổ phiếu"
              value={number(dcf.data.base.per_share)}
              icon={<Calculator size={18} />}
            />
            <Stat
              label="Giá trị doanh nghiệp"
              value={number(dcf.data.base.enterprise_value)}
              icon={<Landmark size={18} />}
            />
            <Stat
              label="Giá trị vốn chủ sở hữu"
              value={number(dcf.data.base.equity_value)}
              icon={<Layers3 size={18} />}
            />
          </div>
          <section className="panel">
            <Section title="Phân tích độ nhạy" />
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>WACC</th>
                    <th>Tăng trưởng dài hạn</th>
                    <th>Giá trị mỗi cổ phiếu</th>
                  </tr>
                </thead>
                <tbody>
                  {dcf.data.sensitivity.map((row, index) => (
                    <tr key={index}>
                      <td>{number(row.discount * 100)}%</td>
                      <td>{number(row.terminal_growth * 100)}%</td>
                      <td>
                        {row.valuation
                          ? number(row.valuation.per_share)
                          : "Không hợp lệ"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </>
  );
}
