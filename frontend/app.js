const API = "http://localhost:8000";
const CHAT_HISTORY_KEY = "smartmart-chat-history";
const CHAT_PRODUCTS_KEY = "smartmart-chat-products";
const CHAT_INVITATION_DISMISSED_KEY = "smartmart-chat-invitation-dismissed";
const CART_KEY = "smartmart-cart";
const PRODUCT_PAGE_SIZE = 50;
const state = {
  chatHistory: loadChatHistory(),
  activeCategory: "",
  categories: [],
  brands: [],
  selectedBrands: new Set(),
  showAllCategories: false,
  showAllBrands: false,
  totalProducts: 0,
  maxPriceLimit: 500000,
  viewMode: "grid",
  productsById: new Map(),
  pendingImageFile: null,
  pendingImageLoading: false,
  cart: loadCart(),
  recentProductIds: loadRecentProductIds(),
  searchOffset: 0,
  searchRequestId: 0
};
const productList = document.querySelector("#productList");
let searchAbortController = null;
let keywordSearchTimer = null;
let invitationTimer = null;
let invitationHideTimer = null;
let invitationConcealTimer = null;
let chatCloseTimer = null;
let chatRequestId = 0;
let invitationIndex = 0;
const chatInvitationMessages = [
  "Xin chào! Mình có thể giúp gì cho bạn? 👋",
  "Bạn đang tìm sản phẩm nào hôm nay? 🛒",
  "Để mình tìm sản phẩm phù hợp với bạn nhé! ✨",
  "Muốn biết sản phẩm nào đang giảm giá không? 🎁",
  "Hỏi mình về giá và tình trạng tồn kho nhé!"
];
let chatInvitationDismissedForSession = false;
try {
  chatInvitationDismissedForSession = sessionStorage.getItem(CHAT_INVITATION_DISMISSED_KEY) === "true";
} catch (error) {
  console.warn("Không thể đọc tùy chọn lời mời chatbot:", error.name);
}

function hideChatInvitation(dismiss = false) {
  clearTimeout(invitationTimer);
  clearTimeout(invitationHideTimer);
  clearTimeout(invitationConcealTimer);
  const wrapper = document.querySelector("#chatInvitationWrap");
  wrapper.classList.remove("is-visible");
  invitationConcealTimer = setTimeout(() => { wrapper.hidden = true; }, 180);
  if (dismiss) {
    chatInvitationDismissedForSession = true;
    try {
      sessionStorage.setItem(CHAT_INVITATION_DISMISSED_KEY, "true");
    } catch (error) {
      console.warn("Không thể lưu tùy chọn lời mời chatbot:", error.name);
    }
  }
}

function scheduleChatInvitation(delay) {
  clearTimeout(invitationTimer);
  if (chatInvitationDismissedForSession) return;
  invitationTimer = setTimeout(showChatInvitation, delay);
}

function showChatInvitation() {
  const panel = document.querySelector("#assistant");
  const question = document.querySelector("#question");
  if (chatInvitationDismissedForSession || !panel.hidden || document.activeElement === question || question.value.trim()) return;
  clearTimeout(invitationConcealTimer);
  const wrapper = document.querySelector("#chatInvitationWrap");
  document.querySelector("#chatInvitationText").textContent =
    chatInvitationMessages[invitationIndex++ % chatInvitationMessages.length];
  wrapper.hidden = false;
  requestAnimationFrame(() => wrapper.classList.add("is-visible"));
  invitationHideTimer = setTimeout(() => {
    wrapper.classList.remove("is-visible");
    invitationConcealTimer = setTimeout(() => {
      wrapper.hidden = true;
      scheduleChatInvitation(5500);
    }, 180);
  }, 4500);
}

function openChat() {
  const panel = document.querySelector("#assistant");
  const toggle = document.querySelector("#chatToggle");
  clearTimeout(chatCloseTimer);
  hideChatInvitation();
  panel.classList.remove("is-closing");
  panel.hidden = false;
  toggle.hidden = true;
  toggle.setAttribute("aria-expanded", "true");
  document.querySelector("#question").focus();
}

function closeChat() {
  const panel = document.querySelector("#assistant");
  const toggle = document.querySelector("#chatToggle");
  panel.classList.add("is-closing");
  toggle.hidden = false;
  toggle.setAttribute("aria-expanded", "false");
  toggle.focus({ preventScroll: true });
  chatCloseTimer = setTimeout(() => {
    panel.hidden = true;
    panel.classList.remove("is-closing");
    scheduleChatInvitation(2500);
  }, 200);
}

function loadChatHistory() {
  try {
    const stored = JSON.parse(localStorage.getItem(CHAT_HISTORY_KEY) || "[]");
    if (!Array.isArray(stored)) return [];
    return stored
      .filter(item => item && ["user", "assistant"].includes(item.role) && typeof item.content === "string")
      .slice(-24)
      .map(item => ({ role: item.role, content: item.content.slice(0, 2000) }));
  } catch (error) {
    console.warn("Không thể khôi phục lịch sử hội thoại:", error.name);
    return [];
  }
}

function persistChatHistory() {
  try {
    localStorage.setItem(CHAT_HISTORY_KEY, JSON.stringify(state.chatHistory.slice(-24)));
  } catch (error) {
    console.warn("Không thể lưu lịch sử hội thoại:", error.name);
  }
}

function loadRecentProductIds() {
  try {
    const stored = JSON.parse(localStorage.getItem(CHAT_PRODUCTS_KEY) || "[]");
    if (!Array.isArray(stored)) return [];
    return [...new Set(stored.filter(id => Number.isInteger(id) && id > 0))].slice(0, 30);
  } catch (error) {
    console.warn("Không thể khôi phục ngữ cảnh sản phẩm:", error.name);
    return [];
  }
}

function rememberChatProducts(products) {
  const productIds = (Array.isArray(products) ? products : [])
    .map(product => Number(product.MaSP))
    .filter(id => Number.isInteger(id) && id > 0);
  if (!productIds.length) return;
  state.recentProductIds = [...new Set(productIds)].slice(0, 30);
  try {
    localStorage.setItem(CHAT_PRODUCTS_KEY, JSON.stringify(state.recentProductIds));
  } catch (error) {
    console.warn("Không thể lưu ngữ cảnh sản phẩm:", error.name);
  }
}

function prioritizeChatProduct(productId) {
  const selectedId = Number(productId);
  if (!Number.isInteger(selectedId) || selectedId <= 0) return;
  state.recentProductIds = [
    selectedId,
    ...state.recentProductIds.filter(id => id !== selectedId)
  ].slice(0, 30);
  try {
    localStorage.setItem(CHAT_PRODUCTS_KEY, JSON.stringify(state.recentProductIds));
  } catch (error) {
    console.warn("Không thể lưu sản phẩm đang tư vấn:", error.name);
  }
}

function loadCart() {
  try {
    const stored = JSON.parse(localStorage.getItem(CART_KEY) || "[]");
    if (!Array.isArray(stored)) return {};
    return Object.fromEntries(stored
      .filter(item => item && Number.isInteger(Number(item.MaSP)) && Number(item.MaSP) > 0
        && Number.isInteger(Number(item.SoLuong)) && Number(item.SoLuong) > 0)
      .map(item => {
        const productId = Number(item.MaSP);
        return [productId, {
          MaSP: productId,
          TenSP: String(item.TenSP || "Sản phẩm"),
          GiaBan: Math.max(0, Number(item.GiaBan) || 0),
          DonViTinh: String(item.DonViTinh || ""),
          SoLuong: Number(item.SoLuong)
        }];
      }));
  } catch (error) {
    console.warn("Không thể khôi phục giỏ hàng:", error.name);
    return {};
  }
}

function cartItemCount() {
  return Object.values(state.cart).reduce((total, item) => total + Number(item.SoLuong || 0), 0);
}

function cartSubtotal() {
  return Object.values(state.cart).reduce((total, item) => total + Number(item.GiaBan || 0) * Number(item.SoLuong || 0), 0);
}

function persistCart() {
  try {
    localStorage.setItem(CART_KEY, JSON.stringify(Object.values(state.cart)));
  } catch (error) {
    console.warn("Không thể lưu giỏ hàng:", error.name);
  }
}

