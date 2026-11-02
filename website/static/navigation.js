(() => {
  const views = [...document.querySelectorAll("[data-view]")];
  const links = [...document.querySelectorAll(".rail-menu a")];
  const title = document.getElementById("view-name");
  const descriptions = {
    "#du-doan": [
      "MÔ PHỎNG NHU CẦU",
      "Dự đoán theo giờ",
      "Chọn thời điểm và điều kiện thời tiết để xem lượt thuê ước tính trong ngày.",
    ],
    "#cao-diem": [
      "LÊN KẾ HOẠCH THEO GIỜ",
      "Giờ cao điểm",
      "Ba khung giờ có nhu cầu cao nhất từ lần dự đoán gần nhất của bạn.",
    ],
    "#lich-su": [
      "KHÁM PHÁ DỮ LIỆU",
      "Nhìn lại nhịp thuê xe",
      "Lọc dữ liệu, đọc bản đồ nhiệt và khám phá những ngày đằng sau mỗi khung giờ.",
    ],
    "#doi-chieu": [
      "ĐÁNH GIÁ TRÊN DỮ LIỆU LỊCH SỬ",
      "Dự đoán so với thực tế",
      "Quan sát mô hình dự đoán cao hay thấp ở từng giờ trong tập kiểm tra.",
    ],
    "#danh-gia": [
      "THỰC NGHIỆM THEO GIỜ",
      "Đánh giá mô hình",
      "So sánh Random Forest với mô hình đối chứng HistGradientBoosting.",
    ],
  };
  function showView() {
    const selected =
      links.find((link) => link.hash === location.hash) || links[0];
    for (const panel of views)
      panel.hidden = "#" + panel.dataset.view !== selected.hash;
    for (const link of links) {
      if (link === selected) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    }
    const label = selected.querySelector("span").textContent.trim();
    title.textContent = label;
    document.title = label + " · Bike Rental";
    const description = descriptions[selected.hash];
    document.getElementById("screen-heading").hidden = !description;
    if (description) {
      for (const [index, id] of [
        "screen-kicker",
        "screen-title",
        "screen-description",
      ].entries())
        document.getElementById(id).textContent = description[index];
    }
  }
  showView();
  window.addEventListener("hashchange", () => {
    showView();
    title.focus({ preventScroll: true });
    window.scrollTo(0, 0);
  });
})();

// Keep the controls outside the rail so the menu can always be reopened.
(() => {
  const rail = document.querySelector(".rail");
  const toggle = document.createElement("button");
  const grip = document.createElement("div");
  rail.id = "side-menu";
  toggle.type = "button";
  toggle.className = "menu-toggle";
  toggle.innerHTML =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" aria-hidden="true"><path d="M4 5h16v14H4zM9 5v14m4-9 3 2-3 2"/></svg>';
  toggle.setAttribute("aria-controls", rail.id);
  document.querySelector(".topbar").prepend(toggle);
  grip.className = "rail-grip";
  grip.tabIndex = 0;
  grip.setAttribute("role", "separator");
  grip.setAttribute("aria-orientation", "vertical");
  grip.setAttribute("aria-controls", rail.id);
  grip.setAttribute("aria-label", "Độ rộng menu bên trái");
  grip.title = "Kéo để đổi độ rộng hoặc dùng phím mũi tên trái, phải";
  rail.after(grip);

  let preferredWidth = null;
  let closed = false;
  try {
    const saved = JSON.parse(localStorage.getItem("bike-rental.sidebar"));
    if (saved) {
      if (Number.isFinite(saved.width)) preferredWidth = saved.width;
      closed = saved.closed === true;
    }
  } catch {}
  function save() {
    try {
      localStorage.setItem(
        "bike-rental.sidebar",
        JSON.stringify({ width: preferredWidth, closed }),
      );
    } catch {}
  }
  function bounds() {
    const w = document.documentElement.clientWidth;
    const min = w <= 600 ? 84 : w <= 900 ? 140 : 170;
    const max = Math.max(
      min,
      Math.min(w <= 600 ? 96 : 360, Math.floor(w * 0.44), w - 230),
    );
    return {
      min,
      max,
      initial: w <= 600 ? 84 : w <= 900 ? 145 : w <= 1150 ? 190 : 244,
    };
  }
  function apply() {
    const { min, max, initial } = bounds();
    const width = Math.max(min, Math.min(max, preferredWidth ?? initial));
    document.body.style.setProperty(
      "--sidebar-size",
      (closed ? 0 : width) + "px",
    );
    rail.hidden = grip.hidden = closed;
    toggle.setAttribute("aria-label", closed ? "Hiện menu" : "Ẩn menu");
    toggle.title = closed ? "Hiện menu" : "Ẩn menu";
    toggle.setAttribute("aria-expanded", String(!closed));
    grip.setAttribute("aria-valuemin", min);
    grip.setAttribute("aria-valuemax", max);
    grip.setAttribute("aria-valuenow", width);
    grip.setAttribute("aria-valuetext", width + " pixel");
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
    document.body.classList.add("resizing-menu");
  };
  grip.onpointermove = (e) => {
    if (grip.hasPointerCapture(e.pointerId)) resize(e.clientX - offset);
  };
  grip.onlostpointercapture = () => {
    document.body.classList.remove("resizing-menu");
    save();
  };
  grip.onkeydown = (e) => {
    const { min, max } = bounds();
    const width = rail.getBoundingClientRect().width;
    const next = {
      ArrowLeft: width - 12,
      ArrowRight: width + 12,
      Home: min,
      End: max,
    }[e.key];
    if (next === undefined) return;
    e.preventDefault();
    resize(next);
    save();
  };
  window.addEventListener("resize", apply);
  apply();
})();
