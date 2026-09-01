document.addEventListener('DOMContentLoaded', function() {
    // Get form elements
    const quantityOptionsInput = document.getElementById('id_quantity_options');
    const priceOptionsInput = document.getElementById('id_price_options');
    const unlimitedQuantityCheckbox = document.getElementById('id_unlimited_quantity');
    const unlimitedPriceCheckbox = document.getElementById('id_unlimited_price');

    // Function to toggle input field state
    function toggleInputState(input, checkbox) {
        input.disabled = checkbox.checked;
        if (checkbox.checked) {
            input.value = '';
        }
    }

    // Add event listeners for quantity options
    if (unlimitedQuantityCheckbox && quantityOptionsInput) {
        unlimitedQuantityCheckbox.addEventListener('change', function() {
            toggleInputState(quantityOptionsInput, this);
        });
        // Initial state
        toggleInputState(quantityOptionsInput, unlimitedQuantityCheckbox);
    }

    // Add event listeners for price options
    if (unlimitedPriceCheckbox && priceOptionsInput) {
        unlimitedPriceCheckbox.addEventListener('change', function() {
            toggleInputState(priceOptionsInput, this);
        });
        // Initial state
        toggleInputState(priceOptionsInput, unlimitedPriceCheckbox);
    }

    // Validate number input on blur
    function validateNumberInput(input) {
        if (!input.value) return;
        
        const numbers = input.value.split(',').map(n => n.trim());
        const isValid = numbers.every(n => {
            const num = parseInt(n);
            return !isNaN(num) && num > 0;
        });

        if (!isValid) {
            input.setCustomValidity('請輸入以逗號分隔的正整數');
            input.reportValidity();
        } else {
            input.setCustomValidity('');
        }
    }

    // Add validation for quantity options
    if (quantityOptionsInput) {
        quantityOptionsInput.addEventListener('blur', function() {
            validateNumberInput(this);
        });
    }

    // Add validation for price options
    if (priceOptionsInput) {
        priceOptionsInput.addEventListener('blur', function() {
            validateNumberInput(this);
        });
    }
});