function addToCart(product) {
  const productId = Number(product.MaSP);
  if (!Number.isInteger(productId) || productId <= 0) return 0;
  const current = state.cart[productId];
  state.cart[productId] = {
    MaSP: productId,
    TenSP: String(product.TenSP || "Sản phẩm"),
    GiaBan: Number(product.GiaBan || 0),
    DonViTinh: String(product.DonViTinh || ""),
    SoLuong: Number(current?.SoLuong || 0) + 1
  };
  persistCart();
  return state.cart[productId].SoLuong;
}

function changeCartQuantity(productId, quantity) {
  const item = state.cart[productId];
  if (!item || !Number.isSafeInteger(quantity) || quantity < 1) return false;
  item.SoLuong = quantity;
  persistCart();
  updateCartDisplays();
  return true;
}

function removeCartItem(productId) {
  if (!state.cart[productId]) return;
  delete state.cart[productId];
  persistCart();
  updateCartDisplays();
}

function renderCartItems() {
  const items = Object.values(state.cart);
  const container = document.querySelector("#cartItems");
  if (!items.length) {
    container.innerHTML = `<div class="cart-empty"><span aria-hidden="true">🛒</span><strong>Giỏ hàng đang trống</strong><p>Thêm sản phẩm bạn yêu thích để bắt đầu mua sắm.</p></div>`;
  } else {
    container.innerHTML = items.map(item => {
      const productId = Number(item.MaSP);
      return `<article class="cart-item">
        <img class="cart-item-image" src="${escapeHtml(productImageUrl(item))}" alt="${escapeHtml(item.TenSP)}" loading="lazy">
        <div class="cart-item-details">
          <h3>${escapeHtml(item.TenSP)}</h3>
          <p>${escapeHtml(item.DonViTinh || "Sản phẩm")}</p>
          <strong>${formatMoney(item.GiaBan)}</strong>
        </div>
        <div class="cart-item-controls">
          <div class="quantity-control" aria-label="Số lượng ${escapeHtml(item.TenSP)}">
            <button type="button" data-cart-decrement="${productId}" aria-label="Giảm số lượng ${escapeHtml(item.TenSP)}">−</button>
            <input type="number" min="1" step="1" inputmode="numeric" value="${Number(item.SoLuong)}" data-cart-quantity="${productId}" aria-label="Số lượng ${escapeHtml(item.TenSP)}">
            <button type="button" data-cart-increment="${productId}" aria-label="Tăng số lượng ${escapeHtml(item.TenSP)}">+</button>
          </div>
          <strong class="cart-line-total">${formatMoney(Number(item.GiaBan) * Number(item.SoLuong))}</strong>
          <button class="remove-cart-item" type="button" data-remove-cart-item="${productId}" aria-label="Xóa ${escapeHtml(item.TenSP)} khỏi giỏ hàng">Xóa</button>
        </div>
      </article>`;
    }).join("");
  }
  document.querySelector("#cartItemCount").textContent = `(${cartItemCount()} sản phẩm)`;
  document.querySelector("#cartSubtotal").textContent = formatMoney(cartSubtotal());
  document.querySelector("#clearCart").disabled = items.length === 0;
}

function updateCartDisplays() {
  const total = cartItemCount();
  const cartButton = document.querySelector("#cartButton");
  document.querySelector("#cartCount").textContent = String(total);
  cartButton.setAttribute("aria-label", `Mở giỏ hàng, ${total} sản phẩm`);
  document.querySelectorAll(".chat-product-cart-count").forEach(element => {
    element.textContent = total ? `Giỏ hàng · ${total}` : "";
  });
  document.querySelectorAll(".product-add, .chat-product-add").forEach(button => {
    const productId = Number(button?.dataset.cartProductId);
    const quantity = Number(state.cart[productId]?.SoLuong || 0);
    if (!button) return;
    const name = state.cart[productId]?.TenSP || button.getAttribute("aria-label").replace(/^(Thêm|Đã thêm) | vào giỏ hàng.*$/g, "");
    button.querySelector("span").textContent = quantity ? `Đã thêm · ${quantity}` : "Thêm vào giỏ";
    button.setAttribute("aria-label", quantity
      ? `Đã thêm ${name} vào giỏ hàng, số lượng ${quantity}`
      : `Thêm ${name} vào giỏ hàng`);
  });
  renderCartItems();
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  }[char]));
}

function formatMoney(value) {
  return `${Number(value || 0).toLocaleString("vi-VN")} đồng`;
}

function productImageUrl(product) {
  const imagePath = typeof product?.Anh === "string" ? product.Anh.trim() : "";
  if (/^\/api\/products\/\d+\/image$/.test(imagePath)) {
    return `${API}${imagePath}?v=2`;
  }
  const productId = Number(product?.MaSP);
  return Number.isInteger(productId) && productId > 0
    ? `${API}/api/products/${productId}/image?v=2`
    : `${API}/api/products/default-image`;
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || "Không thể kết nối máy chủ.");
  return data;
}

function renderProducts(products, append = false) {
  products.forEach(product => state.productsById.set(Number(product.MaSP), product));
  const productCards = products.map(product => {
      const image = productImageUrl(product);
      const stock = Number(product.SoLuongTon) > 0;
      return `<article class="product-card">
        <div class="product-image-wrap">
          <img class="product-image" src="${escapeHtml(image)}" alt="${escapeHtml(product.TenSP)}" loading="lazy" onerror="if(this.dataset.fallbackApplied!=='true'){this.dataset.fallbackApplied='true';this.src='${API}/api/products/default-image';}">
        </div>
        <div class="product-body">
          <h3>${escapeHtml(product.TenSP)}</h3>
          <p class="product-meta">${escapeHtml(product.DanhMuc || "")} · ${escapeHtml(product.ThuongHieu || "Chưa cập nhật thương hiệu")}</p>
          <div class="product-bottom">
            <span class="price">${formatMoney(product.GiaBan)}</span>
            <span class="stock ${stock ? "in-stock" : ""}">${stock ? `Còn ${product.SoLuongTon}` : "Hết hàng"}</span>
          </div>
          <div class="product-actions">
            <button class="detail-button" type="button" data-product-id="${Number(product.MaSP)}">Xem chi tiết</button>
            <button class="product-add" type="button" data-cart-product-id="${Number(product.MaSP)}" aria-label="Thêm ${escapeHtml(product.TenSP)} vào giỏ hàng">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/>
              </svg>
              <span>${Number(state.cart[Number(product.MaSP)]?.SoLuong || 0) ? `Đã thêm · ${Number(state.cart[Number(product.MaSP)].SoLuong)}` : "Thêm vào giỏ"}</span>
            </button>
          </div>
        </div>
      </article>`;
  }).join("");
  productList.classList.toggle("list-view", state.viewMode === "list");
  if (append) {
    productList.insertAdjacentHTML("beforeend", productCards);
  } else {
    productList.innerHTML = productCards || `<div class="empty-state">Chưa tìm thấy sản phẩm phù hợp trong CSDL siêu thị. Hãy thử từ khóa khác hoặc chọn một danh mục.</div>`;
  }
}


function renderCategories(categories) {
  state.categories = Array.isArray(categories) ? categories : [];
  const list = document.querySelector("#categoryList");
  const visible = state.showAllCategories ? state.categories : state.categories.slice(0, 6);
  list.innerHTML = `
    <label class="filter-option">
      <input type="checkbox" data-category="" ${state.activeCategory ? "" : "checked"}>
      <span>Tất cả danh mục</span><small>${state.totalProducts}</small>
    </label>
    ${visible.map(category => `
      <label class="filter-option">
        <input type="checkbox" data-category="${escapeHtml(category.TenDM)}" ${state.activeCategory === category.TenDM ? "checked" : ""}>
        <span>${escapeHtml(category.TenDM)}</span><small>${Number(category.SoLuongSanPham || 0)}</small>
      </label>
    `).join("")}`;
  document.querySelector("#categoryViewMore").hidden = state.categories.length <= 6;
  document.querySelector("#categoryViewMore").textContent = state.showAllCategories ? "Thu gọn" : "Xem thêm";
}

