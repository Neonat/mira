"""Auditor-facing outcome and source detail, from saved/frozen assessments only."""
from html import escape
from datetime import datetime, timezone
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


def _checked_time(raw):
    try:
        return datetime.fromisoformat(str(raw).replace("Z","+00:00")).astimezone(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    except (ValueError,TypeError):
        return "date unknown"


def provenance_html(passage):
    provenance=passage.get("acquisition_provenance") or {}
    if not provenance:
        return ""
    items={"Acquisition method":provenance.get("acquisition_method"),
           "Acquired at":provenance.get("acquired_at"),"Capture SHA-256":provenance.get("capture_sha256"),
           "Original capture SHA-256":provenance.get("original_capture_sha256"),
           "Extraction SHA-256":provenance.get("extraction_sha256"),
           "Original retained":provenance.get("original_retained")}
    browser=provenance.get('browser_context')
    import json
    context=('<dt>Browser context</dt><dd><pre style="white-space:pre-wrap;overflow-wrap:anywhere">'+escape(json.dumps(browser,ensure_ascii=False,indent=2))+'</pre></dd>') if browser else ''
    return '<details><summary>Capture and extraction provenance</summary><dl>'+''.join(
        f'<dt>{escape(key)}</dt><dd>{escape(str(value) if value is not None else "unknown")}</dd>'
        for key,value in items.items())+context+'</dl></details>'


def assessment_html(envelope, *, title=None):
    """Escape all source data; display support/origin decisions separately."""
    result = envelope.get('assessment',{})
    status = LABELS.get(result.get('status'),'Not checked')
    parts = ['<style>.corroboration {font-family:system-ui,sans-serif;overflow-wrap:anywhere;line-height:1.55}.corroboration p {text-align:left;hyphens:none}.corroboration dd {margin:0 0 .6rem;font-size:.85em}</style>', f'<div class="corroboration"><h3>{escape(title or "Corroboration")}</h3>',
             f'<p><strong>{status}</strong> · {escape(_checked_time(result.get("checked_at")))}</p>']
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
        parts.append(provenance_html(passage))
    limits=result.get('limits',{})
    if limits:
        parts.append(f'<p>Search allowance: {limits.get("max_queries",0)} queries, '
                     f'{limits.get("max_documents",0)} documents, {limits.get("max_passages",0)} passages, '
                     f'{limits.get("max_seconds",0):g} seconds.</p>')
    stops = result.get('stop_reasons',[])
    if stops:
        parts.append(f'<p>Search limits and outcome: {escape(", ".join(str(s).replace("_", " ") for s in stops))}. '
                     f'Queries: {result.get("queries_used",0)}; document attempts: {result.get("document_attempts",0)}.</p>')
    parts.append('</div>')
    return '\n'.join(parts)
