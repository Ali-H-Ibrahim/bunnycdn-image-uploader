/* ── DOM refs ─────────────────────────────────────── */

const form            = document.getElementById('uploadForm');
const uploadSection   = document.getElementById('uploadSection');
const progressSection = document.getElementById('progressSection');
const resultsSection  = document.getElementById('resultsSection');
const submitBtn       = document.getElementById('submitBtn');
const fileInput       = document.getElementById('file');
const fileNameSpan    = document.getElementById('fileName');
const fieldsContainer = document.getElementById('fieldsContainer');
const fieldsPlaceholder = document.getElementById('fieldsPlaceholder');
const toggleManual    = document.getElementById('toggleManual');
const manualEntry     = document.getElementById('manualEntry');
const fileStatsEl     = document.getElementById('fileStats');
const brandChartWrap  = document.getElementById('brandChartWrap');

let pollTimer = null;

/* ── Chart palette ────────────────────────────────── */

const COLORS = [
    '#2563eb','#16a34a','#d97706','#dc2626','#7c3aed',
    '#0891b2','#c026d3','#65a30d','#ea580c','#4f46e5',
    '#059669','#b91c1c','#9333ea','#0284c7','#ca8a04',
];


/* ═══════════════════════════════════════════════════
   File Upload → Detect Fields + Show Stats
   ═══════════════════════════════════════════════════ */

fileInput.addEventListener('change', async () => {
    if (!fileInput.files.length) return;

    const file = fileInput.files[0];
    fileNameSpan.textContent = file.name;
    fileNameSpan.style.color = '#1f2937';

    // Show "analyzing" state
    fieldsPlaceholder.textContent = 'Analyzing file...';
    fieldsPlaceholder.classList.add('loading');
    clearCheckboxes();
    hideFileStats();

    try {
        const text = await file.text();
        const data = JSON.parse(text);
        const products = findProductsArray(data);

        if (!products.length) {
            fieldsPlaceholder.textContent = 'No products found in JSON';
            fieldsPlaceholder.classList.remove('loading');
            return;
        }

        const fields = detectImageFields(products);

        // ── Show stats ──────────────────────────────
        showFileStats(products, fields);

        // ── Show field checkboxes ───────────────────
        if (fields.length) {
            renderCheckboxes(fields);
        } else {
            fieldsPlaceholder.textContent = 'No image URLs detected — use manual input below';
            fieldsPlaceholder.classList.remove('loading');
            toggleManual.classList.remove('hidden');
            manualEntry.classList.remove('hidden');
        }
    } catch (e) {
        console.error('Detection error:', e);
        fieldsPlaceholder.textContent = 'Could not parse JSON — use manual input below';
        fieldsPlaceholder.classList.remove('loading');
        toggleManual.classList.remove('hidden');
        manualEntry.classList.remove('hidden');
    }
});

/* ── Find the products array ─────────────────────── */

function findProductsArray(data) {
    if (Array.isArray(data)) return data;
    if (typeof data === 'object' && data !== null) {
        for (const value of Object.values(data)) {
            if (Array.isArray(value) && value.length && typeof value[0] === 'object') {
                return value;
            }
        }
    }
    return [];
}


/* ═══════════════════════════════════════════════════
   File Stats & Brand Chart
   ═══════════════════════════════════════════════════ */

