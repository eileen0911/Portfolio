from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from django.urls import path, reverse
from django.shortcuts import redirect
from django.contrib import messages
from .models import OperationLog, Order, OrderItem, CourseInventory, Course, Product, ProductInventory, Session
from .forms import OrderItemForm, AdminOrderItemForm

@admin.register(OperationLog)
class OperationLogAdmin(admin.ModelAdmin):
    list_display = ('operation_time', 'user', 'module', 'operation_content')
    list_filter = ('module', 'user', 'operation_time')
    search_fields = ('operation_content', 'user__username')
    readonly_fields = ('operation_time', 'user', 'module', 'operation_content')
    ordering = ('-operation_time',)
    date_hierarchy = 'operation_time'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    class Media:
        css = {
            'all': ('admin/css/operation_logs.css',)
        }


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    form = AdminOrderItemForm
    extra = 1
    readonly_fields = ('total_price',)
    fields = ('item_type', 'item_id', 'quantity', 'unit_price', 'total_price')
    
    class Media:
        js = ('admin/js/order_item_dynamic.js',)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_code', 'member', 'order_date', 'total_amount', 'payment_method', 'order_status', 'created_by', 'created_at')
    list_filter = ('order_status', 'payment_method', 'order_date', 'created_at')
    search_fields = ('order_code', 'member__name', 'member__phone')
    readonly_fields = ('order_code', 'total_amount', 'created_at', 'updated_at')
    date_hierarchy = 'order_date'
    inlines = [OrderItemInline]
    
    fieldsets = (
        (_('基本資料'), {
            'fields': ('order_code', 'member', 'order_date', 'payment_method', 'order_status')
        }),
        (_('金額資訊'), {
            'fields': ('total_amount',)
        }),
        (_('其他資訊'), {
            'fields': ('notes', 'created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


# OrderItemAdmin removed - Order items are managed through OrderAdmin inline


@admin.register(CourseInventory)
class CourseInventoryAdmin(admin.ModelAdmin):
    list_display = ('member', 'course', 'initial_quantity', 'remaining_quantity', 'status', 'order', 'created_at')
    list_filter = ('status', 'course', 'created_at')
    search_fields = ('member__name', 'member__phone', 'course__name', 'order__order_code')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'created_at'


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('course_code', 'name', 'display_quantity_options', 'display_price_options', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('course_code', 'name')
    readonly_fields = ('course_code', 'created_at', 'updated_at')
    date_hierarchy = 'created_at'

    fieldsets = (
        (_('基本資料'), {
            'fields': ('course_code', 'name', 'status')
        }),
        (_('選項設定'), {
            'fields': (
                ('quantity_options', 'unlimited_quantity'),
                ('price_options', 'unlimited_price'),
            ),
            'description': _('數量和價格選項可以設定特定值（以逗號分隔）或選擇不限制')
        }),
        (_('其他資訊'), {
            'fields': ('notes', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def display_quantity_options(self, obj):
        if obj.unlimited_quantity:
            return _('不限制')
        return obj.quantity_options or '-'
    display_quantity_options.short_description = _('數量選項')

    def display_price_options(self, obj):
        if obj.unlimited_price:
            return _('不限制')
        return obj.price_options or '-'
    display_price_options.short_description = _('單價選項')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('product_code', 'name', 'display_quantity_options', 'display_price_options', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('product_code', 'name')
    readonly_fields = ('product_code', 'created_at', 'updated_at')
    date_hierarchy = 'created_at'

    fieldsets = (
        (_('基本資料'), {
            'fields': ('product_code', 'name', 'status')
        }),
        (_('選項設定'), {
            'fields': (
                ('quantity_options', 'unlimited_quantity'),
                ('price_options', 'unlimited_price'),
            ),
            'description': _('數量和價格選項可以設定特定值（以逗號分隔）或選擇不限制')
        }),
        (_('其他資訊'), {
            'fields': ('notes', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def display_quantity_options(self, obj):
        if obj.unlimited_quantity:
            return _('不限制')
        return obj.quantity_options or '-'
    display_quantity_options.short_description = _('數量選項')

    def display_price_options(self, obj):
        if obj.unlimited_price:
            return _('不限制')
        return obj.price_options or '-'
    display_price_options.short_description = _('單價選項')


@admin.register(ProductInventory)
class ProductInventoryAdmin(admin.ModelAdmin):
    list_display = ('product', 'display_product_code', 'quantity', 'display_quantity_status', 'last_updated_by', 'updated_at')
    list_filter = ('quantity', 'last_updated_by', 'updated_at')
    search_fields = ('product__name', 'product__product_code', 'last_updated_by__username')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'updated_at'
    
    fieldsets = (
        (_('商品資訊'), {
            'fields': ('product', 'quantity')
        }),
        (_('更新資訊'), {
            'fields': ('last_updated_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def display_product_code(self, obj):
        return obj.product.product_code
    display_product_code.short_description = _('商品編號')
    
    def display_quantity_status(self, obj):
        if obj.quantity < 0:
            return format_html('<span style="color: red; font-weight: bold;">{} (缺貨)</span>', obj.quantity)
        elif obj.quantity == 0:
            return format_html('<span style="color: orange; font-weight: bold;">{} (零庫存)</span>', obj.quantity)
        else:
            return format_html('<span style="color: green; font-weight: bold;">{}</span>', obj.quantity)
    display_quantity_status.short_description = _('庫存狀態')
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('product', 'last_updated_by')


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ('session_code', 'member', 'coach', 'course', 'session_date', 'created_by', 'created_at')
    list_filter = ('session_date', 'coach', 'member', 'created_by')
    search_fields = ('session_code', 'member__name', 'member__phone', 'coach__name', 'course__name')
    readonly_fields = ('session_code', 'created_by', 'created_at')
    date_hierarchy = 'session_date'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# Import Management Admin
class ImportManagementAdmin(admin.ModelAdmin):
    """Admin interface for import management"""
    
    def get_urls(self):
        """Add custom URLs for import management"""
        urls = super().get_urls()
        custom_urls = [
            path('import-management/', self.admin_site.admin_view(self.import_management_view), name='core_import_management'),
            path('import-type-selection/', self.admin_site.admin_view(self.import_type_selection_view), name='core_import_type_selection'),
            path('import-file-upload/<str:import_type>/', self.admin_site.admin_view(self.import_file_upload_view), name='core_import_file_upload'),
            path('import-validation/<str:import_type>/', self.admin_site.admin_view(self.import_validation_view), name='core_import_validation'),
            path('import-confirmation/<str:import_type>/', self.admin_site.admin_view(self.import_confirmation_view), name='core_import_confirmation'),
            path('download-template/<str:import_type>/', self.admin_site.admin_view(self.download_template_view), name='core_download_template'),
        ]
        return custom_urls + urls
    
    def import_management_view(self, request):
        """Import management dashboard"""
        from django.template.response import TemplateResponse
        from .forms import ImportTypeForm
        
        context = {
            'title': _('數據導入管理'),
            'import_type_form': ImportTypeForm(),
            'has_permission': True,
        }
        return TemplateResponse(request, 'admin/core/import/import_management.html', context)
    
    def import_type_selection_view(self, request):
        """Import type selection"""
        from django.template.response import TemplateResponse
        from django.shortcuts import redirect
        from .forms import ImportTypeForm
        
        if request.method == 'POST':
            form = ImportTypeForm(request.POST)
            if form.is_valid():
                import_type = form.cleaned_data['import_type']
                return redirect(f'admin:core_download_template_{import_type}')
        else:
            form = ImportTypeForm()
        
        context = {
            'title': _('選擇導入類型'),
            'form': form,
            'has_permission': True,
        }
        return TemplateResponse(request, 'admin/core/import/import_type_selection.html', context)
    
    def import_file_upload_view(self, request, import_type):
        """File upload view"""
        from django.template.response import TemplateResponse
        from django.shortcuts import redirect
        from .forms import ImportFileForm
        from django.urls import reverse
        
        if request.method == 'POST':
            form = ImportFileForm(request.POST, request.FILES)
            if form.is_valid():
                # Process file upload and validation
                try:
                    import tempfile
                    import os
                    from .utils import MembersImportProcessor, OrdersImportProcessor, SessionsImportProcessor
                    
                    import_file = form.cleaned_data['import_file']
                    
                    # Save uploaded file temporarily
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as temp_file:
                        for chunk in import_file.chunks():
                            temp_file.write(chunk)
                        temp_file_path = temp_file.name
                    
                    # Process the file based on import type
                    if import_type == 'members':
                        processor = MembersImportProcessor(temp_file_path)
                    elif import_type == 'orders':
                        processor = OrdersImportProcessor(temp_file_path)
                    elif import_type == 'sessions':
                        processor = SessionsImportProcessor(temp_file_path)
                    else:
                        raise ValueError(f"不支援的導入類型: {import_type}")
                    
                    # Open workbook and get data
                    processor.open_workbook()
                    data_rows = processor.get_data_rows()
                    processor.close_workbook()
                    
                    # Validate data
                    errors, warnings = processor.validate_data(data_rows)
                    
                    # Store validation results in session
                    request.session['import_data'] = {
                        'import_type': import_type,
                        'file_path': temp_file_path,
                        'data_rows': data_rows,
                        'errors': errors,
                        'warnings': warnings,
                        'total_rows': len(data_rows)
                    }
                    
                    # Clean up temp file
                    os.unlink(temp_file_path)
                    
                    if errors:
                        return redirect(f'admin:core_import_validation_{import_type}')
                    else:
                        return redirect(f'admin:core_import_confirmation_{import_type}')
                        
                except Exception as e:
                    messages.error(request, _('檔案處理失敗：{}').format(str(e)))
        else:
            form = ImportFileForm()
        
        # Add import type specific information
        import_info = {}
        if import_type == 'members':
            import_info = {
                'name': _('會員數據導入'),
                'description': _('批量導入會員基本資料'),
                'required_fields': _('姓名、手機號碼、負責教練、註冊日期、狀態為必填欄位'),
            }
        elif import_type == 'orders':
            import_info = {
                'name': _('訂單數據導入'),
                'description': _('批量導入歷史訂單資料'),
                'required_fields': _('會員手機號碼、訂單日期、課程名稱、購買數量、單價、付款方式、訂單狀態為必填欄位'),
            }
        elif import_type == 'sessions':
            import_info = {
                'name': _('授課記錄導入'),
                'description': _('批量導入授課記錄，系統會自動從會員課程庫存中扣減'),
                'required_fields': _('會員手機號碼、課程名稱、授課日期為必填欄位'),
            }
        
        context = {
            'title': _('上傳導入檔案'),
            'import_type': import_type,
            'form': form,
            'import_info': import_info,
            'has_permission': True,
        }
        return TemplateResponse(request, 'admin/core/import/import_file_upload.html', context)
    
    def import_validation_view(self, request, import_type):
        """Import validation results"""
        from django.template.response import TemplateResponse
        from django.shortcuts import redirect
        
        # Get validation results from session
        import_data = request.session.get('import_data', {})
        if not import_data or import_data.get('import_type') != import_type:
            messages.error(request, _('導入資料已過期，請重新上傳檔案'))
            return redirect('admin:core_import_management')
        
        context = {
            'title': _('導入驗證結果'),
            'import_type': import_type,
            'errors': import_data.get('errors', []),
            'warnings': import_data.get('warnings', []),
            'total_rows': import_data.get('total_rows', 0),
            'has_errors': len(import_data.get('errors', [])) > 0,
            'has_permission': True,
        }
        return TemplateResponse(request, 'admin/core/import/import_validation.html', context)
    
    def import_confirmation_view(self, request, import_type):
        """Import confirmation"""
        from django.template.response import TemplateResponse
        from django.shortcuts import redirect
        from .forms import ImportValidationForm
        
        # Get import data from session
        import_data = request.session.get('import_data', {})
        if not import_data or import_data.get('import_type') != import_type:
            messages.error(request, _('導入資料已過期，請重新上傳檔案'))
            return redirect('admin:core_import_management')
        
        if request.method == 'POST':
            form = ImportValidationForm(request.POST)
            if form.is_valid():
                try:
                    # Process import
                    from .utils import MembersImportProcessor, OrdersImportProcessor, SessionsImportProcessor
                    
                    data_rows = import_data.get('data_rows', [])
                    
                    if import_type == 'members':
                        processor = MembersImportProcessor('')
                    elif import_type == 'orders':
                        processor = OrdersImportProcessor('')
                    elif import_type == 'sessions':
                        processor = SessionsImportProcessor('')
                    
                    # Import data
                    imported_count, import_errors = processor.import_data(data_rows, request.user)
                    
                    # Log operation
                    from .utils import log_operation
                    log_operation(
                        user=request.user,
                        module="數據導入管理",
                        content=f"導入{import_type}數據：成功{imported_count}筆，失敗{len(import_errors)}筆"
                    )
                    
                    # Clear session data
                    if 'import_data' in request.session:
                        del request.session['import_data']
                    
                    if import_errors:
                        messages.warning(request, _('導入完成，但有部分資料失敗：{}').format('; '.join(import_errors[:5])))
                    else:
                        messages.success(request, _('導入成功：共導入 {} 筆資料').format(imported_count))
                    
                    return redirect('admin:core_import_management')
                    
                except Exception as e:
                    messages.error(request, _('導入失敗：{}').format(str(e)))
        else:
            form = ImportValidationForm()
        
        context = {
            'title': _('確認導入'),
            'import_type': import_type,
            'total_rows': import_data.get('total_rows', 0),
            'warnings': import_data.get('warnings', []),
            'form': form,
            'has_permission': True,
        }
        return TemplateResponse(request, 'admin/core/import/import_confirmation.html', context)
    
    def download_template_view(self, request, import_type):
        """Download Excel template"""
        from .utils import create_excel_template
        return create_excel_template(import_type)


# Note: Import management is accessible through the main admin interface
# The ImportManagementAdmin class provides the necessary views and URLs