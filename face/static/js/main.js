// ==================== 全局变量 ====================
let mediaStream = null;
let videoProcessing = false;
let currentResults = [];
let originalImageSize = { width: 0, height: 0 };
let frameSkipCounter = 0;
const FRAME_SKIP = 3;

// ==================== Toast 通知系统 ====================
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
    initTabs();
    initSettings();
    initUpload();
    refreshStats();
    refreshPersons();
    refreshRecords();
});

// ==================== 标签切换 ====================
function initTabs() {
    const tabBtns = document.querySelectorAll('.workspace-tab');
    const tabPanes = document.querySelectorAll('.tab-pane');

    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const tabId = btn.dataset.tab;

            tabBtns.forEach(b => {
                b.classList.remove('active');
                b.setAttribute('aria-selected', 'false');
            });
            tabPanes.forEach(c => c.classList.remove('active'));

            btn.classList.add('active');
            btn.setAttribute('aria-selected', 'true');
            document.getElementById(tabId).classList.add('active');
        });
    });
}

// ==================== 设置面板 ====================
function initSettings() {
    const modeRadios = document.querySelectorAll('input[name="mode"]');
    modeRadios.forEach(radio => {
        radio.addEventListener('change', () => {
            const targetSelect = document.getElementById('targetSelect');
            if (document.querySelector('input[name="mode"]:checked').value === 'verification') {
                targetSelect.disabled = false;
                loadTargetPersons();
            } else {
                targetSelect.disabled = true;
                targetSelect.value = '';
            }
        });
    });

    const thresholdSlider = document.getElementById('thresholdSlider');
    const thresholdValue = document.getElementById('thresholdValue');
    thresholdSlider.addEventListener('input', () => {
        thresholdValue.textContent = parseFloat(thresholdSlider.value).toFixed(2);
    });
}

// ==================== 上传功能 ====================
function initUpload() {
    const imageInput = document.getElementById('imageInput');
    const uploadArea = document.getElementById('uploadArea');

    imageInput.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) showPreview(file);
    });

    uploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadArea.classList.add('drag-over');
    });

    uploadArea.addEventListener('dragleave', () => {
        uploadArea.classList.remove('drag-over');
    });

    uploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadArea.classList.remove('drag-over');
        const file = e.dataTransfer.files[0];
        if (file && file.type.startsWith('image/')) {
            showPreview(file);
        }
    });

    document.getElementById('recognizeBtn').addEventListener('click', () => {
        const file = imageInput.files[0];
        if (file) recognizeImage(file);
    });

    function showPreview(file) {
        const reader = new FileReader();
        reader.onload = (e) => {
            const img = new Image();
            img.onload = () => {
                originalImageSize.width = img.naturalWidth;
                originalImageSize.height = img.naturalHeight;

                const container = document.getElementById('uploadArea');
                const containerWidth = container.clientWidth - 4;
                const containerHeight = container.clientHeight - 4;

                const scale = Math.min(
                    containerWidth / img.naturalWidth,
                    containerHeight / img.naturalHeight
                );

                const displayWidth = Math.floor(img.naturalWidth * scale);
                const displayHeight = Math.floor(img.naturalHeight * scale);

                const previewCanvas = document.getElementById('previewCanvas');
                previewCanvas.width = displayWidth;
                previewCanvas.height = displayHeight;

                const ctx = previewCanvas.getContext('2d');
                ctx.drawImage(img, 0, 0, displayWidth, displayHeight);

                document.getElementById('uploadPlaceholder').classList.add('hidden');
                document.getElementById('previewArea').hidden = false;
                document.getElementById('recognizeBtn').disabled = false;
            };
            img.src = e.target.result;
        };
        reader.readAsDataURL(file);
    }
}

function clearUpload() {
    document.getElementById('imageInput').value = '';
    const placeholder = document.getElementById('uploadPlaceholder');
    placeholder.classList.remove('hidden');
    document.getElementById('previewArea').hidden = true;
    document.getElementById('recognizeBtn').disabled = true;
    const canvas = document.getElementById('previewCanvas');
    canvas.getContext('2d').clearRect(0, 0, canvas.width, canvas.height);
    document.getElementById('uploadResults').innerHTML = '<div class="empty-state">上传图片开始识别</div>';
}