function showFileStats(products, detectedFields) {
    // Count images
    let totalImages = 0;
    for (const product of products) {
        for (const f of detectedFields) {
            totalImages += countImagesAtPath(product, f.path);
        }
    }

    // Count brands
    const brands = {};
    for (const product of products) {
        const brand = product.Brand || product.brand || product.BRAND || product.brand_name || 'Unknown';
        brands[brand] = (brands[brand] || 0) + 1;
    }

    // Update numbers
    const numBrands = Object.keys(brands).length;
    document.getElementById('fstatProducts').textContent = products.length.toLocaleString();
    document.getElementById('fstatImages').textContent   = totalImages.toLocaleString();
    document.getElementById('fstatBrands').textContent    = numBrands;

    // Brief summary (visible when collapsed)
    document.getElementById('fstatBrief').textContent =
        `${products.length.toLocaleString()} products · ${totalImages.toLocaleString()} images · ${numBrands} brands`;

    fileStatsEl.classList.remove('hidden');

    // Draw brand chart
    const brandEntries = Object.entries(brands)
        .sort((a, b) => b[1] - a[1]);

    if (brandEntries.length > 1) {
        // Group small brands into "Others" if > 8
        let chartData;
        if (brandEntries.length > 8) {
            const top = brandEntries.slice(0, 7);
            const othersCount = brandEntries.slice(7).reduce((s, e) => s + e[1], 0);
            top.push(['Others', othersCount]);
            chartData = top;
        } else {
            chartData = brandEntries;
        }

        const data = chartData.map(([label, value], i) => ({
            label,
            value,
            color: COLORS[i % COLORS.length],
        }));

        brandChartWrap.classList.remove('hidden');
        drawDonutChart(document.getElementById('brandChart'), data, products.length);
        renderLegend(document.getElementById('brandLegend'), data, products.length);
    }
}

function hideFileStats() {
    fileStatsEl.classList.add('hidden');
    fileStatsEl.open = false;
    brandChartWrap.classList.add('hidden');
    document.getElementById('brandLegend').innerHTML = '';
    document.getElementById('fstatBrief').textContent = '';
}

/* ── Count images at a detected path ─────────────── */

function countImagesAtPath(product, pathStr) {
    const parts = pathStr.split('.');
    return _countAtPath(product, parts, 0);
}

function _countAtPath(obj, parts, idx) {
    if (idx >= parts.length) {
        return (typeof obj === 'string') ? 1 : 0;
    }

    let part = parts[idx];
    const isArray = part.endsWith('[]');
    if (isArray) part = part.slice(0, -2);

    if (!obj || typeof obj !== 'object' || !(part in obj)) return 0;

    const value = obj[part];

    if (isArray) {
        if (!Array.isArray(value)) return 0;
        if (idx === parts.length - 1) {
            return value.filter(v => typeof v === 'string').length;
        }
        let count = 0;
        for (const item of value) {
            count += _countAtPath(item, parts, idx + 1);
        }
        return count;
    }

    return _countAtPath(value, parts, idx + 1);
}

/* ── Donut Chart (canvas) ────────────────────────── */

function drawDonutChart(canvas, data, total) {
    const dpr = window.devicePixelRatio || 1;
    const size = 180;
    canvas.width  = size * dpr;
    canvas.height = size * dpr;
    canvas.style.width  = size + 'px';
    canvas.style.height = size + 'px';

    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);

    const cx = size / 2;
    const cy = size / 2;
    const outerR = (size / 2) - 6;
    const innerR = outerR * 0.58;

    let startAngle = -Math.PI / 2;

    for (const d of data) {
        const slice = (d.value / total) * 2 * Math.PI;

        ctx.beginPath();
        ctx.arc(cx, cy, outerR, startAngle, startAngle + slice);
        ctx.arc(cx, cy, innerR, startAngle + slice, startAngle, true);
        ctx.closePath();
        ctx.fillStyle = d.color;
        ctx.fill();

        startAngle += slice;
    }

    // Center text
    ctx.fillStyle = '#1f2937';
    ctx.font = 'bold 22px -apple-system, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(total.toLocaleString(), cx, cy - 8);

    ctx.fillStyle = '#9ca3af';
    ctx.font = '11px -apple-system, sans-serif';
    ctx.fillText('products', cx, cy + 10);
}

/* ── Legend ───────────────────────────────────────── */

