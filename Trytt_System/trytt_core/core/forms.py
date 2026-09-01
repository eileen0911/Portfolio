from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from .models import Order, OrderItem, Course, Product, ProductInventory
from accounts.models import Member, Coach
from .models import Session # Import Session model


class SessionSearchForm(forms.Form):
    """Form for searching sessions"""
    search_term = forms.CharField(
        label=_('搜尋'),
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('輸入會員姓名/電話/課程名稱')
        })
    )
    
    coach_filter = forms.ModelChoiceField(
        label=_('上課教練'),
        required=False,
        queryset=Coach.objects.filter(status='active').order_by('name'),
        empty_label=_('上課教練'),
        widget=forms.Select(attrs={
            'class': 'form-control'
        })
    )
    
    date_from = forms.DateField(
        label=_('開始日期'),
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control'
        })
    )
    
    date_to = forms.DateField(
        label=_('結束日期'),
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control'
        })
    )


class CourseForm(forms.ModelForm):
    """Form for creating and updating courses"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Add CSS classes
        self.fields['name'].widget.attrs.update({
            'class': 'form-control',
            'autocomplete': 'off'
        })
        self.fields['quantity_options'].widget.attrs.update({
            'class': 'form-control',
            'autocomplete': 'off'
        })
        self.fields['price_options'].widget.attrs.update({
            'class': 'form-control',
            'autocomplete': 'off'
        })
        self.fields['unlimited_quantity'].widget.attrs.update({
            'class': 'form-check-input'
        })
        self.fields['unlimited_price'].widget.attrs.update({
            'class': 'form-check-input'
        })
        self.fields['notes'].widget.attrs.update({
            'class': 'form-control',
            'autocomplete': 'off'
        })
        self.fields['status'].widget.attrs.update({
            'class': 'form-control',
            'autocomplete': 'off'
        })

    class Meta:
        model = Course
        fields = ['name', 'quantity_options', 'price_options', 'unlimited_quantity', 'unlimited_price', 'notes', 'status']
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
        }


class OrderForm(forms.ModelForm):
    """Form for creating and updating orders"""
    
    # Add member search field for new orders
    member_search = forms.CharField(
        label=_('搜尋會員'),
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('輸入會員姓名或手機號碼'),
            'id': 'member-search-input',
            'autocomplete': 'off'
        })
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set initial order date to today for new orders
        if not self.instance.pk:  # If creating new order
            self.fields['order_date'].initial = timezone.now().date()
            self.fields['order_status'].initial = 'unpaid'
            # Hide the member field for new orders, use search instead
            self.fields['member'].widget = forms.HiddenInput()
        else:
            # For existing orders, hide the search field and make member field hidden
            self.fields['member_search'].widget = forms.HiddenInput()
            # Make member field hidden for existing orders (displayed as plain text in template)
            self.fields['member'].widget = forms.HiddenInput()
        
        # Make fields readonly if order is paid
        if self.instance.pk and self.instance.order_status == 'paid':
            # Make order_status disabled (readonly doesn't work on select elements)
            self.fields['order_status'].widget.attrs.update({
                'class': 'form-control',
                'autocomplete': 'off',
                'disabled': True
            })
            self.fields['order_status'].help_text = _('已付款的訂單狀態不可修改')
            
            # Make order_date readonly
            self.fields['order_date'].widget.attrs.update({
                'class': 'form-control',
                'autocomplete': 'off',
                'readonly': True
            })
            self.fields['order_date'].help_text = _('已付款的訂單日期不可修改')
            
            # Make payment_method disabled (readonly doesn't work on select elements)
            self.fields['payment_method'].widget.attrs.update({
                'class': 'form-control',
                'autocomplete': 'off',
                'disabled': True
            })
            self.fields['payment_method'].help_text = _('已付款的訂單付款方式不可修改')
        else:
            # Normal field styling for non-paid orders
            self.fields['order_status'].widget.attrs.update({
                'class': 'form-control',
                'autocomplete': 'off'
            })
            self.fields['member'].widget.attrs.update({
                'class': 'form-control',
                'autocomplete': 'off'
            })
            self.fields['order_date'].widget.attrs.update({
                'class': 'form-control',
                'autocomplete': 'off'
            })
            self.fields['payment_method'].widget.attrs.update({
                'class': 'form-control',
                'autocomplete': 'off'
            })
        
        # Add CSS classes for notes field (always editable)
        self.fields['notes'].widget.attrs.update({
            'class': 'form-control',
            'autocomplete': 'off'
        })

    class Meta:
        model = Order
        fields = ['member', 'order_date', 'payment_method', 'order_status', 'notes']
        widgets = {
            'order_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def clean(self):
        cleaned_data = super().clean()
        
        # If order is paid, restore original values for readonly fields
        if self.instance.pk and self.instance.order_status == 'paid':
            # Restore original values for readonly fields
            if not cleaned_data.get('order_status'):
                cleaned_data['order_status'] = self.instance.order_status
            if not cleaned_data.get('order_date'):
                cleaned_data['order_date'] = self.instance.order_date
            if not cleaned_data.get('payment_method'):
                cleaned_data['payment_method'] = self.instance.payment_method
        
        # For existing orders, ensure member is always set (hidden field should have value)
        if self.instance.pk:
            if not cleaned_data.get('member'):
                cleaned_data['member'] = self.instance.member
        
        # Validate member selection for new orders only
        if not self.instance.pk:  # New order
            member = cleaned_data.get('member')
            if not member:
                raise ValidationError(_('請選擇會員'))
        
        return cleaned_data


class OrderItemForm(forms.ModelForm):
    """Form for order items"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Import models at the top level to avoid UnboundLocalError
        from .models import Course, Product
        
        # Add CSS classes
        self.fields['item_type'].widget.attrs.update({
            'class': 'form-control',
            'onchange': 'updateItemOptions(this)'
        })
        self.fields['quantity'].widget.attrs.update({
            'class': 'form-control',
            'onchange': 'calculateTotal(this)'
        })
        self.fields['unit_price'].widget.attrs.update({
            'class': 'form-control',
            'onchange': 'calculateTotal(this)'
        })
        
        # Always show all courses and products - let JavaScript handle the filtering
        courses = Course.objects.filter(status='active')
        products = Product.objects.filter(status='active')
        choices = [('', '請選擇課程或商品')] + \
                  [(f"course-{course.id}", f"{course.course_code} - {course.name}") for course in courses] + \
                  [(f"product-{product.id}", f"{product.product_code} - {product.name}") for product in products]
        self.fields['item_id'].widget = forms.Select(choices=choices, attrs={'class': 'form-control'})
        
        # Add data attributes for JavaScript
        self.fields['item_type'].widget.attrs.update({
            'data-target': 'item_id'
        })

    class Meta:
        model = OrderItem
        fields = ['item_type', 'item_id', 'quantity', 'unit_price']
        widgets = {
            'quantity': forms.NumberInput(attrs={'min': 1}),
            'unit_price': forms.NumberInput(attrs={'min': 0, 'step': 0.01}),
        }

    def clean(self):
        cleaned_data = super().clean()
        item_type = cleaned_data.get('item_type')
        item_id = cleaned_data.get('item_id')
        quantity = cleaned_data.get('quantity')
        unit_price = cleaned_data.get('unit_price')
        
        # Validate item exists
        if item_type and item_id:
            if item_type == 'course':
                try:
                    Course.objects.get(id=item_id, status='active')
                except Course.DoesNotExist:
                    raise ValidationError(_('選擇的課程不存在或已停用'))
            elif item_type == 'product':
                try:
                    Product.objects.get(id=item_id, status='active')
                except Product.DoesNotExist:
                    raise ValidationError(_('選擇的商品不存在或已停用'))
        
        # Validate quantity and price
        if quantity and quantity <= 0:
            raise ValidationError(_('數量必須大於0'))
        
        if unit_price and unit_price < 0:
            raise ValidationError(_('單價不能為負數'))
        
        return cleaned_data


