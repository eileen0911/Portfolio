/**
 * Order Form JavaScript
 * Handles dynamic order item management and form validation
 */

let coursesData = [];
let productsData = [];
let itemCounter = 0;

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    loadCoursesData();
    loadProductsData();
    initializeMemberSearch();
    
    // Only add initial order item if this is a new order (no existing items)
    const existingItems = document.querySelectorAll('#orderItems .order-item').length;
    if (existingItems === 0) {
        addOrderItem(); // Add initial order item for new orders
    }
});

/**
 * Load courses data from server
 */
function loadCoursesData() {
    fetch('/api/courses/')
        .then(response => response.json())
        .then(data => {
            coursesData = data;
        })
        .catch(error => {
            console.error('Error loading courses:', error);
        });
}

/**
 * Load products data from server
 */
function loadProductsData() {
    fetch('/api/products/')
        .then(response => response.json())
        .then(data => {
            productsData = data;
        })
        .catch(error => {
            console.error('Error loading products:', error);
        });
}

/**
 * Add a new order item row
 */
function addOrderItem() {
    const template = document.getElementById('orderItemTemplate');
    const clone = template.content.cloneNode(true);
    const container = document.getElementById('orderItems');
    
    // Update names with counter to ensure uniqueness
    const selects = clone.querySelectorAll('select');
    const inputs = clone.querySelectorAll('input');
    
    selects.forEach(select => {
        const originalName = select.name;
        select.name = originalName;
    });
    
    container.appendChild(clone);
    itemCounter++;
}

/**
 * Remove an order item row
 */
function removeOrderItem(button) {
    const orderItem = button.closest('.order-item');
    orderItem.remove();
    calculateTotalAmount();
}

/**
 * Update item options based on selected type
 */
function updateItemOptions(select) {
    const itemType = select.value;
    const orderItem = select.closest('.order-item');
    const itemSelect = orderItem.querySelector('select[name="item_id"]');
    const quantitySelect = orderItem.querySelector('select[name="quantity"]');
    const priceSelect = orderItem.querySelector('select[name="unit_price"]');
    
    // Clear dependent selects
    clearSelect(itemSelect, '請先選擇類型');
    clearSelect(quantitySelect, '請先選擇項目');
    clearSelect(priceSelect, '請先選擇項目');
    
    if (itemType === 'course') {
        populateCourseOptions(itemSelect);
    } else if (itemType === 'product') {
        populateProductOptions(itemSelect);
    }
}

/**
 * Populate course options
 */
function populateCourseOptions(select) {
    coursesData.forEach(course => {
        const option = document.createElement('option');
        option.value = course.id;
        option.textContent = `${course.course_code} - ${course.name}`;
        option.dataset.quantityOptions = course.quantity_options;
        option.dataset.priceOptions = course.price_options;
        option.dataset.unlimitedQuantity = course.unlimited_quantity;
        option.dataset.unlimitedPrice = course.unlimited_price;
        select.appendChild(option);
    });
}

/**
 * Populate product options
 */
function populateProductOptions(select) {
    productsData.forEach(product => {
        const option = document.createElement('option');
        option.value = product.id;
        option.textContent = `${product.product_code} - ${product.name}`;
        option.dataset.quantityOptions = product.quantity_options;
        option.dataset.priceOptions = product.price_options;
        option.dataset.unlimitedQuantity = product.unlimited_quantity;
        option.dataset.unlimitedPrice = product.unlimited_price;
        select.appendChild(option);
    });
}

/**
 * Update quantity and price options based on selected item
 */
