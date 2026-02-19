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
