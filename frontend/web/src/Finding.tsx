import {
  claimVerificationLabel,
  dimensions,
  roles,
  type Claim,
} from "./data";
import { EvidenceButton, type Selection } from "./Evidence";
import { Badge } from "./ui";

export function ClaimCard({
  claim,
  open,
}: {
  claim: Claim;
  open: (selection: Selection) => void;
}) {
  const ids = [...new Set([...claim.evidence_ids, ...claim.counter_ids])];
  return (
    <article className="finding">
      <div className="finding-meta">
        <span>
          {dimensions[claim.claim.dimension] ?? claim.claim.dimension} ·{" "}
          {roles[claim.role] ?? claim.role}
        </span>
        <Badge
          status={claim.status}
          claim
          label={claimVerificationLabel(claim)}
        />
      </div>
      <p>{claim.claim.text}</p>
      <p className="muted">Cơ sở đánh giá: {claim.reason}</p>
      <div className="finding-actions">
        <EvidenceButton onClick={() => open({ claim })}>
          {ids.length
            ? "Xem bằng chứng (" + ids.length + ")"
            : "Xem tình trạng bằng chứng"}
        </EvidenceButton>
        {ids.map((id, index) => (
          <button
            className="citation"
            title={id}
            key={id}
            onClick={() => open({ claim, only: id })}
          >
            Nguồn {index + 1}
          </button>
        ))}
      </div>
    </article>
  );
}