function updateQuantityPriceOptions(select) {
    const selectedOption = select.options[select.selectedIndex];
    const orderItem = select.closest('.order-item');
    const quantityContainer = orderItem.querySelector('.col-md-2:nth-child(3)');
    const priceContainer = orderItem.querySelector('.col-md-2:nth-child(4)');
    
    if (!selectedOption.dataset) return;
    
    // Handle quantity options
    if (selectedOption.dataset.unlimitedQuantity === 'true') {
        // Replace dropdown with text input for unlimited quantity
        replaceWithTextInput(quantityContainer, 'quantity', '請輸入數量', 'number', '1', 'min="1"');
    } else if (selectedOption.dataset.quantityOptions) {
        // Keep dropdown for limited options
        replaceWithSelect(quantityContainer, 'quantity', '請選擇數量');
        const quantitySelect = quantityContainer.querySelector('select[name="quantity"]');
        const quantities = selectedOption.dataset.quantityOptions.split(',');
        quantities.forEach(qty => {
            const option = document.createElement('option');
            option.value = qty.trim();
            option.textContent = qty.trim();
            quantitySelect.appendChild(option);
        });
    }
    
    // Handle price options
    if (selectedOption.dataset.unlimitedPrice === 'true') {
        // Replace dropdown with text input for unlimited price
        replaceWithTextInput(priceContainer, 'unit_price', '請輸入單價', 'number', '0', 'min="0" step="0.01"');
    } else if (selectedOption.dataset.priceOptions) {
        // Keep dropdown for limited options
        replaceWithSelect(priceContainer, 'unit_price', '請選擇單價');
        const priceSelect = priceContainer.querySelector('select[name="unit_price"]');
        const prices = selectedOption.dataset.priceOptions.split(',');
        prices.forEach(price => {
            const option = document.createElement('option');
            option.value = price.trim();
            option.textContent = '$' + price.trim();
            priceSelect.appendChild(option);
        });
    }
}

/**
 * Calculate total for a specific order item
 */
function calculateTotal(element) {
    const orderItem = element.closest('.order-item');
    const quantityElement = orderItem.querySelector('input[name="quantity"], select[name="quantity"]');
    const unitPriceElement = orderItem.querySelector('input[name="unit_price"], select[name="unit_price"]');
    const totalDisplay = orderItem.querySelector('.form-control-plaintext');
    
    const quantity = quantityElement ? quantityElement.value : '';
    const unitPrice = unitPriceElement ? unitPriceElement.value : '';
    
    if (quantity && unitPrice && quantity !== 'custom' && unitPrice !== 'custom') {
        const total = parseInt(quantity) * parseFloat(unitPrice);
        totalDisplay.textContent = '$' + total.toLocaleString();
    } else {
        totalDisplay.textContent = '$0';
    }
    
    calculateTotalAmount();
}

/**
 * Calculate total amount for all order items
 */
function calculateTotalAmount() {
    const totalDisplays = document.querySelectorAll('#orderItems .form-control-plaintext');
    let total = 0;
    
    totalDisplays.forEach(display => {
        const text = display.textContent;
        if (text && text !== '$0') {
            // Extract number from text like "$1,000"
            const number = text.replace(/[$,]/g, '');
            if (!isNaN(number)) {
                total += parseFloat(number);
            }
        }
    });
    
    const totalElement = document.getElementById('totalAmount');
    if (totalElement) {
        totalElement.textContent = total.toLocaleString();
    }
}

/**
 * Clear a select element and add a default option
 */
function clearSelect(select, defaultText) {
    select.innerHTML = `<option value="">${defaultText}</option>`;
    select.disabled = false;
}

/**
 * Add a custom option to a select element
 */
function addCustomOption(select, value, text) {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = text;
    select.appendChild(option);
}

/**
 * Replace dropdown with text input for unlimited options
 */