function renderLegend(container, data, total) {
    container.innerHTML = '';
    for (const d of data) {
        const pct = ((d.value / total) * 100).toFixed(1);
        const row = document.createElement('div');
        row.className = 'brand-legend-item';
        row.innerHTML = `
            <span class="brand-dot" style="background:${d.color}"></span>
            <span class="brand-name">${d.label}</span>
            <span class="brand-count">${d.value} (${pct}%)</span>
        `;
        container.appendChild(row);
    }
}


/* ═══════════════════════════════════════════════════
   Field Detection & Checkboxes
   ═══════════════════════════════════════════════════ */

function detectImageFields(products) {
    const fields = new Map();
    const sample = products.slice(0, 5);

    for (const product of sample) {
        scanObject(product, [], fields);
    }

    return Array.from(fields.entries()).map(([path, info]) => ({
        path,
        count: info.count,
        example: info.example,
    }));
}

function scanObject(obj, pathParts, fields) {
    if (!obj || typeof obj !== 'object' || Array.isArray(obj)) return;

    for (const [key, value] of Object.entries(obj)) {
        if (typeof value === 'string' && isUrl(value)) {
            const path = [...pathParts, key].join('.');
            if (!fields.has(path)) fields.set(path, { count: 0, example: value });
            fields.get(path).count++;

        } else if (Array.isArray(value) && value.length) {
            if (typeof value[0] === 'string' && isUrl(value[0])) {
                const path = [...pathParts, key + '[]'].join('.');
                if (!fields.has(path)) fields.set(path, { count: 0, example: value[0] });
                fields.get(path).count++;

            } else if (typeof value[0] === 'object' && value[0] !== null) {
                scanObject(value[0], [...pathParts, key + '[]'], fields);
            }

        } else if (typeof value === 'object' && value !== null) {
            scanObject(value, [...pathParts, key], fields);
        }
    }
}

function isImageSource(s) {
    const t = s.trim();
    // URL
    if (t.startsWith('http://') || t.startsWith('https://')) return true;
    // Windows file path:  C:\..  D:/..
    if (/^[A-Za-z]:[\\\/]/.test(t)) return true;
    // Unix absolute or relative
    if (t.startsWith('/') || t.startsWith('./') || t.startsWith('../')) return true;
    return false;
}

// Keep backward compat alias
const isUrl = isImageSource;

/* ── Render checkboxes ───────────────────────────── */

function renderCheckboxes(fields) {
    clearCheckboxes();
    fieldsPlaceholder.classList.add('hidden');
    toggleManual.classList.remove('hidden');

    for (const f of fields) {
        const id = 'field_' + f.path.replace(/[^a-zA-Z0-9]/g, '_');
        const shortExample = f.example.length > 60
            ? f.example.slice(0, 57) + '...'
            : f.example;

        const item = document.createElement('label');
        item.className = 'field-item';
        item.setAttribute('for', id);
        item.innerHTML = `
            <input type="checkbox" id="${id}" value="${f.path}" checked>
            <span class="field-info">
                <span class="field-path">${f.path}</span>
                <span class="field-example" title="${f.example}">${shortExample}</span>
            </span>
        `;
        fieldsContainer.appendChild(item);
    }
}

function clearCheckboxes() {
    fieldsContainer.querySelectorAll('.field-item').forEach(el => el.remove());
    fieldsPlaceholder.classList.remove('hidden', 'loading');
    toggleManual.classList.add('hidden');
    manualEntry.classList.add('hidden');
}

/* ── Toggle manual input ─────────────────────────── */

toggleManual.addEventListener('click', (e) => {
    e.preventDefault();
    const visible = !manualEntry.classList.contains('hidden');
    manualEntry.classList.toggle('hidden');
    toggleManual.textContent = visible ? '+ Add custom path' : '- Hide custom path';
});


/* ═══════════════════════════════════════════════════
   Form Submit
   ═══════════════════════════════════════════════════ */

