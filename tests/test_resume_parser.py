"""Tests for resume_parser.py — resume text extraction and Ollama parsing."""

import io
import json
from unittest.mock import MagicMock, patch

import pytest
import requests
import responses

import resume_parser
from resume_parser import extract_text, parse_resume, parse_resume_text

OLLAMA_URL = resume_parser.OLLAMA_URL


# --- extract_text ---


def test_extract_pdf():
    """PDF bytes → text extraction."""
    mock_page = MagicMock()
    mock_page.extract_text.return_value = "Resume content from PDF"
    mock_pdf = MagicMock()
    mock_pdf.pages = [mock_page]
    mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
    mock_pdf.__exit__ = MagicMock(return_value=False)

    with patch.dict("sys.modules", {"pdfplumber": MagicMock()}) as mock_modules:
        import sys
        sys.modules["pdfplumber"].open.return_value = mock_pdf
        # Need to reimport to pick up the mock
        result = extract_text(b"fake pdf bytes", "resume.pdf")

    assert "Resume content from PDF" in result


def test_extract_docx():
    """DOCX bytes → text extraction."""
    mock_para = MagicMock()
    mock_para.text = "Resume content from DOCX"
    mock_doc = MagicMock()
    mock_doc.paragraphs = [mock_para]
    mock_doc.tables = []

    with patch.dict("sys.modules", {"docx": MagicMock()}) as mock_modules:
        import sys
        sys.modules["docx"].Document.return_value = mock_doc
        result = extract_text(b"fake docx bytes", "resume.docx")

    assert "Resume content from DOCX" in result


def test_extract_unsupported_extension():
    """.txt raises ValueError."""
    with pytest.raises(ValueError, match="Unsupported file type"):
        extract_text(b"plain text", "resume.txt")


def test_extract_empty_pdf():
    """PDF with no text raises ValueError."""
    mock_page = MagicMock()
    mock_page.extract_text.return_value = ""
    mock_pdf = MagicMock()
    mock_pdf.pages = [mock_page]
    mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
    mock_pdf.__exit__ = MagicMock(return_value=False)

    with patch.dict("sys.modules", {"pdfplumber": MagicMock()}) as mock_modules:
        import sys
        sys.modules["pdfplumber"].open.return_value = mock_pdf
        with pytest.raises(ValueError, match="Could not extract text"):
            extract_text(b"empty pdf bytes", "empty.pdf")


# --- parse_resume_text ---


def test_parse_resume_text_empty():
    """Empty string raises ValueError."""
    with pytest.raises(ValueError, match="Resume text is empty"):
        parse_resume_text("   ")


@responses.activate
def test_parse_resume_text_valid():
    """Mocked Ollama returns valid profile dict."""
    result = {
        "role_tags": ["customer success"],
        "industry_tags": ["saas"],
        "skills": ["jira", "python"],
        "primary_role_tags": ["Customer Success Manager"],
        "secondary_role_tags": ["Solutions Engineer"],
        "resume_summary": "Experienced professional.",
    }

    # Simulate streaming response — each line is a JSON chunk
    chunks = []
    content = json.dumps(result)
    # Send content token by token (simplified — send whole thing as one chunk)
    chunks.append(json.dumps({"message": {"content": content}, "done": True}))

    body = "\n".join(chunks)

    responses.add(
        responses.POST,
        f"{OLLAMA_URL}/api/chat",
        body=body,
        status=200,
        stream=True,
    )

    parsed = parse_resume_text("My resume text goes here")
    assert "customer success" in parsed["role_tags"]
    assert parsed["resume_summary"] == "Experienced professional."


def test_parse_resume_ollama_down():
    """Connection error raises ValueError."""
    with patch("resume_parser.requests.post",
               side_effect=requests.exceptions.ConnectionError("Connection refused")):
        with pytest.raises(ValueError, match="Could not connect"):
            parse_resume_text("My resume text")


def test_progress_callback_called():
    """progress_callback is invoked during parsing."""
    callback = MagicMock()

    # parse_resume_text calls the callback before calling _call_ollama
    # We can test that the callback is called at least for the initial message
    with patch.object(resume_parser, "_call_ollama", return_value={
        "role_tags": [], "industry_tags": [], "skills": [],
        "primary_role_tags": [], "secondary_role_tags": [], "resume_summary": "",
    }):
        parse_resume_text("My resume text here", progress_callback=callback)

    assert callback.call_count >= 1
    # First call should mention word count
    first_call_msg = callback.call_args_list[0][0][0]
    assert "words" in first_call_msg.lower()