function replaceWithTextInput(container, name, placeholder, type, defaultValue, attributes) {
    // Remove existing input/select
    const existingInput = container.querySelector('input, select');
    if (existingInput) {
        existingInput.remove();
    }
    
    // Create new text input
    const input = document.createElement('input');
    input.type = type;
    input.name = name;
    input.className = 'form-control';
    input.placeholder = placeholder;
    input.value = defaultValue;
    
    // Add additional attributes
    if (attributes) {
        const attrs = attributes.split(' ');
        attrs.forEach(attr => {
            if (attr.includes('=')) {
                const [key, value] = attr.split('=');
                input.setAttribute(key, value.replace(/"/g, ''));
            }
        });
    }
    
    // Add event listener for calculation
    input.addEventListener('input', function() {
        calculateTotal(this);
    });
    
    container.appendChild(input);
}

/**
 * Replace text input with dropdown for limited options
 */
function replaceWithSelect(container, name, placeholder) {
    // Remove existing input/select
    const existingInput = container.querySelector('input, select');
    if (existingInput) {
        existingInput.remove();
    }
    
    // Create new select
    const select = document.createElement('select');
    select.name = name;
    select.className = 'form-control';
    select.onchange = function() { calculateTotal(this); };
    
    // Add default option
    const defaultOption = document.createElement('option');
    defaultOption.value = '';
    defaultOption.textContent = placeholder;
    select.appendChild(defaultOption);
    
    container.appendChild(select);
}

/**
 * Validate order form before submission
 */
function validateOrderForm() {
    const memberInput = document.querySelector('input[name="member"]');
    const orderDate = document.querySelector('input[name="order_date"]');
    const paymentMethod = document.querySelector('select[name="payment_method"]');
    const orderStatus = document.querySelector('select[name="order_status"]');
    
    // Check required fields
    if (!memberInput || !memberInput.value) {
        alert('請選擇會員');
        return false;
    }
    
    if (!orderDate.value) {
        alert('請選擇訂單日期');
        return false;
    }
    
    if (!paymentMethod.value) {
        alert('請選擇付款方式');
        return false;
    }
    
    if (!orderStatus.value) {
        alert('請選擇訂單狀態');
        return false;
    }
    
    // Check if there are any order items (only for new orders)
    const orderItems = document.querySelectorAll('#orderItems .order-item');
    const hasExistingItems = document.querySelector('table tbody tr') !== null;
    
    // Only validate order items for new orders
    if (!hasExistingItems) {
        if (orderItems.length === 0) {
            alert('請至少新增一個訂單項目');
            return false;
        }
        
        // Validate each order item
        for (let item of orderItems) {
            const itemType = item.querySelector('select[name="item_type"]').value;
            const itemId = item.querySelector('select[name="item_id"]').value;
            const quantityElement = item.querySelector('input[name="quantity"], select[name="quantity"]');
            const unitPriceElement = item.querySelector('input[name="unit_price"], select[name="unit_price"]');
            const subtotalDisplay = item.querySelector('.form-control-plaintext');
            
            const quantity = quantityElement ? quantityElement.value : '';
            const unitPrice = unitPriceElement ? unitPriceElement.value : '';
            
            if (!itemType || !itemId || !quantity || !unitPrice) {
                alert('請完整填寫所有訂單項目');
                return false;
            }
            
            // Check if subtotal is calculated (not $0)
            if (subtotalDisplay.textContent === '$0') {
                alert('請確認所有訂單項目的數量和單價都已正確選擇');
                return false;
            }
        }
    }
    
    return true;
}

// Add form validation on submit
document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('orderForm');
    if (form) {
        form.addEventListener('submit', function(e) {
            if (!validateOrderForm()) {
                e.preventDefault();
            }
        });
    }
});

/**
 * Initialize member search functionality
 */
function initializeMemberSearch() {
    const searchInput = document.getElementById('member-search-input');
    const searchResults = document.getElementById('member-search-results');
    
    if (!searchInput || !searchResults) return;
    
    let searchTimeout;
    
    // Handle input events
    searchInput.addEventListener('input', function() {
        const query = this.value.trim();
        
        // Clear previous timeout
        clearTimeout(searchTimeout);
        
        if (query.length >= 2) {
            // Debounce search requests
            searchTimeout = setTimeout(() => {
                searchMembers(query);
            }, 300);
        } else if (query.length > 0) {
            // Show message for insufficient characters
            showInsufficientCharactersMessage();
        } else {
            hideSearchResults();
        }
    });
    
    // Handle focus events
    searchInput.addEventListener('focus', function() {
        const query = this.value.trim();
        if (query.length >= 2) {
            showSearchResults();
        }
    });
    
    // Handle blur events (with delay to allow clicking on results)
    searchInput.addEventListener('blur', function() {
        setTimeout(() => {
            hideSearchResults();
        }, 200);
    });
    
    // Hide results when clicking outside
    document.addEventListener('click', function(e) {
        if (!searchInput.contains(e.target) && !searchResults.contains(e.target)) {
            hideSearchResults();
        }
    });
}

/**
 * Search for members via AJAX
 */