// ==================== 识别功能 ====================
async function recognizeImage(file) {
    const resultsDiv = document.getElementById('uploadResults');
    const mode = document.querySelector('input[name="mode"]:checked').value;
    const threshold = parseFloat(document.getElementById('thresholdSlider').value);
    const target = document.getElementById('targetSelect').value;

    if (mode === 'verification' && !target) {
        showToast('请选择目标人员', 'error');
        return;
    }

    resultsDiv.innerHTML = '<div class="empty-state">识别中...</div>';

    const formData = new FormData();
    formData.append('image', file);
    formData.append('mode', mode);
    formData.append('threshold', threshold);
    if (mode === 'verification') {
        formData.append('target', target);
    }

    try {
        const response = await fetch('/api/recognize', {
            method: 'POST',
            body: formData
        });
        const data = await response.json();

        if (data.success) {
            displayResults(data.results, 'uploadResults');
            drawResultsOnCanvas(data.results, document.getElementById('previewCanvas'),
                             originalImageSize.width, originalImageSize.height);
            refreshRecords();
            refreshStats();
        } else {
            resultsDiv.innerHTML = `<div class="empty-state">${data.message}</div>`;
        }
    } catch (error) {
        console.error('识别失败:', error);
        resultsDiv.innerHTML = '<div class="empty-state">识别失败，请重试</div>';
    }
}

function displayResults(results, containerId) {
    const resultsDiv = document.getElementById(containerId);
    if (!results || results.length === 0) {
        resultsDiv.innerHTML = '<div class="empty-state">未检测到人脸</div>';
        return;
    }

    let html = '';
    results.forEach(r => {
        const isUnknown = r.name === 'Unknown' || r.match === false;
        let matchBadge = '';
        if (r.match !== undefined) {
            matchBadge = r.match
                ? '<span class="match-badge match">匹配</span>'
                : '<span class="match-badge no-match">不匹配</span>';
        }
        html += `
            <div class="result-item ${isUnknown ? 'unknown' : ''}">
                <div class="name">${r.name}${matchBadge}</div>
                <div class="similarity">相似度 ${(r.similarity * 100).toFixed(1)}%</div>
                <div class="face-info">位置 (${r.rect.join(', ')})</div>
            </div>
        `;
    });
    resultsDiv.innerHTML = html;
}

function drawResultsOnCanvas(results, canvas, origWidth, origHeight) {
    const ctx = canvas.getContext('2d');
    const scaleX = canvas.width / origWidth;
    const scaleY = canvas.height / origHeight;

    results.forEach(r => {
        const [left, top, right, bottom] = r.rect;
        const isUnknown = r.name === 'Unknown' || r.match === false;

        ctx.strokeStyle = isUnknown ? '#ef4444' : '#3b82f6';
        ctx.lineWidth = 3;
        ctx.strokeRect(left * scaleX, top * scaleY, (right - left) * scaleX, (bottom - top) * scaleY);

        // 标签背景
        const label = r.name === 'Unknown' ? 'Unknown' : `${r.name}: ${(r.similarity * 100).toFixed(0)}%`;
        ctx.font = '600 14px "DM Sans", sans-serif';
        const textWidth = ctx.measureText(label).width;
        const labelY = (top - 5) * scaleY;

        ctx.fillStyle = isUnknown ? 'rgba(239,68,68,0.85)' : 'rgba(59,130,246,0.85)';
        ctx.fillRect(left * scaleX, labelY - 16, textWidth + 12, 20);

        ctx.fillStyle = '#fff';
        ctx.fillText(label, left * scaleX + 6, labelY - 2);
    });
}

