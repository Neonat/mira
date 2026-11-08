"""Auditor-facing outcome and source detail, from saved/frozen assessments only."""
from html import escape
from urllib.parse import urlsplit

LABELS = {
    'independently_corroborated':'Independently corroborated',
    'primary_source_only':'Primary-source only',
    'conflicting_evidence':'Conflicting evidence',
    'not_checked':'Not checked',
    'inconclusive':'Inconclusive',
}


def _link(url, text):
    if urlsplit(url).scheme in {'http','https'}:
        return f'<a href="{escape(url,quote=True)}" target="_blank" rel="noopener noreferrer">{escape(text)}</a>'
    return escape(text)


def assessment_html(envelope, *, title=None):
    """Escape all source data; display support/origin decisions separately."""
    result = envelope.get('assessment',{})
    status = LABELS.get(result.get('status'),'Not checked')
    parts = [f'<div class="corroboration"><h3>{escape(title or "Corroboration")}</h3>',
             f'<p><strong>{status}</strong> · {escape(str(result.get("checked_at") or "date unknown"))}</p>']
    reasons = result.get('reasons') or ([result['reason']] if result.get('reason') else [])
    for reason in reasons:
        parts.append(f'<p>{escape(str(reason))}</p>')
    primary = result.get('base_evidence_input',{}).get('passages',{})
    passages = dict(primary)
    for candidate in result.get('candidates',[]):
        passage = candidate.get('passage',{})
        passages[str(passage.get('id'))] = passage
    for decision in result.get('decisions',[]):
        passage = passages.get(str(decision.get('passage_id')), {})
        published = passage.get('published_at') or 'publication date unknown'
        parts += [f'<h4>{_link(passage.get("source_url", ""), passage.get("title") or "Saved source")}</h4>',
                  f'<p>{escape(str(passage.get("source_name", "Source")))} · {escape(str(published))} · '
                  f'Document version {escape(str(passage.get("document_version_id", "unknown")))}</p>',
                  f'<blockquote>{escape(str(decision.get("quote", "")))}</blockquote>',
                  f'<p>Proposition: {escape(str(decision.get("relation", "uncertain")))} · '
                  f'Origin: {escape(str(decision.get("origin_relation", "unknown")))}. '
                  f'{escape(str(decision.get("reason", "")))}</p>']
        for origin in decision.get('origin_evidence',[]):
            source = passages.get(str(origin.get('passage_id')), {})
            parts.append(f'<p>Origin evidence: {_link(source.get("source_url", ""), source.get("title") or "Saved passage")} · '
                         f'{escape(str(origin.get("reason", "")))}</p>'
                         f'<blockquote>{escape(str(origin.get("quote", "")))}</blockquote>')
    stops = result.get('stop_reasons',[])
    if stops:
        parts.append(f'<p>Search limits and outcome: {escape(", ".join(str(s).replace("_", " ") for s in stops))}. '
                     f'Queries: {result.get("queries_used",0)}; document attempts: {result.get("document_attempts",0)}.</p>')
    parts.append('</div>')
    return '\n'.join(parts)