class OrderSearchForm(forms.Form):
    """Form for searching orders"""
    search_term = forms.CharField(
        label=_('搜尋'),
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('輸入會員姓名或訂單編號')
        })
    )
    
    status_filter = forms.ChoiceField(
        label=_('狀態篩選'),
        required=False,
        choices=[('', _('付款狀態'))] + Order.ORDER_STATUS_CHOICES,
        widget=forms.Select(attrs={
            'class': 'form-control'
        })
    )
    
    date_from = forms.DateField(
        label=_('開始日期'),
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control'
        })
    )
    
    date_to = forms.DateField(
        label=_('結束日期'),
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control'
        })
    )


class MemberSearchForm(forms.Form):
    """Form for searching members in order creation"""
    search_term = forms.CharField(
        label=_('搜尋會員'),
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('輸入會員姓名或手機號碼'),
            'id': 'member-search'
        })
    )


class CourseBalanceSearchForm(forms.Form):
    """Form for searching course balance"""
    search_term = forms.CharField(
        label=_('搜尋會員'),
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('輸入會員姓名或手機號碼'),
            'id': 'balance-search'
        })
    )


class SessionForm(forms.ModelForm):
    """Form for creating session records (minimal, as most is via AJAX)"""
    class Meta:
        model = Session
        fields = [] # No direct fields, handled by AJAX