// ==================== 摄像头实时识别 ====================
async function startCamera() {
    try {
        mediaStream = await navigator.mediaDevices.getUserMedia({
            video: { width: 640, height: 480, facingMode: 'user' }
        });

        const videoElement = document.getElementById('videoElement');
        videoElement.srcObject = mediaStream;
        videoElement.classList.add('active');
        document.getElementById('videoPlaceholder').classList.add('hidden');

        document.getElementById('startCameraBtn').disabled = true;
        document.getElementById('stopCameraBtn').disabled = false;
        document.getElementById('cameraStatus').classList.add('active');

        videoElement.onloadedmetadata = () => {
            startVideoProcessing();
        };

        showToast('摄像头已开启', 'success');
    } catch (error) {
        console.error('无法打开摄像头:', error);
        showToast('无法打开摄像头，请检查权限', 'error');
    }
}

function stopCamera() {
    if (mediaStream) {
        mediaStream.getTracks().forEach(track => track.stop());
        mediaStream = null;
    }

    const videoElement = document.getElementById('videoElement');
    videoElement.srcObject = null;
    videoElement.classList.remove('active');
    document.getElementById('videoPlaceholder').classList.remove('hidden');

    document.getElementById('startCameraBtn').disabled = false;
    document.getElementById('stopCameraBtn').disabled = true;
    document.getElementById('cameraStatus').classList.remove('active');

    videoProcessing = false;
    showToast('摄像头已关闭', 'info');
}

async function startVideoProcessing() {
    videoProcessing = true;
    frameSkipCounter = 0;
    processVideoFrame();
}

async function processVideoFrame() {
    if (!videoProcessing) return;

    frameSkipCounter++;
    if (frameSkipCounter < FRAME_SKIP) {
        requestAnimationFrame(processVideoFrame);
        return;
    }
    frameSkipCounter = 0;

    const videoElement = document.getElementById('videoElement');
    const canvas = document.getElementById('videoCanvas');
    const ctx = canvas.getContext('2d');

    canvas.width = videoElement.videoWidth || 640;
    canvas.height = videoElement.videoHeight || 480;

    ctx.drawImage(videoElement, 0, 0, canvas.width, canvas.height);

    try {
        const blob = await new Promise(resolve => {
            canvas.toBlob(resolve, 'image/jpeg', 0.8);
        });

        const formData = new FormData();
        formData.append('image', blob, 'frame.jpg');
        formData.append('mode', document.querySelector('input[name="mode"]:checked').value);
        formData.append('threshold', parseFloat(document.getElementById('thresholdSlider').value));
        const target = document.getElementById('targetSelect').value;
        if (document.querySelector('input[name="mode"]:checked').value === 'verification' && target) {
            formData.append('target', target);
        }

        const response = await fetch('/api/recognize', {
            method: 'POST',
            body: formData
        });
        const data = await response.json();

        if (data.success && data.results) {
            drawVideoResults(data.results, ctx, canvas.width, canvas.height);
            displayRealtimeResults(data.results);
        }
    } catch (error) {
        console.error('视频帧处理失败:', error);
    }

    setTimeout(processVideoFrame, 100);
}

function drawVideoResults(results, ctx, width, height) {
    results.forEach(r => {
        const [left, top, right, bottom] = r.rect;
        const isUnknown = r.name === 'Unknown' || r.match === false;

        ctx.strokeStyle = isUnknown ? '#ef4444' : '#3b82f6';
        ctx.lineWidth = 2;
        ctx.strokeRect(left, top, right - left, bottom - top);

        const label = r.name === 'Unknown' ? 'Unknown' : `${r.name}: ${(r.similarity * 100).toFixed(0)}%`;
        ctx.font = '600 13px "DM Sans", sans-serif';
        const textWidth = ctx.measureText(label).width;

        ctx.fillStyle = isUnknown ? 'rgba(239,68,68,0.85)' : 'rgba(59,130,246,0.85)';
        ctx.fillRect(left, top - 22, textWidth + 12, 20);

        ctx.fillStyle = '#fff';
        ctx.fillText(label, left + 6, top - 7);
    });
}

