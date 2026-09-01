(function($) {
    'use strict';
    
    console.log('Order item dynamic script loaded');
    
    // Store courses and products data
    var coursesData = [];
    var productsData = [];
    
    // Load courses and products data
    function loadItemData() {
        // Load courses
        $.getJSON('/api/courses/', function(data) {
            coursesData = data;
            console.log('Loaded courses:', coursesData.length);
        });
        
        // Load products
        $.getJSON('/api/products/', function(data) {
            productsData = data;
            console.log('Loaded products:', productsData.length);
        });
    }
    
    // Function to update item_id dropdown based on item_type
    function updateItemIdDropdown(itemTypeSelect, itemIdSelect) {
        var itemType = itemTypeSelect.val();
        var currentValue = itemIdSelect.val();
        
        console.log('Updating dropdown for item_type:', itemType);
        
        // Clear existing options
        itemIdSelect.empty();
        itemIdSelect.append('<option value="">請選擇項目</option>');
        
        if (itemType === 'course') {
            // Populate with courses
            coursesData.forEach(function(course) {
                var selected = (currentValue == course.id) ? 'selected' : '';
                itemIdSelect.append('<option value="' + course.id + '" ' + selected + '>' + 
                                  course.course_code + ' - ' + course.name + '</option>');
            });
            itemIdSelect.show();
            itemIdSelect.closest('td').show();
        } else if (itemType === 'product') {
            // Populate with products
            productsData.forEach(function(product) {
                var selected = (currentValue == product.id) ? 'selected' : '';
                itemIdSelect.append('<option value="' + product.id + '" ' + selected + '>' + 
                                  product.product_code + ' - ' + product.name + '</option>');
            });
            itemIdSelect.show();
            itemIdSelect.closest('td').show();
        } else {
            // Hide the item_id dropdown when no type is selected
            itemIdSelect.hide();
            itemIdSelect.closest('td').hide();
        }
    }
    
    // Function to convert number input to select dropdown
    function convertToSelectField(itemIdInput, row) {
        var itemIdSelect = $('<select name="' + itemIdInput.attr('name') + '" id="' + itemIdInput.attr('id') + '" class="form-control"></select>');
        itemIdSelect.append('<option value="">請選擇項目</option>');
        
        // Copy current value if exists
        var currentValue = itemIdInput.val();
        if (currentValue) {
            itemIdSelect.val(currentValue);
        }
        
        // Replace the input with select
        itemIdInput.replaceWith(itemIdSelect);
        
        return itemIdSelect;
    }
    
    // Function to setup event handlers for a specific row
    function setupRowHandlers(row) {
        var itemTypeSelect = row.find('select[name$="-item_type"]');
        var itemIdInput = row.find('input[name$="-item_id"]');
        
        if (itemTypeSelect.length && itemIdInput.length && !itemTypeSelect.data('initialized')) {
            console.log('Setting up handlers for row');
            itemTypeSelect.data('initialized', true);
            
            // Convert number input to select dropdown
            var itemIdSelect = convertToSelectField(itemIdInput, row);
            
            itemTypeSelect.on('change', function() {
                console.log('Item type changed to:', $(this).val());
                updateItemIdDropdown(itemTypeSelect, itemIdSelect);
            });
            
            // Initialize the dropdown
            updateItemIdDropdown(itemTypeSelect, itemIdSelect);
        }
    }
    
    // Initialize when document is ready
    $(document).ready(function() {
        console.log('Document ready, setting up order item handlers');
        
        // Load item data first
        loadItemData();
        
        // Wait a bit for data to load, then setup handlers
        setTimeout(function() {
            // Handle existing rows
            $('.inline-group .tabular tr').each(function() {
                setupRowHandlers($(this));
            });
        }, 500);
        
        // Handle dynamically added rows
        $(document).on('click', '.add-row a', function() {
            console.log('Add row clicked');
            setTimeout(function() {
                $('.inline-group .tabular tr').each(function() {
                    setupRowHandlers($(this));
                });
            }, 300);
        });
    });
    
})(django.jQuery);
