#!/usr/bin/env python3
"""
Semantic Scholar Paper Explorer
A local web application to explore papers, their references, citations, and connections.
"""

import requests
from flask import Flask, render_template_string, jsonify, request
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from datetime import datetime
import time

app = Flask(__name__)

# Global state for papers
papers_db: Dict[str, 'Paper'] = {}
edges: Set[tuple] = set()  # Set of (paper_id1, paper_id2) tuples


@dataclass
class Paper:
    paper_id: str
    title: str
    authors: List[str]
    year: Optional[int]
    publication_date: Optional[str]  # Format: YYYY-MM-DD
    citation_count: int
    url: Optional[str]
    references: List[str] = field(default_factory=list)  # List of paper IDs
    citations: List[str] = field(default_factory=list)   # List of paper IDs
    edge_count: int = 0
    is_main: bool = False  # Whether this was directly added by user


def fetch_paper_from_semantic_scholar(paper_id: str) -> Optional[dict]:
    """Fetch paper details from Semantic Scholar API."""
    base_url = "https://api.semanticscholar.org/graph/v1/paper"
    fields = "paperId,title,authors,year,publicationDate,citationCount,url,references.paperId,references.title,references.authors,references.year,references.publicationDate,references.citationCount,references.url,citations.paperId,citations.title,citations.authors,citations.year,citations.publicationDate,citations.citationCount,citations.url"
    
    url = f"{base_url}/{paper_id}?fields={fields}"
    
    try:
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 429:
            # Rate limited, wait and retry
            time.sleep(1)
            response = requests.get(url, timeout=30)
            if response.status_code == 200:
                return response.json()
        return None
    except requests.RequestException as e:
        print(f"Error fetching paper {paper_id}: {e}")
        return None


def add_paper_to_db(paper_data: dict, is_main: bool = False) -> Optional[Paper]:
    """Add a paper to the database from API response."""
    paper_id = paper_data.get('paperId')
    if not paper_id:
        return None
    
    authors = [a.get('name', 'Unknown') for a in paper_data.get('authors', [])]
    
    # Build Semantic Scholar URL
    url = paper_data.get('url') or f"https://www.semanticscholar.org/paper/{paper_id}"
    
    paper = Paper(
        paper_id=paper_id,
        title=paper_data.get('title', 'Unknown Title'),
        authors=authors[:5],  # Limit to first 5 authors
        year=paper_data.get('year'),
        publication_date=paper_data.get('publicationDate'),
        citation_count=paper_data.get('citationCount', 0),
        url=url,
        is_main=is_main
    )
    
    # If paper already exists and is now being added as main, update that flag
    if paper_id in papers_db:
        if is_main:
            papers_db[paper_id].is_main = True
        return papers_db[paper_id]
    
    papers_db[paper_id] = paper
    return paper


def process_main_paper(paper_id: str) -> dict:
    """Process a main paper: fetch it and all its references/citations."""
    result = {
        'success': False,
        'message': '',
        'paper': None,
        'new_papers': 0,
        'new_edges': 0
    }
    
    # Check if already processed as main
    if paper_id in papers_db and papers_db[paper_id].is_main:
        result['message'] = 'Paper already added'
        result['paper'] = paper_to_dict(papers_db[paper_id])
        return result
    
    # Fetch paper data
    paper_data = fetch_paper_from_semantic_scholar(paper_id)
    if not paper_data:
        result['message'] = 'Failed to fetch paper from Semantic Scholar'
        return result
    
    # Add main paper
    main_paper = add_paper_to_db(paper_data, is_main=True)
    if not main_paper:
        result['message'] = 'Failed to process paper data'
        return result
    
    new_papers = 0
    new_edges = 0
    
    # Process references
    references = paper_data.get('references', []) or []
    for ref in references:
        ref_id = ref.get('paperId')
        if ref_id:
            main_paper.references.append(ref_id)
            
            # Add reference paper to DB if not exists
            if ref_id not in papers_db:
                add_paper_to_db(ref, is_main=False)
                new_papers += 1
            
            # Add edge
            edge = tuple(sorted([paper_id, ref_id]))
            if edge not in edges:
                edges.add(edge)
                new_edges += 1
                papers_db[paper_id].edge_count += 1
                papers_db[ref_id].edge_count += 1
    
    # Process citations
    citations = paper_data.get('citations', []) or []
    for cite in citations:
        cite_id = cite.get('paperId')
        if cite_id:
            main_paper.citations.append(cite_id)
            
            # Add citing paper to DB if not exists
            if cite_id not in papers_db:
                add_paper_to_db(cite, is_main=False)
                new_papers += 1
            
            # Add edge
            edge = tuple(sorted([paper_id, cite_id]))
            if edge not in edges:
                edges.add(edge)
                new_edges += 1
                papers_db[paper_id].edge_count += 1
                papers_db[cite_id].edge_count += 1
    
    result['success'] = True
    result['message'] = f'Added paper with {len(references)} references and {len(citations)} citations'
    result['paper'] = paper_to_dict(main_paper)
    result['new_papers'] = new_papers
    result['new_edges'] = new_edges
    
    return result


