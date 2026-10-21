"""Local source intake, queue and evidence inspection."""
import json
import os
from pathlib import Path
import streamlit as st
from mira.batch import create_run
from mira.workbench import create_intake, submit_run, job_state, read_runs, library_entries, original_bytes

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get('MIRA_DATA_DIR', ROOT / 'data/ingestion')).resolve()


def navigate(page, document=None):
    st.session_state['destination'] = page
    st.session_state['document'] = document
    st.rerun(scope='app')


def detail(entry):
    if st.button('← Back to library'):
        navigate('Library')
    bundle = entry['bundle']
    version = bundle['document_version']
    metadata = version['metadata']
    st.text(version['title'])
    st.text(version['source_url'])
    if entry['item']['input'].get('origin') == 'fixture':
        st.warning('Synthetic test content — not regulatory evidence.')
    st.caption(f"{version['extraction_status'].capitalize()} extraction · {len(bundle['passages'])} passages · Publication: {version.get('published_at') or 'Unknown'}")
    if metadata.get('extraction_warning'):
        st.info(metadata['extraction_warning'])
    left, right = st.columns(2, gap='large')
    with left:
        st.subheader('Original source')
        try:
            data = original_bytes(DATA, bundle)
            if metadata.get('raw_pdf_sha256'):
                st.pdf(data, height=650, key=entry['key'], alt='Original source PDF')
                st.download_button('Download original PDF', data, file_name='source.pdf', mime='application/pdf')
            else:
                st.caption('HTML is shown as source code for safe inspection.')
                st.code(data.decode('utf8', errors='replace'), language='html', height=650)
        except (OSError, ValueError) as error:
            st.error(str(error))
    with right:
        st.subheader('Extracted passages')
        query = st.text_input('Find in passages', placeholder='Search exact wording')
        pages = sorted({p['page_number'] for p in bundle['passages'] if p.get('page_number')})
        page = st.selectbox('Page', ['All pages'] + pages) if pages else 'All pages'
        st.caption('Page filters refer to physical PDF pages. The original viewer scrolls independently.')
        matches = [p for p in bundle['passages'] if query.casefold() in p['content'].casefold() and (page == 'All pages' or p.get('page_number') == page)]
        if not matches:
            st.info('No passages match. Try another term or page.')
        with st.container(height=530):
            for passage in matches:
                with st.container(border=True):
                    st.caption(f"PASSAGE {passage['passage_number']:03d} · PAGE {passage.get('page_number') or 'HTML'} · CHARACTERS {passage['char_start']}–{passage['char_end']}")
                    st.text(passage['content'])
    with st.expander('Evidence details & export'):
        st.caption('Observed: ' + version['retrieved_at'])
        st.text(metadata.get('date_warning', 'Publication dates are retained only when explicitly supplied by the source.'))
        st.code(version['content_sha256'], language=None)
        st.text(version['extraction_version'])
        st.download_button('Download evidence JSON', json.dumps(bundle, indent=2, ensure_ascii=False), file_name=entry['key'], mime='application/json')


def library(runs):
    entries, errors = library_entries(DATA, runs)
    for error in errors:
        st.error(error)
    selected = st.session_state.get('document')
    if selected:
        entry = next((e for e in entries if e['key'] == selected), None)
        if entry:
            detail(entry)
            return
    st.title('Source library')
    st.write('Find a source, inspect its original, and trace every extracted passage.')
    cols = st.columns(3)
    cols[0].metric('Saved versions', len(entries))
    cols[1].metric('Need review', sum(e['bundle']['document_version']['extraction_status'] != 'complete' for e in entries))
    cols[2].metric('Failed inputs', sum(i['status'] == 'failed' for r in runs for i in r['items']))
    query = st.text_input('Search library', placeholder='Title, source URL, or extracted wording')
    kind = st.radio('Document type', ['All', 'PDF', 'HTML'], horizontal=True)
    if not entries:
        st.info('Your library is empty. Add sources or load the synthetic demo to explore the workflow.')
    count = 0
    for entry in entries:
        version = entry['bundle']['document_version']
        pdf = bool(version['metadata'].get('raw_pdf_sha256'))
        if kind != 'All' and kind != ('PDF' if pdf else 'HTML'):
            continue
        if query.casefold() not in ' '.join([version['title'], version['source_url'], version['extracted_text']]).casefold():
            continue
        count += 1
        with st.container(border=True):
            main, action = st.columns([5, 1])
            main.text(version['title'])
            main.caption(f"{'PDF' if pdf else 'HTML'} · {version['extraction_status']} · {len(entry['bundle']['passages'])} passages · {version.get('published_at') or 'Publication unknown'}")
            main.text(version['source_url'])
            if entry['item']['input'].get('origin') == 'fixture':
                main.caption('SYNTHETIC DEMO')
            if action.button('Open', key='open_' + entry['key'], width='stretch'):
                navigate('Library', entry['key'])
    if entries and not count:
        st.info('No documents match your search.')


