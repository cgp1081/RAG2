import React from "react";
import { type Citation, getApiBaseUrl } from "../lib/api";

export type CitationListProps = {
  citations: Citation[];
  tenantId: string;
};

const CitationList: React.FC<CitationListProps> = ({ citations, tenantId }) => {
  if (!citations || citations.length === 0) {
    return <p className="citations-empty">No supporting documents were cited for this answer.</p>;
  }

  const baseUrl = getApiBaseUrl();

  return (
    <ol className="citations">
      {citations.map((citation) => {
        const title = citation.title?.trim() || citation.document_id;
        const url = `${baseUrl}/admin/documents?tenant=${encodeURIComponent(tenantId)}&highlight=${encodeURIComponent(
          citation.document_id
        )}`;
        const percentage = Math.round(citation.normalized_score * 100);
        return (
          <li key={citation.chunk_id} className="citation-item">
            <div className="citation-header">
              <span className="citation-title">{title}</span>
              <span className="citation-score">{percentage}% match</span>
            </div>
            <p className="citation-snippet">{citation.snippet}</p>
            <a className="citation-link" href={url} target="_blank" rel="noreferrer">
              View document
            </a>
          </li>
        );
      })}
    </ol>
  );
};

export default CitationList;
