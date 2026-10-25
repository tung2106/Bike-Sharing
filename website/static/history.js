// Historical exploration is independent of the prediction form and model.
(() => {
  const get = (id) => document.getElementById(id);
  const form = get('history-form');
  if (!form) return;
  const fmt = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 2 });
  let revision = 0;
  function invalidate() {
    revision++;
    get('history-results').hidden = true;
    get('history-status').textContent = 'Bộ lọc đã thay đổi. Bấm Xem dữ liệu để cập nhật.';
  }
  form.addEventListener('input', invalidate);
  form.addEventListener('change', invalidate);
  async function load(event) {
    if (event) event.preventDefault();
    const current = ++revision;
    const params = new URLSearchParams(new FormData(form));
    get('history-results').hidden = true;
    get('history-status').textContent = 'Đang đọc dữ liệu lịch sử…';
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(`/api/history?${params}`, { signal: controller.signal });
      const result = await response.json();
      if (current !== revision) return;
      if (!response.ok) throw new Error(result.error || 'Không tải được dữ liệu.');
      if (!result.rows) {
        get('history-status').textContent = 'Không có bản ghi phù hợp. Hãy chọn khoảng ngày hoặc loại ngày khác.';
        return;
      }
      get('history-status').textContent = `${result.filters.start} → ${result.filters.end} · ${fmt.format(result.days)} ngày có dữ liệu · ${fmt.format(result.rows)} bản ghi giờ.`;
      for (const key of ['total', 'average', 'casual', 'registered']) get(`history-${key}`).textContent = fmt.format(result[key]);
      get('history-peak').textContent = `${String(result.peak.hour).padStart(2,'0')}:00 — ${fmt.format(result.peak.mean)} lượt/giờ`;
      const body = get('history-rows');
      body.replaceChildren();
      for (const row of result.hourly) {
        const tr = document.createElement('tr');
        for (const value of [`${String(row.hour).padStart(2,'0')}:00`, row.mean === null ? 'Không có dữ liệu' : fmt.format(row.mean), fmt.format(row.samples)]) {
          const td = document.createElement('td'); td.textContent = value; tr.append(td);
        }
        body.append(tr);
      }
      const ns = 'http://www.w3.org/2000/svg';
      const svg = document.createElementNS(ns, 'svg');
      svg.setAttribute('viewBox','0 0 720 250'); svg.setAttribute('role','img');
      svg.setAttribute('aria-label','Lượt thuê thực tế trung bình theo giờ; số liệu và số mẫu ở bảng bên dưới.');
      const add = (tag, attrs, text) => {
        const el = document.createElementNS(ns,tag);
        for (const [k,v] of Object.entries(attrs)) el.setAttribute(k,v);
        if (text !== undefined) el.textContent = text;
        svg.append(el); return el;
      };
      const max = Math.max(1,...result.hourly.map(r=>r.mean || 0));
      const x = h => 54+h*28, y = n => 206-n/max*170;
      for (let i=0;i<=4;i++) {
        const value=max*i/4;
        add('line',{x1:54,x2:698,y1:y(value),y2:y(value),class:'chart-grid'});
        add('text',{x:46,y:y(value)+4,'text-anchor':'end',class:'chart-label'},fmt.format(value));
      }
      add('text',{x:54,y:18,class:'chart-label'},'Lượt thuê trung bình / bản ghi giờ');
      for (const h of [0,3,6,9,12,15,18,21,23]) add('text',{x:x(h),y:232,'text-anchor':'middle',class:'chart-label'},`${h}h`);
      let path = '', connected = false;
      for (const row of result.hourly) {
        if (row.mean === null) { connected=false; continue; }
        path += `${connected?'L':'M'}${x(row.hour)},${y(row.mean)} `; connected=true;
      }
      add('path',{d:path,class:'chart-line'});
      for (const row of result.hourly.filter(r=>r.mean!==null)) {
        const dot=add('circle',{cx:x(row.hour),cy:y(row.mean),r:4,class:'chart-dot'});
        const title=document.createElementNS(ns,'title');
        title.textContent=`${row.hour}h: ${fmt.format(row.mean)} lượt, ${row.samples} mẫu`; dot.append(title);
      }
      get('history-chart').replaceChildren(svg);
      get('history-results').hidden=false;
    } catch(error) {
      if (current===revision) get('history-status').textContent=error.name==='AbortError'?'Tải dữ liệu quá lâu. Vui lòng thử lại.':error.message;
    } finally { clearTimeout(timeout); }
  }
  form.addEventListener('submit',load);
  load();
})();
