const API_BASE_URL = 'http://localhost:8000/api/v1';

// Tab Navigation
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const tabName = btn.dataset.tab;

        // Update buttons
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');

        // Update content
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        document.getElementById(`${tabName}-tab`).classList.add('active');
    });
});

// Profile Setup Form
document.getElementById('profile-form').addEventListener('submit', async (e) => {
    e.preventDefault();

    const statusEl = document.getElementById('profile-status');
    const submitBtn = e.target.querySelector('button[type="submit"]');

    // Get form data
    const profileData = {
        profile_id: document.getElementById('profile-id').value.trim(),
        name: document.getElementById('name').value.trim(),
        skills: document.getElementById('skills').value.split(',').map(s => s.trim()).filter(s => s),
        experience: document.getElementById('experience').value.trim(),
        past_projects: document.getElementById('projects').value.split('\n').map(p => p.trim()).filter(p => p),
        hourly_rate: parseFloat(document.getElementById('rate').value) || null,
        availability: document.getElementById('availability').value.trim() || null,
    };

    // Show loading
    submitBtn.disabled = true;
    submitBtn.textContent = '⏳ Saving...';
    showStatus(statusEl, 'First-time setup will download AI model (~87MB). Please wait...', 'loading');

    try {
        const response = await fetch(`${API_BASE_URL}/profile/setup`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(profileData),
        });

        const data = await response.json();

        if (response.ok) {
            showStatus(statusEl, `✅ ${data.data.message}`, 'success');
            // Save profile ID for later use
            document.getElementById('gen-profile-id').value = profileData.profile_id;
            document.getElementById('history-profile-id').value = profileData.profile_id;
        } else {
            showStatus(statusEl, `❌ Error: ${data.error?.message || 'Failed to save profile'}`, 'error');
        }
    } catch (error) {
        showStatus(statusEl, `❌ Network error: ${error.message}`, 'error');
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = '💾 Save Profile';
    }
});

// Proposal Generation Form
document.getElementById('proposal-form').addEventListener('submit', async (e) => {
    e.preventDefault();

    const statusEl = document.getElementById('generation-status');
    const outputEl = document.getElementById('proposal-output');
    const textEl = document.getElementById('proposal-text');
    const metadataEl = document.getElementById('proposal-metadata');
    const submitBtn = e.target.querySelector('button[type="submit"]');

    // Get form data
    const jobData = {
        profile_id: document.getElementById('gen-profile-id').value.trim(),
        job_title: document.getElementById('job-title').value.trim(),
        job_description: document.getElementById('job-description').value.trim(),
        budget_range: document.getElementById('budget').value.trim() || null,
    };

    // Reset output
    textEl.textContent = '';
    metadataEl.innerHTML = '';
    outputEl.style.display = 'none';

    // Show loading
    submitBtn.disabled = true;
    submitBtn.textContent = '⏳ Generating...';
    showStatus(statusEl, '🔄 Analyzing job and generating proposal...', 'loading');

    try {
        const response = await fetch(`${API_BASE_URL}/proposal/generate`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(jobData),
        });

        if (!response.ok) {
            throw new Error('Failed to generate proposal');
        }

        // Show output container
        outputEl.style.display = 'block';

        // Stream response using SSE
        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop(); // Keep incomplete line in buffer

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));

                        if (data.text) {
                            // Append proposal chunk
                            textEl.textContent += data.text;
                            textEl.scrollTop = textEl.scrollHeight;
                        } else if (data.status) {
                            // Update status
                            showStatus(statusEl, `${getStatusIcon(data.status)} ${data.message}`, 'info');
                        } else if (data.metadata) {
                            // Show final metadata
                            displayMetadata(metadataEl, data);
                            showStatus(statusEl, '✅ Proposal generated successfully!', 'success');
                        } else if (data.code) {
                            // Error
                            showStatus(statusEl, `❌ Error: ${data.message}`, 'error');
                        }
                    } catch (e) {
                        console.error('Failed to parse SSE data:', e);
                    }
                }
            }
        }
    } catch (error) {
        showStatus(statusEl, `❌ Error: ${error.message}`, 'error');
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = '✨ Generate Proposal';
    }
});

// Copy Proposal Button
document.getElementById('copy-btn').addEventListener('click', () => {
    const text = document.getElementById('proposal-text').textContent;
    navigator.clipboard.writeText(text).then(() => {
        const btn = document.getElementById('copy-btn');
        const originalText = btn.textContent;
        btn.textContent = '✅ Copied!';
        setTimeout(() => {
            btn.textContent = originalText;
        }, 2000);
    });
});