function renderBrands(brands = state.brands) {
  state.brands = Array.isArray(brands) ? brands : [];
  const list = document.querySelector("#brandList");
  const search = document.querySelector("#brandSearch").value.trim().toLocaleLowerCase("vi");
  const filtered = state.brands.filter(item =>
    String(item.ThuongHieu || "").toLocaleLowerCase("vi").includes(search)
  );
  const visible = state.showAllBrands || search ? filtered : filtered.slice(0, 8);
  list.innerHTML = visible.map(brand => `
    <label class="filter-option">
      <input type="checkbox" data-brand="${escapeHtml(brand.ThuongHieu)}" ${state.selectedBrands.has(brand.ThuongHieu) ? "checked" : ""}>
      <span>${escapeHtml(brand.ThuongHieu)}</span><small>${Number(brand.SoLuongSanPham || 0)}</small>
    </label>
  `).join("") || `<p class="filter-empty">Không tìm thấy thương hiệu.</p>`;
  const more = document.querySelector("#brandViewMore");
  more.hidden = !!search || filtered.length <= 8;
  more.textContent = state.showAllBrands ? "Thu gọn" : "Xem thêm";
}

function updatePriceSummary() {
  const min = Number(document.querySelector("#minPriceFilter").value || 0);
  const max = Number(document.querySelector("#maxPriceFilter").value || state.maxPriceLimit);
  const suffix = max >= state.maxPriceLimit ? "+" : "";
  document.querySelector("#priceRangeSummary").textContent =
    `${formatMoney(min)} – ${formatMoney(max)}${suffix}`;
}

function setPriceRange(minValue, maxValue) {
  const minInput = document.querySelector("#minPriceFilter");
  const maxInput = document.querySelector("#maxPriceFilter");
  const minRange = document.querySelector("#minPriceRange");
  const maxRange = document.querySelector("#maxPriceRange");
  const min = Math.max(0, Math.min(Number(minValue) || 0, state.maxPriceLimit));
  const requestedMax = maxValue === "" || maxValue == null
    ? state.maxPriceLimit
    : Number(maxValue);
  const max = Math.max(min, Math.min(requestedMax || state.maxPriceLimit, state.maxPriceLimit));
  minInput.value = min > 0 ? String(min) : "";
  maxInput.value = max < state.maxPriceLimit ? String(max) : "";
  minRange.value = String(min);
  maxRange.value = String(max);
  updatePriceSummary();
}

function renderActiveFilters() {
  const chips = [];
  const keyword = document.querySelector("#keyword").value.trim();
  if (keyword) chips.push({ label: `Từ khóa: ${keyword}`, type: "keyword" });
  if (state.activeCategory) chips.push({ label: state.activeCategory, type: "category" });
  state.selectedBrands.forEach(brand => chips.push({ label: brand, type: "brand", value: brand }));
  const min = document.querySelector("#minPriceFilter").value;
  const max = document.querySelector("#maxPriceFilter").value;
  if (min || max) {
    chips.push({ label: `${formatMoney(min || 0)} – ${max ? formatMoney(max) : "không giới hạn"}`, type: "price" });
  }
  if (document.querySelector("#inStockOnly").checked) chips.push({ label: "Còn hàng", type: "stock" });
  if (document.querySelector("#outOfStockOnly").checked) chips.push({ label: "Hết hàng", type: "stock" });
  const container = document.querySelector("#activeFilterChips");
  container.innerHTML = chips.map(chip => `
    <button class="filter-chip" type="button" data-remove-filter="${chip.type}" ${chip.value ? `data-filter-value="${escapeHtml(chip.value)}"` : ""}>
      ${escapeHtml(chip.label)} <span aria-hidden="true">×</span>
    </button>
  `).join("");
}

async function searchProducts({ append = false } = {}) {
  const keyword = document.querySelector("#keyword").value.trim();
  const button = document.querySelector("#searchButton");
  const loadMore = document.querySelector("#loadMoreProducts");
  const offset = append ? state.searchOffset : 0;
  searchAbortController?.abort();
  searchAbortController = new AbortController();
  const requestId = ++state.searchRequestId;
  if (!append) {
    state.searchOffset = 0;
    loadMore.hidden = true;
  }
  const params = new URLSearchParams({ keyword });
  const minPrice = document.querySelector("#minPriceFilter").value;
  const maxPrice = document.querySelector("#maxPriceFilter").value;
  const selectedSort = document.querySelector("#sortBy").value;
  state.selectedBrands.forEach(brand => params.append("brands", brand));
  if (minPrice) params.set("min_price", minPrice);
  if (maxPrice) params.set("max_price", maxPrice);
  if (state.activeCategory) params.set("category", state.activeCategory);
  params.set("in_stock_only", String(document.querySelector("#inStockOnly").checked));
  params.set("out_of_stock_only", String(document.querySelector("#outOfStockOnly").checked));
  const sortBy = selectedSort.startsWith("price") ? "price"
    : selectedSort.startsWith("name") ? "name" : selectedSort;
  params.set("sort_by", sortBy);
  params.set("order", selectedSort.endsWith("_desc") ? "desc" : "asc");
  params.set("limit", String(PRODUCT_PAGE_SIZE));
  params.set("offset", String(offset));
  renderActiveFilters();
  button.disabled = true;
  if (append) loadMore.disabled = true;
  else {
    button.innerHTML = "Đang tìm...";
    document.querySelector("#resultsStatus").hidden = false;
    document.querySelector("#resultsStatus").textContent = "Đang cập nhật sản phẩm...";
    document.querySelector("#products").classList.add("is-loading");
  }
  try {
    const products = await requestJson(
      `${API}/api/products/search?${params}`,
      { signal: searchAbortController.signal }
    );
    if (requestId !== state.searchRequestId) return;
    renderProducts(products, append);
    state.searchOffset = offset + products.length;
    const hasMore = products.length === PRODUCT_PAGE_SIZE;
    document.querySelector("#resultCount").textContent = hasMore
      ? `Đang hiển thị ${state.searchOffset}+ kết quả`
      : `Tìm thấy ${state.searchOffset} kết quả`;
    document.querySelector("#totalProducts").textContent =
      `${state.totalProducts.toLocaleString("vi-VN")} sản phẩm trong cửa hàng`;
    loadMore.hidden = products.length < PRODUCT_PAGE_SIZE;
  } catch (error) {
    if (error.name === "AbortError") return;
    if (requestId !== state.searchRequestId) return;
    productList.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
    document.querySelector("#resultCount").textContent = "Không tải được kết quả";
  } finally {
    if (requestId === state.searchRequestId) {
      button.disabled = false;
      button.innerHTML = 'Tìm sản phẩm <span aria-hidden="true">↗</span>';
      loadMore.disabled = false;
      document.querySelector("#resultsStatus").hidden = true;
      document.querySelector("#products").classList.remove("is-loading");
    }
  }
}

function debounceSearch() {
  clearTimeout(keywordSearchTimer);
  keywordSearchTimer = setTimeout(() => searchProducts(), 300);
}

function initializePriceRange(maxPrice) {
  const availableMax = Number(maxPrice);
  state.maxPriceLimit = Math.max(
    500000,
    Number.isFinite(availableMax) ? Math.ceil(availableMax / 1000) * 1000 : 0
  );
  ["minPriceRange", "maxPriceRange"].forEach(id => {
    document.querySelector(`#${id}`).max = String(state.maxPriceLimit);
  });
  setPriceRange(0, "");
}

function toggleFilterSidebar() {
  const workspace = document.querySelector(".workspace-grid");
  if (window.matchMedia("(max-width: 900px)").matches) {
    const expanded = workspace.classList.toggle("filters-open");
    document.querySelector("#filterBackdrop").hidden = !expanded;
    document.querySelector("#toggleFilters").setAttribute("aria-expanded", String(expanded));
    return;
  }
  const expanded = workspace.classList.toggle("filters-collapsed") === false;
  document.querySelector("#toggleFilters").setAttribute("aria-expanded", String(expanded));
}

function closeMobileFilterSidebar() {
  if (!window.matchMedia("(max-width: 900px)").matches) return;
  const workspace = document.querySelector(".workspace-grid");
  workspace.classList.remove("filters-open");
  document.querySelector("#filterBackdrop").hidden = true;
  document.querySelector("#toggleFilters").setAttribute("aria-expanded", "false");
}

function resetFilters() {
  document.querySelector("#keyword").value = "";
  document.querySelector("#brandSearch").value = "";
  document.querySelector("#minPriceFilter").value = "";
  document.querySelector("#maxPriceFilter").value = "";
  document.querySelector("#sortBy").value = "relevance";
  document.querySelector("#inStockOnly").checked = false;
  document.querySelector("#outOfStockOnly").checked = false;
  state.activeCategory = "";
  state.selectedBrands.clear();
  state.showAllCategories = false;
  state.showAllBrands = false;
  setPriceRange(0, "");
  renderCategories(state.categories);
  renderBrands();
  renderActiveFilters();
  closeMobileFilterSidebar();
  searchProducts();
}

