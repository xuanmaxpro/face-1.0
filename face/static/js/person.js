// ==================== Toast ====================
function showToast(message, type = 'info', duration = 3000) {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;

    const icons = {
        success: '<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="#22c55e" stroke-width="2"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
        error: '<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
        info: '<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>'
    };

    toast.innerHTML = `${icons[type] || icons.info}<span>${message}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
        toast.classList.add('toast-out');
        toast.addEventListener('animationend', () => toast.remove());
    }, duration);
}

// ==================== 初始化 ====================
document.addEventListener('DOMContentLoaded', () => {
    refreshPersons();
    refreshStats();
    initFileDrop();
    initFilePreview();
});

// ==================== 人员列表 ====================
async function refreshPersons() {
    try {
        const response = await fetch('/api/persons');
        const data = await response.json();
        const grid = document.getElementById('personGrid');

        if (data.persons && data.persons.length > 0) {
            let html = '';
            data.persons.forEach(name => {
                html += `
                    <div class="person-card">
                        <div class="person-avatar">${name.charAt(0).toUpperCase()}</div>
                        <div class="person-info">
                            <div class="person-name">${name}</div>
                        </div>
                        <button class="btn btn-icon btn-danger-icon" onclick="deletePerson('${name}')" title="删除">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>
                        </button>
                    </div>
                `;
            });
            grid.innerHTML = html;
        } else {
            grid.innerHTML = `
                <div class="empty-state" style="grid-column: 1 / -1; min-height: 300px;">
                    <div style="text-align:center">
                        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.2"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                        <p style="margin-top:12px">暂无已录入人员</p>
                        <p style="font-size:12px;color:var(--text-tertiary);margin-top:4px">点击右上角按钮开始录入</p>
                    </div>
                </div>
            `;
        }
    } catch (error) {
        console.error('获取人员列表失败:', error);
    }
}

async function refreshStats() {
    try {
        const response = await fetch('/api/stats');
        const data = await response.json();
        document.getElementById('personCount').textContent = data.person_count;
    } catch (error) {
        console.error('获取统计失败:', error);
    }
}

async function deletePerson(name) {
    if (!confirm(`确定删除 ${name} 吗?`)) return;

    try {
        const response = await fetch('/api/person/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });
        const data = await response.json();

        if (data.success) {
            showToast(data.message, 'success');
            refreshPersons();
            refreshStats();
        } else {
            showToast(data.message, 'error');
        }
    } catch (error) {
        console.error('删除失败:', error);
        showToast('删除失败，请重试', 'error');
    }
}

// ==================== 录入弹窗 ====================
function openEnrollModal() {
    document.getElementById('enrollModal').hidden = false;
}

function closeEnrollModal() {
    document.getElementById('enrollModal').hidden = true;
    document.getElementById('enrollName').value = '';
    document.getElementById('enrollImages').value = '';
    document.getElementById('enrollPreview').innerHTML = '';
}

async function submitEnroll() {
    const name = document.getElementById('enrollName').value.trim();
    const files = document.getElementById('enrollImages').files;

    if (!name) {
        showToast('请输入姓名', 'error');
        return;
    }

    if (!files || files.length === 0) {
        showToast('请选择图片', 'error');
        return;
    }

    const btn = document.getElementById('enrollSubmitBtn');
    btn.disabled = true;
    btn.textContent = '录入中...';

    const formData = new FormData();
    formData.append('name', name);
    Array.from(files).forEach(file => {
        formData.append('images', file);
    });

    try {
        const response = await fetch('/api/person/add', {
            method: 'POST',
            body: formData
        });
        const data = await response.json();

        if (data.success) {
            showToast(data.message, 'success');
            closeEnrollModal();
            refreshPersons();
            refreshStats();
        } else {
            showToast(data.message, 'error');
        }
    } catch (error) {
        console.error('录入失败:', error);
        showToast('录入失败，请重试', 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = '确认录入';
    }
}

// ==================== 文件拖拽 ====================
function initFileDrop() {
    const dropZone = document.getElementById('fileDropZone');
    const fileInput = document.getElementById('enrollImages');

    dropZone.addEventListener('click', (e) => {
        if (e.target.tagName !== 'BUTTON') {
            fileInput.click();
        }
    });

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('drag-over');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('drag-over');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('drag-over');
        if (e.dataTransfer.files.length > 0) {
            fileInput.files = e.dataTransfer.files;
            updatePreview(e.dataTransfer.files);
        }
    });
}

function initFilePreview() {
    document.getElementById('enrollImages').addEventListener('change', (e) => {
        updatePreview(e.target.files);
    });
}

function updatePreview(files) {
    const preview = document.getElementById('enrollPreview');
    preview.innerHTML = '';
    Array.from(files).forEach(file => {
        const reader = new FileReader();
        reader.onload = (evt) => {
            const img = document.createElement('img');
            img.src = evt.target.result;
            preview.appendChild(img);
        };
        reader.readAsDataURL(file);
    });
}
