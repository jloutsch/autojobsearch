"""Generate a self-contained static HTML dashboard for daily job search results."""

import html
import json
import os
from datetime import date

from ai_scorer import OLLAMA_MODEL
from user_profile import get_profile


def generate_dashboard(ranked_jobs: list[dict], output_dir: str = "reports/", filename: str | None = None) -> str:
    """Generate a static HTML dashboard. Returns the filepath."""
    os.makedirs(output_dir, exist_ok=True)
    today = date.today().strftime("%Y-%m-%d")
    today_display = date.today().strftime("%A, %B %d, %Y")

    is_landing = filename == "index.html"
    if filename:
        filepath = os.path.join(output_dir, filename)
    else:
        filepath = os.path.join(output_dir, f"{today}.html")

    high = [j for j in ranked_jobs if j.get("priority") == "high"]
    medium = [j for j in ranked_jobs if j.get("priority") == "medium"]
    low = [j for j in ranked_jobs if j.get("priority") == "low"]

    job_rows = "\n".join(_render_row(j) for j in ranked_jobs)

    # Embed job data as JSON for AI re-scoring from browser
    # Escape </ to prevent </script> from breaking the HTML script block
    jobs_json = json.dumps([
        {
            "title": j.get("title", ""),
            "company": j.get("company", ""),
            "description": j.get("description", "")[:3000],
            "salary_min": j.get("salary_min", 0),
            "salary_max": j.get("salary_max", 0),
            "location": j.get("location", ""),
        }
        for j in ranked_jobs
    ]).replace("</", "<\\/")

    # Embed profile data for frontend editing
    profile = get_profile()
    profile_json = json.dumps(profile).replace("</", "<\\/")

    content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{"Job Search Dashboard" if is_landing else f"Job Search Dashboard — {today}"}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         background: #0f172a; color: #e2e8f0; line-height: 1.5; }}

  .header {{ background: #1e293b; padding: 24px 32px; border-bottom: 1px solid #334155;
            display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 16px; }}
  .header h1 {{ font-size: 24px; color: #f1f5f9; }}
  .header .subtitle {{ color: #94a3b8; font-size: 14px; margin-top: 4px; }}

  .header-right {{ display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }}
  .profile-toggle {{ background: #334155; border: 1px solid #475569; color: #e2e8f0;
                     padding: 6px 14px; border-radius: 6px; cursor: pointer; font-size: 13px;
                     font-weight: 500; transition: all 0.15s; }}
  .profile-toggle:hover {{ background: #475569; }}
  .profile-toggle.active {{ background: #7c3aed; border-color: #7c3aed; }}

  .ollama-panel {{ display: flex; align-items: center; gap: 8px; }}
  .ollama-panel select {{ background: #334155; border: 1px solid #475569; border-radius: 6px;
                         color: #e2e8f0; padding: 6px 10px; font-size: 13px; cursor: pointer; }}
  .ollama-panel select:focus {{ outline: none; border-color: #60a5fa; }}
  .ollama-panel .rescore-btn {{ background: #7c3aed; border: none; color: white; padding: 6px 14px;
                               border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 500;
                               transition: background 0.15s; }}
  .ollama-panel .rescore-btn:hover {{ background: #6d28d9; }}
  .ollama-panel .rescore-btn:disabled {{ background: #475569; cursor: not-allowed; }}
  .ollama-status {{ font-size: 12px; color: #94a3b8; }}
  .ollama-progress {{ font-size: 12px; color: #a78bfa; }}

  .search-btn {{ background: #059669; border: none; color: white; padding: 6px 14px;
                 border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 500;
                 transition: background 0.15s; }}
  .search-btn:hover {{ background: #047857; }}
  .search-btn:disabled {{ background: #475569; cursor: not-allowed; }}
  .search-status {{ font-size: 12px; color: #94a3b8; }}

  .progress-panel {{ background: #0f172a; border: 1px solid #334155; border-radius: 8px;
                     margin: 0 32px; padding: 16px; display: none; max-height: 200px;
                     overflow-y: auto; font-family: 'SF Mono', Monaco, Consolas, monospace; }}
  .progress-panel.visible {{ display: block; }}
  .progress-line {{ font-size: 12px; color: #94a3b8; padding: 2px 0; }}
  .progress-line.phase {{ color: #60a5fa; font-weight: 600; }}
  .progress-line.ai {{ color: #a78bfa; }}
  .progress-line.done {{ color: #4ade80; font-weight: 600; }}
  .progress-line.error {{ color: #f87171; }}

  /* --- Profile Panel --- */
  .profile-panel {{ background: #1e293b; border-bottom: 1px solid #334155; padding: 24px 32px;
                    display: none; }}
  .profile-panel.visible {{ display: block; }}
  .profile-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
  .profile-section {{ display: flex; flex-direction: column; gap: 6px; }}
  .profile-section.full-width {{ grid-column: 1 / -1; }}
  .profile-label {{ font-size: 12px; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 600;
                    display: flex; align-items: center; gap: 8px; }}
  .clear-tags {{ font-size: 11px; color: #94a3b8; cursor: pointer; text-transform: none;
                 letter-spacing: 0; font-weight: 400; }}
  .clear-tags:hover {{ color: #f87171; }}
  .profile-textarea {{ background: #0f172a; border: 1px solid #334155; border-radius: 6px;
                       color: #e2e8f0; padding: 10px 12px; font-size: 13px; font-family: inherit;
                       resize: vertical; min-height: 80px; }}
  .profile-textarea:focus {{ outline: none; border-color: #60a5fa; }}
  .profile-textarea.tall {{ min-height: 120px; }}

  .tag-container {{ display: flex; flex-wrap: wrap; gap: 6px; align-items: center;
                    background: #0f172a; border: 1px solid #334155; border-radius: 6px;
                    padding: 8px 10px; min-height: 40px; }}
  .tag-container:focus-within {{ border-color: #60a5fa; }}
  .tag-pill {{ background: #334155; color: #e2e8f0; padding: 3px 10px; border-radius: 4px;
               font-size: 13px; display: flex; align-items: center; gap: 6px; white-space: nowrap; }}
  .tag-pill .remove {{ cursor: pointer; color: #94a3b8; font-size: 15px; line-height: 1; }}
  .tag-pill .remove:hover {{ color: #f87171; }}
  .tag-add {{ background: none; border: none; color: #e2e8f0; font-size: 13px;
              outline: none; min-width: 80px; flex: 1; }}
  .tag-add::placeholder {{ color: #475569; }}

  .salary-inputs {{ display: flex; gap: 12px; align-items: center; }}
  .salary-input {{ background: #0f172a; border: 1px solid #334155; border-radius: 6px;
                   color: #e2e8f0; padding: 6px 10px; font-size: 13px; width: 120px; }}
  .salary-input:focus {{ outline: none; border-color: #60a5fa; }}
  .salary-sep {{ color: #475569; }}

  .profile-actions {{ display: flex; gap: 10px; margin-top: 16px; grid-column: 1 / -1; }}
  .profile-btn {{ padding: 8px 18px; border-radius: 6px; font-size: 13px; font-weight: 500;
                  cursor: pointer; border: none; transition: background 0.15s; }}
  .profile-btn.save {{ background: #059669; color: white; }}
  .profile-btn.save:hover {{ background: #047857; }}
  .profile-btn.download {{ background: #2563eb; color: white; }}
  .profile-btn.download:hover {{ background: #1d4ed8; }}
  .profile-btn.reset {{ background: #334155; color: #e2e8f0; }}
  .profile-btn.reset:hover {{ background: #475569; }}
  .toast {{ position: fixed; bottom: 24px; right: 24px; background: #059669; color: white;
            padding: 10px 20px; border-radius: 8px; font-size: 14px; font-weight: 500;
            opacity: 0; transition: opacity 0.3s; pointer-events: none; z-index: 100; }}
  .toast.show {{ opacity: 1; }}

  .stats {{ display: flex; gap: 16px; padding: 20px 32px; flex-wrap: wrap; }}
  .stat-card {{ background: #1e293b; border-radius: 8px; padding: 16px 20px;
               border: 1px solid #334155; min-width: 140px; cursor: pointer;
               transition: border-color 0.15s; }}
  .stat-card:hover {{ border-color: #60a5fa; }}
  .stat-card.active {{ border-color: #60a5fa; border-width: 2px; }}
  .stat-card .number {{ font-size: 28px; font-weight: 700; }}
  .stat-card .label {{ font-size: 13px; color: #94a3b8; }}
  .stat-high .number {{ color: #f87171; }}
  .stat-med .number {{ color: #fbbf24; }}
  .stat-low .number {{ color: #94a3b8; }}
  .stat-total .number {{ color: #60a5fa; }}

  .controls {{ padding: 12px 32px; display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }}
  .control-group {{ display: flex; gap: 8px; align-items: center; }}
  .control-label {{ font-size: 12px; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin-right: 2px; }}
  .search {{ background: #1e293b; border: 1px solid #334155; border-radius: 6px;
            color: #e2e8f0; padding: 8px 12px; font-size: 14px; width: 260px; }}
  .search:focus {{ outline: none; border-color: #60a5fa; }}
  .sep {{ width: 1px; height: 24px; background: #334155; margin: 0 4px; }}

  .filter-btn {{ background: #334155; border: 2px solid transparent; color: #e2e8f0;
                padding: 5px 12px; border-radius: 6px; cursor: pointer; font-size: 13px;
                transition: all 0.15s; }}
  .filter-btn:hover {{ background: #475569; }}
  .filter-btn.active {{ background: #3b82f6; border-color: #60a5fa; }}
  .filter-btn[data-priority="high"] {{ color: #f87171; border-color: #334155; }}
  .filter-btn[data-priority="high"].active {{ background: #991b1b; border-color: #f87171; color: #fecaca; }}
  .filter-btn[data-priority="medium"] {{ color: #fbbf24; border-color: #334155; }}
  .filter-btn[data-priority="medium"].active {{ background: #854d0e; border-color: #fbbf24; color: #fef3c7; }}
  .filter-btn[data-priority="low"] {{ color: #94a3b8; border-color: #334155; }}
  .filter-btn[data-priority="low"].active {{ background: #334155; border-color: #94a3b8; color: #e2e8f0; }}

  .age-btn {{ background: #334155; border: 1px solid transparent; color: #94a3b8;
             padding: 5px 12px; border-radius: 6px; cursor: pointer; font-size: 13px;
             transition: all 0.15s; }}
  .age-btn:hover {{ background: #475569; color: #e2e8f0; }}
  .age-btn.active {{ background: #1e40af; border-color: #3b82f6; color: #bfdbfe; }}

  .filter-count {{ font-size: 12px; color: #94a3b8; margin-left: 8px; }}

  .table-wrap {{ padding: 0 32px 32px; overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
  th {{ text-align: left; padding: 10px 12px; color: #94a3b8; font-weight: 600;
       border-bottom: 2px solid #334155; cursor: pointer; user-select: none;
       white-space: nowrap; }}
  th:hover {{ color: #e2e8f0; }}
  th .arrow {{ margin-left: 4px; font-size: 11px; }}
  td {{ padding: 10px 12px; border-bottom: 1px solid #1e293b; vertical-align: top; }}
  tr:hover {{ background: #1e293b; }}
  tr.hidden {{ display: none; }}

  .priority-high {{ color: #f87171; font-weight: 600; }}
  .priority-medium {{ color: #fbbf24; }}
  .priority-low {{ color: #94a3b8; }}
  .job-title {{ color: #60a5fa; text-decoration: none; font-weight: 500; }}
  .job-title:hover {{ text-decoration: underline; }}
  .company {{ color: #e2e8f0; font-weight: 500; }}
  .source-badge {{ background: #334155; padding: 2px 8px; border-radius: 4px;
                  font-size: 12px; color: #94a3b8; }}
  .salary {{ color: #4ade80; white-space: nowrap; }}
  .age {{ color: #94a3b8; font-size: 13px; white-space: nowrap; }}
  .summary {{ color: #94a3b8; font-size: 13px; max-width: 320px; }}
  .score {{ font-weight: 600; }}
  .score.rescored {{ color: #a78bfa; }}
  .empty {{ text-align: center; padding: 60px 20px; color: #64748b; }}

  .resume-upload-area {{ display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }}
  .profile-btn.upload {{ background: #7c3aed; color: white; border: none; padding: 8px 16px;
                        border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 500; }}
  .profile-btn.upload:hover {{ background: #6d28d9; }}
  .profile-btn.upload:disabled {{ background: #475569; cursor: not-allowed; }}
  .upload-status {{ font-size: 13px; color: #a78bfa; }}
  .upload-status.error {{ color: #f87171; }}
  .upload-hint {{ font-size: 12px; color: #64748b; width: 100%; }}
  .resume-progress {{ background: #0f172a; border: 1px solid #334155; border-radius: 6px;
                     padding: 10px 14px; margin-top: 8px; width: 100%; display: none;
                     max-height: 120px; overflow-y: auto; }}
  .resume-progress.visible {{ display: block; }}
  .resume-progress .rp-line {{ font-size: 12px; color: #94a3b8; padding: 2px 0;
                              font-family: 'SF Mono', Monaco, Consolas, monospace; }}
  .resume-progress .rp-line.done {{ color: #4ade80; font-weight: 600; }}
  .resume-progress .rp-line.error {{ color: #f87171; }}
</style>
</head>
<body>

<div class="header">
  <div>
    <h1>Daily Job Search Dashboard</h1>
    <div class="subtitle">{"Click <strong>Run Search</strong> to find new jobs" if is_landing and not ranked_jobs else f"{today_display} &mdash; {len(ranked_jobs)} matches found"}</div>
  </div>
  <div class="header-right">
    <button class="profile-toggle active" id="profileToggle" onclick="toggleProfile()">Profile</button>
    <button class="search-btn" id="runSearchBtn" onclick="runSearch()">Run Search</button>
    <span class="search-status" id="searchStatus"></span>
    <div class="ollama-panel">
      <select id="modelSelect"><option value="">Loading models...</option></select>
      <button class="rescore-btn" id="rescoreBtn" onclick="rescoreAll()" disabled>Re-score with AI</button>
      <span class="ollama-status" id="ollamaStatus"></span>
      <span class="ollama-progress" id="ollamaProgress"></span>
    </div>
  </div>
</div>

<div class="profile-panel visible" id="profilePanel">
  <div class="profile-grid">
    <div class="profile-section full-width">
      <span class="profile-label">Resume Upload</span>
      <div class="resume-upload-area">
        <input type="file" id="resumeFileInput" accept=".pdf,.doc,.docx" style="display:none">
        <button class="profile-btn upload" id="uploadResumeBtn" onclick="document.getElementById('resumeFileInput').click()">Upload Resume</button>
        <span class="upload-status" id="uploadStatus"></span>
        <div class="upload-hint">Upload a PDF or DOCX resume to auto-populate your profile tags and summary using AI</div>
      </div>
      <div class="resume-progress" id="resumeProgress"></div>
    </div>
    <div class="profile-section full-width">
      <span class="profile-label">Resume Summary</span>
      <textarea class="profile-textarea tall" id="resumeSummary"></textarea>
      <div class="resume-upload-area" style="margin-top:8px">
        <button class="profile-btn upload" id="analyzeTextBtn" onclick="analyzeResumeText()">Analyze Text</button>
        <span class="upload-status" id="analyzeTextStatus"></span>
        <div class="upload-hint">Paste your resume above, then click to auto-populate tags using AI</div>
      </div>
      <div class="resume-progress" id="analyzeTextProgress"></div>
    </div>
    <div class="profile-section">
      <span class="profile-label">Role Tags <span class="clear-tags" onclick="clearTags('roleTags')">clear all</span></span>
      <div class="tag-container" id="roleTags"></div>
    </div>
    <div class="profile-section">
      <span class="profile-label">Industry Tags <span class="clear-tags" onclick="clearTags('industryTags')">clear all</span></span>
      <div class="tag-container" id="industryTags"></div>
    </div>
    <div class="profile-section">
      <span class="profile-label">Skills <span class="clear-tags" onclick="clearTags('skillTags')">clear all</span></span>
      <div class="tag-container" id="skillTags"></div>
    </div>
    <div class="profile-section">
      <span class="profile-label">Priority Companies <span class="clear-tags" onclick="clearTags('companyTags')">clear all</span></span>
      <div class="tag-container" id="companyTags"></div>
    </div>
    <div class="profile-section">
      <span class="profile-label">Salary Range</span>
      <div class="salary-inputs">
        <input type="number" class="salary-input" id="salaryMin" placeholder="Min">
        <span class="salary-sep">&ndash;</span>
        <input type="number" class="salary-input" id="salaryMax" placeholder="Max">
        <span class="salary-sep">Floor:</span>
        <input type="number" class="salary-input" id="salaryFloor" placeholder="Floor">
      </div>
    </div>
    <div class="profile-section full-width">
      <span class="profile-label">AI Prompt Template</span>
      <textarea class="profile-textarea tall" id="aiPrompt"></textarea>
    </div>
    <div class="profile-actions">
      <button class="profile-btn save" onclick="saveProfile()">Save to Browser</button>
      <button class="profile-btn download" onclick="downloadProfile()">Download profile.json</button>
      <button class="profile-btn reset" onclick="resetProfile()">Reset to Default</button>
    </div>
  </div>
</div>

<div class="stats">
  <div class="stat-card stat-total active" onclick="cardFilter('all')">
    <div class="number" id="statTotal">{len(ranked_jobs)}</div>
    <div class="label">Total</div>
  </div>
  <div class="stat-card stat-high" onclick="cardFilter('high')">
    <div class="number" id="statHigh">{len(high)}</div>
    <div class="label">High Priority</div>
  </div>
  <div class="stat-card stat-med" onclick="cardFilter('medium')">
    <div class="number" id="statMed">{len(medium)}</div>
    <div class="label">Medium Priority</div>
  </div>
  <div class="stat-card stat-low" onclick="cardFilter('low')">
    <div class="number" id="statLow">{len(low)}</div>
    <div class="label">Other</div>
  </div>
</div>

<div class="progress-panel" id="progressPanel"></div>

<div class="controls">
  <input type="text" class="search" placeholder="Filter by title, company, source..."
         oninput="filterTable()" id="searchBox">
  <div class="sep"></div>
  <div class="control-group">
    <span class="control-label">Priority</span>
    <button class="filter-btn active" data-priority="all" onclick="setPriority('all', this)">All</button>
    <button class="filter-btn" data-priority="high" onclick="setPriority('high', this)">High</button>
    <button class="filter-btn" data-priority="medium" onclick="setPriority('medium', this)">Medium</button>
    <button class="filter-btn" data-priority="low" onclick="setPriority('low', this)">Low</button>
  </div>
  <div class="sep"></div>
  <div class="control-group">
    <span class="control-label">Posted</span>
    <button class="age-btn active" data-age="all" onclick="setAge('all', this)">All</button>
    <button class="age-btn" data-age="1" onclick="setAge('1', this)">Today</button>
    <button class="age-btn" data-age="3" onclick="setAge('3', this)">3 Days</button>
    <button class="age-btn" data-age="7" onclick="setAge('7', this)">1 Week</button>
    <button class="age-btn" data-age="14" onclick="setAge('14', this)">2 Weeks</button>
    <button class="age-btn" data-age="30" onclick="setAge('30', this)">1 Month</button>
  </div>
  <span class="filter-count" id="filterCount"></span>
</div>

<div class="table-wrap">
{"<p class='empty'>No new matching jobs found today.</p>" if not ranked_jobs else f'''
<table id="jobTable">
<thead>
  <tr>
    <th onclick="sortTable(0)">Score <span class="arrow"></span></th>
    <th onclick="sortTable(1)">Priority <span class="arrow"></span></th>
    <th onclick="sortTable(2)">Title <span class="arrow"></span></th>
    <th onclick="sortTable(3)">Company <span class="arrow"></span></th>
    <th onclick="sortTable(4)">Salary <span class="arrow"></span></th>
    <th onclick="sortTable(5)">Location <span class="arrow"></span></th>
    <th onclick="sortTable(6)">Posted <span class="arrow"></span></th>
    <th onclick="sortTable(7)">Source <span class="arrow"></span></th>
    <th>Summary</th>
  </tr>
</thead>
<tbody>
{job_rows}
</tbody>
</table>
'''}
</div>

<div class="toast" id="toast"></div>

<script>
const OLLAMA_URL = 'http://localhost:11434';
const DEFAULT_MODEL = '{OLLAMA_MODEL}';
const jobData = {jobs_json};
const DEFAULT_PROFILE = {profile_json};

function escapeHtml(str) {{
  if (!str) return '';
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}}

// --- Profile Management ---
function getProfile() {{
  const stored = localStorage.getItem('autojobsearch_profile');
  if (stored) {{
    try {{ return JSON.parse(stored); }}
    catch(e) {{ console.warn('Invalid stored profile, using default'); }}
  }}
  return JSON.parse(JSON.stringify(DEFAULT_PROFILE));
}}

let currentProfile = getProfile();

const TAG_FIELDS = {{
  roleTags: 'role_tags',
  industryTags: 'industry_tags',
  skillTags: 'skills',
  companyTags: 'priority_companies'
}};

function toggleProfile() {{
  const panel = document.getElementById('profilePanel');
  const btn = document.getElementById('profileToggle');
  const isVisible = panel.classList.toggle('visible');
  btn.classList.toggle('active', isVisible);
  if (isVisible) renderProfile();
}}

function renderProfile() {{
  document.getElementById('resumeSummary').value = currentProfile.resume_summary || '';
  document.getElementById('salaryMin').value = currentProfile.salary_range?.min || '';
  document.getElementById('salaryMax').value = currentProfile.salary_range?.max || '';
  document.getElementById('salaryFloor').value = currentProfile.salary_range?.floor || '';
  document.getElementById('aiPrompt').value = currentProfile.ai_prompt_template || '';
  for (const [elemId, key] of Object.entries(TAG_FIELDS)) {{
    renderTags(elemId, currentProfile[key] || []);
  }}
}}

function renderTags(containerId, tags) {{
  const container = document.getElementById(containerId);
  container.innerHTML = '';
  tags.forEach((tag, i) => {{
    const pill = document.createElement('span');
    pill.className = 'tag-pill';
    const text = document.createTextNode(tag + ' ');
    const rm = document.createElement('span');
    rm.className = 'remove';
    rm.textContent = '\\u00d7';
    rm.onclick = () => removeTag(containerId, i);
    pill.appendChild(text);
    pill.appendChild(rm);
    container.appendChild(pill);
  }});
  const input = document.createElement('input');
  input.className = 'tag-add';
  input.placeholder = 'Add...';
  input.onkeydown = (e) => {{
    if (e.key === 'Enter' && e.target.value.trim()) {{
      e.preventDefault();
      addTag(containerId, e.target.value.trim());
      e.target.value = '';
    }}
  }};
  container.appendChild(input);
}}

function autoSaveProfile() {{
  localStorage.setItem('autojobsearch_profile', JSON.stringify(currentProfile));
  fetch('/api/profile', {{
    method: 'PUT',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify(currentProfile)
  }}).catch(() => {{}});
}}

function addTag(containerId, value) {{
  const key = TAG_FIELDS[containerId];
  if (!currentProfile[key]) currentProfile[key] = [];
  if (!currentProfile[key].includes(value)) {{
    currentProfile[key].push(value);
    renderTags(containerId, currentProfile[key]);
    autoSaveProfile();
  }}
  // Re-focus the input so the user can keep typing
  const input = document.getElementById(containerId).querySelector('.tag-add');
  if (input) input.focus();
}}

function removeTag(containerId, index) {{
  const key = TAG_FIELDS[containerId];
  if (currentProfile[key]) {{
    currentProfile[key].splice(index, 1);
    renderTags(containerId, currentProfile[key]);
    autoSaveProfile();
  }}
}}

function clearTags(containerId) {{
  const key = TAG_FIELDS[containerId];
  currentProfile[key] = [];
  renderTags(containerId, []);
  autoSaveProfile();
}}

function readProfileFromUI() {{
  currentProfile.resume_summary = document.getElementById('resumeSummary').value;
  currentProfile.ai_prompt_template = document.getElementById('aiPrompt').value;
  currentProfile.salary_range = {{
    min: parseInt(document.getElementById('salaryMin').value) || 0,
    max: parseInt(document.getElementById('salaryMax').value) || 0,
    floor: parseInt(document.getElementById('salaryFloor').value) || 0,
  }};
  // Tags are already updated live via addTag/removeTag
}}

function saveProfile() {{
  readProfileFromUI();
  localStorage.setItem('autojobsearch_profile', JSON.stringify(currentProfile));
  showToast('Profile saved to browser');
}}

function downloadProfile() {{
  readProfileFromUI();
  const blob = new Blob([JSON.stringify(currentProfile, null, 2)], {{type: 'application/json'}});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'profile.json';
  a.click();
  URL.revokeObjectURL(url);
}}

function resetProfile() {{
  localStorage.removeItem('autojobsearch_profile');
  currentProfile = JSON.parse(JSON.stringify(DEFAULT_PROFILE));
  renderProfile();
  showToast('Profile reset to defaults');
}}

function showToast(msg) {{
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2500);
}}

// --- Resume Upload ---
document.getElementById('resumeFileInput').addEventListener('change', handleResumeUpload);

async function handleResumeUpload(event) {{
  const file = event.target.files[0];
  if (!file) return;

  const ext = file.name.split('.').pop().toLowerCase();
  if (!['pdf', 'doc', 'docx'].includes(ext)) {{
    showUploadError('Unsupported file type. Upload a PDF or DOCX.');
    return;
  }}
  if (file.size > 10 * 1024 * 1024) {{
    showUploadError('File too large (max 10 MB)');
    return;
  }}

  const btn = document.getElementById('uploadResumeBtn');
  const status = document.getElementById('uploadStatus');
  const progressPanel = document.getElementById('resumeProgress');

  btn.disabled = true;
  btn.textContent = 'Processing...';
  status.textContent = '';
  status.className = 'upload-status';
  progressPanel.innerHTML = '';
  progressPanel.classList.add('visible');

  try {{
    addResumeProgressLine('Reading file...');
    const base64 = await readFileAsBase64(file);
    addResumeProgressLine('Uploading to server (' + (file.size / 1024).toFixed(0) + ' KB)...');

    const resp = await fetch('/api/parse-resume', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{ file: base64, filename: file.name }})
    }});

    if (!resp.ok && !resp.body) {{
      const err = await resp.json().catch(() => ({{}}));
      showUploadError(err.error || 'Upload failed');
      addResumeProgressLine(err.error || 'Upload failed', true);
      btn.disabled = false;
      btn.textContent = 'Upload Resume';
      event.target.value = '';
      return;
    }}

    addResumeProgressLine('Processing resume (this may take a minute)...');

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let profileResult = null;

    while (true) {{
      const {{ done, value }} = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, {{ stream: true }});

      const lines = buffer.split('\\n');
      buffer = lines.pop();
      for (const line of lines) {{
        if (!line.trim()) continue;
        try {{
          const msg = JSON.parse(line);
          if (msg.type === 'progress') {{
            addResumeProgressLine(msg.message);
          }} else if (msg.type === 'result') {{
            profileResult = msg.profile;
          }} else if (msg.type === 'error') {{
            showUploadError(msg.error || 'Resume parsing failed');
            addResumeProgressLine(msg.error || 'Failed', true);
          }}
        }} catch(e) {{ /* skip malformed lines */ }}
      }}
    }}

    if (buffer.trim()) {{
      try {{
        const msg = JSON.parse(buffer);
        if (msg.type === 'result') profileResult = msg.profile;
        else if (msg.type === 'error') showUploadError(msg.error || 'Failed');
      }} catch(e) {{}}
    }}

    if (profileResult) {{
      applyResumeProfile(profileResult);
      addResumeProgressLine('Profile populated — review and save when ready', false, true);
      status.textContent = 'Tags extracted — review below';
    }}

  }} catch(e) {{
    showUploadError('Upload failed: ' + e.message);
    addResumeProgressLine('Failed: ' + e.message, true);
  }}

  btn.disabled = false;
  btn.textContent = 'Upload Resume';
  event.target.value = '';
}}

function readFileAsBase64(file) {{
  return new Promise((resolve, reject) => {{
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error('Failed to read file'));
    reader.readAsDataURL(file);
  }});
}}

function addResumeProgressLine(msg, isError, isDone) {{
  const panel = document.getElementById('resumeProgress');
  const line = document.createElement('div');
  line.className = 'rp-line';
  if (isError) line.className += ' error';
  if (isDone) line.className += ' done';
  line.textContent = msg;
  panel.appendChild(line);
  panel.scrollTop = panel.scrollHeight;
}}

function showUploadError(msg) {{
  const status = document.getElementById('uploadStatus');
  status.textContent = msg;
  status.className = 'upload-status error';
}}

function applyResumeProfile(profile) {{
  if (profile.resume_summary) {{
    currentProfile.resume_summary = profile.resume_summary;
    document.getElementById('resumeSummary').value = profile.resume_summary;
  }}

  if (profile.role_tags && profile.role_tags.length > 0) {{
    currentProfile.role_tags = profile.role_tags;
    renderTags('roleTags', currentProfile.role_tags);
  }}
  if (profile.industry_tags && profile.industry_tags.length > 0) {{
    currentProfile.industry_tags = profile.industry_tags;
    renderTags('industryTags', currentProfile.industry_tags);
  }}
  if (profile.skills && profile.skills.length > 0) {{
    currentProfile.skills = profile.skills;
    renderTags('skillTags', currentProfile.skills);
  }}

  if (!currentProfile.scoring) currentProfile.scoring = {{}};
  if (profile.primary_role_tags && profile.primary_role_tags.length > 0) {{
    currentProfile.scoring.primary_role_tags = profile.primary_role_tags;
  }}
  if (profile.secondary_role_tags && profile.secondary_role_tags.length > 0) {{
    currentProfile.scoring.secondary_role_tags = profile.secondary_role_tags;
  }}

  autoSaveProfile();
  showToast('Resume parsed — review your profile tags');
}}

// --- Analyze Pasted Text ---
async function analyzeResumeText() {{
  const text = document.getElementById('resumeSummary').value.trim();
  if (!text) {{
    const s = document.getElementById('analyzeTextStatus');
    s.textContent = 'Paste your resume text above first';
    s.className = 'upload-status error';
    return;
  }}

  const btn = document.getElementById('analyzeTextBtn');
  const status = document.getElementById('analyzeTextStatus');
  const progressPanel = document.getElementById('analyzeTextProgress');

  btn.disabled = true;
  btn.textContent = 'Analyzing...';
  status.textContent = '';
  status.className = 'upload-status';
  progressPanel.innerHTML = '';
  progressPanel.classList.add('visible');

  addTextProgressLine('Sending text to server...');

  try {{
    const resp = await fetch('/api/analyze-text', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{ text: text }})
    }});

    if (!resp.ok && !resp.body) {{
      const err = await resp.json().catch(() => ({{}}));
      status.textContent = err.error || 'Analysis failed';
      status.className = 'upload-status error';
      addTextProgressLine(err.error || 'Failed', true);
      btn.disabled = false;
      btn.textContent = 'Analyze Text';
      return;
    }}

    addTextProgressLine('Processing (this may take a minute)...');

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let profileResult = null;

    while (true) {{
      const {{ done, value }} = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, {{ stream: true }});

      const lines = buffer.split('\\n');
      buffer = lines.pop();
      for (const line of lines) {{
        if (!line.trim()) continue;
        try {{
          const msg = JSON.parse(line);
          if (msg.type === 'progress') {{
            addTextProgressLine(msg.message);
          }} else if (msg.type === 'result') {{
            profileResult = msg.profile;
          }} else if (msg.type === 'error') {{
            status.textContent = msg.error || 'Analysis failed';
            status.className = 'upload-status error';
            addTextProgressLine(msg.error || 'Failed', true);
          }}
        }} catch(e) {{}}
      }}
    }}

    if (buffer.trim()) {{
      try {{
        const msg = JSON.parse(buffer);
        if (msg.type === 'result') profileResult = msg.profile;
        else if (msg.type === 'error') {{
          status.textContent = msg.error || 'Failed';
          status.className = 'upload-status error';
        }}
      }} catch(e) {{}}
    }}

    if (profileResult) {{
      applyResumeProfile(profileResult);
      addTextProgressLine('Tags populated — review and save when ready', false, true);
      status.textContent = 'Tags extracted — review below';
    }}

  }} catch(e) {{
    status.textContent = 'Analysis failed: ' + e.message;
    status.className = 'upload-status error';
    addTextProgressLine('Failed: ' + e.message, true);
  }}

  btn.disabled = false;
  btn.textContent = 'Analyze Text';
}}

function addTextProgressLine(msg, isError, isDone) {{
  const panel = document.getElementById('analyzeTextProgress');
  const line = document.createElement('div');
  line.className = 'rp-line';
  if (isError) line.className += ' error';
  if (isDone) line.className += ' done';
  line.textContent = msg;
  panel.appendChild(line);
  panel.scrollTop = panel.scrollHeight;
}}

// --- Run Search ---
function formatAge(isoDate) {{
  if (!isoDate) return '';
  try {{
    const posted = new Date(isoDate);
    const now = new Date();
    const ms = now - posted;
    const days = Math.floor(ms / 86400000);
    if (days === 0) {{
      const hours = Math.floor(ms / 3600000);
      return hours === 0 ? 'Just now' : hours + 'h ago';
    }}
    if (days === 1) return '1 day ago';
    if (days < 7) return days + ' days ago';
    if (days < 14) return '1 week ago';
    if (days < 30) return Math.floor(days / 7) + ' weeks ago';
    if (days < 60) return '1 month ago';
    return Math.floor(days / 30) + ' months ago';
  }} catch(e) {{ return ''; }}
}}

function formatSalary(min, max) {{
  if (min && max) return '$' + min.toLocaleString() + '\\u2013$' + max.toLocaleString();
  if (min) return '$' + min.toLocaleString() + '+';
  return '';
}}

function buildJobRow(job) {{
  const pOrder = {{high: 0, medium: 1, low: 2}};
  const score = job.score || 0;
  const priority = job.priority || 'low';
  const salMin = job.salary_min || 0;
  const salMax = job.salary_max || 0;
  const posted = job.posted_date || '';
  const tr = document.createElement('tr');
  tr.dataset.priority = priority;
  tr.dataset.posted = posted;
  tr.innerHTML = `
    <td data-sort="${{score}}" class="score">${{Math.round(score)}}</td>
    <td data-sort="${{pOrder[priority] ?? 2}}" class="priority-${{priority}}">${{escapeHtml(priority)}}</td>
    <td><a href="${{escapeHtml(job.url || '#')}}" target="_blank" class="job-title">${{escapeHtml(job.title)}}</a></td>
    <td class="company">${{escapeHtml(job.company)}}</td>
    <td data-sort="${{salMin}}" class="salary">${{formatSalary(salMin, salMax)}}</td>
    <td>${{escapeHtml(job.location)}}</td>
    <td data-sort="${{posted}}" class="age">${{formatAge(posted)}}</td>
    <td><span class="source-badge">${{escapeHtml(job.source)}}</span></td>
    <td class="summary">${{escapeHtml(job.summary)}}</td>`;
  return tr;
}}

function loadResults(jobs) {{
  // Update jobData for re-scoring
  jobData.length = 0;
  jobs.forEach(j => jobData.push({{
    title: j.title || '', company: j.company || '',
    description: (j.description || '').substring(0, 3000),
    salary_min: j.salary_min || 0, salary_max: j.salary_max || 0,
    location: j.location || ''
  }}));

  // Rebuild table
  const wrap = document.querySelector('.table-wrap');
  let table = document.getElementById('jobTable');
  if (!table && jobs.length > 0) {{
    // Remove "no results" message and create table
    wrap.innerHTML = `<table id="jobTable">
      <thead><tr>
        <th onclick="sortTable(0)">Score <span class="arrow"></span></th>
        <th onclick="sortTable(1)">Priority <span class="arrow"></span></th>
        <th onclick="sortTable(2)">Title <span class="arrow"></span></th>
        <th onclick="sortTable(3)">Company <span class="arrow"></span></th>
        <th onclick="sortTable(4)">Salary <span class="arrow"></span></th>
        <th onclick="sortTable(5)">Location <span class="arrow"></span></th>
        <th onclick="sortTable(6)">Posted <span class="arrow"></span></th>
        <th onclick="sortTable(7)">Source <span class="arrow"></span></th>
        <th>Summary</th>
      </tr></thead><tbody></tbody></table>`;
    table = document.getElementById('jobTable');
  }}

  if (jobs.length === 0) {{
    wrap.innerHTML = "<p class='empty'>No new matching jobs found.</p>";
    document.getElementById('statTotal').textContent = 0;
    document.getElementById('statHigh').textContent = 0;
    document.getElementById('statMed').textContent = 0;
    document.getElementById('statLow').textContent = 0;
    return;
  }}

  const tbody = table.querySelector('tbody');
  tbody.innerHTML = '';
  jobs.forEach(j => tbody.appendChild(buildJobRow(j)));

  // Update stats
  let h=0, m=0, l=0;
  jobs.forEach(j => {{
    if (j.priority === 'high') h++;
    else if (j.priority === 'medium') m++;
    else l++;
  }});
  document.getElementById('statTotal').textContent = jobs.length;
  document.getElementById('statHigh').textContent = h;
  document.getElementById('statMed').textContent = m;
  document.getElementById('statLow').textContent = l;

  // Reset filters
  currentPriority = 'all';
  currentAge = 'all';
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  document.querySelector('.filter-btn[data-priority="all"]').classList.add('active');
  document.querySelectorAll('.age-btn').forEach(b => b.classList.remove('active'));
  document.querySelector('.age-btn[data-age="all"]').classList.add('active');
  document.getElementById('searchBox').value = '';
  document.getElementById('filterCount').textContent = '';
}}

function addProgressLine(msg) {{
  const panel = document.getElementById('progressPanel');
  const line = document.createElement('div');
  line.className = 'progress-line';
  // Highlight phases and AI scoring lines
  if (msg.includes('Phase') || msg.includes('===')) line.className += ' phase';
  else if (msg.includes('AI scored')) line.className += ' ai';
  else if (msg.includes('Pipeline complete')) line.className += ' done';
  line.textContent = msg;
  panel.appendChild(line);
  panel.scrollTop = panel.scrollHeight;
}}

async function runSearch() {{
  const btn = document.getElementById('runSearchBtn');
  const status = document.getElementById('searchStatus');
  const panel = document.getElementById('progressPanel');
  btn.disabled = true;
  btn.textContent = 'Searching...';
  status.textContent = '';
  panel.innerHTML = '';
  panel.classList.add('visible');

  try {{
    readProfileFromUI();
    localStorage.setItem('autojobsearch_profile', JSON.stringify(currentProfile));

    const resp = await fetch('/api/search', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify(currentProfile)
    }});

    if (resp.status === 409) {{
      status.textContent = 'Search already in progress';
      btn.disabled = false;
      btn.textContent = 'Run Search';
      return;
    }}

    // Read streaming NDJSON response
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let resultJobs = null;

    while (true) {{
      const {{ done, value }} = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, {{ stream: true }});

      // Process complete lines
      const lines = buffer.split('\\n');
      buffer = lines.pop(); // Keep incomplete line in buffer
      for (const line of lines) {{
        if (!line.trim()) continue;
        try {{
          const msg = JSON.parse(line);
          if (msg.type === 'progress') {{
            addProgressLine(msg.message);
          }} else if (msg.type === 'result') {{
            resultJobs = msg.jobs || [];
          }} else if (msg.type === 'error') {{
            addProgressLine('ERROR: ' + (msg.error || 'Pipeline failed'));
            const errLine = panel.lastChild;
            if (errLine) errLine.className = 'progress-line error';
          }}
        }} catch(e) {{ /* skip malformed lines */ }}
      }}
    }}

    // Process any remaining buffer
    if (buffer.trim()) {{
      try {{
        const msg = JSON.parse(buffer);
        if (msg.type === 'result') resultJobs = msg.jobs || [];
      }} catch(e) {{}}
    }}

    if (resultJobs !== null) {{
      loadResults(resultJobs);
      const count = resultJobs.length;
      addProgressLine(count > 0 ? 'Done — ' + count + ' results loaded' : 'Done — no new results');
      if (panel.lastChild) panel.lastChild.className = 'progress-line done';
      status.textContent = count > 0 ? count + ' results' : 'No new results';
      // Auto-hide progress after a delay
      setTimeout(() => {{ panel.classList.remove('visible'); }}, 8000);
    }}
  }} catch(e) {{
    addProgressLine('Failed: ' + e.message);
    if (panel.lastChild) panel.lastChild.className = 'progress-line error';
    status.textContent = 'Failed';
  }}
  btn.disabled = false;
  btn.textContent = 'Run Search';
}}

let currentPriority = 'all';
let currentAge = 'all';
let sortCol = 0, sortAsc = false;

// --- Ollama model loading ---
async function loadModels() {{
  const sel = document.getElementById('modelSelect');
  const status = document.getElementById('ollamaStatus');
  const btn = document.getElementById('rescoreBtn');
  try {{
    const resp = await fetch(OLLAMA_URL + '/api/tags');
    const data = await resp.json();
    const models = data.models || [];
    sel.innerHTML = models.map(m => {{
      const isDefault = m.name === DEFAULT_MODEL;
      const label = isDefault ? '\u2713 ' + escapeHtml(m.name) : '  ' + escapeHtml(m.name);
      return `<option value="${{escapeHtml(m.name)}}"${{isDefault ? ' selected' : ''}}>${{label}}</option>`;
    }}).join('');
    if (models.length > 0) {{
      btn.disabled = false;
      const defaultFound = models.some(m => m.name === DEFAULT_MODEL);
      status.textContent = defaultFound
        ? DEFAULT_MODEL + ' (default)'
        : models.length + ' models available';
    }} else {{
      sel.innerHTML = '<option value="">No models found</option>';
      status.textContent = 'No models';
    }}
  }} catch(e) {{
    sel.innerHTML = '<option value="">Ollama not running</option>';
    status.textContent = 'Ollama offline';
    btn.disabled = true;
  }}
}}
loadModels();
renderProfile();

// --- AI re-scoring ---
function buildPrompt(job) {{
  readProfileFromUI();
  const template = currentProfile.ai_prompt_template || '';
  return template
    .replaceAll('$resume_summary', currentProfile.resume_summary || '')
    .replaceAll('$title', job.title || '')
    .replaceAll('$company', job.company || '')
    .replaceAll('$description', (job.description || '').substring(0, 2000))
    .replaceAll('$salary_min', String(job.salary_min || 0))
    .replaceAll('$salary_max', String(job.salary_max || 0))
    .replaceAll('$location', job.location || '');
}}

async function rescoreAll() {{
  const model = document.getElementById('modelSelect').value;
  if (!model) return;
  const btn = document.getElementById('rescoreBtn');
  const progress = document.getElementById('ollamaProgress');
  btn.disabled = true;
  btn.textContent = 'Scoring...';

  const rows = document.querySelectorAll('#jobTable tbody tr');
  const rowArr = Array.from(rows);
  rowArr.sort((a,b) => parseFloat(b.children[0].dataset.sort) - parseFloat(a.children[0].dataset.sort));
  const toScore = rowArr.slice(0, 15);

  for (let i = 0; i < toScore.length; i++) {{
    const row = toScore[i];
    const idx = Array.from(rows).indexOf(row);
    progress.textContent = `${{i+1}}/15`;
    try {{
      const job = jobData[idx];
      if (!job) continue;
      const prompt = buildPrompt(job);

      const resp = await fetch(OLLAMA_URL + '/api/chat', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{
          model: model,
          messages: [{{role: 'user', content: prompt}}],
          stream: false,
          format: 'json'
        }})
      }});
      const data = await resp.json();
      let text = data.message.content.trim();
      if (text.startsWith('```')) text = text.split('\\n').slice(1).join('\\n').replace(/```$/,'').trim();
      const result = JSON.parse(text);

      const ruleScore = parseFloat(row.children[0].dataset.sort) || 0;
      const baseScore = Math.min(ruleScore, 50);
      const aiScore = Math.max(0, Math.min(50, parseInt(result.fit_score) || 0));
      const newTotal = baseScore + aiScore;
      const newPriority = result.priority || 'low';

      row.children[0].dataset.sort = newTotal;
      row.children[0].textContent = newTotal;
      row.children[0].classList.add('rescored');
      row.dataset.priority = newPriority;
      row.children[1].dataset.sort = {{'high':0,'medium':1,'low':2}}[newPriority] ?? 2;
      row.children[1].className = 'priority-' + newPriority;
      row.children[1].textContent = newPriority;
      if (result.summary) row.children[row.children.length - 1].textContent = result.summary;
    }} catch(e) {{
      console.warn('Score failed for row', idx, e);
    }}
  }}

  sortCol = 0; sortAsc = false;
  const tbody = document.querySelector('#jobTable tbody');
  const sorted = Array.from(tbody.querySelectorAll('tr'));
  sorted.sort((a,b) => parseFloat(b.children[0].dataset.sort) - parseFloat(a.children[0].dataset.sort));
  sorted.forEach(r => tbody.appendChild(r));

  updateStatCounts();
  btn.disabled = false;
  btn.textContent = 'Re-score with AI';
  progress.textContent = 'Done';
  setTimeout(() => {{ progress.textContent = ''; }}, 3000);
}}

function updateStatCounts() {{
  const rows = document.querySelectorAll('#jobTable tbody tr');
  let h=0, m=0, l=0;
  rows.forEach(r => {{
    const p = r.dataset.priority;
    if (p === 'high') h++;
    else if (p === 'medium') m++;
    else l++;
  }});
  document.getElementById('statHigh').textContent = h;
  document.getElementById('statMed').textContent = m;
  document.getElementById('statLow').textContent = l;
  document.getElementById('statTotal').textContent = rows.length;
}}

// --- Filtering ---
function filterTable() {{
  const q = document.getElementById('searchBox').value.toLowerCase();
  const now = new Date();
  const maxAgeDays = currentAge === 'all' ? Infinity : parseInt(currentAge);
  let visible = 0;

  document.querySelectorAll('#jobTable tbody tr').forEach(row => {{
    const text = row.textContent.toLowerCase();
    const priority = row.dataset.priority;
    const posted = row.dataset.posted;

    const matchesSearch = !q || text.includes(q);
    const matchesPriority = currentPriority === 'all' || priority === currentPriority;

    let matchesAge = true;
    if (maxAgeDays !== Infinity && posted) {{
      const postedDate = new Date(posted);
      const ageDays = (now - postedDate) / (1000 * 60 * 60 * 24);
      matchesAge = ageDays <= maxAgeDays;
    }}

    const show = matchesSearch && matchesPriority && matchesAge;
    row.classList.toggle('hidden', !show);
    if (show) visible++;
  }});

  const total = document.querySelectorAll('#jobTable tbody tr').length;
  const countEl = document.getElementById('filterCount');
  if (q || currentPriority !== 'all' || currentAge !== 'all') {{
    countEl.textContent = `Showing ${{visible}} of ${{total}}`;
  }} else {{
    countEl.textContent = '';
  }}
}}

function setPriority(p, btn) {{
  currentPriority = p;
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.querySelectorAll('.stat-card').forEach(c => c.classList.remove('active'));
  const cardMap = {{'all': '.stat-total', 'high': '.stat-high', 'medium': '.stat-med', 'low': '.stat-low'}};
  const card = document.querySelector(cardMap[p]);
  if (card) card.classList.add('active');
  filterTable();
}}

function cardFilter(p) {{
  const btn = document.querySelector(`.filter-btn[data-priority="${{p}}"]`);
  if (btn) setPriority(p, btn);
}}

function setAge(age, btn) {{
  currentAge = age;
  document.querySelectorAll('.age-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  filterTable();
}}

// --- Sorting ---
function sortTable(col) {{
  if (sortCol === col) sortAsc = !sortAsc;
  else {{ sortCol = col; sortAsc = true; }}

  const tbody = document.querySelector('#jobTable tbody');
  const rows = Array.from(tbody.querySelectorAll('tr'));

  rows.sort((a, b) => {{
    let av = a.children[col].dataset.sort || a.children[col].textContent.trim();
    let bv = b.children[col].dataset.sort || b.children[col].textContent.trim();
    const an = parseFloat(av), bn = parseFloat(bv);
    if (!isNaN(an) && !isNaN(bn)) return sortAsc ? an - bn : bn - an;
    return sortAsc ? av.localeCompare(bv) : bv.localeCompare(av);
  }});

  rows.forEach(r => tbody.appendChild(r));

  document.querySelectorAll('#jobTable th .arrow').forEach((a, i) => {{
    a.textContent = i === col ? (sortAsc ? '\\u25B2' : '\\u25BC') : '';
  }});
}}
</script>

</body>
</html>"""

    with open(filepath, "w") as f:
        f.write(content)

    return filepath


def generate_landing_page(output_dir: str = "reports/") -> str:
    """Generate a static landing page (index.html) with no baked-in job data.

    This is the persistent entry point served at localhost:8080.
    Jobs are loaded dynamically via the 'Run Search' button.
    """
    return generate_dashboard([], output_dir=output_dir, filename="index.html")


def _format_age(posted_iso: str) -> str:
    """Format a posted date as a human-readable age string."""
    if not posted_iso:
        return ""
    try:
        from datetime import datetime, timezone
        posted = datetime.fromisoformat(posted_iso)
        now = datetime.now(timezone.utc)
        if posted.tzinfo is None:
            posted = posted.replace(tzinfo=timezone.utc)
        delta = now - posted
        days = delta.days
        if days == 0:
            hours = delta.seconds // 3600
            if hours == 0:
                return "Just now"
            return f"{hours}h ago"
        elif days == 1:
            return "1 day ago"
        elif days < 7:
            return f"{days} days ago"
        elif days < 14:
            return "1 week ago"
        elif days < 30:
            return f"{days // 7} weeks ago"
        elif days < 60:
            return "1 month ago"
        else:
            return f"{days // 30} months ago"
    except (ValueError, TypeError):
        return ""


def _render_row(job: dict) -> str:
    """Render a single table row."""
    title = html.escape(job.get("title", ""))
    company = html.escape(job.get("company", ""))
    url = html.escape(job.get("url", "#"))
    score = job.get("score", 0)
    priority_raw = job.get("priority", "low")
    # Whitelist priority to prevent injection via AI output
    priority = priority_raw if priority_raw in ("high", "medium", "low") else "low"
    source = html.escape(job.get("source", ""))
    location = html.escape(job.get("location", ""))
    summary = html.escape(job.get("summary", ""))
    posted_iso = html.escape(job.get("posted_date", ""))
    age_display = _format_age(job.get("posted_date", ""))

    sal_min = job.get("salary_min", 0)
    sal_max = job.get("salary_max", 0)
    if sal_min and sal_max:
        salary = f"${sal_min:,}&ndash;${sal_max:,}"
        salary_sort = sal_min
    elif sal_min:
        salary = f"${sal_min:,}+"
        salary_sort = sal_min
    else:
        salary = ""
        salary_sort = 0

    priority_order = {"high": 0, "medium": 1, "low": 2}

    return f"""  <tr data-priority="{priority}" data-posted="{posted_iso}">
    <td data-sort="{score}" class="score">{score:.0f}</td>
    <td data-sort="{priority_order.get(priority, 2)}" class="priority-{priority}">{priority}</td>
    <td><a href="{url}" target="_blank" class="job-title">{title}</a></td>
    <td class="company">{company}</td>
    <td data-sort="{salary_sort}" class="salary">{salary}</td>
    <td>{location}</td>
    <td data-sort="{posted_iso}" class="age">{age_display}</td>
    <td><span class="source-badge">{source}</span></td>
    <td class="summary">{summary}</td>
  </tr>"""
