/**
 * GestPro Móvil & Web — Aplicación SPA
 * Control completo de analíticas, POS, inventario, caja y gastos.
 */

class GestProApp {
  constructor() {
    this.token = localStorage.getItem("gestpro_token") || "";
    this.user = JSON.parse(localStorage.getItem("gestpro_user") || "null");
    this.config = { currency_symbol: "$", business_name: "GestPro" };
    
    this.currentView = "dashboard";
    this.dashboardRange = "today";
    
    // Estado del POS
    this.products = [];
    this.filteredProducts = [];
    this.categories = [];
    this.selectedCategory = "Todas";
    this.cart = [];
    this.selectedClientId = "";
    this.paymentMethod = "efectivo";
    this.cartDiscount = 0;
    this.cashReceived = 0;
    this.stockFilter = "en_stock"; // filtro por defecto: solo en stock

    // Estado de Caja
    this.cashSession = null;

    // Estado de Clientes e Inventario
    this.clients = [];
    this.lowStockFilter = false;
    this.adjustProdId = null;
    this.adjustProdCurrent = 0;
    this.selectedSaleForDetail = null;
    this.clientForPayment = null;

    // Instancias de Chart.js
    this.charts = {
      daily: null,
      payments: null,
      categories: null
    };

    // Escáner de cámara
    this.html5QrCode = null;
    this.lastCompletedSale = null;

    this.init();
  }

  async init() {
    this.bindEvents();
    this.startClock();
    if (this.token && this.user) {
      this.showApp();
    } else {
      this.showLogin();
    }
  }