@responses.activate
def test_field_sanitization():
    """Non-string items in lists filtered out, lists truncated."""
    result = {
        "role_tags": ["valid", 123, None, "also valid", {"nested": True}],
        "industry_tags": ["saas"],
        "skills": [f"skill{i}" for i in range(50)],  # way over limit
        "primary_role_tags": ["CSM"],
        "secondary_role_tags": ["SE"],
        "resume_summary": "Summary text.",
    }

    chunks = [json.dumps({"message": {"content": json.dumps(result)}, "done": True})]
    body = "\n".join(chunks)

    responses.add(
        responses.POST,
        f"{OLLAMA_URL}/api/chat",
        body=body,
        status=200,
        stream=True,
    )

    parsed = parse_resume_text("Test resume")

    # Non-strings should be filtered out
    assert parsed["role_tags"] == ["valid", "also valid"]
    # Skills list should be truncated to max 30
    assert len(parsed["skills"]) <= 30


# --- Additional edge cases ---


def test_extract_docx_with_tables():
    """Tables extracted alongside paragraphs."""
    mock_para = MagicMock()
    mock_para.text = "Resume paragraph"

    mock_cell1 = MagicMock()
    mock_cell1.text = "Skill 1"
    mock_cell2 = MagicMock()
    mock_cell2.text = "Skill 2"
    mock_row = MagicMock()
    mock_row.cells = [mock_cell1, mock_cell2]
    mock_table = MagicMock()
    mock_table.rows = [mock_row]

    mock_doc = MagicMock()
    mock_doc.paragraphs = [mock_para]
    mock_doc.tables = [mock_table]

    with patch.dict("sys.modules", {"docx": MagicMock()}):
        import sys
        sys.modules["docx"].Document.return_value = mock_doc
        result = extract_text(b"fake docx bytes", "resume.docx")

    assert "Resume paragraph" in result
    assert "Skill 1" in result
    assert "Skill 2" in result


def test_extract_pdf_multipage():
    """Multiple pages concatenated."""
    mock_page1 = MagicMock()
    mock_page1.extract_text.return_value = "Page 1 content"
    mock_page2 = MagicMock()
    mock_page2.extract_text.return_value = "Page 2 content"
    mock_pdf = MagicMock()
    mock_pdf.pages = [mock_page1, mock_page2]
    mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
    mock_pdf.__exit__ = MagicMock(return_value=False)

    with patch.dict("sys.modules", {"pdfplumber": MagicMock()}):
        import sys
        sys.modules["pdfplumber"].open.return_value = mock_pdf
        result = extract_text(b"fake pdf bytes", "resume.pdf")

    assert "Page 1 content" in result
    assert "Page 2 content" in result


@responses.activate
def test_call_ollama_streaming_chunks():
    """Multi-chunk streaming response assembled correctly."""
    result = {
        "role_tags": ["support"],
        "industry_tags": ["tech"],
        "skills": ["python"],
        "primary_role_tags": ["CSM"],
        "secondary_role_tags": ["SE"],
        "resume_summary": "Good.",
    }
    content = json.dumps(result)

    # Split content across multiple chunks
    chunks = []
    for i in range(0, len(content), 10):
        chunk_content = content[i:i+10]
        is_done = (i + 10) >= len(content)
        chunks.append(json.dumps({"message": {"content": chunk_content}, "done": is_done}))

    body = "\n".join(chunks)
    responses.add(
        responses.POST,
        f"{OLLAMA_URL}/api/chat",
        body=body,
        status=200,
        stream=True,
    )

    parsed = parse_resume_text("My resume text")
    assert "support" in parsed["role_tags"]


def test_call_ollama_timeout():
    """ReadTimeout handled gracefully → ValueError."""
    with patch("resume_parser.requests.post",
               side_effect=requests.exceptions.ReadTimeout("timeout")):
        with pytest.raises(ValueError, match="timed out"):
            parse_resume_text("My resume text")