function removeActiveFilter(type, value = "") {
  if (type === "keyword") document.querySelector("#keyword").value = "";
  if (type === "category") {
    state.activeCategory = "";
    renderCategories(state.categories);
  }
  if (type === "brand") state.selectedBrands.delete(value);
  if (type === "price") setPriceRange(0, "");
  if (type === "stock") {
    document.querySelector("#inStockOnly").checked = false;
    document.querySelector("#outOfStockOnly").checked = false;
  }
  renderBrands();
  renderActiveFilters();
  searchProducts();
}

async function showProductDetail(productId) {
  const dialog = document.querySelector("#productDialog");
  const content = document.querySelector("#dialogContent");
  content.innerHTML = "<p>Đang tải thông tin từ CSDL...</p>";
  dialog.showModal();
  try {
    const product = await requestJson(`${API}/api/products/${productId}`);
    const imgUrl = productImageUrl(product);
    content.innerHTML = `
      <div class="detail-image-wrap">
        <img class="detail-image" src="${escapeHtml(imgUrl)}" alt="${escapeHtml(product.TenSP)}" onerror="if(this.dataset.fallbackApplied!=='true'){this.dataset.fallbackApplied='true';this.src='${API}/api/products/default-image';}">
      </div>
      <p class="dialog-label">${escapeHtml(product.DanhMuc)}</p>
      <h2>${escapeHtml(product.TenSP)}</h2>
      <p class="dialog-price">${formatMoney(product.GiaBan)} / ${escapeHtml(product.DonViTinh)}</p>
      <p class="dialog-description">${escapeHtml(product.MoTa || "Chưa có mô tả cho sản phẩm này.")}</p>
      <p><b>Thương hiệu:</b> ${escapeHtml(product.ThuongHieu || "Chưa cập nhật")}<br><b>Tồn kho trong SQL:</b> ${product.SoLuongTon > 0 ? `${product.SoLuongTon} ${escapeHtml(product.DonViTinh)}` : "Hết hàng"}</p>
    `;
  } catch (error) {
    content.innerHTML = `<p>${escapeHtml(error.message)}</p>`;
  }
}

function renderMarkdown(text) {
  const renderInline = value => escapeHtml(value)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  const blocks = [];
  let paragraph = [];
  let listType = "";
  const flushParagraph = () => {
    if (!paragraph.length) return;
    blocks.push(`<p>${paragraph.map(renderInline).join("<br>")}</p>`);
    paragraph = [];
  };
  const closeList = () => {
    if (!listType) return;
    blocks.push(`</${listType}>`);
    listType = "";
  };
  String(text ?? "").split(/\r?\n/).forEach(line => {
    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    const unorderedItem = line.match(/^\s*[-*]\s+(.+)$/);
    const orderedItem = line.match(/^\s*\d+[.)]\s+(.+)$/);
    if (heading) {
      flushParagraph();
      closeList();
      const level = heading[1].length;
      blocks.push(`<h${level}>${renderInline(heading[2])}</h${level}>`);
    } else if (unorderedItem || orderedItem) {
      flushParagraph();
      const nextListType = unorderedItem ? "ul" : "ol";
      if (listType && listType !== nextListType) closeList();
      if (!listType) {
        listType = nextListType;
        blocks.push(`<${listType}>`);
      }
      blocks.push(`<li>${renderInline((unorderedItem || orderedItem)[1])}</li>`);
    } else if (!line.trim()) {
      flushParagraph();
      closeList();
    } else {
      closeList();
      paragraph.push(line);
    }
  });
  flushParagraph();
  closeList();
  return blocks.join("");
}

function shouldAutoScrollChat(messages) {
  return messages.scrollHeight - messages.scrollTop - messages.clientHeight < 90;
}

function appendMessage(role, text) {
  const messages = document.querySelector("#chatMessages");
  const shouldScroll = shouldAutoScrollChat(messages);
  messages.hidden = false;
  document.querySelector("#chatWelcome").hidden = true;
  const message = document.createElement("div");
  const isUser = role === "user";
  message.className = `message ${isUser ? "user-message" : "bot-message"}`;
  if (!isUser) {
    const avatar = document.createElement("span");
    avatar.className = "message-avatar";
    avatar.textContent = "✦";
    message.appendChild(avatar);
  }
  const content = document.createElement("div");
  content.className = "message-content";
  if (isUser) content.textContent = text;
  else content.innerHTML = renderMarkdown(text);
  const timestamp = document.createElement("time");
  timestamp.className = "message-time";
  timestamp.dateTime = new Date().toISOString();
  timestamp.textContent = new Date().toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
  message.append(content, timestamp);
  messages.appendChild(message);
  if (shouldScroll) messages.scrollTop = messages.scrollHeight;
}

function appendThinkingIndicator(text) {
  const messages = document.querySelector("#chatMessages");
  const shouldScroll = shouldAutoScrollChat(messages);
  messages.hidden = false;
  document.querySelector("#chatWelcome").hidden = true;
  const indicator = document.createElement("div");
  indicator.className = "message bot-message thinking-message";
  const avatar = document.createElement("span");
  avatar.className = "message-avatar";
  avatar.textContent = "✦";
  const content = document.createElement("div");
  content.className = "thinking-content";
  content.append(document.createTextNode(text));
  const dots = document.createElement("span");
  dots.className = "thinking-dots";
  dots.setAttribute("aria-label", "AI đang trả lời");
  dots.innerHTML = "<i></i><i></i><i></i>";
  content.appendChild(dots);
  indicator.append(avatar, content);
  messages.appendChild(indicator);
  if (shouldScroll) messages.scrollTop = messages.scrollHeight;
  return indicator;
}

function appendFollowUpQuestions(questions) {
  if (!Array.isArray(questions) || !questions.length) return;
  const messages = document.querySelector("#chatMessages");
  const shouldScroll = shouldAutoScrollChat(messages);
  const wrapper = document.createElement("div");
  wrapper.className = "chat-followups";
  questions.slice(0, 3).forEach(question => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = question;
    button.addEventListener("click", () => sendChat(question));
    wrapper.appendChild(button);
  });
  messages.appendChild(wrapper);
  if (shouldScroll) messages.scrollTop = messages.scrollHeight;
}

function appendStatistics(statistics) {
  if (!statistics || typeof statistics !== "object") return;
  const rows = [
    ["Tổng sản phẩm", statistics.total_products],
    ["Còn hàng", statistics.in_stock_products],
    ["Hết hàng", statistics.out_of_stock_products]
  ].filter(([, value]) => Number.isFinite(Number(value)));
  if (!rows.length) return;

  const wrapper = document.createElement("div");
  wrapper.className = "message bot-message chat-statistics";
  const avatar = document.createElement("span");
  avatar.className = "message-avatar";
  avatar.textContent = "✦";
  const grid = document.createElement("div");
  grid.className = "chat-statistics-grid";
  rows.forEach(([label, value]) => {
    const item = document.createElement("div");
    item.className = "chat-statistic";
    const title = document.createElement("span");
    title.textContent = label;
    const count = document.createElement("strong");
    count.textContent = Number(value).toLocaleString("vi-VN");
    item.append(title, count);
    grid.appendChild(item);
  });
  const messages = document.querySelector("#chatMessages");
  const shouldScroll = shouldAutoScrollChat(messages);
  wrapper.append(avatar, grid);
  messages.appendChild(wrapper);
  if (shouldScroll) messages.scrollTop = messages.scrollHeight;
}

// Thêm message kèm ảnh vào chat
function appendImageMessage(role, text, imageUrl) {
  const messages = document.querySelector("#chatMessages");
  const shouldScroll = shouldAutoScrollChat(messages);
  messages.hidden = false;
  document.querySelector("#chatWelcome").hidden = true;
  const message = document.createElement("div");
  message.className = `message ${role === "user" ? "user-message" : "bot-message"}`;
  if (imageUrl) {
    const img = document.createElement("img");
    img.className = "chat-msg-image";
    img.src = imageUrl;
    img.alt = "Ảnh đã gửi";
    message.appendChild(img);
  }
  if (text) {
    const span = document.createElement("div");
    span.className = "message-content";
    span.textContent = text;
    message.appendChild(span);
  }
  const timestamp = document.createElement("time");
  timestamp.className = "message-time";
  timestamp.dateTime = new Date().toISOString();
  timestamp.textContent = new Date().toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
  message.appendChild(timestamp);
  messages.appendChild(message);
  if (shouldScroll) messages.scrollTop = messages.scrollHeight;
  return message;
}