  startClock() {
    const DAYS = ["Dom","Lun","Mar","Mié","Jue","Vie","Sáb"];
    const MONTHS = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
    const tick = () => {
      const now = new Date();
      const hh = String(now.getHours()).padStart(2, "0");
      const mm = String(now.getMinutes()).padStart(2, "0");
      const ss = String(now.getSeconds()).padStart(2, "0");
      const dayName = DAYS[now.getDay()];
      const day = now.getDate();
      const month = MONTHS[now.getMonth()];
      const timeEl = document.getElementById("clock-time");
      const dateEl = document.getElementById("clock-date");
      if (timeEl) timeEl.textContent = `${hh}:${mm}:${ss}`;
      if (dateEl) dateEl.textContent = `${dayName} ${day} ${month}`;
    };
    // Esperar DOM listo antes de arrancar
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", () => { tick(); setInterval(tick, 1000); });
    } else {
      tick();
      setInterval(tick, 1000);
    }
  }

  // ── Helper de Peticiones Fetch API ────────────────────────────
  async api(endpoint, method = "GET", body = null) {
    const headers = { "Content-Type": "application/json" };
    if (this.token) {
      headers["Authorization"] = `Bearer ${this.token}`;
    }

    const options = { method, headers };
    if (body && (method === "POST" || method === "PUT")) {
      options.body = JSON.stringify(body);
    }

    try {
      const res = await fetch(endpoint, options);
      if (res.status === 401) {
        this.logout();
        throw new Error("Sesión expirada o inválida");
      }
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Error en el servidor");
      }
      return data;
    } catch (err) {
      console.error(`API Error [${endpoint}]:`, err);
      throw err;
    }
  }

  // ── Formateo de Moneda ───────────────────────────────────────
  fmt(amount) {
    const sym = this.config.currency_symbol || "$";
    const val = Number(amount) || 0;
    return `${sym} ${val.toLocaleString("es-CO", { maximumFractionDigits: 0 })}`;
  }

  // ── Notificaciones Toast ──────────────────────────────────────
  toast(message, type = "success") {
    const container = document.getElementById("toast-container");
    if (!container) return;

    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    const icon = type === "success" ? "✅" : (type === "warning" ? "⚠️" : "❌");
    toast.innerHTML = `<span>${icon}</span> <span>${message}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateY(-10px)";
      setTimeout(() => toast.remove(), 250);
    }, 3200);
  }

  // ── Modales Utilitarios ───────────────────────────────────────
  modal(id, show = true) {
    const el = document.getElementById(id);
    if (el) el.style.display = show ? "flex" : "none";
  }

  closeModal(id) {
    this.modal(id, false);
  }

  // ── Autenticación ─────────────────────────────────────────────
  bindEvents() {
    // Formulario de login
    const formLogin = document.getElementById("form-login");
    if (formLogin) {
      formLogin.addEventListener("submit", (e) => {
        e.preventDefault();
        this.handleLogin();
      });
    }

    // Cerrar bottom sheet al dar click fuera
    const modalCart = document.getElementById("modal-cart");
    if (modalCart) {
      modalCart.addEventListener("click", (e) => {
        if (e.target === modalCart) this.closeCartSheet();
      });
    }
  }

  async handleLogin() {
    const u = document.getElementById("login-username").value.trim();
    const p = document.getElementById("login-password").value.trim();
    const errBox = document.getElementById("login-error");
    errBox.style.display = "none";

    try {
      const data = await this.api("/api/auth/login", "POST", { username: u, password: p });
      this.token = data.token;
      this.user = data.user;
      localStorage.setItem("gestpro_token", this.token);
      localStorage.setItem("gestpro_user", JSON.stringify(this.user));
      this.showApp();
      this.toast(`¡Bienvenido, ${this.user.username}!`);
    } catch (err) {
      errBox.textContent = err.message;
      errBox.style.display = "block";
    }
  }

  logout() {
    this.token = "";
    this.user = null;
    localStorage.removeItem("gestpro_token");
    localStorage.removeItem("gestpro_user");
    this.showLogin();
  }

  showLogin() {
    document.getElementById("view-login").style.display = "flex";
    document.getElementById("app-container").style.display = "none";
    this.loadConfig();
  }

  async showApp() {
    document.getElementById("view-login").style.display = "none";
    document.getElementById("app-container").style.display = "flex";
    document.getElementById("header-username").textContent = this.user.username;

    await this.loadConfig();
    await this.loadCashStatus();
    this.navTo("dashboard");
  }

  async loadConfig() {
    try {
      this.config = await this.api("/api/config");
      const name = this.config.business_name || "GestPro";
      document.getElementById("login-biz-name").textContent = name;
      document.getElementById("header-business-name").textContent = name;
    } catch (e) {
      console.warn("No se pudo cargar la configuración:", e);
    }
  }

  // ── Navegación Principal ──────────────────────────────────────
  navTo(viewName) {
    this.currentView = viewName;
    document.querySelectorAll(".app-view").forEach(v => v.classList.remove("active"));
    document.querySelectorAll(".nav-item").forEach(btn => {
      btn.classList.toggle("active", btn.dataset.view === viewName);
    });

    const activeView = document.getElementById(`view-${viewName}`);
    if (activeView) activeView.classList.add("active");

    window.scrollTo({ top: 0, behavior: "smooth" });

    // Cargar datos según la vista
    if (viewName === "dashboard") {
      this.loadDashboard();
    } else if (viewName === "pos") {
      this.loadPosData();
    } else if (viewName === "inventario") {
      this.loadInventory();
    } else if (viewName === "caja") {
      this.loadCashStatus();
    } else if (viewName === "mas") {
      // Vista de menú
    }
  }

  showSubView(name) {
    document.querySelector(".menu-cards-grid").style.display = "none";
    document.querySelectorAll(".subview-container").forEach(el => el.style.display = "none");
    const sub = document.getElementById(`subview-${name}`);
    if (sub) sub.style.display = "block";

    if (name === "gastos") this.loadExpenses();
    if (name === "clientes") this.loadClients();
    if (name === "ventas") this.loadSalesHistory();
  }

  hideSubView(name) {
    const sub = document.getElementById(`subview-${name}`);
    if (sub) sub.style.display = "none";
    document.querySelector(".menu-cards-grid").style.display = "flex";
  }

  // ═══════════════════════════════════════════════════════════════
  // 1. MÓDULO: DASHBOARD & ANALÍTICAS
  // ═══════════════════════════════════════════════════════════════
  setDashboardRange(range, btn) {
    this.dashboardRange = range;
    document.querySelectorAll(".date-chips-scroll .chip").forEach(c => c.classList.remove("active"));
    if (btn) btn.classList.add("active");
    this.loadDashboard();
  }

  getDateRangeParams() {
    const now = new Date();
    const toISO = (d) => d.toISOString().split("T")[0];

    let start = toISO(now);
    let end = toISO(now);

    if (this.dashboardRange === "yesterday") {
      const y = new Date();
      y.setDate(y.getDate() - 1);
      start = toISO(y);
      end = start;
    } else if (this.dashboardRange === "week") {
      const w = new Date();
      w.setDate(w.getDate() - 6);
      start = toISO(w);
    } else if (this.dashboardRange === "month") {
      const m = new Date(now.getFullYear(), now.getMonth(), 1);
      start = toISO(m);
    }

    return { start_date: start, end_date: end };
  }

  async loadDashboard() {
    const { start_date, end_date } = this.getDateRangeParams();

    // Actualizar etiqueta
    const lbl = document.getElementById("dash-date-label");
    if (this.dashboardRange === "today") lbl.textContent = "Métricas de Hoy";
    else if (this.dashboardRange === "yesterday") lbl.textContent = "Métricas de Ayer";
    else if (this.dashboardRange === "week") lbl.textContent = "Últimos 7 Días";
    else if (this.dashboardRange === "month") lbl.textContent = "Este Mes en Curso";

    try {
      // 1. Cargar Estadísticas (KPIs)
      const stats = await this.api(`/api/dashboard/stats?start_date=${start_date}&end_date=${end_date}`);
      
      document.getElementById("kpi-revenue").textContent = this.fmt(stats.revenue);
      document.getElementById("kpi-sales-count").textContent = `${stats.sales_count} ventas`;
      
      document.getElementById("kpi-profit").textContent = this.fmt(stats.net_profit);
      const marginPct = stats.revenue > 0 ? ((stats.net_profit / stats.revenue) * 100).toFixed(1) : 0;
      document.getElementById("kpi-margin-percent").textContent = `Margen: ${marginPct}%`;

      document.getElementById("kpi-expenses").textContent = this.fmt(stats.expenses);
      document.getElementById("kpi-operating-profit").textContent = `Operativo: ${this.fmt(stats.operating_profit)}`;

      document.getElementById("kpi-ticket").textContent = this.fmt(stats.avg_ticket);
      document.getElementById("kpi-low-stock-alert").textContent = `⚠️ ${stats.low_stock_count} bajo stock`;

      // 2. Cargar Gráficos
      const chartsData = await this.api(`/api/dashboard/charts?start_date=${start_date}&end_date=${end_date}`);
      this.renderDailyChart(chartsData.by_day);
      this.renderPaymentsChart(chartsData.by_payment);
      this.renderCategoriesChart(chartsData.by_category);
      this.renderTopProducts(chartsData.top_products);

    } catch (e) {
      console.error("Error al cargar dashboard:", e);
      this.toast("Error al actualizar métricas", "error");
    }
  }

  renderDailyChart(data) {
    const ctx = document.getElementById("chart-daily-sales");
    if (!ctx) return;

    if (this.charts.daily) this.charts.daily.destroy();

    const labels = data.map(d => d.date.slice(5)); // MM-DD
    const values = data.map(d => d.rev);

    this.charts.daily = new Chart(ctx, {
      type: "line",
      data: {
        labels: labels.length ? labels : ["Sin datos"],
        datasets: [{
          label: "Ventas ($)",
          data: values.length ? values : [0],
          borderColor: "#10b981",
          backgroundColor: "rgba(16, 185, 129, 0.12)",
          fill: true,
          tension: 0.35,
          borderWidth: 2.5,
          pointBackgroundColor: "#10b981",
          pointRadius: 4
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { color: "rgba(255,255,255,0.05)" }, ticks: { color: "#94a3b8", font: { size: 11 } } },
          y: { grid: { color: "rgba(255,255,255,0.05)" }, ticks: { color: "#94a3b8", font: { size: 11 }, callback: v => "$" + v.toLocaleString() } }
        }
      }
    });
  }

  renderPaymentsChart(data) {
    const ctx = document.getElementById("chart-payment-methods");
    if (!ctx) return;

    if (this.charts.payments) this.charts.payments.destroy();

    const labels = data.map(d => d.pm.charAt(0).toUpperCase() + d.pm.slice(1));
    const values = data.map(d => d.total);
    const colors = ["#10b981", "#38bdf8", "#818cf8", "#f59e0b"];

    this.charts.payments = new Chart(ctx, {
      type: "doughnut",
      data: {
        labels: labels.length ? labels : ["Sin ventas"],
        datasets: [{
          data: values.length ? values : [1],
          backgroundColor: values.length ? colors.slice(0, values.length) : ["#27272a"],
          borderWidth: 0
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: "bottom", labels: { color: "#94a3b8", font: { size: 11 }, boxWidth: 12 } }
        },
        cutout: "68%"
      }
    });
  }

  renderCategoriesChart(data) {
    const ctx = document.getElementById("chart-categories");
    if (!ctx) return;

    if (this.charts.categories) this.charts.categories.destroy();

    const labels = data.map(d => d.cat);
    const values = data.map(d => d.rev);

    this.charts.categories = new Chart(ctx, {
      type: "bar",
      data: {
        labels: labels.length ? labels : ["Sin datos"],
        datasets: [{
          label: "Ingresos",
          data: values.length ? values : [0],
          backgroundColor: "#6366f1",
          borderRadius: 6
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { display: false }, ticks: { color: "#94a3b8", font: { size: 11 } } },
          y: { grid: { color: "rgba(255,255,255,0.05)" }, ticks: { color: "#94a3b8", font: { size: 11 }, callback: v => "$" + v.toLocaleString() } }
        }
      }
    });
  }

  renderTopProducts(items) {
    const list = document.getElementById("dash-top-products-list");
    if (!list) return;

    if (!items || items.length === 0) {
      list.innerHTML = `<div class="empty-state-sm">No hay ventas registradas en este periodo</div>`;
      return;
    }

    list.innerHTML = items.map((it, idx) => `
      <div class="ranking-item">
        <div class="ranking-left">
          <span class="ranking-pos">${idx + 1}</span>
          <div>
            <div class="ranking-name">${it.pname}</div>
            <div class="ranking-qty">${it.qty} unidades vendidas</div>
          </div>
        </div>
        <div class="ranking-rev">${this.fmt(it.rev)}</div>
      </div>
    `).join("");
  }

  // ═══════════════════════════════════════════════════════════════
  // 2. MÓDULO: PUNTO DE VENTA (POS / VENDER)
  // ═══════════════════════════════════════════════════════════════
  async loadPosData() {
    try {
      const [resProd, cats, clients] = await Promise.all([
        this.api("/api/products?limit=200"),
        this.api("/api/categories"),
        this.api("/api/clients")
      ]);

      this.products = resProd.products || [];
      this.filteredProducts = [...this.products];
      this.categories = cats || [];
      this.clients = clients || [];

      this.renderCategoryChips();
      this.filterPosProducts();
      this.populateClientsSelect();
      this.updateCartFloatingBar();
    } catch (e) {
      console.error("Error al cargar POS:", e);
      this.toast("Error al cargar productos del POS", "error");
    }
  }

  renderCategoryChips() {
    const container = document.getElementById("pos-category-chips");
    if (!container) return;

    let html = `<button class="cat-chip ${this.selectedCategory === 'Todas' ? 'active' : ''}" onclick="app.selectPosCategory('Todas', this)">Todas</button>`;
    this.categories.forEach(c => {
      const active = this.selectedCategory === c.name ? "active" : "";
      html += `<button class="cat-chip ${active}" onclick="app.selectPosCategory('${c.name}', this)">${c.name}</button>`;
    });
    container.innerHTML = html;
  }

  selectPosCategory(cat, btn) {
    this.selectedCategory = cat;
    document.querySelectorAll("#pos-category-chips .cat-chip").forEach(c => c.classList.remove("active"));
    if (btn) btn.classList.add("active");
    this.filterPosProducts();
  }

  selectStockFilter(filter, btn) {
    this.stockFilter = filter;
    document.querySelectorAll("#pos-stock-chips .cat-chip").forEach(c => c.classList.remove("active"));
    if (btn) btn.classList.add("active");
    this.filterPosProducts();
  }

  filterPosProducts() {
    const term = document.getElementById("pos-search-input").value.trim().toLowerCase();
    const clearBtn = document.getElementById("btn-clear-pos-search");
    if (clearBtn) clearBtn.style.display = term ? "block" : "none";

    this.filteredProducts = this.products.filter(p => {
      const matchCat = this.selectedCategory === "Todas" || p.category === this.selectedCategory;
      const matchText = !term ||
        p.name.toLowerCase().includes(term) ||
        String(p.sku || "").includes(term) ||
        (p.barcode && p.barcode.toLowerCase().includes(term));
      const matchStock =
        this.stockFilter === "todos" ? true :
        this.stockFilter === "en_stock" ? p.stock > 0 :
        this.stockFilter === "agotados" ? p.stock <= 0 : true;
      return matchCat && matchText && matchStock;
    });

    this.renderPosProducts();
  }

  clearPosSearch() {
    document.getElementById("pos-search-input").value = "";
    document.getElementById("btn-clear-pos-search").style.display = "none";
    this.filterPosProducts();
  }

  renderPosProducts() {
    const grid = document.getElementById("pos-products-grid");
    if (!grid) return;

    if (this.filteredProducts.length === 0) {
      grid.innerHTML = `<div class="empty-state">No se encontraron productos coincidentes</div>`;
      return;
    }

    grid.innerHTML = this.filteredProducts.map(p => {
      let badgeClass = "stock-badge-ok";
      let badgeText = `${p.stock} disp`;
      if (p.stock <= 0) {
        badgeClass = "stock-badge-out";
        badgeText = "Agotado";
      } else if (p.stock <= p.min_stock) {
        badgeClass = "stock-badge-low";
        badgeText = `${p.stock} bajo`;
      }

      return `
        <div class="product-card glass-panel" onclick="app.addToCart(${p.id})">
          <div class="product-header">
            <div class="product-name">${p.name}</div>
            <span class="stock-badge ${badgeClass}">${badgeText}</span>
          </div>
          <div class="product-sku">SKU: ${p.sku || 'N/A'}</div>
          <div class="product-footer">
            <span class="product-price">${this.fmt(p.price)}</span>
            <button class="icon-btn-sm" title="Agregar">+🛒</button>
          </div>
        </div>
      `;
    }).join("");
  }

  addToCart(prodId) {
    const prod = this.products.find(p => p.id === prodId);
    if (!prod) return;

    if (prod.stock <= 0) {
      this.toast(`"${prod.name}" no tiene stock disponible`, "warning");
    }

    const existing = this.cart.find(i => i.product_id === prod.id);
    if (existing) {
      existing.quantity += 1;
      existing.subtotal = existing.quantity * existing.unit_price;
    } else {
      this.cart.push({
        product_id: prod.id,
        product_name: prod.name,
        quantity: 1,
        unit_price: Number(prod.price),
        subtotal: Number(prod.price),
        stock: prod.stock
      });
    }

    this.updateCartFloatingBar();
    this.toast(`+1 ${prod.name}`);
  }

  updateCartFloatingBar() {
    const bar = document.getElementById("floating-cart-bar");
    const navBadge = document.getElementById("nav-cart-count");
    if (!bar) return;

    const totalQty = this.cart.reduce((sum, i) => sum + i.quantity, 0);
    const subtotal = this.cart.reduce((sum, i) => sum + i.subtotal, 0);

    if (totalQty > 0) {
      bar.style.display = "flex";
      document.getElementById("cart-bar-badge").textContent = totalQty;
      document.getElementById("cart-bar-total").textContent = this.fmt(subtotal);

      if (navBadge) {
        navBadge.style.display = "flex";
        navBadge.textContent = totalQty;
      }
    } else {
      bar.style.display = "none";
      if (navBadge) navBadge.style.display = "none";
    }
  }

  openCartSheet() {
    this.renderCartItems();
    this.updateCartTotals();
    this.modal("modal-cart", true);
  }

  closeCartSheet() {
    this.modal("modal-cart", false);
  }

  renderCartItems() {
    const container = document.getElementById("cart-items-container");
    if (!container) return;

    if (this.cart.length === 0) {
      container.innerHTML = `<div class="empty-state">El carrito de compra está vacío</div>`;
      return;
    }

    container.innerHTML = this.cart.map((item, idx) => `
      <div class="cart-item-row">
        <div>
          <div class="cart-item-name">${item.product_name}</div>
          <div class="cart-item-unit-price">${this.fmt(item.unit_price)} c/u</div>
        </div>
        <div class="cart-item-controls">
          <button class="cart-stepper-btn" onclick="app.updateCartQty(${idx}, -1)">-</button>
          <span class="cart-stepper-qty">${item.quantity}</span>
          <button class="cart-stepper-btn" onclick="app.updateCartQty(${idx}, 1)">+</button>
          <div class="cart-item-subtotal">${this.fmt(item.subtotal)}</div>
          <button class="btn-text-danger text-sm" onclick="app.removeCartItem(${idx})">🗑️</button>
        </div>
      </div>
    `).join("");
  }

  updateCartQty(index, delta) {
    if (!this.cart[index]) return;
    this.cart[index].quantity += delta;
    if (this.cart[index].quantity <= 0) {
      this.cart.splice(index, 1);
    } else {
      this.cart[index].subtotal = this.cart[index].quantity * this.cart[index].unit_price;
    }
    this.renderCartItems();
    this.updateCartTotals();
    this.updateCartFloatingBar();
  }

  removeCartItem(index) {
    this.cart.splice(index, 1);
    this.renderCartItems();
    this.updateCartTotals();
    this.updateCartFloatingBar();
  }

  clearCart() {
    this.cart = [];
    this.renderCartItems();
    this.updateCartTotals();
    this.updateCartFloatingBar();
    this.closeCartSheet();
  }

  populateClientsSelect() {
    const sel = document.getElementById("cart-client-select");
    if (!sel) return;

    let html = `<option value="">Mostrador (Cliente Casual)</option>`;
    this.clients.forEach(c => {
      const debtText = c.debt > 0 ? ` (Debe ${this.fmt(c.debt)})` : "";
      html += `<option value="${c.id}">${c.name}${debtText}</option>`;
    });
    sel.innerHTML = html;
  }

  updateCartTotals() {
    const discInput = document.getElementById("cart-discount-input");
    this.cartDiscount = Number(discInput ? discInput.value : 0) || 0;

    const subtotal = this.cart.reduce((s, i) => s + i.subtotal, 0);
    const baseAfterDisc = Math.max(0, subtotal - this.cartDiscount);

    const rappiRow = document.getElementById("cart-rappi-row");
    const rappiVal = document.getElementById("cart-rappi-val");

    let total = baseAfterDisc;
    if (this.paymentMethod === "rappi") {
      const rappiComm = Math.round(baseAfterDisc * 0.14);
      total = Math.max(0, baseAfterDisc - rappiComm);
      if (rappiRow) {
        rappiRow.style.display = "flex";
        if (rappiVal) rappiVal.textContent = `-${this.fmt(rappiComm)}`;
      }
    } else {
      if (rappiRow) rappiRow.style.display = "none";
    }

    document.getElementById("cart-subtotal").textContent = this.fmt(subtotal);
    document.getElementById("cart-discount-val").textContent = this.fmt(this.cartDiscount);
    document.getElementById("cart-total-val").textContent = this.fmt(total);

    this.renderQuickCashChips(total);
    this.calcChange();
  }

  setPaymentMethod(method, btn) {
    this.paymentMethod = method;
    document.querySelectorAll(".payment-tabs-grid .pay-tab").forEach(t => t.classList.remove("active"));
    if (btn) btn.classList.add("active");

    const cashBox = document.getElementById("cash-change-calculator");
    if (cashBox) {
      cashBox.style.display = method === "efectivo" ? "block" : "none";
    }
    this.updateCartTotals();
  }

  renderQuickCashChips(total) {
    const container = document.getElementById("quick-cash-chips");
    if (!container) return;

    if (total <= 0) {
      container.innerHTML = "";
      return;
    }

    // Sugerencias de billetes en COP o denominaciones comunes
    const suggestions = new Set([total]);
    [10000, 20000, 50000, 100000].forEach(denom => {
      if (denom >= total) suggestions.add(denom);
      else {
        const next = Math.ceil(total / denom) * denom;
        suggestions.add(next);
      }
    });

    const sorted = Array.from(suggestions).sort((a, b) => a - b).slice(0, 4);
    container.innerHTML = sorted.map(val => `
      <button class="cash-chip" onclick="app.setReceivedCash(${val})">${this.fmt(val)}</button>
    `).join("");
  }

  setReceivedCash(val) {
    document.getElementById("cash-received-input").value = val;
    this.calcChange();
  }

  calcChange() {
    const subtotal = this.cart.reduce((s, i) => s + i.subtotal, 0);
    const baseAfterDisc = Math.max(0, subtotal - this.cartDiscount);
    let total = baseAfterDisc;
    if (this.paymentMethod === "rappi") {
      total = Math.max(0, baseAfterDisc - Math.round(baseAfterDisc * 0.14));
    }
    const recInput = document.getElementById("cash-received-input");
    const rec = Number(recInput ? recInput.value : 0) || 0;

    const change = Math.max(0, rec - total);
    document.getElementById("change-due-val").textContent = this.fmt(change);
  }

  async confirmSale() {
    if (this.cart.length === 0) {
      this.toast("El carrito está vacío", "warning");
      return;
    }

    const clientSel = document.getElementById("cart-client-select");
    const clientId = clientSel && clientSel.value ? Number(clientSel.value) : null;

    if (this.paymentMethod === "crédito" && !clientId) {
      this.toast("Para ventas a crédito debes seleccionar un cliente registrado", "error");
      return;
    }

    // Si el pago es Rappi, sumar la comisión (14%) al descuento efectivo
    const subtotalCart = this.cart.reduce((s, i) => s + i.subtotal, 0);
    let effectiveDiscount = this.cartDiscount;
    if (this.paymentMethod === "rappi") {
      const rappiComm = Math.round(Math.max(0, subtotalCart - this.cartDiscount) * 0.14);
      effectiveDiscount = this.cartDiscount + rappiComm;
    }

    const payload = {
      client_id: clientId,
      items: this.cart.map(i => ({
        product_id: i.product_id,
        product_name: i.product_name,
        quantity: i.quantity,
        unit_price: i.unit_price,
        subtotal: i.subtotal
      })),
      discount: effectiveDiscount,
      payment_method: this.paymentMethod,
      notes: "Venta desde celular"
    };

    const btn = document.getElementById("btn-confirm-sale");
    btn.disabled = true;
    btn.textContent = "Procesando...";

    try {
      const res = await this.api("/api/sales", "POST", payload);
      this.toast("¡Venta registrada con éxito!", "success");
      
      // Guardar datos para recibo y WhatsApp
      this.lastCompletedSale = {
        ...res,
        items: [...this.cart],
        client_name: clientId ? (clientSel.options[clientSel.selectedIndex].text.split("(")[0].trim()) : "Cliente Mostrador",
        cash_received: Number(document.getElementById("cash-received-input").value) || 0
      };

      this.clearCart();
      this.closeCartSheet();
      this.showReceiptModal();

      // Recargar catálogo e historial
      this.loadPosData();
      this.loadCashStatus();
    } catch (err) {
      this.toast(err.message, "error");
    } finally {
      btn.disabled = false;
      btn.innerHTML = `<span>✅ REGISTRAR VENTA</span>`;
    }
  }

  // ── Comprobante / Recibo Post-Venta ───────────────────────────
  showReceiptModal() {
    if (!this.lastCompletedSale) return;
    const sale = this.lastCompletedSale;

    document.getElementById("receipt-sale-id").textContent = `Venta #${sale.id} · ${sale.date} ${sale.time}`;

    const itemsHtml = sale.items.map(it => `
      <div class="flex-between text-sm py-2">
        <span>${it.quantity}x ${it.product_name}</span>
        <strong>${this.fmt(it.subtotal)}</strong>
      </div>
    `).join("");

    document.getElementById("receipt-summary-box").innerHTML = `
      <div class="font-bold mb-8 text-center">${this.config.business_name}</div>
      <div class="text-xs text-dim text-center mb-12">Cliente: ${sale.client_name} · Pago: ${sale.payment_method.toUpperCase()}</div>
      <div class="border-t border-b border-subtle py-8 my-8">${itemsHtml}</div>
      <div class="flex-between text-sm"><span>Subtotal:</span><span>${this.fmt(sale.subtotal)}</span></div>
      ${sale.discount > 0 ? `<div class="flex-between text-sm text-warning"><span>Descuento:</span><span>-${this.fmt(sale.discount)}</span></div>` : ''}
      <div class="flex-between font-bold text-lg mt-6 pt-6 border-t border-subtle">
        <span>TOTAL:</span>
        <span class="text-success">${this.fmt(sale.total)}</span>
      </div>
    `;

    this.modal("modal-receipt", true);
  }

  sendReceiptWhatsApp() {
    if (!this.lastCompletedSale) return;
    const s = this.lastCompletedSale;

    let msg = `*${this.config.business_name}*\n`;
    msg += `📄 *Comprobante de Venta #${s.id}*\n`;
    msg += `📅 Fecha: ${s.date} ${s.time}\n`;
    msg += `👤 Cliente: ${s.client_name}\n`;
    msg += `💳 Pago: ${s.payment_method.toUpperCase()}\n`;
    msg += `--------------------------------\n`;

    s.items.forEach(it => {
      msg += `• ${it.quantity}x ${it.product_name} - ${this.fmt(it.subtotal)}\n`;
    });

    msg += `--------------------------------\n`;
    if (s.discount > 0) msg += `Descuento: -${this.fmt(s.discount)}\n`;
    msg += `*TOTAL: ${this.fmt(s.total)}*\n\n`;
    msg += `¡Gracias por tu compra!`;

    const encoded = encodeURIComponent(msg);
    window.open(`https://wa.me/?text=${encoded}`, "_blank");
  }

  printReceipt() {
    window.print();
  }

  closeReceiptModal() {
    this.modal("modal-receipt", false);
  }

  // ── Escáner de Código de Barras por Cámara ────────────────────
  openBarcodeScanner() {
    this.modal("modal-scanner", true);
    document.getElementById("scanner-result-msg").textContent = "Iniciando cámara...";

    if (!window.Html5Qrcode) {
      document.getElementById("scanner-result-msg").textContent = "Cámara no soportada en este navegador";
      return;
    }

    try {
      this.html5QrCode = new Html5Qrcode("interactive-barcode-reader");
      const config = { fps: 10, qrbox: { width: 250, height: 180 } };

      this.html5QrCode.start(
        { facingMode: "environment" },
        config,
        (decodedText) => {
          this.onBarcodeDetected(decodedText);
        },
        (error) => {
          // Errores de frame normales mientras busca
        }
      ).catch(err => {
        console.error("Camera start error:", err);
        document.getElementById("scanner-result-msg").textContent = "Permiso de cámara denegado o no disponible.";
      });
    } catch (e) {
      console.error(e);
    }
  }

  async onBarcodeDetected(code) {
    if (!code) return;
    this.closeBarcodeScanner();
    this.toast(`Código escaneado: ${code}`);

    try {
      const prod = await this.api(`/api/products/by-barcode/${encodeURIComponent(code)}`);
      this.addToCart(prod.id);
      this.toast(`¡Producto encontrado: ${prod.name}!`);
    } catch (e) {
      // Si no existe, buscar en el filtro de texto
      document.getElementById("pos-search-input").value = code;
      this.filterPosProducts();
      this.toast(`Buscando código ${code}...`, "warning");
    }
  }

  closeBarcodeScanner() {
    if (this.html5QrCode) {
      this.html5QrCode.stop().then(() => {
        this.html5QrCode.clear();
        this.html5QrCode = null;
      }).catch(() => {});
    }
    this.modal("modal-scanner", false);
  }

  // ═══════════════════════════════════════════════════════════════
  // 3. MÓDULO: INVENTARIO & PRODUCTOS
  // ═══════════════════════════════════════════════════════════════
  async loadInventory() {
    try {
      const [res, cats] = await Promise.all([
        this.api("/api/products?limit=250"),
        this.api("/api/categories")
      ]);
      this.products = res.products || [];
      this.categories = cats || [];
      document.getElementById("inv-total-count").textContent = `${this.products.length} productos registrados`;
      this.renderInventory();
    } catch (e) {
      this.toast("Error al cargar inventario", "error");
    }
  }

  filterInvProducts() {
    this.renderInventory();
  }

  toggleLowStockFilter(btn) {
    this.lowStockFilter = !this.lowStockFilter;
    if (btn) btn.classList.toggle("btn-primary", this.lowStockFilter);
    this.renderInventory();
  }

  renderInventory() {
    const list = document.getElementById("inv-products-list");
    if (!list) return;

    const term = document.getElementById("inv-search-input").value.trim().toLowerCase();

    const filtered = this.products.filter(p => {
      const matchText = !term ||
        p.name.toLowerCase().includes(term) ||
        String(p.sku || "").includes(term) ||
        (p.barcode && p.barcode.toLowerCase().includes(term));
      const matchLow = !this.lowStockFilter || (p.stock <= p.min_stock);
      return matchText && matchLow;
    });

    if (filtered.length === 0) {
      list.innerHTML = `<div class="empty-state">No hay productos que coincidan con la búsqueda</div>`;
      return;
    }

    list.innerHTML = filtered.map(p => {
      let badgeClass = "stock-badge-ok";
      if (p.stock <= 0) badgeClass = "stock-badge-out";
      else if (p.stock <= p.min_stock) badgeClass = "stock-badge-low";

      return `
        <div class="inv-card glass-panel">
          <div class="inv-card-left" onclick="app.openEditProductModal(${p.id})">
            <div class="inv-prod-name">${p.name}</div>
            <div class="inv-meta-row">
              <span>SKU: ${p.sku || 'N/A'}</span>
              <span>Cat: ${p.category}</span>
              <span>Costo: ${this.fmt(p.cost)}</span>
            </div>
          </div>
          <div class="inv-card-right">
            <div class="inv-price-col">
              <div class="inv-price">${this.fmt(p.price)}</div>
              <span class="stock-badge ${badgeClass}">${p.stock} disp</span>
            </div>
            <button class="inv-stock-btn" onclick="app.openStockAdjustModal(${p.id})" title="Ajustar Stock">
              +/-
            </button>
          </div>
        </div>
      `;
    }).join("");
  }

  openNewProductModal() {
    document.getElementById("modal-product-title").textContent = "Nuevo Producto";
    document.getElementById("prod-form-id").value = "";
    document.getElementById("prod-form-name").value = "";
    document.getElementById("prod-form-sku").value = "";
    document.getElementById("prod-form-barcode").value = "";
    document.getElementById("prod-form-price").value = "";
    document.getElementById("prod-form-cost").value = "";
    document.getElementById("prod-form-stock").value = "0";
    document.getElementById("prod-form-min-stock").value = "5";

    this.populateCategorySelect();
    this.modal("modal-product", true);
  }

  openEditProductModal(id) {
    const prod = this.products.find(p => p.id === id);
    if (!prod) return;

    document.getElementById("modal-product-title").textContent = "Editar Producto";
    document.getElementById("prod-form-id").value = prod.id;
    document.getElementById("prod-form-name").value = prod.name;
    document.getElementById("prod-form-sku").value = prod.sku || "";
    document.getElementById("prod-form-barcode").value = prod.barcode || "";
    document.getElementById("prod-form-price").value = prod.price;
    document.getElementById("prod-form-cost").value = prod.cost || 0;
    document.getElementById("prod-form-stock").value = prod.stock;
    document.getElementById("prod-form-min-stock").value = prod.min_stock;

    this.populateCategorySelect(prod.category);
    this.modal("modal-product", true);
  }

  populateCategorySelect(selected = "") {
    const sel = document.getElementById("prod-form-category");
    if (!sel) return;
    sel.innerHTML = this.categories.map(c =>
      `<option value="${c.name}" ${c.name === selected ? 'selected' : ''}>${c.name}</option>`
    ).join("");
  }

  async saveProduct(e) {
    e.preventDefault();
    const id = document.getElementById("prod-form-id").value;
    const payload = {
      name: document.getElementById("prod-form-name").value.trim(),
      sku: Number(document.getElementById("prod-form-sku").value) || null,
      barcode: document.getElementById("prod-form-barcode").value.trim(),
      category: document.getElementById("prod-form-category").value,
      price: Number(document.getElementById("prod-form-price").value) || 0,
      cost: Number(document.getElementById("prod-form-cost").value) || 0,
      stock: Number(document.getElementById("prod-form-stock").value) || 0,
      min_stock: Number(document.getElementById("prod-form-min-stock").value) || 5
    };

    try {
      if (id) {
        await this.api(`/api/products/${id}`, "PUT", payload);
        this.toast("Producto actualizado");
      } else {
        await this.api("/api/products", "POST", payload);
        this.toast("Producto creado con éxito");
      }
      this.closeModal("modal-product");
      this.loadInventory();
      this.loadPosData();
    } catch (err) {
      this.toast(err.message, "error");
    }
  }

  openStockAdjustModal(id) {
    const prod = this.products.find(p => p.id === id);
    if (!prod) return;

    this.adjustProdId = id;
    this.adjustProdCurrent = prod.stock;
    document.getElementById("adjust-stock-prod-name").textContent = prod.name;
    document.getElementById("adjust-stock-current").textContent = prod.stock;
    document.getElementById("adjust-delta-input").value = 1;

    this.modal("modal-adjust-stock", true);
  }

  changeAdjustDelta(n) {
    const inp = document.getElementById("adjust-delta-input");
    inp.value = (Number(inp.value) || 0) + n;
  }

  async saveStockAdjustment() {
    const delta = Number(document.getElementById("adjust-delta-input").value) || 0;
    if (delta === 0) {
      this.closeModal("modal-adjust-stock");
      return;
    }

    try {
      await this.api(`/api/products/${this.adjustProdId}/adjust-stock`, "POST", { delta });
      this.toast("Stock actualizado");
      this.closeModal("modal-adjust-stock");
      this.loadInventory();
      this.loadPosData();
    } catch (e) {
      this.toast(e.message, "error");
    }
  }

  // ═══════════════════════════════════════════════════════════════
  // 4. MÓDULO: CAJA (TURNOS & ARQUEO)
  // ═══════════════════════════════════════════════════════════════
  async loadCashStatus() {
    try {
      const data = await this.api("/api/cash/current");
      const badge = document.getElementById("header-cash-badge");
      const badgeText = document.getElementById("header-cash-text");

      const title = document.getElementById("caja-status-title");
      const indicator = document.getElementById("caja-status-indicator");
      const openContent = document.getElementById("caja-open-content");
      const closedContent = document.getElementById("caja-closed-content");

      if (data.status === "open" && data.session) {
        this.cashSession = data.session;

        // Header badge
        badge.className = "status-pill status-open";
        badgeText.textContent = "Caja Abierta";

        // Panel de caja
        title.textContent = `Turno #${this.cashSession.id} en curso`;
        indicator.className = "status-indicator-badge badge-open";
        indicator.textContent = "🟢 ABIERTA";

        openContent.style.display = "block";
        closedContent.style.display = "none";

        document.getElementById("caja-expected-amount").textContent = this.fmt(this.cashSession.expected_cash);
        document.getElementById("caja-initial-amount").textContent = this.fmt(this.cashSession.initial_cash);
        document.getElementById("caja-cash-sales").textContent = this.fmt(this.cashSession.cash_sales);
        document.getElementById("caja-other-sales").textContent = this.fmt(this.cashSession.other_sales);
        document.getElementById("caja-incomes").textContent = this.fmt(this.cashSession.incomes);
        document.getElementById("caja-outcomes").textContent = this.fmt(this.cashSession.outcomes);
        document.getElementById("caja-sales-count").textContent = this.cashSession.sales_count;

        this.renderCashTransactions(this.cashSession.transactions);
      } else {
        this.cashSession = null;

        // Header badge
        badge.className = "status-pill status-closed";
        badgeText.textContent = "Caja Cerrada";

        title.textContent = "Caja Cerrada";
        indicator.className = "status-indicator-badge badge-closed";
        indicator.textContent = "🔴 CERRADA";

        openContent.style.display = "none";
        closedContent.style.display = "block";
        this.renderCashTransactions([]);
      }
    } catch (e) {
      console.error(e);
    }
  }

  renderCashTransactions(txs) {
    const list = document.getElementById("caja-transactions-list");
    if (!list) return;

    if (!txs || txs.length === 0) {
      list.innerHTML = `<div class="empty-state-sm">No hay movimientos registrados en este turno</div>`;
      return;
    }

    list.innerHTML = txs.map(t => {
      const isInc = t.type === "income";
      const cls = isInc ? "tx-amount-in" : "tx-amount-out";
      const sign = isInc ? "+" : "-";

      return `
        <div class="tx-item">
          <div>
            <div class="tx-desc">${t.description}</div>
            <div class="tx-time">${t.timestamp}</div>
          </div>
          <div class="${cls}">${sign}${this.fmt(t.amount)}</div>
        </div>
      `;
    }).join("");
  }

  openOpenCashModal() {
    this.modal("modal-open-cash", true);
  }

  async submitOpenCash() {
    const amt = Number(document.getElementById("open-cash-amount").value) || 0;
    try {
      await this.api("/api/cash/open", "POST", { initial_cash: amt });
      this.toast("¡Caja abierta exitosamente!");
      this.closeModal("modal-open-cash");
      this.loadCashStatus();
    } catch (e) {
      this.toast(e.message, "error");
    }
  }

  openCloseCashModal() {
    if (!this.cashSession) return;
    document.getElementById("close-cash-expected-display").textContent = this.fmt(this.cashSession.expected_cash);
    document.getElementById("close-cash-actual").value = "";
    document.getElementById("close-cash-diff-display").textContent = "$ 0";
    this.modal("modal-close-cash", true);
  }

  calcCashDifference() {
    if (!this.cashSession) return;
    const actual = Number(document.getElementById("close-cash-actual").value) || 0;
    const diff = actual - this.cashSession.expected_cash;

    const diffEl = document.getElementById("close-cash-diff-display");
    diffEl.textContent = this.fmt(diff);
    if (diff === 0) {
      diffEl.className = "text-success";
      diffEl.textContent = "Exacto ($ 0)";
    } else if (diff > 0) {
      diffEl.className = "text-primary";
      diffEl.textContent = `Sobrante: +${this.fmt(diff)}`;
    } else {
      diffEl.className = "text-danger";
      diffEl.textContent = `Faltante: ${this.fmt(diff)}`;
    }
  }

  async submitCloseCash() {
    const actual = Number(document.getElementById("close-cash-actual").value) || 0;
    const notes = document.getElementById("close-cash-notes").value.trim();

    try {
      await this.api("/api/cash/close", "POST", { actual_cash: actual, notes });
      this.toast("¡Caja cerrada correctamente!");
      this.closeModal("modal-close-cash");
      this.loadCashStatus();
    } catch (e) {
      this.toast(e.message, "error");
    }
  }

  openCashMovementModal(type) {
    document.getElementById("cash-movement-type").value = type;
    document.getElementById("cash-movement-title").textContent = type === "income" ? "📥 Ingreso Manual de Dinero" : "📤 Retiro Manual de Dinero";
    document.getElementById("cash-movement-amount").value = "";
    document.getElementById("cash-movement-desc").value = "";
    this.modal("modal-cash-movement", true);
  }

  async submitCashMovement() {
    const type = document.getElementById("cash-movement-type").value;
    const amount = Number(document.getElementById("cash-movement-amount").value) || 0;
    const desc = document.getElementById("cash-movement-desc").value.trim();

    if (amount <= 0 || !desc) {
      this.toast("Completa el monto y motivo", "warning");
      return;
    }

    try {
      await this.api("/api/cash/transaction", "POST", { type, amount, description: desc });
      this.toast("Movimiento guardado con éxito");
      this.closeModal("modal-cash-movement");
      this.loadCashStatus();
    } catch (e) {
      this.toast(e.message, "error");
    }
  }

  // ═══════════════════════════════════════════════════════════════
  // 5. MÓDULO: GASTOS
  // ═══════════════════════════════════════════════════════════════
  async loadExpenses() {
    const { start_date, end_date } = this.getDateRangeParams();
    try {
      const expenses = await this.api(`/api/expenses?start_date=${start_date}&end_date=${end_date}`);
      const list = document.getElementById("gastos-list");
      if (!list) return;

      if (!expenses || expenses.length === 0) {
        list.innerHTML = `<div class="empty-state">No hay gastos registrados en este periodo</div>`;
        return;
      }

      list.innerHTML = expenses.map(e => `
        <div class="inv-card glass-panel">
          <div>
            <div class="inv-prod-name">${e.category}</div>
            <div class="inv-meta-row">
              <span>${e.description || 'Sin detalle'}</span>
              <span>${e.timestamp}</span>
            </div>
          </div>
          <div class="text-danger font-bold text-lg">-${this.fmt(e.amount)}</div>
        </div>
      `).join("");
    } catch (e) {
      this.toast("Error al cargar gastos", "error");
    }
  }

  openNewExpenseModal() {
    document.getElementById("expense-amount").value = "";
    document.getElementById("expense-desc").value = "";
    this.modal("modal-expense", true);
  }

  async submitExpense() {
    const cat = document.getElementById("expense-category").value;
    const amount = Number(document.getElementById("expense-amount").value) || 0;
    const desc = document.getElementById("expense-desc").value.trim();
    const affect = document.getElementById("expense-affect-cash").checked;

    if (amount <= 0) {
      this.toast("Ingresa un monto válido", "warning");
      return;
    }

    try {
      await this.api("/api/expenses", "POST", {
        category: cat,
        amount,
        description: desc,
        affect_cash: affect
      });
      this.toast("Gasto registrado");
      this.closeModal("modal-expense");
      this.loadExpenses();
      this.loadCashStatus();
    } catch (e) {
      this.toast(e.message, "error");
    }
  }

  // ═══════════════════════════════════════════════════════════════
  // 6. MÓDULO: CLIENTES & CRÉDITOS
  // ═══════════════════════════════════════════════════════════════
  async loadClients() {
    try {
      this.clients = await this.api("/api/clients");
      this.renderClientsList();
    } catch (e) {
      this.toast("Error al cargar clientes", "error");
    }
  }

  filterClients() {
    this.renderClientsList();
  }

  renderClientsList() {
    const list = document.getElementById("clientes-list");
    if (!list) return;

    const term = document.getElementById("clientes-search").value.trim().toLowerCase();
    const filtered = this.clients.filter(c =>
      !term ||
      c.name.toLowerCase().includes(term) ||
      (c.phone && c.phone.includes(term)) ||
      (c.document && c.document.includes(term))
    );

    if (filtered.length === 0) {
      list.innerHTML = `<div class="empty-state">No se encontraron clientes</div>`;
      return;
    }

    list.innerHTML = filtered.map(c => `
      <div class="inv-card glass-panel">
        <div>
          <div class="inv-prod-name">${c.name}</div>
          <div class="inv-meta-row">
            <span>📱 ${c.phone || 'Sin tel'}</span>
            <span>Doc: ${c.document || 'N/A'}</span>
          </div>
        </div>
        <div class="text-right">
          <div class="${c.debt > 0 ? 'text-danger font-bold' : 'text-dim'} text-sm">
            ${c.debt > 0 ? `Debe: ${this.fmt(c.debt)}` : 'Sin deuda'}
          </div>
          ${c.debt > 0 ? `
            <button class="btn btn-secondary btn-sm mt-4" onclick="app.openClientPaymentModal(${c.id})">
              Abonar
            </button>
          ` : ''}
        </div>
      </div>
    `).join("");
  }

  openNewClientModal(fromCart = false) {
    this.fromCartModal = fromCart;
    document.getElementById("client-name").value = "";
    document.getElementById("client-phone").value = "";
    document.getElementById("client-doc").value = "";
    document.getElementById("client-address").value = "";
    this.modal("modal-client", true);
  }

  async submitNewClient() {
    const name = document.getElementById("client-name").value.trim();
    if (!name) {
      this.toast("El nombre es requerido", "warning");
      return;
    }

    const payload = {
      name,
      phone: document.getElementById("client-phone").value.trim(),
      document: document.getElementById("client-doc").value.trim(),
      address: document.getElementById("client-address").value.trim()
    };

    try {
      const created = await this.api("/api/clients", "POST", payload);
      this.toast("Cliente creado");
      this.closeModal("modal-client");
      await this.loadClients();
      this.populateClientsSelect();

      if (this.fromCartModal) {
        document.getElementById("cart-client-select").value = created.id;
      }
    } catch (e) {
      this.toast(e.message, "error");
    }
  }

  openClientPaymentModal(clientId) {
    const c = this.clients.find(x => x.id === clientId);
    if (!c) return;

    this.clientForPayment = c;
    document.getElementById("pay-client-name").textContent = c.name;
    document.getElementById("pay-client-debt").textContent = this.fmt(c.debt);
    document.getElementById("pay-amount").value = c.debt;
    document.getElementById("pay-notes").value = "";
    this.modal("modal-client-payment", true);
  }

  async submitClientPayment() {
    if (!this.clientForPayment) return;
    const amount = Number(document.getElementById("pay-amount").value) || 0;
    const notes = document.getElementById("pay-notes").value.trim();

    if (amount <= 0) {
      this.toast("Monto inválido", "warning");
      return;
    }

    try {
      await this.api(`/api/clients/${this.clientForPayment.id}/payment`, "POST", { amount, notes });
      this.toast("Abono registrado correctamente");
      this.closeModal("modal-client-payment");
      this.loadClients();
      this.loadCashStatus();
    } catch (e) {
      this.toast(e.message, "error");
    }
  }

  // ═══════════════════════════════════════════════════════════════
  // 7. MÓDULO: HISTORIAL DE VENTAS
  // ═══════════════════════════════════════════════════════════════
  async loadSalesHistory() {
    const dateInput = document.getElementById("sales-filter-date");
    if (!dateInput.value) {
      dateInput.value = new Date().toISOString().split("T")[0];
    }
    const d = dateInput.value;

    try {
      const sales = await this.api(`/api/sales?start_date=${d}&end_date=${d}`);
      const list = document.getElementById("sales-history-list");
      if (!list) return;

      if (!sales || sales.length === 0) {
        list.innerHTML = `<div class="empty-state">No se registraron ventas en esta fecha</div>`;
        return;
      }

      list.innerHTML = sales.map(s => `
        <div class="inv-card glass-panel" onclick="app.viewSaleDetail(${s.id})">
          <div>
            <div class="inv-prod-name">Venta #${s.id} · ${s.time}</div>
            <div class="inv-meta-row">
              <span>👤 ${s.client_name}</span>
              <span>💳 ${s.payment_method.toUpperCase()}</span>
              <span>${s.items_count} producto(s)</span>
            </div>
          </div>
          <div class="text-right">
            <div class="inv-price">${this.fmt(s.total)}</div>
            <span class="text-dim text-xs">Ver detalle →</span>
          </div>
        </div>
      `).join("");
    } catch (e) {
      this.toast("Error al cargar historial", "error");
    }
  }

  async viewSaleDetail(id) {
    try {
      const s = await this.api(`/api/sales/${id}`);
      this.selectedSaleForDetail = s;

      document.getElementById("sale-detail-title").textContent = `Detalle de Venta #${s.id}`;

      const itemsHtml = s.items.map(it => `
        <div class="flex-between py-2 text-sm border-b border-subtle">
          <span>${it.quantity}x ${it.product_name}</span>
          <strong>${this.fmt(it.subtotal)}</strong>
        </div>
      `).join("");

      document.getElementById("sale-detail-body").innerHTML = `
        <div class="text-sm mb-8">
          <div><strong>Fecha:</strong> ${s.date} ${s.time}</div>
          <div><strong>Cliente:</strong> ${s.client_name}</div>
          <div><strong>Medio de Pago:</strong> ${s.payment_method.toUpperCase()}</div>
          <div><strong>Atendido por:</strong> ${s.uname || 'admin'}</div>
        </div>
        <div class="mb-12">${itemsHtml}</div>
        <div class="flex-between text-sm"><span>Subtotal:</span><span>${this.fmt(s.subtotal)}</span></div>
        ${s.discount > 0 ? `<div class="flex-between text-sm text-warning"><span>Descuento:</span><span>-${this.fmt(s.discount)}</span></div>` : ''}
        <div class="flex-between font-bold text-lg mt-6 pt-6 border-t border-subtle">
          <span>TOTAL:</span>
          <span class="text-success">${this.fmt(s.total)}</span>
        </div>
      `;

      this.modal("modal-sale-detail", true);
    } catch (e) {
      this.toast(e.message, "error");
    }
  }

  async cancelSaleConfirm() {
    if (!this.selectedSaleForDetail) return;
    if (!confirm(`¿Estás seguro de anular la venta #${this.selectedSaleForDetail.id}? El stock será devuelto automáticamente al inventario.`)) {
      return;
    }

    try {
      await this.api(`/api/sales/${this.selectedSaleForDetail.id}/cancel`, "POST");
      this.toast("Venta anulada y stock devuelto");
      this.closeModal("modal-sale-detail");
      this.loadSalesHistory();
      this.loadCashStatus();
      this.loadInventory();
    } catch (e) {
      this.toast(e.message, "error");
    }
  }

  // ═══════════════════════════════════════════════════════════════
  // 8. RED & QR DE CONEXIÓN
  // ═══════════════════════════════════════════════════════════════
  async showNetworkModal() {
    try {
      const data = await this.api("/api/system/network-info");
      document.getElementById("qr-image").src = data.qr_base64;
      document.getElementById("network-url-text").textContent = data.url;
      this.networkUrl = data.url;
      this.modal("modal-network", true);
    } catch (e) {
      this.toast("No se pudo obtener información de red", "error");
    }
  }

  copyUrl() {
    if (this.networkUrl) {
      navigator.clipboard.writeText(this.networkUrl);
      this.toast("¡Enlace copiado al portapapeles!");
    }
  }
}

// Inicializar la aplicación global
const app = new GestProApp();
window.app = app;