def intake():
    st.title('Add sources')
    st.write('Stage public or licensed MAS documents for extraction and review.')
    st.caption('Supported domains: mas.gov.sg and www.mas.gov.sg. Upload PDFs up to 10 MB; URL downloads up to 2 MB. Scans require OCR before ingestion.')
    mode = st.radio('Source input', ['Upload PDFs', 'Paste URLs'], horizontal=True)
    uploads = []
    urls = []
    if mode == 'Upload PDFs':
        files = st.file_uploader('Choose PDF documents', type=['pdf'], accept_multiple_files=True)
        for index, file in enumerate(files):
            st.text(file.name)
            url = st.text_input('Original MAS source URL', key=f'url_{index}_{file.name}', placeholder='https://www.mas.gov.sg/…')
            uploads.append({'name': file.name, 'data': file.getvalue(), 'url': url})
    else:
        urls = [line.strip() for line in st.text_area('Source URLs, one per line', height=180).splitlines() if line.strip()]
    approved = st.checkbox('I have confirmed these sources are public or licensed for this use.')
    if st.button('Start extraction', type='primary'):
        if not approved:
            st.error('Confirm source permissions before starting extraction.')
            return
        try:
            run = create_intake(DATA, uploads=uploads, urls=urls)
            submit_run(DATA, run['run_id'])
            st.session_state['selected_run'] = run['run_id']
            navigate('Ingestion queue')
        except (OSError, ValueError) as error:
            st.error(str(error))


@st.fragment(run_every='1s')
def queue():
    st.title('Ingestion queue')
    st.write('Progress is saved after each item. You can leave this screen while extraction runs.')
    runs, errors = read_runs(DATA)
    for error in errors:
        st.error(error)
    if not runs:
        st.info('No ingestion runs yet. Add sources to start.')
        return
    ids = [r['run_id'] for r in runs]
    selected = st.session_state.get('selected_run')
    rid = st.selectbox('Submission', ids, index=ids.index(selected) if selected in ids else 0, format_func=lambda v: next(r['created_at'][:19].replace('T', ' ') + ' UTC · ' + v[:8] for r in runs if r['run_id'] == v))
    run = next(r for r in runs if r['run_id'] == rid)
    state, error = job_state(DATA, rid)
    active = state in ('queued', 'running')
    done = sum(i['status'] in ('saved', 'unchanged', 'failed') for i in run['items'])
    st.progress(done / len(run['items']), text=f"{done} of {len(run['items'])} processed · {state if active else run['status'].replace('_', ' ')}")
    if error:
        st.error(error)
    if not active and any(i['status'] not in ('saved', 'unchanged') for i in run['items']):
        if st.button('Resume / retry remaining items'):
            submit_run(DATA, rid)
            st.rerun(scope='fragment')
    for item in run['items']:
        with st.container(border=True):
            st.text(item['input']['url'])
            st.caption(f"{item['input']['kind'].upper()} · {item['status'].upper()} · {len(item['attempts'])} attempt(s)")
            if item.get('error'):
                st.error(item['error'])
            if item['status'] in ('saved', 'unchanged'):
                if st.button('Inspect document', key='inspect_' + item['input']['id']):
                    navigate('Library', item['bundle'])
            elif st.button('Retry this item', key='retry_' + item['input']['id'], disabled=active):
                submit_run(DATA, rid, item_ids=[item['input']['id']])
                st.rerun(scope='fragment')
            with st.expander('Attempt history'):
                st.json(item['attempts'])


def main():
    st.set_page_config(page_title='Mira · Sources', layout='wide')
    st.markdown('''<style>.block-container {max-width:1320px;padding-top:2.5rem;} h1 {letter-spacing:-.04em;} [data-testid="stSidebar"] {border-right:1px solid #d7e1dc;} button:focus-visible,a:focus-visible {outline:3px solid #125c58;outline-offset:3px;}</style>''', unsafe_allow_html=True)
    if 'destination' in st.session_state:
        st.session_state['navigation'] = st.session_state.pop('destination')
    with st.sidebar:
        st.title('Mira')
        st.caption('EVIDENCE WORKSPACE')
        page = st.radio('Workspace', ['Library', 'Add sources', 'Ingestion queue'], key='navigation')
        st.divider()
        st.caption('Local staging · Not synced to Supabase')
        with st.expander('Try the workflow'):
            st.caption('Invented HTML, PDF and a scan requiring OCR.')
            if st.button('Load synthetic demo'):
                run = create_run(ROOT / 'tests/fixtures/batch.json', DATA)
                submit_run(DATA, run['run_id'])
                st.session_state['selected_run'] = run['run_id']
                navigate('Ingestion queue')
    if page == 'Add sources':
        intake()
    elif page == 'Ingestion queue':
        queue()
    else:
        runs, errors = read_runs(DATA)
        for error in errors:
            st.error(error)
        library(runs)


if __name__ == '__main__':
    main()