function appendChatProductResults(
  products,
  title = "Sản phẩm gợi ý",
  searchId = "",
  hasMore = false,
  offset = 10,
  existingWrapper = null
) {
  if (!products || products.length === 0) return;
  const messages = document.querySelector("#chatMessages");
  const shouldScroll = shouldAutoScrollChat(messages);
  const wrapper = existingWrapper || document.createElement("div");
  let grid = wrapper.querySelector(".chat-product-grid");
  if (!existingWrapper) {
    wrapper.className = "chat-product-results";
    wrapper.setAttribute("role", "group");
    wrapper.setAttribute("aria-label", title);
    const heading = document.createElement("div");
    heading.className = "chat-product-heading";
    const headingTitle = document.createElement("strong");
    headingTitle.textContent = title;
    const cartCount = document.createElement("span");
    cartCount.className = "chat-product-cart-count";
    cartCount.setAttribute("aria-live", "polite");
    cartCount.textContent = cartItemCount() ? `Giỏ hàng · ${cartItemCount()}` : "";
    heading.append(headingTitle, cartCount);
    grid = document.createElement("div");
    grid.className = "chat-product-grid";
    wrapper.append(heading, grid);
  }
  products.forEach(product => {
    const card = document.createElement("article");
    card.className = "chat-product-card";
    const productId = Number(product.MaSP);
    const imgUrl = productImageUrl(product);
    const category = product.DanhMuc || "";
    const brand = product.ThuongHieu || "Chưa cập nhật thương hiệu";
    const stock = Number(product.SoLuongTon);
    const stockLabel = Number.isFinite(stock)
      ? stock > 0 ? `Còn hàng · ${stock}` : "Hết hàng"
      : "Tồn kho chưa cập nhật";
    const similarity = Number(product.similarity);
    const semanticSimilarity = Number(product.semantic_similarity);
    const matchLabels = {
      closest: "Giống nhất",
      similar: "Tương tự",
      substitute: "Thay thế phù hợp"
    };
    const matchLabel = matchLabels[product.match_type] || "";
    const reasons = Array.isArray(product.match_reason)
      ? product.match_reason.slice(0, 2).join(" · ")
      : "";
    const quantity = Number(state.cart[productId]?.SoLuong || 0);
    card.innerHTML = `
      <div class="chat-product-image-wrap">
        <img class="chat-product-image" src="${escapeHtml(imgUrl)}" alt="${escapeHtml(product.TenSP)}" loading="lazy" decoding="async">
      </div>
      <div class="chat-product-body">
        ${matchLabel ? `<span class="chat-product-match ${escapeHtml(product.match_type)}">${escapeHtml(matchLabel)}</span>` : ""}
        <h3 class="chat-product-name" title="${escapeHtml(product.TenSP)}">${escapeHtml(product.TenSP)}</h3>
        ${product.matched_object ? `<p class="chat-product-object">Tìm cho: ${escapeHtml(product.matched_object)}</p>` : ""}
        <p class="chat-product-meta">${escapeHtml(brand)}${category ? ` · ${escapeHtml(category)}` : ""}</p>
        <p class="chat-product-price">${formatMoney(product.GiaBan)}</p>
        <p class="chat-product-stock ${Number.isFinite(stock) && stock > 0 ? "in-stock" : ""}">${escapeHtml(stockLabel)}</p>
        <p class="chat-product-unit">${product.DonViTinh ? `Đơn vị: ${escapeHtml(product.DonViTinh)}` : "Đơn vị: chưa cập nhật"}</p>
        ${Number.isFinite(similarity) ? `<p class="chat-product-similarity">Ảnh · cosine ${similarity.toFixed(3)}${Number.isFinite(semanticSimilarity) ? ` · ngữ nghĩa ${semanticSimilarity.toFixed(3)}` : ""}</p>` : ""}
        ${reasons ? `<p class="chat-product-reason">${escapeHtml(reasons)}</p>` : ""}
        <div class="chat-product-actions">
          <button class="chat-product-detail" type="button" data-product-id="${productId}">Xem chi tiết</button>
          <button class="chat-product-add" type="button" data-cart-product-id="${productId}" aria-label="Thêm ${escapeHtml(product.TenSP)} vào giỏ hàng">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/>
            </svg>
            <span>${quantity ? `Đã thêm · ${quantity}` : "Thêm vào giỏ"}</span>
          </button>
        </div>
      </div>
    `;
    const image = card.querySelector(".chat-product-image");
    image.addEventListener("error", () => {
      if (image.dataset.fallbackApplied === "true") return;
      image.dataset.fallbackApplied = "true";
      image.src = `${API}/api/products/default-image`;
    });
    card.querySelector(".chat-product-detail").addEventListener("click", () => {
      prioritizeChatProduct(productId);
      if (searchId) recordVisualSearchFeedback(searchId, productId, "selected");
      showProductDetail(productId);
    });
    card.querySelector(".chat-product-add").addEventListener("click", () => {
      const count = addToCart(product);
      if (!count) return;
      prioritizeChatProduct(productId);
      if (searchId) recordVisualSearchFeedback(searchId, productId, "selected");
      updateCartDisplays();
    });
    grid.appendChild(card);
  });
  if (!existingWrapper) {
    messages.appendChild(wrapper);
    if (searchId) {
      const feedback = document.createElement("div");
      feedback.className = "chat-search-feedback";
      const prompt = document.createElement("span");
      prompt.textContent = "Kết quả có hữu ích không?";
      const yesButton = document.createElement("button");
      yesButton.type = "button";
      yesButton.textContent = "Có";
      const noButton = document.createElement("button");
      noButton.type = "button";
      noButton.textContent = "Chưa";
      yesButton.addEventListener("click", () => recordVisualSearchFeedback(searchId, Number(products[0].MaSP), "helpful", yesButton));
      noButton.addEventListener("click", () => recordVisualSearchFeedback(searchId, Number(products[0].MaSP), "not_helpful", noButton));
      feedback.append(prompt, yesButton, noButton);
      wrapper.appendChild(feedback);
    }
    if (searchId && hasMore) {
      const more = document.createElement("button");
      more.type = "button";
      more.className = "chat-product-more";
      more.textContent = "Xem thêm sản phẩm";
      more.dataset.searchId = searchId;
      more.dataset.offset = String(offset);
      more.addEventListener("click", () => loadMoreVisualResults(more));
      wrapper.appendChild(more);
    }
  } else {
    const more = wrapper.querySelector(".chat-product-more");
    if (more) {
      more.dataset.offset = String(offset);
      more.hidden = !hasMore;
      more.disabled = false;
      more.textContent = "Xem thêm sản phẩm";
    }
  }
  if (shouldScroll) messages.scrollTop = messages.scrollHeight;
}

