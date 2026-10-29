// Multi-DWG Project Mode UI Logic
(function() {
  let projectDocs = [];
  let selectedDocIds = new Set();
  let currentProjectPlanId = null;
  let isAnalyzing = false;
  let isApplying = false;

  const escapeHtml = str => String(str||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');

  function formatBytes(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }

  // Switch between Single DWG and Multi-DWG Project Mode
  window.switchAppMode = function(mode) {
    const singleTab = document.getElementById('tabSingleMode');
    const projectTab = document.getElementById('tabProjectMode');
    const singleMain = document.getElementById('singleModeContainer');
    const projectMain = document.getElementById('projectModeContainer');

    if (mode === 'project') {
      if (singleTab) {
        singleTab.classList.remove('active');
        singleTab.style.background = 'transparent';
        singleTab.style.color = '#94a3b8';
      }
      if (projectTab) {
        projectTab.classList.add('active');
        projectTab.style.background = '#2563eb';
        projectTab.style.color = '#ffffff';
      }
      if (singleMain) singleMain.style.display = 'none';
      if (projectMain) projectMain.style.display = 'block';
      loadProjectDocuments();
    } else {
      if (singleTab) {
        singleTab.classList.add('active');
        singleTab.style.background = '#2563eb';
        singleTab.style.color = '#ffffff';
      }
      if (projectTab) {
        projectTab.classList.remove('active');
        projectTab.style.background = 'transparent';
        projectTab.style.color = '#94a3b8';
      }
      if (singleMain) singleMain.style.display = '';
      if (projectMain) projectMain.style.display = 'none';
    }
  };

  // Load project DWGs
  async function loadProjectDocuments() {
    const tbody = document.getElementById('projectDocsTbody');
    const countBadge = document.getElementById('projectDocCountBadge');
    if (!tbody) return;

    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:20px;color:#64748b;">⏳ Đang quét danh sách file DWG trong dự án…</td></tr>';

    try {
      const res = await fetch('/project/documents');
      if (!res.ok) throw new Error('Không thể tải danh sách tài liệu dự án');
      const data = await res.json();
      projectDocs = data.items || [];
      selectedDocIds = new Set(projectDocs.map(d => d.id));

      if (countBadge) {
        countBadge.textContent = `${projectDocs.length} file DWG sẵn sàng`;
      }

      renderDocTable();
    } catch (err) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:20px;color:#dc2626;">❌ Lỗi: ${escapeHtml(err.message)}</td></tr>`;
    }
  }

  function renderDocTable() {
    const tbody = document.getElementById('projectDocsTbody');
    const countLabel = document.getElementById('projectSelectedCountLabel');
    if (!tbody) return;

    if (countLabel) {
      countLabel.textContent = `(Đã chọn ${selectedDocIds.size} / ${projectDocs.length} file)`;
    }

    if (projectDocs.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:20px;color:#64748b;">Chưa có file DWG nào sẵn sàng trong thư mục lưu trữ.</td></tr>';
      return;
    }

    tbody.innerHTML = projectDocs.map(doc => {
      const isChecked = selectedDocIds.has(doc.id);
      const sampleSheetsStr = (doc.sample_sheets || []).map(s => `<span class="sheet-tag-pill">${escapeHtml(s)}</span>`).join(' ') || '<span style="color:#94a3b8">Không có</span>';
      return `
        <tr class="${isChecked ? 'selected-row' : ''}">
          <td style="text-align:center;width:40px;">
            <input type="checkbox" class="project-doc-checkbox" data-id="${doc.id}" ${isChecked ? 'checked' : ''}>
          </td>
          <td>
            <strong>${escapeHtml(doc.filename)}</strong>
            <br><small style="color:#64748b;font-family:monospace;">ID: ${doc.id.substring(0, 8)}…</small>
          </td>
          <td style="text-align:center;">
            <span class="badge-ready" style="font-size:11px;">${doc.sheet_count} khung</span>
          </td>
          <td style="text-align:center;">
            <span style="font-weight:600;color:#0284c7;">${doc.part_count} chi tiết</span>
          </td>
          <td>
            <div style="max-width:320px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
              ${sampleSheetsStr}
            </div>
          </td>
          <td style="text-align:right;color:#64748b;">
            ${formatBytes(doc.size_bytes)}
          </td>
        </tr>
      `;
    }).join('');

    // Attach checkbox events
    tbody.querySelectorAll('.project-doc-checkbox').forEach(cb => {
      cb.addEventListener('change', (e) => {
        const id = e.target.getAttribute('data-id');
        if (e.target.checked) {
          selectedDocIds.add(id);
        } else {
          selectedDocIds.delete(id);
        }
        renderDocTable();
      });
    });
  }

  // Select all / deselect all
  window.toggleSelectAllProjectDocs = function(selectAll) {
    if (selectAll) {
      selectedDocIds = new Set(projectDocs.map(d => d.id));
    } else {
      selectedDocIds.clear();
    }
    renderDocTable();
  };

  // Run Project AI Analysis
  window.runProjectAnalysis = async function() {
    const promptInput = document.getElementById('projectChangeRequest');
    const statusBox = document.getElementById('projectAnalysisStatus');
    const resultsContainer = document.getElementById('projectResultsMount');
    const btnAnalyze = document.getElementById('btnProjectAnalyze');
    const btnApply = document.getElementById('btnProjectApply');

    let requestText = (promptInput ? promptInput.value : '').trim();
    if (!requestText) {
      requestText = 'đổi chi tiết số 6 481.5mm thành 480mm';
      if (promptInput) promptInput.value = requestText;
    }

    if (selectedDocIds.size === 0) {
      if (statusBox) {
        statusBox.innerHTML = '<div class="impact-summary-badge" style="background:#fef2f2;border:1px solid #fecaca;color:#991b1b;">⚠️ Vui lòng chọn ít nhất 1 file DWG trong dự án để phân tích!</div>';
      }
      return;
    }

    isAnalyzing = true;
    if (btnAnalyze) btnAnalyze.disabled = true;
    if (btnApply) btnApply.disabled = true;
    if (statusBox) {
      statusBox.innerHTML = `
        <div class="impact-summary-badge info">
          <span>⏳</span>
          <span>Đang quét và đối chiếu yêu cầu qua <strong>${selectedDocIds.size} file DWG</strong> trong dự án… Vui lòng chờ…</span>
        </div>
      `;
    }
    if (resultsContainer) resultsContainer.innerHTML = '';

    try {
      const res = await fetch('/project/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          document_ids: Array.from(selectedDocIds),
          request: requestText
        })
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Lỗi khi phân tích dự án');
      }

      const data = await res.json();
      renderAnalysisResults(data);
      if (btnApply) btnApply.disabled = data.affected_count === 0;
    } catch (err) {
      if (statusBox) {
        statusBox.innerHTML = `
          <div class="impact-summary-badge" style="background:#fef2f2;border:1px solid #fecaca;color:#991b1b;">
            <span>❌</span>
            <span>Lỗi phân tích: ${escapeHtml(err.message)}</span>
          </div>
        `;
      }
    } finally {
      isAnalyzing = false;
      if (btnAnalyze) btnAnalyze.disabled = false;
    }
  };

  // Render analysis output
  function renderAnalysisResults(data) {
    const statusBox = document.getElementById('projectAnalysisStatus');
    const resultsContainer = document.getElementById('projectResultsMount');
    if (!resultsContainer) return;

    if (statusBox) {
      statusBox.innerHTML = `
        <div class="impact-summary-badge info">
          <span>📊</span>
          <span>${escapeHtml(data.summary)}</span>
        </div>
      `;
    }

    const affected = data.affected_documents || [];
    const unaffected = data.unaffected_documents || [];

    let html = `
      <div class="project-results-container">
        <div class="project-card-header">
          <h3>🎯 1. Các file DWG bị tác động (${affected.length} file)</h3>
        </div>
    `;

    if (affected.length === 0) {
      html += `
        <div style="padding:16px;background:#f8fafc;border-radius:8px;border:1px dashed #cbd5e1;color:#64748b;">
          Không tìm thấy file DWG nào chứa chi tiết hoặc quy cách kích thước khớp với yêu cầu này.
        </div>
      `;
    } else {
      html += `<div class="affected-docs-grid">`;
      affected.forEach(doc => {
        const targets = doc.matched_targets || [];
        const partCodes = doc.part_codes || [];
        const targetsHtml = targets.map(t => {
          const tName = t.name || t.id || 'Khung';
          return `<span class="sheet-tag-pill" title="${escapeHtml(t.id)}">📄 ${escapeHtml(tName)}</span>`;
        }).join(' ');

        const partCodesHtml = partCodes.length > 0
          ? `<div style="font-size:12px;color:#0284c7;font-weight:600;">Mã chi tiết nhận diện: ${partCodes.map(escapeHtml).join(', ')}</div>`
          : '';

        html += `
          <div class="affected-card">
            <div class="affected-card-header">
              <span class="affected-card-title">${escapeHtml(doc.filename)}</span>
              <span class="badge-affected">Bị tác động</span>
            </div>
            <div class="affected-detail">
              ${escapeHtml(doc.explanation)}
            </div>
            ${partCodesHtml}
            <div style="margin-top:4px;">
              <strong style="font-size:11.5px;color:#475569;">Khung bản vẽ & mục tiêu:</strong>
              <div class="affected-sheets-wrap" style="margin-top:4px;">
                ${targetsHtml || '<span style="color:#94a3b8;font-size:12px;">Tự động nhận diện toàn file</span>'}
              </div>
            </div>
            <div style="margin-top:8px;padding-top:8px;border-top:1px solid #f1f5f9;display:flex;justify-content:space-between;align-items:center;">
              <small style="color:#94a3b8;font-family:monospace;">ID: ${doc.document_id.substring(0, 8)}</small>
              <a href="/?doc=${doc.document_id}" target="_blank" style="font-size:12px;color:#2563eb;text-decoration:none;font-weight:700;">
                Mở trong CAD Studio ↗
              </a>
            </div>
          </div>
        `;
      });
      html += `</div>`;
    }

    html += `
        <div class="project-card-header" style="margin-top:20px;">
          <h3>🛡️ 2. Các file DWG không bị tác động (${unaffected.length} file - Giữ nguyên 100%)</h3>
        </div>
        <div class="unaffected-list-wrap">
          <p style="margin:0 0 8px 0;font-weight:600;color:#0f172a;">
            ✓ Tất cả các file dưới đây không chứa chi tiết cần sửa, 100% block và nét vẽ được giữ nguyên bản gốc:
          </p>
          <div style="display:flex;flex-wrap:wrap;gap:8px;">
            ${unaffected.map(u => `<span class="sheet-tag-pill" style="background:#ffffff;">✓ ${escapeHtml(u.filename)}</span>`).join(' ')}
          </div>
        </div>
      </div>
    `;

    resultsContainer.innerHTML = html;
  }

  // Apply Changes and Export Project Package (ZIP)
  window.applyAndExportProject = async function() {
    const promptInput = document.getElementById('projectChangeRequest');
    const statusBox = document.getElementById('projectAnalysisStatus');
    const resultsContainer = document.getElementById('projectResultsMount');
    const btnApply = document.getElementById('btnProjectApply');
    const btnAnalyze = document.getElementById('btnProjectAnalyze');

    let requestText = (promptInput ? promptInput.value : '').trim();
    if (!requestText) {
      requestText = 'đổi chi tiết số 6 481.5mm thành 480mm';
      if (promptInput) promptInput.value = requestText;
    }

    isApplying = true;
    if (btnApply) btnApply.disabled = true;
    if (btnAnalyze) btnAnalyze.disabled = true;

    if (statusBox) {
      statusBox.innerHTML = `
        <div class="impact-summary-badge info">
          <span>⚙️</span>
          <span>Bước 1/2: Đang lập kế hoạch thay đổi đồng bộ trên toàn bộ file DWG bị tác động…</span>
        </div>
      `;
    }

    try {
      // 1. Plan project changes
      const planRes = await fetch('/project/plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          document_ids: Array.from(selectedDocIds),
          request: requestText
        })
      });

      if (!planRes.ok) {
        const err = await planRes.json();
        throw new Error(err.detail || 'Lỗi lập kế hoạch dự án');
      }

      const planData = await planRes.json();
      currentProjectPlanId = planData.project_plan_id;

      if (statusBox) {
        statusBox.innerHTML = `
          <div class="impact-summary-badge info">
            <span>🚀</span>
            <span>Bước 2/2: Đang tự động chỉnh sửa hình học CAD, DIM, cập nhật BOM, xuất file DWG (100% block gốc) và đóng gói ZIP… Vui lòng chờ…</span>
          </div>
        `;
      }

      // 2. Apply and export project changes
      const applyRes = await fetch('/project/apply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_plan_id: currentProjectPlanId
        })
      });

      if (!applyRes.ok) {
        const err = await applyRes.json();
        throw new Error(err.detail || 'Lỗi áp dụng chỉnh sửa dự án');
      }

      const applyData = await applyRes.json();
      renderExportArchiveBanner(applyData);

    } catch (err) {
      if (statusBox) {
        statusBox.innerHTML = `
          <div class="impact-summary-badge" style="background:#fef2f2;border:1px solid #fecaca;color:#991b1b;">
            <span>❌</span>
            <span>Lỗi áp dụng: ${escapeHtml(err.message)}</span>
          </div>
        `;
      }
    } finally {
      isApplying = false;
      if (btnApply) btnApply.disabled = false;
      if (btnAnalyze) btnAnalyze.disabled = false;
    }
  };

  // Render final ZIP Archive banner and individual downloads
  function renderExportArchiveBanner(data) {
    const statusBox = document.getElementById('projectAnalysisStatus');
    const resultsContainer = document.getElementById('projectResultsMount');
    if (!resultsContainer) return;

    const archive = data.archive || {};
    const results = data.results || [];
    const successCount = results.filter(r => r.status === 'success').length;

    if (statusBox) {
      statusBox.innerHTML = `
        <div class="impact-summary-badge" style="background:#f0fdf4;border:1px solid #bbf7d0;color:#166534;">
          <span>🎉</span>
          <span>Đã hoàn thành đồng bộ ${successCount} file DWG trong dự án! Gói tải về trọn gói ZIP đã sẵn sàng.</span>
        </div>
      `;
    }

    let bannerHtml = `
      <div class="project-archive-banner" style="margin-bottom:20px;">
        <div class="project-archive-info">
          <h3>📦 GÓI DỰ ÁN CAD ĐÃ ĐƯỢC XUẤT TRỌN GÓI THÀNH CÔNG</h3>
          <p>
            Tệp nén: <strong>${escapeHtml(archive.filename)}</strong> (${formatBytes(archive.size_bytes)}) · 
            Bao gồm toàn bộ file DWG đã sửa (100% CAD gốc & block được giữ nguyên) + Báo cáo BAO_CAO_THAY_DOI.md
          </p>
        </div>
        <div>
          <a href="${archive.download_url}" class="btn-download-zip" download>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="7 10 12 15 17 10"/>
              <line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
            TẢI TRỌN GÓI DỰ ÁN (ZIP)
          </a>
        </div>
      </div>

      <div class="project-card-header">
        <h3>📋 Danh sách file DWG đã sửa & Tải lẻ từng file</h3>
      </div>
      <div class="affected-docs-grid" style="margin-bottom:20px;">
    `;

    results.forEach(res => {
      const isSuccess = res.status === 'success';
      bannerHtml += `
        <div class="affected-card" style="border-color:${isSuccess ? '#10b981' : '#ef4444'};">
          <div class="affected-card-header">
            <span class="affected-card-title">${escapeHtml(res.clean_filename || res.filename)}</span>
            <span class="${isSuccess ? 'badge-planned' : 'badge-affected'}" style="${isSuccess ? '' : 'background:#fee2e2;color:#991b1b;'}">
              ${isSuccess ? '✓ Đã sửa thành công' : 'Thất bại'}
            </span>
          </div>
          <div class="affected-detail">
            File gốc: <code>${escapeHtml(res.filename)}</code><br>
            Kích thước file DWG đầy đủ: <strong>${formatBytes(res.file_size)}</strong>
          </div>
          ${isSuccess ? `
            <div style="margin-top:10px;display:flex;gap:10px;align-items:center;">
              <a href="${res.download_url}" class="btn-hero-download" download style="font-size:12px;padding:6px 12px;text-decoration:none;display:inline-flex;align-items:center;gap:6px;background:#0284c7;color:#fff;border-radius:6px;font-weight:700;">
                📥 Tải riêng file DWG này
              </a>
              <a href="/?doc=${res.document_id}&revision=${res.revision_id}" target="_blank" style="font-size:12px;color:#2563eb;text-decoration:none;font-weight:600;">
                Xem trước trong Studio ↗
              </a>
            </div>
          ` : `
            <div style="color:#ef4444;font-size:12px;">Lỗi: ${escapeHtml(res.error)}</div>
          `}
        </div>
      `;
    });

    bannerHtml += `</div>`;
    resultsContainer.innerHTML = bannerHtml;
  }

  function initProjectKeydown() {
    const pReq = document.getElementById('projectChangeRequest');
    if (pReq && !pReq.dataset.enterBound) {
      pReq.dataset.enterBound = 'true';
      pReq.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          const btn = document.getElementById('btnProjectAnalyze');
          if (btn && !btn.disabled) {
            btn.click();
          }
        }
      });
    }
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initProjectKeydown);
  } else {
    initProjectKeydown();
  }

})();