form.addEventListener('submit', async (e) => {
    e.preventDefault();

    const checked = fieldsContainer.querySelectorAll('input[type="checkbox"]:checked');
    const paths = Array.from(checked).map(cb => cb.value);

    const manualPaths = document.getElementById('manualPaths');
    if (manualPaths && manualPaths.value.trim()) {
        const extra = manualPaths.value.trim().split('\n').map(p => p.trim()).filter(Boolean);
        paths.push(...extra);
    }

    if (!paths.length) {
        alert('Please select at least one image field or add a custom path.');
        return;
    }

    submitBtn.disabled    = true;
    submitBtn.textContent = 'Uploading...';

    const formData = new FormData(form);
    formData.set('image_paths', paths.join('\n'));

    try {
        const resp = await fetch('/v1/jobs', { method: 'POST', body: formData });

        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Server error' }));
            throw new Error(err.detail || `HTTP ${resp.status}`);
        }

        const data = await resp.json();
        showProgress();
        startPolling(data.job_id);

    } catch (err) {
        alert('Error: ' + err.message);
        submitBtn.disabled    = false;
        submitBtn.textContent = 'Start Processing';
    }
});


/* ═══════════════════════════════════════════════════
   Polling & Progress
   ═══════════════════════════════════════════════════ */

function startPolling(jobId) {
    pollTimer = setInterval(async () => {
        try {
            const resp = await fetch(`/v1/jobs/${jobId}`);
            const p    = await resp.json();
            updateProgress(p);

            if (p.status === 'completed' || p.status === 'failed') {
                clearInterval(pollTimer);
                showResults(jobId, p);
            }
        } catch (err) {
            console.error('Poll error:', err);
        }
    }, 1000);
}

function showProgress() {
    uploadSection.classList.add('hidden');
    progressSection.classList.remove('hidden');
    resultsSection.classList.add('hidden');
}

function updateProgress(p) {
    const done = p.succeeded_images + p.failed_images + p.skipped_images;
    const pct  = p.total_images > 0 ? Math.round((done / p.total_images) * 100) : 0;

    document.getElementById('progressFill').style.width = pct + '%';
    document.getElementById('progressText').textContent =
        `${pct}% — ${p.processed_products} / ${p.total_products} products`;

    document.getElementById('statProducts').textContent  = `${p.processed_products} / ${p.total_products}`;
    document.getElementById('statSucceeded').textContent  = p.succeeded_images;
    document.getElementById('statFailed').textContent     = p.failed_images;
    document.getElementById('statSkipped').textContent    = p.skipped_images;
}

function showResults(jobId, p) {
    progressSection.classList.add('hidden');
    resultsSection.classList.remove('hidden');

    const title   = document.getElementById('resultsTitle');
    const summary = document.getElementById('resultsSummary');

    if (p.status === 'completed') {
        title.textContent   = 'Processing Complete!';
        summary.textContent =
            `${p.succeeded_images} images uploaded, ` +
            `${p.failed_images} failed, ${p.skipped_images} skipped.`;
    } else {
        title.textContent   = 'Processing Failed';
        summary.textContent = p.error_message || 'An error occurred.';
    }

    document.getElementById('downloadResult').href = `/v1/jobs/${jobId}/result`;
    document.getElementById('downloadErrors').href = `/v1/jobs/${jobId}/errors`;
}


/* ═══════════════════════════════════════════════════
   Reset
   ═══════════════════════════════════════════════════ */

function resetForm() {
    resultsSection.classList.add('hidden');
    uploadSection.classList.remove('hidden');
    form.reset();
    fileNameSpan.textContent = 'Choose a JSON file or drag it here';
    fileNameSpan.style.color = '';
    submitBtn.disabled    = false;
    submitBtn.textContent = 'Start Processing';
    clearCheckboxes();
    hideFileStats();
    fieldsPlaceholder.textContent = 'Upload a JSON file to auto-detect image fields';
}