function appendRecipeResults(recipes) {
  if (!Array.isArray(recipes) || recipes.length === 0) return;
  const messages = document.querySelector("#chatMessages");
  const shouldScroll = shouldAutoScrollChat(messages);
  const wrapper = document.createElement("section");
  wrapper.className = "chat-recipe-results";
  wrapper.setAttribute("aria-label", "Công thức tham khảo");
  const heading = document.createElement("h3");
  heading.className = "chat-recipe-heading";
  heading.textContent = "Công thức tham khảo";
  wrapper.appendChild(heading);

  recipes.forEach(recipe => {
    const card = document.createElement("article");
    card.className = "chat-recipe-card";

    const image = document.createElement("img");
    image.className = "chat-recipe-image";
    image.src = new URL(String(recipe.ImageURL || ""), API).href;
    image.alt = recipe.ImageIsIngredientReference
      ? "Ảnh sản phẩm nguyên liệu, không phải ảnh món ăn"
      : String(recipe.RecipeName || "Ảnh minh họa món ăn");
    image.loading = "lazy";
    image.addEventListener("error", () => {
      if (image.dataset.fallbackApplied === "true") return;
      image.dataset.fallbackApplied = "true";
      image.src = `${API}/api/products/default-image`;
    });

    const body = document.createElement("div");
    body.className = "chat-recipe-body";
    const title = document.createElement("h4");
    title.className = "chat-recipe-name";
    title.textContent = String(recipe.RecipeName || "Công thức");
    const description = document.createElement("p");
    description.className = "chat-recipe-description";
    description.textContent = String(recipe.Description || "");
    const meta = document.createElement("p");
    meta.className = "chat-recipe-meta";
    meta.textContent = [
      recipe.CategoryName || "Món ăn",
      `${Number(recipe.Servings) || 1} người`,
      `Chuẩn bị ${Number(recipe.PreparationTimeMinutes) || 0} phút`,
      `Chế biến ${Number(recipe.CookingTimeMinutes) || 0} phút`,
      recipe.Difficulty || ""
    ].filter(Boolean).join(" · ");

    const toggle = document.createElement("button");
    toggle.className = "chat-recipe-toggle";
    toggle.type = "button";
    toggle.textContent = "Xem công thức";
    toggle.setAttribute("aria-expanded", "false");

    const details = document.createElement("div");
    details.className = "chat-recipe-details";
    details.hidden = true;
    const ingredientsHeading = document.createElement("strong");
    ingredientsHeading.textContent = "Nguyên liệu";
    const ingredients = document.createElement("ul");
    (Array.isArray(recipe.Ingredients) ? recipe.Ingredients : []).forEach(item => {
      const row = document.createElement("li");
      const quantity = `${item.Quantity ?? ""} ${item.Unit || ""}`.trim();
      const name = document.createElement("span");
      name.textContent = `${quantity} ${item.IngredientName || ""}`.trim();
      row.appendChild(name);
      const availability = document.createElement("small");
      availability.className = item.IsAvailableInStore
        ? item.IsInStock ? "recipe-ingredient-in-stock" : "recipe-ingredient-out-of-stock"
        : "recipe-ingredient-external";
      availability.textContent = item.IsAvailableInStore
        ? item.IsInStock ? "Có trong danh mục · còn hàng" : "Có trong danh mục · hiện hết hàng"
        : "Không tìm thấy trong danh mục";
      row.appendChild(availability);
      if (Number.isInteger(Number(item.ProductID)) && Number(item.ProductID) > 0) {
        const productButton = document.createElement("button");
        productButton.className = "chat-recipe-product-link";
        productButton.type = "button";
        productButton.textContent = `Xem ${item.StoreProductName || "sản phẩm"}`;
        productButton.addEventListener("click", () => {
          prioritizeChatProduct(item.ProductID);
          showProductDetail(Number(item.ProductID));
        });
        row.appendChild(productButton);
      }
      if (item.Notes) {
        const note = document.createElement("small");
        note.textContent = String(item.Notes);
        row.appendChild(note);
      }
      ingredients.appendChild(row);
    });

    const stepsHeading = document.createElement("strong");
    stepsHeading.textContent = "Cách chế biến";
    const steps = document.createElement("ol");
    (Array.isArray(recipe.Instructions) ? recipe.Instructions : []).forEach(step => {
      const row = document.createElement("li");
      row.textContent = String(step.instruction || "");
      const detailsText = [
        step.temperature_c != null ? `${step.temperature_c}°C` : "",
        step.duration_minutes != null ? `${step.duration_minutes} phút` : ""
      ].filter(Boolean).join(" · ");
      if (detailsText) row.append(` (${detailsText})`);
      steps.appendChild(row);
    });

    details.append(ingredientsHeading, ingredients, stepsHeading, steps);
    [["Mẹo", recipe.Tips], ["An toàn thực phẩm", recipe.SafetyNotes], ["Lưu ý", recipe.AIReferenceNotice]]
      .forEach(([label, value]) => {
        if (!value) return;
        const note = document.createElement("p");
        note.className = "chat-recipe-note";
        note.textContent = `${label}: ${value}`;
        details.appendChild(note);
      });

    toggle.addEventListener("click", () => {
      details.hidden = !details.hidden;
      toggle.setAttribute("aria-expanded", String(!details.hidden));
      toggle.textContent = details.hidden ? "Xem công thức" : "Thu gọn";
    });

    body.append(title, description, meta, toggle, details);
    card.append(image, body);
    wrapper.appendChild(card);
  });

  messages.appendChild(wrapper);
  if (shouldScroll) messages.scrollTop = messages.scrollHeight;
}

async function recordVisualSearchFeedback(searchId, productId, action, button) {
  try {
    await requestJson(`${API}/api/visual-search/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ search_id: searchId, product_id: productId, action })
    });
    if (button) {
      button.textContent = "Đã ghi nhận";
      button.disabled = true;
    }
  } catch (error) {
    if (button) button.textContent = "Thử lại phản hồi";
    console.warn("Không thể ghi nhận phản hồi tìm kiếm:", error.message);
  }
}

async function loadMoreVisualResults(button) {
  const searchId = button.dataset.searchId;
  const offset = Number(button.dataset.offset || 10);
  button.disabled = true;
  button.textContent = "Đang tải...";
  try {
    const data = await requestJson(
      `${API}/api/chat/search-by-image/${encodeURIComponent(searchId)}?offset=${offset}&limit=10`
    );
    appendChatProductResults(
      data.products,
      "Kết quả tìm kiếm bằng hình ảnh",
      searchId,
      data.has_more,
      offset + data.products.length,
      button.closest(".chat-product-results")
    );
  } catch (error) {
    button.disabled = false;
    button.textContent = "Thử tải lại";
    console.warn("Không thể tải thêm kết quả ảnh:", error.message);
  }
}

async function sendChat(question) {
  const input = document.querySelector("#question");
  const button = document.querySelector("#sendButton");
  const hasImage = !!state.pendingImageFile;

  if (button.disabled || state.pendingImageLoading || (!question.trim() && !hasImage)) return;
  const requestId = ++chatRequestId;

  // Nếu có ảnh pending → gửi qua search-by-image
  if (hasImage) {
    const file = state.pendingImageFile;
    const previewSrc = document.querySelector("#chatPreviewImg").src;
    const userMessage = question || "Tìm sản phẩm tương tự với ảnh này.";
    const historyEntry = {
      role: "user",
      content: question || "Tìm sản phẩm bằng ảnh."
    };
    const previousHistory = state.chatHistory.slice(-12);
    const userMessageElement = appendImageMessage("user", userMessage, previewSrc);

    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    button.textContent = "…";
    input.disabled = true;
    document.querySelector("#chatImageFile").disabled = true;
    document.querySelector("#removeChatImage").disabled = true;

    const thinkingEl = appendThinkingIndicator("Đang phân tích hình ảnh và tìm sản phẩm trong CSDL...");

    try {
      const form = new FormData();
      form.append("file", file);
      form.append("message", question || "");
      form.append("history", JSON.stringify(previousHistory));

      const data = await requestJson(`${API}/api/chat/search-by-image`, { method: "POST", body: form });
      if (requestId !== chatRequestId) return;
      thinkingEl.remove();

      const answer = String(data.answer || "Đã tìm kiếm xong.");
      state.chatHistory.push(historyEntry);
      appendMessage("assistant", answer);
      state.chatHistory.push({ role: "assistant", content: answer });
      persistChatHistory();
      clearChatImage();
      input.value = "";
      input.style.height = "";

      if (data.products && data.products.length > 0) {
        rememberChatProducts(data.products);
        appendChatProductResults(
          data.products,
          "Kết quả tìm kiếm bằng hình ảnh",
          data.search_id || "",
          Boolean(data.has_more)
        );
        renderProducts(data.products);
      }
      appendRecipeResults(data.recipes);
      appendFollowUpQuestions(data.suggestions);
    } catch (error) {
      if (requestId !== chatRequestId) return;
      thinkingEl.remove();
      userMessageElement.remove();
      appendMessage("assistant", error.message || "Không thể tìm kiếm bằng ảnh lúc này.");
    } finally {
      if (requestId === chatRequestId) {
        button.disabled = false;
        button.removeAttribute("aria-busy");
        button.textContent = "↑";
        input.disabled = false;
        document.querySelector("#chatImageFile").disabled = false;
        document.querySelector("#removeChatImage").disabled = false;
      }
    }
    return;
  }

  if (!question.trim()) return;
  const previousHistory = state.chatHistory.slice(-12);
  appendMessage("user", question);
  state.chatHistory.push({ role: "user", content: question });
  persistChatHistory();
  input.value = "";
  input.style.height = "";
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  button.textContent = "…";
  const thinkingEl = appendThinkingIndicator("Đang phân tích câu hỏi và tra cứu dữ liệu...");
  try {
    const data = await requestJson(`${API}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      history: previousHistory,
      recent_product_ids: state.recentProductIds
    })
    });
    if (requestId !== chatRequestId) return;
    thinkingEl.remove();
    const answer = String(data.answer || "Mình chưa có câu trả lời phù hợp lúc này.");
    appendMessage("assistant", answer);
    state.chatHistory.push({ role: "assistant", content: answer });
    persistChatHistory();
    appendStatistics(data.statistics);
    if (data.products && data.products.length > 0) {
      rememberChatProducts(data.products);
      appendChatProductResults(data.products);
      renderProducts(data.products);
    }
    appendRecipeResults(data.recipes);
    appendFollowUpQuestions(data.suggestions);
  } catch (error) {
    if (requestId !== chatRequestId) return;
    thinkingEl.remove();
    appendMessage("assistant", error.message || "Không thể kết nối trợ lý.");
  } finally {
    if (requestId === chatRequestId) {
      button.disabled = false;
      button.removeAttribute("aria-busy");
      button.textContent = "↑";
    }
  }
}