class ProductForm(forms.ModelForm):
    """Form for creating and updating products"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Add CSS classes
        self.fields['name'].widget.attrs.update({
            'class': 'form-control',
            'autocomplete': 'off'
        })
        self.fields['quantity_options'].widget.attrs.update({
            'class': 'form-control',
            'autocomplete': 'off'
        })
        self.fields['price_options'].widget.attrs.update({
            'class': 'form-control',
            'autocomplete': 'off'
        })
        self.fields['unlimited_quantity'].widget.attrs.update({
            'class': 'form-check-input'
        })
        self.fields['unlimited_price'].widget.attrs.update({
            'class': 'form-check-input'
        })
        self.fields['notes'].widget.attrs.update({
            'class': 'form-control',
            'autocomplete': 'off'
        })
        self.fields['status'].widget.attrs.update({
            'class': 'form-control',
            'autocomplete': 'off'
        })

    class Meta:
        model = Product
        fields = ['name', 'quantity_options', 'price_options', 'unlimited_quantity', 'unlimited_price', 'notes', 'status']
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
        }


class AdminOrderItemForm(forms.ModelForm):
    """Form for order items in Admin interface"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set up item_type dropdown
        self.fields['item_type'].widget.attrs.update({
            'class': 'form-control',
        })
        
        # Set up item_id as a regular IntegerField initially
        # JavaScript will handle the dynamic dropdown behavior
        self.fields['item_id'].widget.attrs.update({
            'class': 'form-control',
        })
        
        # Set up quantity and unit_price fields
        self.fields['quantity'].widget.attrs.update({
            'class': 'form-control',
            'min': '1'
        })
        self.fields['unit_price'].widget.attrs.update({
            'class': 'form-control',
            'min': '0',
            'step': '0.01'
        })

    class Meta:
        model = OrderItem
        fields = ['item_type', 'item_id', 'quantity', 'unit_price']
        widgets = {
            'item_type': forms.Select(),
            'item_id': forms.NumberInput(),
            'quantity': forms.NumberInput(attrs={'min': 1}),
            'unit_price': forms.NumberInput(attrs={'min': 0, 'step': 0.01}),
        }

    def clean(self):
        cleaned_data = super().clean()
        item_type = cleaned_data.get('item_type')
        item_id = cleaned_data.get('item_id')
        quantity = cleaned_data.get('quantity')
        unit_price = cleaned_data.get('unit_price')
        
        # Validate item exists
        if item_type and item_id:
            if item_type == 'course':
                try:
                    Course.objects.get(id=item_id, status='active')
                except Course.DoesNotExist:
                    raise ValidationError(_('選擇的課程不存在或已停用'))
            elif item_type == 'product':
                try:
                    Product.objects.get(id=item_id, status='active')
                except Product.DoesNotExist:
                    raise ValidationError(_('選擇的商品不存在或已停用'))
        
        # Validate quantity and price
        if quantity and quantity <= 0:
            raise ValidationError(_('數量必須大於0'))
        
        if unit_price is not None and unit_price < 0:
            raise ValidationError(_('單價不能為負數'))
        
        return cleaned_data