// Load History
document.getElementById('load-history-btn').addEventListener('click', async () => {
    const profileId = document.getElementById('history-profile-id').value.trim();
    const statusEl = document.getElementById('history-status');
    const listEl = document.getElementById('history-list');

    if (!profileId) {
        showStatus(statusEl, '⚠️ Please enter a profile ID', 'error');
        return;
    }

    showStatus(statusEl, '🔄 Loading history...', 'loading');
    listEl.innerHTML = '';

    try {
        const response = await fetch(`${API_BASE_URL}/proposal/history?profile_id=${encodeURIComponent(profileId)}&limit=10`);
        const data = await response.json();

        if (response.ok && data.success) {
            const proposals = data.data.proposals;

            if (proposals.length === 0) {
                showStatus(statusEl, 'ℹ️ No proposals found for this profile', 'info');
                return;
            }

            showStatus(statusEl, `✅ Found ${data.data.total_count} proposals`, 'success');

            proposals.forEach(proposal => {
                const item = createHistoryItem(proposal);
                listEl.appendChild(item);
            });
        } else {
            showStatus(statusEl, `❌ Error: ${data.error?.message || 'Failed to load history'}`, 'error');
        }
    } catch (error) {
        showStatus(statusEl, `❌ Network error: ${error.message}`, 'error');
    }
});

// Helper Functions
function showStatus(element, message, type) {
    element.textContent = message;
    element.className = `status ${type} show`;
}

function getStatusIcon(status) {
    const icons = {
        'analyzing_job': '🔍',
        'retrieving_profile': '📂',
        'generating': '✍️',
    };
    return icons[status] || '⏳';
}

function displayMetadata(element, data) {
    const { metadata, generation_stats } = data;

    element.innerHTML = `
        <h4>📊 Metadata</h4>
        <div class="metadata-item">
            <span class="metadata-label">Confidence Score:</span>
            <span class="metadata-value">${(metadata.confidence_score * 100).toFixed(0)}%</span>
        </div>
        <div class="metadata-item">
            <span class="metadata-label">Skill Match:</span>
            <span class="metadata-value">${metadata.skill_match_percentage.toFixed(0)}%</span>
        </div>
        <div class="metadata-item">
            <span class="metadata-label">Matched Skills:</span>
            <span class="metadata-value">${metadata.matched_skills.join(', ')}</span>
        </div>
        <div class="metadata-item">
            <span class="metadata-label">Relevant Projects:</span>
            <span class="metadata-value">${metadata.relevant_projects.length} found</span>
        </div>
        <div class="metadata-item">
            <span class="metadata-label">Budget Alignment:</span>
            <span class="metadata-value">${formatBudgetAlignment(metadata.budget_alignment)}</span>
        </div>
        <div class="metadata-item">
            <span class="metadata-label">Timeline:</span>
            <span class="metadata-value">${formatTimeline(metadata.timeline_feasibility)}</span>
        </div>
        <div class="metadata-item">
            <span class="metadata-label">Tokens Used:</span>
            <span class="metadata-value">${generation_stats.tokens_used}</span>
        </div>
        <div class="metadata-item">
            <span class="metadata-label">Cost:</span>
            <span class="metadata-value">$${generation_stats.cost_usd.toFixed(4)}</span>
        </div>
        <div class="metadata-item">
            <span class="metadata-label">Generation Time:</span>
            <span class="metadata-value">${(generation_stats.latency_ms / 1000).toFixed(1)}s</span>
        </div>
    `;
}

function createHistoryItem(proposal) {
    const item = document.createElement('div');
    item.className = 'history-item';

    const confidenceBadge = getConfidenceBadge(proposal.confidence_score);
    const date = new Date(proposal.created_at).toLocaleString();

    item.innerHTML = `
        <h4>${proposal.job_title}</h4>
        <p style="color: #666; margin: 10px 0;">${proposal.job_summary}</p>
        <div class="history-meta">
            <span>📅 ${date}</span>
            <span>🎯 ${confidenceBadge}</span>
            <span>💼 ${proposal.matched_skills.slice(0, 3).join(', ')}</span>
            ${proposal.budget_range ? `<span>💰 ${proposal.budget_range}</span>` : ''}
        </div>
    `;

    return item;
}

function getConfidenceBadge(score) {
    const percentage = (score * 100).toFixed(0);
    let badgeClass = 'badge-info';

    if (score >= 0.85) badgeClass = 'badge-success';
    else if (score >= 0.7) badgeClass = 'badge-info';
    else badgeClass = 'badge-warning';

    return `<span class="badge ${badgeClass}">${percentage}% confidence</span>`;
}

function formatBudgetAlignment(alignment) {
    const labels = {
        'excellent': '✅ Excellent',
        'good': '👍 Good',
        'moderate': '⚠️ Moderate',
        'low': '❌ Low',
        'not_specified': 'ℹ️ Not specified',
    };
    return labels[alignment] || alignment;
}

function formatTimeline(timeline) {
    const labels = {
        'urgent': '🚨 Urgent',
        'short_term': '⏱️ Short-term',
        'confirmed': '✅ Confirmed',
        'flexible': '🔄 Flexible',
    };
    return labels[timeline] || timeline;
}