async function boot() {
  try {
    const [filterOptions] = await Promise.all([
      requestJson(`${API}/api/filters`),
      requestJson(`${API}/api/health`)
    ]);
    state.totalProducts = Number(filterOptions.total_products || 0);
    document.querySelector("#totalProducts").textContent =
      `${state.totalProducts.toLocaleString("vi-VN")} sản phẩm trong cửa hàng`;
    initializePriceRange(filterOptions.max_price);
    renderCategories(filterOptions.categories || []);
    renderBrands(filterOptions.brands || []);
    document.querySelector("#apiDot").classList.add("online");
    document.querySelector("#apiStatus").textContent = "API đang hoạt động (SQL Server + trợ lý AI)";
    document.querySelector("#chatStatus").textContent = "Đang trực tuyến";
    document.querySelector("#chatStatusDot").classList.add("online");
    if (state.chatHistory.length) {
      document.querySelector("#chatMessages").replaceChildren();
      document.querySelector("#chatMessages").hidden = false;
      document.querySelector("#chatWelcome").hidden = true;
      state.chatHistory.forEach(item => appendMessage(item.role, item.content));
      const messages = document.querySelector("#chatMessages");
      messages.scrollTop = messages.scrollHeight;
    } else {
      document.querySelector("#chatWelcome").hidden = false;
    }
    await searchProducts();
  } catch (error) {
    document.querySelector("#apiStatus").textContent = "API chưa kết nối";
    document.querySelector("#chatStatus").textContent = "Đang kết nối";
    document.querySelector("#chatStatusDot").classList.remove("online");
    document.querySelector("#productList").innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
  }
}

function startNewChat() {
  chatRequestId += 1;
  state.chatHistory.length = 0;
  state.recentProductIds = [];
  try {
    localStorage.removeItem(CHAT_HISTORY_KEY);
    localStorage.removeItem(CHAT_PRODUCTS_KEY);
  } catch (error) {
    console.warn("Không thể xóa lịch sử đã lưu:", error.name);
  }
  clearChatImage();
  document.querySelector("#question").value = "";
  document.querySelector("#question").style.height = "";
  document.querySelector("#question").disabled = false;
  document.querySelector("#sendButton").disabled = false;
  document.querySelector("#sendButton").removeAttribute("aria-busy");
  document.querySelector("#sendButton").textContent = "↑";
  document.querySelector("#chatImageFile").disabled = false;
  document.querySelector("#removeChatImage").disabled = false;
  document.querySelector("#chatMessages").replaceChildren();
  document.querySelector("#chatMessages").hidden = true;
  document.querySelector("#chatWelcome").hidden = false;
  document.querySelector("#clearChatConfirmation").hidden = true;
}

function resizeChatInput(input) {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 120)}px`;
}

document.querySelector("#searchForm").addEventListener("submit", event => { event.preventDefault(); searchProducts(); });
document.querySelector("#keyword").addEventListener("input", debounceSearch);
document.querySelector("#categoryList").addEventListener("change", event => {
  const input = event.target.closest("[data-category]");
  if (!input) return;
  state.activeCategory = input.checked ? input.dataset.category : "";
  renderCategories(state.categories);
  renderActiveFilters();
});
document.querySelector("#categoryViewMore").addEventListener("click", () => {
  state.showAllCategories = !state.showAllCategories;
  renderCategories(state.categories);
});
document.querySelector("#brandList").addEventListener("change", event => {
  const input = event.target.closest("[data-brand]");
  if (!input) return;
  if (input.checked) state.selectedBrands.add(input.dataset.brand);
  else state.selectedBrands.delete(input.dataset.brand);
  renderBrands();
  renderActiveFilters();
});
document.querySelector("#brandSearch").addEventListener("input", () => renderBrands());
document.querySelector("#brandViewMore").addEventListener("click", () => {
  state.showAllBrands = !state.showAllBrands;
  renderBrands();
});
document.querySelectorAll(".quick-prices button").forEach(button => {
  button.addEventListener("click", () => {
    setPriceRange(button.dataset.minPrice, button.dataset.maxPrice);
    renderActiveFilters();
  });
});
["minPriceRange", "maxPriceRange"].forEach(id => {
  document.querySelector(`#${id}`).addEventListener("input", event => {
    const minRange = document.querySelector("#minPriceRange");
    const maxRange = document.querySelector("#maxPriceRange");
    if (Number(minRange.value) > Number(maxRange.value)) {
      if (event.target === minRange) maxRange.value = minRange.value;
      else minRange.value = maxRange.value;
    }
    setPriceRange(minRange.value, maxRange.value);
    renderActiveFilters();
  });
});
["minPriceFilter", "maxPriceFilter"].forEach(id => {
  document.querySelector(`#${id}`).addEventListener("change", () => {
    setPriceRange(
      document.querySelector("#minPriceFilter").value,
      document.querySelector("#maxPriceFilter").value
    );
    renderActiveFilters();
  });
});
document.querySelector("#inStockOnly").addEventListener("change", () => {
  if (document.querySelector("#inStockOnly").checked) document.querySelector("#outOfStockOnly").checked = false;
  renderActiveFilters();
});
document.querySelector("#outOfStockOnly").addEventListener("change", () => {
  if (document.querySelector("#outOfStockOnly").checked) document.querySelector("#inStockOnly").checked = false;
  renderActiveFilters();
});
document.querySelector("#applyFilters").addEventListener("click", () => {
  closeMobileFilterSidebar();
  searchProducts();
});
document.querySelector("#sortBy").addEventListener("change", () => searchProducts());
document.querySelector("#toggleFilters").addEventListener("click", toggleFilterSidebar);
document.querySelector("#closeFilters").addEventListener("click", closeMobileFilterSidebar);
document.querySelector("#filterBackdrop").addEventListener("click", closeMobileFilterSidebar);
document.querySelector("#collapseFilters").addEventListener("click", event => {
  const sidebar = document.querySelector("#filterSidebar");
  const expanded = sidebar.classList.toggle("content-collapsed") === false;
  document.querySelector("#filterContent").hidden = !expanded;
  event.currentTarget.setAttribute("aria-expanded", String(expanded));
  event.currentTarget.setAttribute("aria-label", expanded ? "Thu gọn bộ lọc" : "Mở bộ lọc");
  event.currentTarget.textContent = expanded ? "−" : "+";
});
document.querySelectorAll(".view-button").forEach(button => {
  button.addEventListener("click", () => {
    state.viewMode = button.dataset.view;
    document.querySelectorAll(".view-button").forEach(item => {
      const active = item === button;
      item.classList.toggle("active", active);
      item.setAttribute("aria-pressed", String(active));
    });
    productList.classList.toggle("list-view", state.viewMode === "list");
  });
});
document.querySelector("#activeFilterChips").addEventListener("click", event => {
  const chip = event.target.closest("[data-remove-filter]");
  if (chip) removeActiveFilter(chip.dataset.removeFilter, chip.dataset.filterValue || "");
});
document.querySelector("#loadMoreProducts").addEventListener("click", () => searchProducts({ append: true }));
document.querySelector("#clearFilters").addEventListener("click", resetFilters);
document.querySelector("#cartButton").addEventListener("click", () => {
  updateCartDisplays();
  document.querySelector("#cartDialog").showModal();
});
document.querySelector("#closeCart").addEventListener("click", () => document.querySelector("#cartDialog").close());
document.querySelector("#cartDialog").addEventListener("click", event => {
  if (event.target === event.currentTarget) event.currentTarget.close();
});
document.querySelector("#cartItems").addEventListener("click", event => {
  const increment = event.target.closest("[data-cart-increment]");
  const decrement = event.target.closest("[data-cart-decrement]");
  const remove = event.target.closest("[data-remove-cart-item]");
  if (increment) {
    const productId = Number(increment.dataset.cartIncrement);
    changeCartQuantity(productId, Number(state.cart[productId]?.SoLuong || 0) + 1);
  } else if (decrement) {
    const productId = Number(decrement.dataset.cartDecrement);
    changeCartQuantity(productId, Math.max(1, Number(state.cart[productId]?.SoLuong || 1) - 1));
  } else if (remove) {
    removeCartItem(Number(remove.dataset.removeCartItem));
  }
});
document.querySelector("#cartItems").addEventListener("change", event => {
  const input = event.target.closest("[data-cart-quantity]");
  if (!input) return;
  const productId = Number(input.dataset.cartQuantity);
  const quantity = Number(input.value);
  if (!Number.isSafeInteger(quantity) || quantity < 1 || !changeCartQuantity(productId, quantity)) {
    updateCartDisplays();
  }
});
document.querySelector("#clearCart").addEventListener("click", () => {
  if (cartItemCount()) document.querySelector("#clearCartConfirmation").hidden = false;
});
document.querySelector("#cancelClearCart").addEventListener("click", () => {
  document.querySelector("#clearCartConfirmation").hidden = true;
});
document.querySelector("#confirmClearCart").addEventListener("click", () => {
  state.cart = {};
  try {
    localStorage.removeItem(CART_KEY);
  } catch (error) {
    console.warn("Không thể xóa giỏ hàng đã lưu:", error.name);
  }
  document.querySelector("#clearCartConfirmation").hidden = true;
  updateCartDisplays();
});
productList.addEventListener("click", event => {
  const addButton = event.target.closest("[data-cart-product-id]");
  if (addButton && productList.contains(addButton)) {
    const product = state.productsById.get(Number(addButton.dataset.cartProductId));
    if (product && addToCart(product)) updateCartDisplays();
    return;
  }
  const detailButton = event.target.closest("[data-product-id]");
  if (detailButton && productList.contains(detailButton)) {
    showProductDetail(detailButton.dataset.productId);
  }
});
document.querySelector("#chatForm").addEventListener("submit", event => { event.preventDefault(); sendChat(document.querySelector("#question").value); });
document.querySelector("#clearChat").addEventListener("click", () => {
  document.querySelector("#clearChatConfirmation").hidden = false;
});
document.querySelector("#cancelClearChat").addEventListener("click", () => {
  document.querySelector("#clearChatConfirmation").hidden = true;
});
document.querySelector("#confirmClearChat").addEventListener("click", startNewChat);
const chatQuestionInput = document.querySelector("#question");
chatQuestionInput.addEventListener("input", () => resizeChatInput(chatQuestionInput));
chatQuestionInput.addEventListener("keydown", event => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    document.querySelector("#chatForm").requestSubmit();
  }
});