class ProductInventoryAdjustmentForm(forms.Form):
    """Form for adjusting product inventory"""
    
    product = forms.ModelChoiceField(
        label=_('商品'),
        queryset=Product.objects.filter(status='active').order_by('product_code'),
        empty_label=_('請選擇商品'),
        widget=forms.Select(attrs={
            'class': 'form-control',
            'autocomplete': 'off'
        })
    )
    
    adjustment_quantity = forms.IntegerField(
        label=_('調整數量'),
        help_text=_('輸入正數增加庫存，負數減少庫存'),
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'autocomplete': 'off',
            'placeholder': _('例如：10 (增加) 或 -5 (減少)')
        })
    )
    
    reason = forms.CharField(
        label=_('調整原因'),
        max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'autocomplete': 'off',
            'placeholder': _('請輸入調整原因，例如：進貨、盤點調整')
        })
    )

    def clean_adjustment_quantity(self):
        quantity = self.cleaned_data.get('adjustment_quantity')
        if quantity == 0:
            raise ValidationError(_('調整數量不能為0'))
        return quantity


class ProductInventorySearchForm(forms.Form):
    """Form for searching product inventory"""
    search_term = forms.CharField(
        label=_('搜尋商品'),
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('輸入商品名稱或商品編號'),
            'id': 'inventory-search'
        })
    )


# Import Management Forms
class ImportTypeForm(forms.Form):
    """Form for selecting import type"""
    IMPORT_TYPE_CHOICES = [
        ('members', _('會員數據導入')),
        ('orders', _('訂單數據導入')),
        ('sessions', _('授課記錄導入')),
    ]
    
    import_type = forms.ChoiceField(
        label=_('導入類型'),
        choices=IMPORT_TYPE_CHOICES,
        widget=forms.Select(attrs={
            'class': 'form-control',
            'onchange': 'updateImportInfo(this.value)'
        })
    )


class ImportFileForm(forms.Form):
    """Form for uploading import files"""
    import_file = forms.FileField(
        label=_('選擇檔案'),
        help_text=_('請選擇要導入的 Excel 檔案'),
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.xlsx,.xls',
            'id': 'import-file'
        })
    )
    
    def clean_import_file(self):
        file = self.cleaned_data.get('import_file')
        if file:
            # Check file extension
            if not file.name.endswith(('.xlsx', '.xls')):
                raise ValidationError(_('請上傳 Excel 檔案 (.xlsx 或 .xls)'))
            
            # Check file size (limit to 10MB)
            if file.size > 10 * 1024 * 1024:
                raise ValidationError(_('檔案大小不能超過 10MB'))
        
        return file


class ImportValidationForm(forms.Form):
    """Form for import validation and confirmation"""
    confirm_import = forms.BooleanField(
        label=_('確認導入'),
        required=True,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
            'id': 'confirm-import'
        })
    )
    
    def clean_confirm_import(self):
        confirmed = self.cleaned_data.get('confirm_import')
        if not confirmed:
            raise ValidationError(_('請確認要執行導入操作'))
        return confirmed