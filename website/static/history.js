// Historical exploration is independent of the prediction form and model.
(() => {
  const get = (id) => document.getElementById(id);
  const form = get('history-form');
  if (!form) return;
  const fmt = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 2 });
  let revision = 0;
  const compare = document.createElement('details');
  compare.className = 'day-comparison';
  compare.innerHTML = `<summary>So sánh ngày làm việc và ngày nghỉ</summary>
    <p class="field-help">So sánh cả hai loại ngày trong khoảng ngày đã áp dụng. Mỗi điểm là lượt thuê trung bình của một giờ.</p>
    <p class="comparison-status" role="status"></p>
    <div class="comparison-peaks"></div><div class="comparison-chart hourly-chart"></div>
    <label class="comparison-hour">Khám phá từng giờ <select></select></label>
    <p class="comparison-readout" aria-live="polite"></p>`;
  get('history-results').append(compare);
  const picker = compare.querySelector('select');
  for (let h=0; h<24; h++) picker.add(new Option(String(h).padStart(2,'0')+':00',h));
  const groups = [
    {kind:'1', label:'Ngày làm việc', color:'#126c98', dash:'none'},
    {kind:'0', label:'Ngày nghỉ / lễ', color:'#a14c16', dash:'8 4'}
  ];
  let applied = null;
  let loaded = -1;
  function resetComparison() {
    applied = null;
    compare.open = false;
    compare.querySelector('.comparison-peaks').replaceChildren();
    compare.querySelector('.comparison-chart').replaceChildren();
    compare.querySelector('.comparison-readout').textContent = '';
    picker.disabled = true;
  }
  compare.addEventListener('toggle', async () => {
    if (!compare.open || !applied || loaded === revision) return;
    const token = revision;
    loaded = token;
    const status = compare.querySelector('.comparison-status');
    status.textContent = 'Đang đối chiếu hai nhóm ngày…';
    try {
      const results = await Promise.all(groups.map(async group => {
        const params = new URLSearchParams({...applied, workingday:group.kind});
        const response = await fetch('/api/history?'+params);
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Không tải được dữ liệu.');
        return data;
      }));
      if (token !== revision) return;
      status.textContent = applied.start+' → '+applied.end;
      const svg = document.createElementNS('http://www.w3.org/2000/svg','svg');
      svg.setAttribute('viewBox','0 0 720 250'); svg.setAttribute('role','img');
      svg.setAttribute('aria-label','So sánh lượt thuê trung bình theo giờ. Chọn giờ bên dưới để đọc giá trị.');
      const add = (tag, attrs, text) => {
        const el = document.createElementNS(svg.namespaceURI,tag);
        for (const [key,value] of Object.entries(attrs)) el.setAttribute(key,value);
        if (text !== undefined) el.textContent = text;
        svg.append(el); return el;
      };
      const max = Math.max(4,Math.ceil(Math.max(...results.flatMap(d=>d.hourly.map(h=>h.mean || 0)))/4)*4);
      const x = h=>54+28*h, y = v=>205-170*v/max;
      for(let i=0;i<=4;i++){
        const v=max*i/4;
        add('line',{x1:54,x2:698,y1:y(v),y2:y(v),class:'chart-grid'});
        add('text',{x:44,y:y(v)+4,'text-anchor':'end',class:'chart-label'},fmt.format(v));
      }
      add('text',{x:54,y:18,class:'chart-label'},'Lượt thuê trung bình / giờ');
      for(const h of [0,3,6,9,12,15,18,21,23]) add('text',{x:x(h),y:232,'text-anchor':'middle',class:'chart-label'},h+'h');
      groups.forEach((g,i)=>{
        const data=results[i], peak=data.peak;
        const card=document.createElement('div');
        card.style.setProperty('--series-color',g.color);
        const name=document.createElement('strong'), detail=document.createElement('span');
        name.textContent=(i?'┄ ':'━ ')+g.label;
        detail.textContent=peak ? 'Cao điểm '+peak.hour+'h · '+fmt.format(peak.mean)+' lượt/giờ' : 'Không có bản ghi';
        card.append(name,detail); compare.querySelector('.comparison-peaks').append(card);
        let path='', connected=false;
        for(const row of data.hourly){
          if(row.mean===null){connected=false; continue;}
          path+=(connected?'L':'M')+x(row.hour)+','+y(row.mean)+' '; connected=true;
          add('circle',{cx:x(row.hour),cy:y(row.mean),r:2.5,fill:g.color});
        }
        add('path',{d:path,fill:'none',stroke:g.color,'stroke-width':3,'stroke-dasharray':g.dash});
        if(peak) add('circle',{cx:x(peak.hour),cy:y(peak.mean),r:6,fill:'white',stroke:g.color,'stroke-width':3});
      });
      const marker=add('line',{y1:30,y2:206,stroke:'#697c89','stroke-dasharray':'3 4'});
      picker.value=String((results[0].peak || results[1].peak)?.hour ?? 0);
      function readHour(){
        const h=Number(picker.value);
        marker.setAttribute('x1',x(h));marker.setAttribute('x2',x(h));
        compare.querySelector('.comparison-readout').textContent=groups.map((g,i)=>{
          const row=results[i].hourly[h];
          return g.label+': '+(row.mean===null?'không có bản ghi':fmt.format(row.mean)+' lượt/giờ ('+row.samples+' mẫu)');
        }).join(' · ');
      }
      picker.disabled=false;picker.onchange=readHour;readHour();
      enableHourlyHover(svg,x,35,205,h => groups.map((g,i) => {
        const row=results[i].hourly[h];
        return g.label+': '+(row.mean===null?'Không có bản ghi':fmt.format(row.mean)+' lượt/giờ');
      }).join('\n'));
      compare.querySelector('.comparison-chart').replaceChildren(svg);
    } catch (error) {
      if(token===revision){loaded=-1;status.textContent=error.message+' Đóng và mở lại để thử lại.';}
    }
  });
  function renderHeatmap(cells) {
    const grid = get('heat-grid');
    const days = ['Thứ Hai','Thứ Ba','Thứ Tư','Thứ Năm','Thứ Sáu','Thứ Bảy','Chủ nhật'];
    const peak = cells.reduce((best,c) => c.mean > best.mean ? c : best);
    const bySlot = new Map(cells.map(c => [24*c.day+c.hour,c]));
    const describe = c => days[c.day]+' · '+c.hour+'h · '+fmt.format(c.mean)+' lượt/giờ ('+c.samples+' mẫu)';
    get('heat-peak').textContent = 'Cao nhất: '+describe(peak);
    get('heat-max').textContent = fmt.format(peak.mean);
    get('heat-detail').textContent = describe(peak);
    grid.onpointermove = event => {
      const cell=event.target.closest('button, .heat-missing');
      if (cell) showChartTip(event,cell.getAttribute('aria-label'));
      else hideChartTip();
    };
    grid.onpointerleave=hideChartTip;
    grid.replaceChildren();
    const head = grid.createTHead().insertRow();
    function heading(row, text, scope) {
      const th=document.createElement('th'); th.scope=scope; th.textContent=text; row.append(th);
    }
    heading(head,'Thứ / giờ','col');
    for(let h=0;h<24;h++) heading(head,String(h),'col');
    const body=grid.createTBody();
    for(let day=0;day<7;day++){
      const row=body.insertRow(); heading(row,days[day],'row');
      for(let h=0;h<24;h++){
        const td=row.insertCell(), c=bySlot.get(day*24+h);
        if(!c){td.className='heat-missing';td.setAttribute('aria-label','Không có dữ liệu');continue;}
        const btn=document.createElement('button');
        btn.type='button';btn.title=describe(c);btn.setAttribute('aria-label',btn.title);
        const position = 4 * c.mean / (peak.mean || 1);
        const left = Math.min(3, Math.floor(position));
        const blend = (position - left) * 100;
        btn.style.backgroundColor = `color-mix(in srgb, var(--heat-${left}), var(--heat-${left+1}) ${blend}%)`;
        if(c.mean===peak.mean) btn.classList.add('heat-high');
        btn.setAttribute('aria-pressed',String(c===peak));
        btn.onclick=()=>{
          grid.querySelector('[aria-pressed="true"]')?.setAttribute('aria-pressed','false');
          btn.setAttribute('aria-pressed','true');get('heat-detail').textContent=btn.title;
        };
        td.append(btn);
      }
    }
  }
  function invalidate() {
    revision++;
    resetComparison();
    get('history-results').hidden = true;
    get('history-status').textContent = 'Bộ lọc đã thay đổi. Bấm Xem dữ liệu để cập nhật.';
  }
  form.addEventListener('input', invalidate);
  form.addEventListener('change', invalidate);
  async function load(event) {
    if (event) event.preventDefault();
    const current = ++revision;
    resetComparison();
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
      enableHourlyHover(svg,x,36,206,h => {
        const row=result.hourly[h];
        return row.mean===null?'Không có bản ghi':'Trung bình: '+fmt.format(row.mean)+' lượt/giờ ('+row.samples+' mẫu)';
      });
      get('history-chart').replaceChildren(svg);
      renderHeatmap(result.heatmap);
      applied = {start:result.filters.start,end:result.filters.end};
      get('history-results').hidden=false;
    } catch(error) {
      if (current===revision) get('history-status').textContent=error.name==='AbortError'?'Tải dữ liệu quá lâu. Vui lòng thử lại.':error.message;
    } finally { clearTimeout(timeout); }
  }
  form.addEventListener('submit',load);
  load();
})();