function searchMembers(query) {
    const searchResults = document.getElementById('member-search-results');
    if (!searchResults) return;
    
    // Show loading state
    searchResults.innerHTML = '<div class="p-3 text-muted text-center"><i class="spinner-border spinner-border-sm me-2"></i>搜尋中...</div>';
    showSearchResults();
    
    fetch(`/api/members/search/?q=${encodeURIComponent(query)}`)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            displaySearchResults(data);
        })
        .catch(error => {
            console.error('Error searching members:', error);
            displaySearchError();
        });
}

/**
 * Display search results
 */
function displaySearchResults(members) {
    const searchResults = document.getElementById('member-search-results');
    if (!searchResults) return;
    
    searchResults.innerHTML = '';
    
    if (members.length === 0) {
        const noResults = document.createElement('div');
        noResults.className = 'p-3 text-muted text-center';
        noResults.innerHTML = `
            <i class="bi bi-search me-2"></i>
            找不到符合條件的會員
            <br>
            <small class="text-muted">請嘗試輸入會員姓名或手機號碼</small>
        `;
        searchResults.appendChild(noResults);
    } else {
        members.forEach(member => {
            const resultItem = document.createElement('div');
            resultItem.className = 'p-3 border-bottom cursor-pointer member-result';
            resultItem.style.cursor = 'pointer';
            resultItem.innerHTML = `
                <div class="fw-bold">${member.name}</div>
                <div class="text-muted small">${member.phone} - ${member.member_code}</div>
            `;
            resultItem.dataset.memberId = member.id;
            resultItem.dataset.memberName = member.name;
            resultItem.dataset.memberPhone = member.phone;
            resultItem.dataset.memberCode = member.member_code;
            
            resultItem.addEventListener('click', function() {
                selectMember(member);
            });
            
            searchResults.appendChild(resultItem);
        });
    }
    
    showSearchResults();
}

/**
 * Display search error
 */
function displaySearchError() {
    const searchResults = document.getElementById('member-search-results');
    if (!searchResults) return;
    
    searchResults.innerHTML = `
        <div class="p-3 text-danger text-center">
            <i class="bi bi-exclamation-triangle me-2"></i>
            搜尋時發生錯誤
            <br>
            <small class="text-muted">請稍後再試或聯繫系統管理員</small>
        </div>
    `;
    showSearchResults();
}

/**
 * Show insufficient characters message
 */
function showInsufficientCharactersMessage() {
    const searchResults = document.getElementById('member-search-results');
    if (!searchResults) return;
    
    searchResults.innerHTML = `
        <div class="p-3 text-info text-center">
            <i class="bi bi-info-circle me-2"></i>
            請輸入至少2個字元進行搜尋
        </div>
    `;
    showSearchResults();
}

/**
 * Show search results dropdown
 */
function showSearchResults() {
    const searchResults = document.getElementById('member-search-results');
    if (searchResults) {
        searchResults.style.display = 'block';
    }
}

/**
 * Hide search results dropdown
 */
function hideSearchResults() {
    const searchResults = document.getElementById('member-search-results');
    if (searchResults) {
        searchResults.style.display = 'none';
    }
}

/**
 * Select a member from search results
 */
function selectMember(member) {
    const searchInput = document.getElementById('member-search-input');
    const memberHiddenInput = document.querySelector('input[name="member"]');
    const selectedMemberDisplay = document.getElementById('selected-member-display');
    const selectedMemberInfo = document.getElementById('selected-member-info');
    
    if (!searchInput || !memberHiddenInput || !selectedMemberDisplay || !selectedMemberInfo) return;
    
    // Set the hidden input value
    memberHiddenInput.value = member.id;
    
    // Update the display
    selectedMemberInfo.textContent = `${member.name} (${member.phone}) - ${member.member_code}`;
    selectedMemberDisplay.style.display = 'block';
    
    // Clear the search input
    searchInput.value = '';
    
    // Hide search results
    hideSearchResults();
}

/**
 * Clear member selection
 */
function clearMemberSelection() {
    const searchInput = document.getElementById('member-search-input');
    const memberHiddenInput = document.querySelector('input[name="member"]');
    const selectedMemberDisplay = document.getElementById('selected-member-display');
    
    if (!searchInput || !memberHiddenInput || !selectedMemberDisplay) return;
    
    // Clear the hidden input value
    memberHiddenInput.value = '';
    
    // Hide the selected member display
    selectedMemberDisplay.style.display = 'none';
    
    // Focus back to search input
    searchInput.focus();
}
