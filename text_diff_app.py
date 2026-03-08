import streamlit as st
import difflib
import json
import csv
import io
import xml.etree.ElementTree as ET
import pdfplumber


st.set_page_config(page_title="Text Diff Tool", page_icon="🔍", layout="wide")

# --- Styles ---
st.markdown(
    """
    <style>
    .diff-add { background-color: #ccffd8; padding: 2px 4px; }
    .diff-del { background-color: #ffd7d5; padding: 2px 4px; text-decoration: line-through; }
    .diff-container {
        font-family: 'Courier New', monospace;
        font-size: 14px;
        line-height: 1.6;
        white-space: pre-wrap;
        word-wrap: break-word;
        border: 1px solid #ddd;
        border-radius: 8px;
        padding: 16px;
        max-height: 600px;
        overflow-y: auto;
    }
    .stats-box {
        padding: 12px 16px;
        border-radius: 8px;
        background: #f0f2f6;
        margin-bottom: 8px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🔍 Text Diff Tool")

SUPPORTED_EXTENSIONS = ["txt", "csv", "json", "xml", "po", "xliff", "xlf", "md", "yaml", "yml", "properties", "strings", "resx", "ts", "js", "html", "htm", "pdf"]

ext_display = ", ".join(f"`.{e}`" for e in SUPPORTED_EXTENSIONS)
st.caption(f"Compare two texts and spot the differences — optimized for localization workflows.  \nSupported formats: {ext_display}")


def extract_text(uploaded_file) -> str:
    """Extract text content from an uploaded file."""
    if uploaded_file is None:
        return ""
    name = uploaded_file.name.lower()

    # Handle PDF files
    if name.endswith(".pdf"):
        pages = []
        with pdfplumber.open(uploaded_file) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages.append(text)
        return "\n".join(pages)

    raw = uploaded_file.read()

    # Try UTF-8 first, then fall back to other encodings
    for encoding in ["utf-8", "utf-8-sig", "utf-16", "cp949", "euc-kr", "latin-1"]:
        try:
            text = raw.decode(encoding)
            return text
        except (UnicodeDecodeError, Exception):
            continue
    return raw.decode("utf-8", errors="replace")


def compute_diff_stats(text_a: str, text_b: str) -> dict:
    """Compute basic diff statistics."""
    lines_a = text_a.splitlines()
    lines_b = text_b.splitlines()
    matcher = difflib.SequenceMatcher(None, lines_a, lines_b)
    added = 0
    removed = 0
    changed = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "insert":
            added += j2 - j1
        elif tag == "delete":
            removed += i2 - i1
        elif tag == "replace":
            changed += max(i2 - i1, j2 - j1)
    unchanged = len(lines_a) - removed - changed
    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "unchanged": max(0, unchanged),
        "lines_a": len(lines_a),
        "lines_b": len(lines_b),
    }


def render_inline_diff(text_a: str, text_b: str) -> str:
    """Render an inline word-level diff as HTML."""
    lines_a = text_a.splitlines()
    lines_b = text_b.splitlines()
    matcher = difflib.SequenceMatcher(None, lines_a, lines_b)
    html_parts = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for line in lines_a[i1:i2]:
                html_parts.append(f"  {_escape(line)}")
        elif tag == "replace":
            for idx in range(max(i2 - i1, j2 - j1)):
                old_line = lines_a[i1 + idx] if i1 + idx < i2 else ""
                new_line = lines_b[j1 + idx] if j1 + idx < j2 else ""
                html_parts.append(_word_diff(old_line, new_line))
        elif tag == "delete":
            for line in lines_a[i1:i2]:
                html_parts.append(f'<span class="diff-del">- {_escape(line)}</span>')
        elif tag == "insert":
            for line in lines_b[j1:j2]:
                html_parts.append(f'<span class="diff-add">+ {_escape(line)}</span>')

    return "\n".join(html_parts)


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _word_diff(old_line: str, new_line: str) -> str:
    """Generate a word-level diff between two lines."""
    old_words = old_line.split()
    new_words = new_line.split()
    sm = difflib.SequenceMatcher(None, old_words, new_words)
    parts = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            parts.append(_escape(" ".join(old_words[i1:i2])))
        elif tag == "replace":
            parts.append(f'<span class="diff-del">{_escape(" ".join(old_words[i1:i2]))}</span>')
            parts.append(f'<span class="diff-add">{_escape(" ".join(new_words[j1:j2]))}</span>')
        elif tag == "delete":
            parts.append(f'<span class="diff-del">{_escape(" ".join(old_words[i1:i2]))}</span>')
        elif tag == "insert":
            parts.append(f'<span class="diff-add">{_escape(" ".join(new_words[j1:j2]))}</span>')
    return "~ " + " ".join(parts)


# ─── Input Mode ───
tab_paste, tab_file = st.tabs(["📋 Paste Text", "📁 Upload Files"])

text_a = ""
text_b = ""

with tab_paste:
    col1, col2 = st.columns(2)
    with col1:
        text_a_input = st.text_area("Original (Source)", height=250, placeholder="Paste original text here...")
    with col2:
        text_b_input = st.text_area("Modified (Target)", height=250, placeholder="Paste modified text here...")
    if text_a_input or text_b_input:
        text_a = text_a_input
        text_b = text_b_input

with tab_file:
    col1, col2 = st.columns(2)
    with col1:
        file_a = st.file_uploader("Original File (Source)", type=SUPPORTED_EXTENSIONS, key="file_a")
    with col2:
        file_b = st.file_uploader("Modified File (Target)", type=SUPPORTED_EXTENSIONS, key="file_b")
    if file_a or file_b:
        text_a = extract_text(file_a) if file_a else ""
        text_b = extract_text(file_b) if file_b else ""

# ─── Options ───
with st.expander("⚙️ Comparison Options"):
    col_opt1, col_opt2 = st.columns(2)
    with col_opt1:
        ignore_whitespace = st.checkbox("Ignore whitespace differences", value=False)
        ignore_case = st.checkbox("Ignore case", value=False)
    with col_opt2:
        context_lines = st.slider("Context lines (unified diff)", 0, 10, 3)

if ignore_whitespace:
    import re
    text_a = re.sub(r"[ \t]+", " ", text_a)
    text_b = re.sub(r"[ \t]+", " ", text_b)
    text_a = "\n".join(line.strip() for line in text_a.splitlines())
    text_b = "\n".join(line.strip() for line in text_b.splitlines())

if ignore_case:
    text_a = text_a.lower()
    text_b = text_b.lower()

# ─── Diff Output ───
if text_a or text_b:
    if text_a == text_b:
        st.success("✅ The two texts are identical!")
    else:
        stats = compute_diff_stats(text_a, text_b)

        # Stats row
        st.markdown("### 📊 Comparison Results")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Added", f"+{stats['added']}")
        c2.metric("Removed", f"-{stats['removed']}")
        c3.metric("Changed", f"~{stats['changed']}")
        c4.metric("Unchanged", stats["unchanged"])

        # Diff views
        view_tab1, view_tab2, view_tab3 = st.tabs(["Inline Diff", "Side-by-Side", "Unified Diff"])

        with view_tab1:
            html = render_inline_diff(text_a, text_b)
            st.markdown(f'<div class="diff-container">{html}</div>', unsafe_allow_html=True)

        with view_tab2:
            lines_a = text_a.splitlines()
            lines_b = text_b.splitlines()
            differ = difflib.HtmlDiff(wrapcolumn=80)
            table_html = differ.make_table(
                lines_a, lines_b,
                fromdesc="Original (Source)", todesc="Modified (Target)",
                context=True, numlines=context_lines,
            )
            # Make the table wider and more readable
            table_html = table_html.replace(
                '<table class="diff"',
                '<table class="diff" style="width:100%; font-size:13px;"',
            )
            st.markdown(table_html, unsafe_allow_html=True)

        with view_tab3:
            unified = difflib.unified_diff(
                text_a.splitlines(keepends=True),
                text_b.splitlines(keepends=True),
                fromfile="Original (Source)",
                tofile="Modified (Target)",
                n=context_lines,
            )
            unified_text = "".join(unified)
            if unified_text:
                st.code(unified_text, language="diff")
            else:
                st.info("No differences found")

        # Download diff report
        st.markdown("---")
        unified_for_download = difflib.unified_diff(
            text_a.splitlines(keepends=True),
            text_b.splitlines(keepends=True),
            fromfile="source",
            tofile="target",
            n=context_lines,
        )
        diff_text = "".join(unified_for_download)
        st.download_button(
            "📥 Download Diff (.diff)",
            data=diff_text,
            file_name="diff_report.diff",
            mime="text/plain",
        )
else:
    st.info("Paste text or upload files to compare.")