def paper_to_dict(paper: Paper) -> dict:
    """Convert Paper object to dictionary for JSON response."""
    return {
        'paper_id': paper.paper_id,
        'title': paper.title,
        'authors': paper.authors,
        'year': paper.year,
        'publication_date': paper.publication_date,
        'citation_count': paper.citation_count,
        'url': paper.url,
        'edge_count': paper.edge_count,
        'is_main': paper.is_main,
        'reference_count': len(paper.references),
        'citing_count': len(paper.citations)
    }


# HTML Template
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Semantic Scholar Explorer</title>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-primary: #0a0a0f;
            --bg-secondary: #12121a;
            --bg-tertiary: #1a1a25;
            --bg-card: #15151f;
            --accent-primary: #6366f1;
            --accent-secondary: #818cf8;
            --accent-glow: rgba(99, 102, 241, 0.3);
            --text-primary: #f1f5f9;
            --text-secondary: #94a3b8;
            --text-muted: #64748b;
            --border-color: #2a2a3a;
            --success: #22c55e;
            --warning: #f59e0b;
            --danger: #ef4444;
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Outfit', sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
            line-height: 1.6;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 2rem;
        }

        header {
            text-align: center;
            margin-bottom: 3rem;
            padding: 2rem 0;
            border-bottom: 1px solid var(--border-color);
        }

        h1 {
            font-size: 2.5rem;
            font-weight: 700;
            background: linear-gradient(135deg, var(--accent-primary), var(--accent-secondary));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 0.5rem;
        }

        .subtitle {
            color: var(--text-secondary);
            font-size: 1.1rem;
            font-weight: 300;
        }

        .input-section {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 2rem;
            margin-bottom: 2rem;
        }

        .input-group {
            display: flex;
            gap: 1rem;
            align-items: stretch;
        }

        input[type="text"] {
            flex: 1;
            padding: 1rem 1.5rem;
            font-size: 1rem;
            font-family: 'JetBrains Mono', monospace;
            background: var(--bg-secondary);
            border: 2px solid var(--border-color);
            border-radius: 12px;
            color: var(--text-primary);
            transition: all 0.3s ease;
        }

        input[type="text"]:focus {
            outline: none;
            border-color: var(--accent-primary);
            box-shadow: 0 0 0 4px var(--accent-glow);
        }

        input[type="text"]::placeholder {
            color: var(--text-muted);
        }

        .btn {
            padding: 1rem 2rem;
            font-size: 1rem;
            font-family: 'Outfit', sans-serif;
            font-weight: 600;
            border: none;
            border-radius: 12px;
            cursor: pointer;
            transition: all 0.3s ease;
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
        }

        .btn-primary {
            background: linear-gradient(135deg, var(--accent-primary), var(--accent-secondary));
            color: white;
        }

        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 24px var(--accent-glow);
        }

        .btn-primary:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }

        .btn-secondary {
            background: var(--bg-tertiary);
            color: var(--text-primary);
            border: 1px solid var(--border-color);
        }

        .btn-secondary:hover {
            background: var(--bg-secondary);
            border-color: var(--accent-primary);
        }

        .stats-bar {
            display: flex;
            gap: 2rem;
            margin-bottom: 2rem;
            padding: 1.5rem;
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
        }

        .stat {
            text-align: center;
        }

        .stat-value {
            font-size: 2rem;
            font-weight: 700;
            color: var(--accent-secondary);
            font-family: 'JetBrains Mono', monospace;
        }

        .stat-label {
            font-size: 0.85rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .controls {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1.5rem;
            flex-wrap: wrap;
            gap: 1rem;
        }

        .sort-controls {
            display: flex;
            align-items: center;
            gap: 1rem;
        }

        .sort-controls label {
            color: var(--text-secondary);
            font-size: 0.9rem;
        }

        select {
            padding: 0.75rem 1.25rem;
            font-size: 0.95rem;
            font-family: 'Outfit', sans-serif;
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            color: var(--text-primary);
            cursor: pointer;
            transition: all 0.3s ease;
        }

        select:focus {
            outline: none;
            border-color: var(--accent-primary);
        }

        .filter-toggle {
            display: flex;
            gap: 0.5rem;
        }

        .filter-btn {
            padding: 0.5rem 1rem;
            font-size: 0.85rem;
            border-radius: 20px;
            border: 1px solid var(--border-color);
            background: transparent;
            color: var(--text-secondary);
            cursor: pointer;
            transition: all 0.3s ease;
        }

        .filter-btn.active {
            background: var(--accent-primary);
            color: white;
            border-color: var(--accent-primary);
        }

        .paper-list {
            display: flex;
            flex-direction: column;
            gap: 1rem;
        }

        .paper-card {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 1.5rem;
            transition: all 0.3s ease;
        }

        .paper-card:hover {
            border-color: var(--accent-primary);
            transform: translateX(4px);
        }

        .paper-card.main-paper {
            border-left: 4px solid var(--accent-primary);
            background: linear-gradient(135deg, var(--bg-card), rgba(99, 102, 241, 0.05));
        }

        .paper-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 1rem;
            margin-bottom: 0.75rem;
        }

        .paper-title {
            font-size: 1.1rem;
            font-weight: 600;
            color: var(--text-primary);
            flex: 1;
            text-decoration: none;
            transition: color 0.2s ease;
        }

        .paper-title:hover {
            color: var(--accent-secondary);
        }

        .paper-badges {
            display: flex;
            gap: 0.5rem;
            flex-shrink: 0;
        }

        .badge {
            padding: 0.25rem 0.75rem;
            font-size: 0.75rem;
            font-weight: 600;
            border-radius: 20px;
            font-family: 'JetBrains Mono', monospace;
        }

        .badge-main {
            background: var(--accent-primary);
            color: white;
        }

        .badge-edges {
            background: rgba(34, 197, 94, 0.2);
            color: var(--success);
            border: 1px solid var(--success);
        }

        .paper-authors {
            font-size: 0.9rem;
            color: var(--text-secondary);
            margin-bottom: 0.5rem;
        }

        .paper-meta {
            display: flex;
            gap: 2rem;
            font-size: 0.85rem;
            color: var(--text-muted);
        }

        .paper-meta span {
            display: flex;
            align-items: center;
            gap: 0.35rem;
        }

        .paper-id {
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.75rem;
            color: var(--text-muted);
            margin-top: 0.75rem;
            padding-top: 0.75rem;
            border-top: 1px solid var(--border-color);
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 0.5rem;
        }

        .paper-link {
            color: var(--accent-secondary);
            text-decoration: none;
            font-family: 'Outfit', sans-serif;
            font-size: 0.8rem;
            transition: color 0.2s ease;
        }

        .paper-link:hover {
            color: var(--accent-primary);
            text-decoration: underline;
        }

        .loading {
            display: none;
            align-items: center;
            justify-content: center;
            padding: 2rem;
            color: var(--text-secondary);
        }

        .loading.active {
            display: flex;
        }

        .spinner {
            width: 24px;
            height: 24px;
            border: 3px solid var(--border-color);
            border-top-color: var(--accent-primary);
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin-right: 1rem;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        .message {
            padding: 1rem 1.5rem;
            border-radius: 8px;
            margin-bottom: 1rem;
            font-size: 0.95rem;
            display: none;
        }

        .message.success {
            display: block;
            background: rgba(34, 197, 94, 0.1);
            border: 1px solid var(--success);
            color: var(--success);
        }

        .message.error {
            display: block;
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid var(--danger);
            color: var(--danger);
        }

        .empty-state {
            text-align: center;
            padding: 4rem 2rem;
            color: var(--text-muted);
        }

        .empty-state svg {
            width: 64px;
            height: 64px;
            margin-bottom: 1rem;
            opacity: 0.5;
        }

        .hint {
            font-size: 0.85rem;
            color: var(--text-muted);
            margin-top: 1rem;
        }

        .hint code {
            background: var(--bg-tertiary);
            padding: 0.2rem 0.5rem;
            border-radius: 4px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.8rem;
        }

        @media (max-width: 768px) {
            .container {
                padding: 1rem;
            }

            .input-group {
                flex-direction: column;
            }

            .stats-bar {
                flex-wrap: wrap;
                gap: 1rem;
            }

            .stat {
                flex: 1;
                min-width: 100px;
            }

            .controls {
                flex-direction: column;
                align-items: stretch;
            }

            .sort-controls {
                flex-wrap: wrap;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Semantic Scholar Explorer</h1>
            <p class="subtitle">Discover paper connections through references and citations</p>
        </header>

        <div class="input-section">
            <div class="input-group">
                <input type="text" id="paperInput" placeholder="Enter Semantic Scholar Paper ID (e.g., 204e3073870fae3d05bcbc2f6a8e263d9b72e776)">
                <button class="btn btn-primary" id="addBtn" onclick="addPaper()">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="12" y1="5" x2="12" y2="19"></line>
                        <line x1="5" y1="12" x2="19" y2="12"></line>
                    </svg>
                    Add Paper
                </button>
            </div>
            <p class="hint">Find paper IDs on <a href="https://www.semanticscholar.org" target="_blank" style="color: var(--accent-secondary);">semanticscholar.org</a> — the ID is in the URL after <code>/paper/</code></p>
        </div>

        <div id="message" class="message"></div>

        <div class="stats-bar">
            <div class="stat">
                <div class="stat-value" id="totalPapers">0</div>
                <div class="stat-label">Total Papers</div>
            </div>
            <div class="stat">
                <div class="stat-value" id="mainPapers">0</div>
                <div class="stat-label">Added Papers</div>
            </div>
            <div class="stat">
                <div class="stat-value" id="totalEdges">0</div>
                <div class="stat-label">Total Edges</div>
            </div>
        </div>

        <div class="controls">
            <div class="sort-controls">
                <label>Primary Sort:</label>
                <select id="primarySort" onchange="updatePaperList()">
                    <option value="edges">Edges (connections)</option>
                    <option value="citations">Citations</option>
                    <option value="year">Year</option>
                </select>
                
                <label>Secondary Sort:</label>
                <select id="secondarySort" onchange="updatePaperList()">
                    <option value="citations">Citations</option>
                    <option value="edges">Edges (connections)</option>
                    <option value="year">Year</option>
                </select>
            </div>
            
            <div class="filter-toggle">
                <button class="filter-btn active" data-filter="all" onclick="setFilter('all')">All Papers</button>
                <button class="filter-btn" data-filter="main" onclick="setFilter('main')">Added Only</button>
            </div>
        </div>

        <div class="loading" id="loading">
            <div class="spinner"></div>
            <span>Fetching paper data...</span>
        </div>

        <div class="paper-list" id="paperList">
            <div class="empty-state">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
                </svg>
                <p>No papers added yet</p>
                <p style="font-size: 0.9rem; margin-top: 0.5rem;">Add a paper ID above to get started</p>
            </div>
        </div>
    </div>

    <script>
        let papers = [];
        let currentFilter = 'all';

        async function addPaper() {
            const input = document.getElementById('paperInput');
            const paperId = input.value.trim();
            
            if (!paperId) {
                showMessage('Please enter a paper ID', 'error');
                return;
            }

            const addBtn = document.getElementById('addBtn');
            const loading = document.getElementById('loading');
            
            addBtn.disabled = true;
            loading.classList.add('active');
            hideMessage();

            try {
                const response = await fetch('/api/add_paper', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ paper_id: paperId })
                });

                const data = await response.json();

                if (data.success) {
                    showMessage(`${data.message} • ${data.new_papers} new papers, ${data.new_edges} new edges`, 'success');
                    input.value = '';
                    await fetchPapers();
                } else {
                    showMessage(data.message || 'Failed to add paper', 'error');
                }
            } catch (error) {
                showMessage('Network error: ' + error.message, 'error');
            } finally {
                addBtn.disabled = false;
                loading.classList.remove('active');
            }
        }

        async function fetchPapers() {
            try {
                const response = await fetch('/api/papers');
                const data = await response.json();
                papers = data.papers;
                updateStats(data.stats);
                updatePaperList();
            } catch (error) {
                console.error('Error fetching papers:', error);
            }
        }

        function updateStats(stats) {
            document.getElementById('totalPapers').textContent = stats.total_papers;
            document.getElementById('mainPapers').textContent = stats.main_papers;
            document.getElementById('totalEdges').textContent = stats.total_edges;
        }

        function updatePaperList() {
            const primarySort = document.getElementById('primarySort').value;
            const secondarySort = document.getElementById('secondarySort').value;
            
            let filteredPapers = currentFilter === 'main' 
                ? papers.filter(p => p.is_main) 
                : [...papers];

            // Sort papers
            filteredPapers.sort((a, b) => {
                // Primary sort
                let comparison = compareBy(a, b, primarySort);
                if (comparison !== 0) return comparison;
                
                // Secondary sort
                return compareBy(a, b, secondarySort);
            });

            renderPapers(filteredPapers);
        }

        function compareBy(a, b, field) {
            switch (field) {
                case 'edges':
                    return (b.edge_count || 0) - (a.edge_count || 0);
                case 'citations':
                    return (b.citation_count || 0) - (a.citation_count || 0);
                case 'year':
                    // Sort by year only (newest first), null years at end
                    if (a.year === null && b.year === null) return 0;
                    if (a.year === null) return 1;
                    if (b.year === null) return -1;
                    return b.year - a.year;
                default:
                    return 0;
            }
        }

        function formatDate(publicationDate, year) {
            if (publicationDate) {
                // Format: YYYY-MM-DD -> Month Day, Year
                const date = new Date(publicationDate + 'T00:00:00');
                const options = { year: 'numeric', month: 'short', day: 'numeric' };
                return date.toLocaleDateString('en-US', options);
            } else if (year) {
                return year.toString();
            }
            return 'N/A';
        }

        function renderPapers(paperList) {
            const container = document.getElementById('paperList');
            
            if (paperList.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                            <path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
                        </svg>
                        <p>${currentFilter === 'main' ? 'No added papers yet' : 'No papers added yet'}</p>
                        <p style="font-size: 0.9rem; margin-top: 0.5rem;">Add a paper ID above to get started</p>
                    </div>
                `;
                return;
            }

            container.innerHTML = paperList.map(paper => `
                <div class="paper-card ${paper.is_main ? 'main-paper' : ''}">
                    <div class="paper-header">
                        <a href="${paper.url}" target="_blank" class="paper-title">${escapeHtml(paper.title)}</a>
                        <div class="paper-badges">
                            ${paper.is_main ? '<span class="badge badge-main">ADDED</span>' : ''}
                            ${paper.edge_count > 0 ? `<span class="badge badge-edges">${paper.edge_count} edges</span>` : ''}
                        </div>
                    </div>
                    <div class="paper-authors">${escapeHtml(paper.authors.join(', '))}</div>
                    <div class="paper-meta">
                        <span>📅 ${formatDate(paper.publication_date, paper.year)}</span>
                        <span>📚 ${paper.citation_count.toLocaleString()} citations</span>
                        ${paper.is_main ? `<span>📖 ${paper.reference_count} refs</span>` : ''}
                        ${paper.is_main ? `<span>🔗 ${paper.citing_count} citing</span>` : ''}
                    </div>
                    <div class="paper-id">
                        <span>ID: ${paper.paper_id}</span>
                        <a href="${paper.url}" target="_blank" class="paper-link">View on Semantic Scholar →</a>
                    </div>
                </div>
            `).join('');
        }

        function setFilter(filter) {
            currentFilter = filter;
            document.querySelectorAll('.filter-btn').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.filter === filter);
            });
            updatePaperList();
        }

        function showMessage(text, type) {
            const msg = document.getElementById('message');
            msg.textContent = text;
            msg.className = 'message ' + type;
        }

        function hideMessage() {
            document.getElementById('message').className = 'message';
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // Handle Enter key
        document.getElementById('paperInput').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') addPaper();
        });

        // Initial fetch
        fetchPapers();
    </script>
</body>
</html>
'''


@app.route('/')
def index():
    """Serve the main page."""
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/add_paper', methods=['POST'])
def api_add_paper():
    """API endpoint to add a new paper."""
    data = request.get_json()
    paper_id = data.get('paper_id', '').strip()
    
    if not paper_id:
        return jsonify({'success': False, 'message': 'Paper ID is required'})
    
    result = process_main_paper(paper_id)
    return jsonify(result)


@app.route('/api/papers', methods=['GET'])
def api_get_papers():
    """API endpoint to get all papers."""
    papers_list = [paper_to_dict(p) for p in papers_db.values()]
    
    stats = {
        'total_papers': len(papers_db),
        'main_papers': sum(1 for p in papers_db.values() if p.is_main),
        'total_edges': len(edges)
    }
    
    return jsonify({'papers': papers_list, 'stats': stats})


@app.route('/api/clear', methods=['POST'])
def api_clear():
    """API endpoint to clear all data."""
    global papers_db, edges
    papers_db = {}
    edges = set()
    return jsonify({'success': True, 'message': 'All data cleared'})


if __name__ == '__main__':
    print("\n" + "="*60)
    print("  Semantic Scholar Paper Explorer")
    print("="*60)
    print("\n  Starting local server...")
    print("  Open your browser to: http://localhost:8080")
    print("\n  Press Ctrl+C to stop the server")
    print("="*60 + "\n")
    
    app.run(host='0.0.0.0', port=8080, debug=True)