function displayRealtimeResults(results) {
    const resultsDiv = document.getElementById('realtimeResults');
    if (!results || results.length === 0) {
        resultsDiv.innerHTML = '<div class="empty-state">未检测到人脸</div>';
        return;
    }

    let html = '';
    results.forEach(r => {
        const isUnknown = r.name === 'Unknown' || r.match === false;
        let matchBadge = '';
        if (r.match !== undefined) {
            matchBadge = r.match
                ? '<span class="match-badge match">匹配</span>'
                : '<span class="match-badge no-match">不匹配</span>';
        }
        html += `
            <div class="result-item ${isUnknown ? 'unknown' : ''}">
                <div class="name">${r.name}${matchBadge}</div>
                <div class="similarity">相似度 ${(r.similarity * 100).toFixed(1)}%</div>
            </div>
        `;
    });
    resultsDiv.innerHTML = html;
}

// ==================== 面板人员录入 (已移至独立页面 /person) ====================

// ==================== 数据刷新 ====================
async function refreshStats() {
    try {
        const response = await fetch('/api/stats');
        const data = await response.json();
        document.getElementById('personCount').textContent = data.person_count;
        document.getElementById('recordCount').textContent = data.record_count;
    } catch (error) {
        console.error('获取统计失败:', error);
    }
}

async function refreshPersons() {
    try {
        const response = await fetch('/api/persons');
        const data = await response.json();
        loadTargetPersons(data.persons || []);
    } catch (error) {
        console.error('获取人员列表失败:', error);
    }
}

function loadTargetPersons(persons) {
    const targetSelect = document.getElementById('targetSelect');
    let options = '<option value="">-- 请选择 --</option>';
    (persons || []).forEach(name => {
        options += `<option value="${name}">${name}</option>`;
    });
    targetSelect.innerHTML = options;
}

async function refreshRecords() {
    try {
        const response = await fetch('/api/records?limit=50');
        const data = await response.json();
        const listDiv = document.getElementById('recordsList');

        if (data.records && data.records.length > 0) {
            let html = '';
            data.records.slice().reverse().forEach(r => {
                const isUnknown = r.name.includes('Unknown') || r.name.includes('否认');
                html += `
                    <div class="record-item">
                        <span class="name">${r.name}</span>
                        <span>${(r.confidence * 100).toFixed(0)}%</span>
                        <span class="time">${r.timestamp.split(' ')[1] || r.timestamp}</span>
                    </div>
                `;
            });
            listDiv.innerHTML = html;
        } else {
            listDiv.innerHTML = '<div class="empty-state small">暂无记录</div>';
        }
    } catch (error) {
        console.error('获取记录失败:', error);
    }
}

async function clearRecords() {
    if (!confirm('确定清空所有识别记录?')) return;

    try {
        const response = await fetch('/api/records/clear', {
            method: 'POST'
        });
        const data = await response.json();

        if (data.success) {
            showToast('记录已清空', 'success');
            refreshRecords();
            refreshStats();
        }
    } catch (error) {
        console.error('清空记录失败:', error);
        showToast('清空失败', 'error');
    }
}

// ==================== 特征信息弹窗 ====================
async function showFeatureInfo() {
    try {
        const response = await fetch('/api/features');
        const data = await response.json();

        let html = '<div class="feature-grid">';
        data.feature_types.forEach(f => {
            const isActive = f.id === data.current_type;
            html += `
                <div class="feature-card ${isActive ? 'active' : ''}">
                    <h4>${f.name}${isActive ? ' (当前)' : ''}</h4>
                    <p>${f.description}</p>
                    <span class="dim">${f.dimension}d</span>
                </div>
            `;
        });
        html += '</div>';

        document.getElementById('featureModalBody').innerHTML = html;
        document.getElementById('featureModal').hidden = false;
    } catch (error) {
        console.error('获取特征信息失败:', error);
        showToast('获取特征信息失败', 'error');
    }
}

function closeFeatureModal() {
    document.getElementById('featureModal').hidden = true;
}

// ==================== 事件绑定 ====================
document.getElementById('startCameraBtn').addEventListener('click', startCamera);
document.getElementById('stopCameraBtn').addEventListener('click', stopCamera);
