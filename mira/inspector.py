"""Local sources inspection screen. Run with streamlit run app.py."""
import json
import os
from pathlib import Path

import streamlit as st

from mira.batch import create_run, run_batch, load_bundle

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get('MIRA_DATA_DIR', ROOT / 'data' / 'ingestion')).resolve()


def read_runs():
    runs, errors = [], []
    for path in sorted((DATA / 'runs').glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            run = json.loads(path.read_text())
            if not isinstance(run.get('items'), list) or not run.get('run_id'):
                raise ValueError('Missing run fields')
            runs.append(run)
        except (ValueError, OSError) as error:
            errors.append(f'{path.name}: {error}')
    return runs, errors


def main():
    st.set_page_config(page_title='Mira · Sources', layout='wide', initial_sidebar_state='auto')
    st.markdown('''<style>
    .block-container {max-width:1200px;padding-top:2.5rem;}
    h1 {letter-spacing:-0.04em;} h2 {letter-spacing:-0.02em;}
    [data-testid="stMetricValue"] {font-variant-numeric:tabular-nums;font-size:1.8rem;}
    [data-testid="stSidebar"] {border-right:1px solid #d7e1dc;}
    button:focus-visible, a:focus-visible {outline:3px solid #125c58;outline-offset:3px;}
    @media (max-width:640px) {
      [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) {display:grid;grid-template-columns:1fr 1fr;gap:1rem;}
      [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) > [data-testid="stColumn"] {width:100%;min-width:0;}
    }
    </style>''', unsafe_allow_html=True)
    with st.sidebar:
        st.title('Mira')
        st.caption('EVIDENCE WORKSPACE')
        st.divider()
        st.subheader('Sources & ingestion')
        st.caption('Local staging · Not synced to Supabase')
        if st.button('Load synthetic demo', width='stretch'):
            with st.spinner('Extracting demo sources…'):
                try:
                    run = create_run(ROOT / 'tests/fixtures/batch.json', DATA)
                    run_batch(DATA, run['run_id'])
                    st.session_state['selected_run'] = run['run_id']
                except (OSError, ValueError) as error:
                    st.error(str(error))
        st.caption('Demo includes HTML, a two-page PDF and a scan requiring OCR. All content is invented.')
        if st.button('Refresh runs', width='stretch'):
            st.rerun()
    st.caption('COLLECT  /  INSPECT  /  HAND OFF')
    st.title('Source inspection')
    st.write('Inspect saved passages and resolve extraction gaps before using evidence.')
    runs, errors = read_runs()
    for error in errors:
        st.error(f'Unreadable run: {error}')
    if not runs:
        st.info('No ingestion runs yet. Load the synthetic demo, or start a batch from the command line.')
        with st.expander('Start a batch'):
            st.code('python -m mira.batch start tests/fixtures/batch.json', language='bash')
        return
    choices = {r['run_id']: r for r in runs}
    selected = st.session_state.get('selected_run')
    ids = list(choices)
    run_id = st.selectbox('Ingestion run', ids, index=ids.index(selected) if selected in ids else 0,
                          format_func=lambda rid: f"{choices[rid]['created_at'][:16].replace('T', ' ')} UTC · {rid[:8]} · {choices[rid]['status'].replace('_', ' ')}")
    st.session_state['selected_run'] = run_id
    run = choices[run_id]
    saved = sum(i['status'] in ('saved', 'unchanged') for i in run['items'])
    failed = sum(i['status'] == 'failed' for i in run['items'])
    pending = len(run['items']) - saved - failed
    for col, label, value in zip(st.columns(4), ['Sources', 'Saved', 'Failed', 'Pending'], [len(run['items']), saved, failed, pending]):
        col.metric(label, value)
    st.caption('Saved counts extraction outputs, not verified facts or complete source coverage.')
    if failed or pending:
        if st.button('Resume / retry failed items', type='primary'):
            with st.spinner('Processing remaining sources…'):
                try:
                    run_batch(DATA, run_id, retry_failed=True)
                except (OSError, ValueError) as error:
                    st.error(str(error))
                else:
                    st.rerun()
    st.divider()
    filter_status = st.radio('Show sources', ['All', 'Saved', 'Needs attention'], horizontal=True)
    items = [i for i in run['items'] if filter_status == 'All'
             or (filter_status == 'Saved' and i['status'] in ('saved', 'unchanged'))
             or (filter_status == 'Needs attention' and (i['status'] not in ('saved', 'unchanged')
                                                        or i.get('extraction_status') == 'partial'))]
    if not items:
        st.info('No sources match this filter.')
        return
    item = st.selectbox('Source', items, format_func=lambda i: f"{i['input']['id']} · {i['input']['kind'].upper()} · {i['status'].replace('_', ' ')}")
    source = item['input']
    if source.get('origin') == 'fixture':
        st.warning('Synthetic test content — not regulatory evidence.')
    st.caption(f"{len(item['attempts'])} attempt(s) · {source.get('origin', 'unknown')} input")
    if item.get('error'):
        st.error(item['error'])
    if item['status'] not in ('saved', 'unchanged'):
        st.info('No usable evidence is available for this item. Supply a readable source or retry after resolving the error.')
        with st.expander('Attempt history'):
            st.json(item['attempts'])
        return
    try:
        bundle = load_bundle(DATA, item)
    except (ValueError, OSError) as error:
        st.error(str(error))
        return
    version = bundle['document_version']
    metadata = version['metadata']
    st.text(version['title'])
    st.text(version['source_url'])
    for col, label, value in zip(st.columns(3), ['Extraction', 'Pages', 'Passages'],
                                 [version['extraction_status'].capitalize(), metadata.get('page_count', 'HTML'), len(bundle['passages'])]):
        col.metric(label, value)
    if metadata.get('extraction_warning'):
        st.info(metadata['extraction_warning'])
    st.caption('Publication: ' + (version.get('published_at') or 'Unknown') + ' · Observed: ' + version['retrieved_at'])
    tabs = st.tabs(['Passages', 'Extracted text', 'Source details'])
    with tabs[0]:
        query = st.text_input('Find in passages', placeholder='Search extracted wording')
        pages = sorted({p.get('page_number') for p in bundle['passages'] if p.get('page_number')})
        page_filter = st.selectbox('Page', ['All pages'] + pages) if pages else 'All pages'
        matches = [p for p in bundle['passages'] if query.casefold() in p['content'].casefold()
                   and (page_filter == 'All pages' or p.get('page_number') == page_filter)]
        if not matches:
            st.info('No passages match. Try another term or page.')
        for passage in matches:
            with st.container(border=True):
                st.caption(f"PASSAGE {passage['passage_number']:03d} · "
                           f"{('PAGE ' + str(passage['page_number'])) if passage.get('page_number') else 'HTML'} · "
                           f"CHARACTERS {passage['char_start']}–{passage['char_end']}")
                # Source text is always rendered literally, never as HTML/Markdown.
                st.text(passage['content'])
    with tabs[1]:
        st.text_area('Saved extraction', version['extracted_text'], height=400, disabled=True)
    with tabs[2]:
        if metadata.get('date_warning'):
            st.warning(metadata['date_warning'])
        st.caption('Extracted content SHA-256')
        st.code(version['content_sha256'], language=None)
        st.caption('Extraction version')
        st.text(version['extraction_version'])
        if bundle.get('pages'):
            st.markdown('| Page | Extraction |\n|---|---|\n' + '\n'.join(
                f"| {page['page_number']} | {page['status'].replace('_', ' ')} |"
                for page in bundle['pages']))
        with st.expander('Attempt history'):
            st.json(item['attempts'])
        st.download_button('Download evidence JSON', json.dumps(bundle, indent=2, ensure_ascii=False),
                           file_name=item['bundle'], mime='application/json')


if __name__ == '__main__':
    main()
