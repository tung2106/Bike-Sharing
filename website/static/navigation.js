(() => {
  const views = [...document.querySelectorAll('[data-view]')];
  const links = [...document.querySelectorAll('.rail-menu a')];
  const title = document.getElementById('view-name');
  function showView() {
    const selected =
      links.find((link) => link.hash === location.hash) || links[0];
    for (const panel of views)
      panel.hidden = '#' + panel.dataset.view !== selected.hash;
    for (const link of links) {
      if (link === selected) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    }
    title.textContent = selected.textContent;
    document.title = selected.textContent + ' · Bike Rental';
  }
  showView();
  window.addEventListener('hashchange', () => {
    showView();
    title.focus({ preventScroll: true });
    window.scrollTo(0, 0);
  });
})();

// Keep the controls outside the rail so the menu can always be reopened.
(() => {
  const rail = document.querySelector('.rail');
  const toggle = document.createElement('button');
  const grip = document.createElement('div');
  rail.id = 'side-menu';
  toggle.type = 'button';
  toggle.className = 'menu-toggle';
  toggle.setAttribute('aria-controls', rail.id);
  document.querySelector('.topbar').prepend(toggle);
  grip.className = 'rail-grip';
  grip.tabIndex = 0;
  grip.setAttribute('role', 'separator');
  grip.setAttribute('aria-orientation', 'vertical');
  grip.setAttribute('aria-controls', rail.id);
  grip.setAttribute('aria-label', 'Độ rộng menu bên trái');
  grip.title = 'Kéo để đổi độ rộng hoặc dùng phím mũi tên trái, phải';
  rail.after(grip);

  let preferredWidth = null;
  let closed = false;
  try {
    const saved = JSON.parse(localStorage.getItem('bike-rental.sidebar'));
    if (saved) {
      if (Number.isFinite(saved.width)) preferredWidth = saved.width;
      closed = saved.closed === true;
    }
  } catch {}
  function save() {
    try {
      localStorage.setItem(
        'bike-rental.sidebar',
        JSON.stringify({ width: preferredWidth, closed })
      );
    } catch {}
  }
  function bounds() {
    const w = document.documentElement.clientWidth;
    const min = w <= 600 ? 84 : w <= 900 ? 140 : 170;
    const max = Math.max(min, Math.min(360, Math.floor(w * 0.44), w - 230));
    return {
      min,
      max,
      initial: w <= 600 ? 84 : w <= 900 ? 145 : w <= 1150 ? 190 : 224
    };
  }
  function apply() {
    const { min, max, initial } = bounds();
    const width = Math.max(min, Math.min(max, preferredWidth ?? initial));
    document.body.style.setProperty(
      '--sidebar-size',
      (closed ? 0 : width) + 'px'
    );
    rail.hidden = grip.hidden = closed;
    toggle.textContent = closed ? '☰ Hiện menu' : '☰ Ẩn menu';
    toggle.setAttribute('aria-expanded', String(!closed));
    grip.setAttribute('aria-valuemin', min);
    grip.setAttribute('aria-valuemax', max);
    grip.setAttribute('aria-valuenow', width);
    grip.setAttribute('aria-valuetext', width + ' pixel');
  }
  function resize(value) {
    const { min, max } = bounds();
    preferredWidth = Math.max(min, Math.min(max, Math.round(value)));
    apply();
  }
  toggle.onclick = () => {
    closed = !closed;
    apply();
    save();
  };
  let offset = 0;
  grip.onpointerdown = (e) => {
    if (e.button !== 0 || !e.isPrimary) return;
    offset = e.clientX - rail.getBoundingClientRect().right;
    grip.setPointerCapture(e.pointerId);
    document.body.classList.add('resizing-menu');
  };
  grip.onpointermove = (e) => {
    if (grip.hasPointerCapture(e.pointerId)) resize(e.clientX - offset);
  };
  grip.onlostpointercapture = () => {
    document.body.classList.remove('resizing-menu');
    save();
  };
  grip.onkeydown = (e) => {
    const { min, max } = bounds();
    const width = rail.getBoundingClientRect().width;
    const next = {
      ArrowLeft: width - 12,
      ArrowRight: width + 12,
      Home: min,
      End: max
    }[e.key];
    if (next === undefined) return;
    e.preventDefault();
    resize(next);
    save();
  };
  window.addEventListener('resize', apply);
  apply();
})();