def test_call_ollama_chunked_encoding_error():
    """ChunkedEncodingError with partial data handled."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None

    # Simulate iter_lines that raises ChunkedEncodingError after some data
    result = {
        "role_tags": ["test"],
        "industry_tags": [],
        "skills": [],
        "primary_role_tags": [],
        "secondary_role_tags": [],
        "resume_summary": "Partial.",
    }
    content = json.dumps(result)
    line = json.dumps({"message": {"content": content}, "done": True}).encode()

    def iter_lines_with_error():
        yield line
        raise requests.exceptions.ChunkedEncodingError("connection lost")

    mock_resp.iter_lines = iter_lines_with_error

    with patch("resume_parser.requests.post", return_value=mock_resp):
        parsed = parse_resume_text("My resume text")
    assert parsed["resume_summary"] == "Partial."


@responses.activate
def test_parse_resume_file_pdf():
    """Full parse_resume() with PDF extraction + Ollama."""
    result = {
        "role_tags": ["csm"],
        "industry_tags": ["saas"],
        "skills": ["jira"],
        "primary_role_tags": ["CSM"],
        "secondary_role_tags": ["SE"],
        "resume_summary": "Great candidate.",
    }

    chunks = [json.dumps({"message": {"content": json.dumps(result)}, "done": True})]
    body = "\n".join(chunks)
    responses.add(
        responses.POST,
        f"{OLLAMA_URL}/api/chat",
        body=body,
        status=200,
        stream=True,
    )

    mock_page = MagicMock()
    mock_page.extract_text.return_value = "Resume content here"
    mock_pdf = MagicMock()
    mock_pdf.pages = [mock_page]
    mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
    mock_pdf.__exit__ = MagicMock(return_value=False)

    with patch.dict("sys.modules", {"pdfplumber": MagicMock()}):
        import sys
        sys.modules["pdfplumber"].open.return_value = mock_pdf
        parsed = parse_resume(b"fake pdf", "resume.pdf")

    assert "csm" in parsed["role_tags"]


@responses.activate
def test_parse_resume_markdown_fences():
    """Response wrapped in ```json``` stripped."""
    inner = json.dumps({
        "role_tags": ["test"],
        "industry_tags": [],
        "skills": [],
        "primary_role_tags": [],
        "secondary_role_tags": [],
        "resume_summary": "Test.",
    })
    wrapped = f"```json\n{inner}\n```"

    chunks = [json.dumps({"message": {"content": wrapped}, "done": True})]
    body = "\n".join(chunks)
    responses.add(
        responses.POST,
        f"{OLLAMA_URL}/api/chat",
        body=body,
        status=200,
        stream=True,
    )

    parsed = parse_resume_text("My resume text")
    assert "test" in parsed["role_tags"]


@responses.activate
def test_field_defaults_for_missing_keys():
    """Missing keys get defaults."""
    # Only partial result — missing several fields
    result = {"role_tags": ["support"]}

    chunks = [json.dumps({"message": {"content": json.dumps(result)}, "done": True})]
    body = "\n".join(chunks)
    responses.add(
        responses.POST,
        f"{OLLAMA_URL}/api/chat",
        body=body,
        status=200,
        stream=True,
    )

    parsed = parse_resume_text("My resume text")
    assert parsed["industry_tags"] == []
    assert parsed["skills"] == []
    assert parsed["primary_role_tags"] == []
    assert parsed["secondary_role_tags"] == []
    assert parsed["resume_summary"] == ""


@responses.activate
def test_resume_summary_truncation():
    """Long summaries truncated to 2000 chars."""
    result = {
        "role_tags": ["test"],
        "industry_tags": [],
        "skills": [],
        "primary_role_tags": [],
        "secondary_role_tags": [],
        "resume_summary": "x" * 5000,
    }

    chunks = [json.dumps({"message": {"content": json.dumps(result)}, "done": True})]
    body = "\n".join(chunks)
    responses.add(
        responses.POST,
        f"{OLLAMA_URL}/api/chat",
        body=body,
        status=200,
        stream=True,
    )

    parsed = parse_resume_text("My resume text")
    assert len(parsed["resume_summary"]) == 2000


def test_extract_doc_legacy_fails():
    """Legacy .doc format raises ValueError when docx parsing fails."""
    with patch.dict("sys.modules", {"docx": MagicMock()}) as mock_modules:
        import sys
        sys.modules["docx"].Document.side_effect = Exception("Not a docx")
        with pytest.raises(ValueError, match="Legacy .doc format"):
            extract_text(b"fake doc bytes", "resume.doc")


def test_extract_empty_docx():
    """DOCX with no text raises ValueError (line 129)."""
    mock_doc = MagicMock()
    mock_doc.paragraphs = []
    mock_doc.tables = []

    with patch.dict("sys.modules", {"docx": MagicMock()}):
        import sys
        sys.modules["docx"].Document.return_value = mock_doc
        with pytest.raises(ValueError, match="Could not extract text"):
            extract_text(b"empty docx bytes", "empty.docx")


@responses.activate
def test_parse_resume_with_progress_callback():
    """parse_resume() calls progress at extract + word count + ollama steps (lines 176, 182)."""
    result = {
        "role_tags": ["test"],
        "industry_tags": [],
        "skills": [],
        "primary_role_tags": [],
        "secondary_role_tags": [],
        "resume_summary": "Test.",
    }

    chunks = [json.dumps({"message": {"content": json.dumps(result)}, "done": True})]
    body = "\n".join(chunks)
    responses.add(
        responses.POST,
        f"{OLLAMA_URL}/api/chat",
        body=body,
        status=200,
        stream=True,
    )

    mock_page = MagicMock()
    mock_page.extract_text.return_value = "Resume content here"
    mock_pdf = MagicMock()
    mock_pdf.pages = [mock_page]
    mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
    mock_pdf.__exit__ = MagicMock(return_value=False)

    callback = MagicMock()

    with patch.dict("sys.modules", {"pdfplumber": MagicMock()}):
        import sys
        sys.modules["pdfplumber"].open.return_value = mock_pdf
        parse_resume(b"fake pdf", "resume.pdf", progress_callback=callback)

    # Should have called callback for extraction, word count, AI steps
    assert callback.call_count >= 3
    messages = [c[0][0] for c in callback.call_args_list]
    assert any("Extracting" in m for m in messages)
    assert any("Extracted" in m for m in messages)


@responses.activate
def test_call_ollama_progress_during_streaming():
    """Progress callback invoked during streaming with percentage (lines 236-238)."""
    result = {
        "role_tags": ["test"],
        "industry_tags": [],
        "skills": [],
        "primary_role_tags": [],
        "secondary_role_tags": [],
        "resume_summary": "Test.",
    }
    content = json.dumps(result)

    # Create many chunks to trigger progress updates (every 15 tokens)
    chunks = []
    for i, char in enumerate(content):
        is_done = (i == len(content) - 1)
        chunks.append(json.dumps({"message": {"content": char}, "done": is_done}))

    body = "\n".join(chunks)
    responses.add(
        responses.POST,
        f"{OLLAMA_URL}/api/chat",
        body=body,
        status=200,
        stream=True,
    )

    callback = MagicMock()
    parse_resume_text("My resume text", progress_callback=callback)

    messages = [c[0][0] for c in callback.call_args_list]
    # Should have progress percentage messages
    assert any("%" in m for m in messages)


def test_call_ollama_chunked_error_no_data():
    """ChunkedEncodingError with no data raises ValueError (lines 243-246)."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None

    def iter_lines_empty_then_error():
        raise requests.exceptions.ChunkedEncodingError("connection lost")
        yield  # never reached - make it a generator

    mock_resp.iter_lines = iter_lines_empty_then_error

    with patch("resume_parser.requests.post", return_value=mock_resp):
        with pytest.raises(ValueError, match="Lost connection"):
            parse_resume_text("My resume text")