// ── Nút upload ảnh trong chat ──────────────────────────────────────────────
const ALLOWED_IMG_TYPES = new Set(["image/jpeg", "image/jpg", "image/png", "image/webp"]);
const MAX_IMG_MB = 8;
let imagePreviewRequestId = 0;

function clearChatImage() {
  imagePreviewRequestId += 1;
  state.pendingImageFile = null;
  state.pendingImageLoading = false;
  const preview = document.querySelector("#chatImagePreview");
  const previewImg = document.querySelector("#chatPreviewImg");
  const label = document.querySelector("#chatImageBtn");
  const fileInput = document.querySelector("#chatImageFile");
  if (preview) preview.hidden = true;
  if (previewImg) previewImg.src = "";
  if (label) label.classList.remove("has-image");
  if (fileInput) fileInput.value = "";
  const sendButton = document.querySelector("#sendButton");
  if (sendButton && !sendButton.hasAttribute("aria-busy")) sendButton.disabled = false;
  const qInput = document.querySelector("#question");
  if (qInput) qInput.placeholder = "Hỏi SmartMart AI hoặc tải ảnh...";
}

function handleChatImageSelect(file) {
  if (!file) return;
  const requestId = ++imagePreviewRequestId;
  const fileInput = document.querySelector("#chatImageFile");
  const showError = message => {
    if (requestId !== imagePreviewRequestId) return;
    state.pendingImageLoading = false;
    fileInput.value = "";
    appendMessage("assistant", message);
    if (!document.querySelector("#sendButton").hasAttribute("aria-busy")) {
      document.querySelector("#sendButton").disabled = false;
    }
  };
  state.pendingImageLoading = false;
  if (!document.querySelector("#sendButton").hasAttribute("aria-busy")) {
    document.querySelector("#sendButton").disabled = false;
  }
  if (!ALLOWED_IMG_TYPES.has(file.type.toLowerCase())) {
    fileInput.value = "";
    appendMessage("assistant", `❌ Định dạng '${file.type}' không được hỗ trợ. Vui lòng dùng JPG, PNG hoặc WebP.`);
    return;
  }
  if (file.size > MAX_IMG_MB * 1024 * 1024) {
    fileInput.value = "";
    appendMessage("assistant", `❌ Ảnh vượt quá ${MAX_IMG_MB}MB. Vui lòng chọn ảnh nhỏ hơn.`);
    return;
  }
  state.pendingImageLoading = true;
  document.querySelector("#sendButton").disabled = true;
  const reader = new FileReader();
  reader.onerror = () => showError("❌ Không thể đọc ảnh này. Vui lòng chọn lại tệp ảnh.");
  reader.onload = () => {
    if (requestId !== imagePreviewRequestId) return;
    if (typeof reader.result !== "string") {
      showError("❌ Không thể đọc ảnh này. Vui lòng chọn lại tệp ảnh.");
      return;
    }
    const image = new Image();
    image.onerror = () => showError("❌ Tệp không phải ảnh hợp lệ hoặc ảnh bị lỗi. Vui lòng chọn ảnh khác.");
    image.onload = () => {
      if (requestId !== imagePreviewRequestId) return;
      state.pendingImageFile = file;
      state.pendingImageLoading = false;
      document.querySelector("#chatPreviewImg").src = reader.result;
      document.querySelector("#chatImagePreview").hidden = false;
      document.querySelector("#chatImageBtn").classList.add("has-image");
      document.querySelector("#question").placeholder = "Thêm mô tả (tùy chọn) rồi nhấn gửi...";
      document.querySelector("#question").focus();
      if (!document.querySelector("#sendButton").hasAttribute("aria-busy")) {
        document.querySelector("#sendButton").disabled = false;
      }
    };
    image.src = reader.result;
  };
  reader.onabort = () => showError("❌ Không thể đọc ảnh này. Vui lòng chọn lại tệp ảnh.");
  reader.readAsDataURL(file);
}

document.querySelector("#chatImageFile").addEventListener("change", e => handleChatImageSelect(e.target.files[0]));
document.querySelector("#removeChatImage").addEventListener("click", e => { e.stopPropagation(); clearChatImage(); });

// ── Các event listeners cũ ────────────────────────────────────────────────
document.querySelector("#chatToggle").addEventListener("click", () => {
  openChat();
});
document.querySelector("#chatInvitation").addEventListener("click", () => {
  hideChatInvitation(true);
  openChat();
});
document.querySelector("#dismissChatInvitation").addEventListener("click", () => hideChatInvitation(true));
document.querySelector("#closeChat").addEventListener("click", closeChat);
document.querySelector("#minimizeChat").addEventListener("click", closeChat);
document.querySelectorAll("[data-question]").forEach(button => button.addEventListener("click", () => sendChat(button.dataset.question)));
document.querySelector("#closeDialog").addEventListener("click", () => document.querySelector("#productDialog").close());

updateCartDisplays();
scheduleChatInvitation(2500);
boot();