def test_call_ollama_stream_with_empty_lines_and_bad_json():
    """Streaming with empty lines and invalid JSON lines handled (lines 226, 229-230)."""
    result = {
        "role_tags": ["test"],
        "industry_tags": [],
        "skills": [],
        "primary_role_tags": [],
        "secondary_role_tags": [],
        "resume_summary": "OK.",
    }
    content = json.dumps(result)

    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None

    def iter_lines_with_junk():
        yield b""  # empty line → continue (line 226)
        yield b"not valid json"  # JSONDecodeError → continue (lines 229-230)
        yield json.dumps({"message": {"content": content}, "done": True}).encode()

    mock_resp.iter_lines = iter_lines_with_junk

    with patch("resume_parser.requests.post", return_value=mock_resp):
        parsed = parse_resume_text("My resume text")
    assert parsed["resume_summary"] == "OK."


def test_call_ollama_chunked_error_with_partial_data():
    """ChunkedEncodingError with partial data uses what's available (line 247)."""
    result = {
        "role_tags": ["partial"],
        "industry_tags": [],
        "skills": [],
        "primary_role_tags": [],
        "secondary_role_tags": [],
        "resume_summary": "Partial.",
    }
    content = json.dumps(result)

    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None

    def iter_lines_partial():
        yield json.dumps({"message": {"content": content}, "done": False}).encode()
        raise requests.exceptions.ChunkedEncodingError("connection lost")

    mock_resp.iter_lines = iter_lines_partial

    with patch("resume_parser.requests.post", return_value=mock_resp):
        parsed = parse_resume_text("My resume text")
    assert parsed["resume_summary"] == "Partial."


@responses.activate
def test_final_progress_with_tag_count():
    """Final progress message shows tag count (lines 284-287)."""
    result = {
        "role_tags": ["csm", "tam"],
        "industry_tags": ["saas", "cybersecurity"],
        "skills": ["python", "jira", "sql"],
        "primary_role_tags": ["CSM"],
        "secondary_role_tags": ["SE"],
        "resume_summary": "Great candidate.",
    }

    chunks = [json.dumps({"message": {"content": json.dumps(result)}, "done": True})]
    body = "\n".join(chunks)
    responses.add(
        responses.POST,
        f"{OLLAMA_URL}/api/chat",
        body=body,
        status=200,
        stream=True,
    )

    callback = MagicMock()
    parse_resume_text("My resume text", progress_callback=callback)

    messages = [c[0][0] for c in callback.call_args_list]
    # Last message should mention tag count: 2 + 2 + 3 = 7 tags
    assert any("7 tags" in m for m in messages)
