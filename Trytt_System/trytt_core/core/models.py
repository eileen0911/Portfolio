from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
import json
from django.core.exceptions import ValidationError
from decimal import Decimal
from django.utils import timezone
from accounts.models import Member, Coach

class OperationLog(models.Model):
    """Model for storing system operation logs"""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_('操作者'),
        on_delete=models.PROTECT,
        related_name='operation_logs'
    )
    operation_time = models.DateTimeField(
        _('操作時間'),
        auto_now_add=True
    )
    module = models.CharField(
        _('功能模組'),
        max_length=50
    )
    operation_content = models.TextField(
        _('操作內容')
    )

    class Meta:
        db_table = 'operation_logs'
        verbose_name = _('操作日誌')
        verbose_name_plural = _('操作日誌')
        indexes = [
            models.Index(fields=['operation_time']),
            models.Index(fields=['module']),
        ]

    def __str__(self):
        return f"{self.operation_time} - {self.user.username} - {self.module}"


def validate_comma_separated_numbers(value):
    """Validate that the value is a comma-separated list of numbers"""
    if not value:
        return
    try:
        numbers = [int(x.strip()) for x in value.split(',')]
        if not all(n > 0 for n in numbers):
            raise ValidationError(_('所有數值必須大於0'))
    except ValueError:
        raise ValidationError(_('請輸入以逗號分隔的數字，例如：3,5,8'))


class Course(models.Model):
    """Model for course management"""
    STATUS_CHOICES = [
        ('active', _('啟用')),
        ('inactive', _('停用')),
    ]

    course_code = models.CharField(
        _('課程編號'),
        max_length=8,
        unique=True,
        help_text=_('系統自動產生，格式：CR + 6位數字')
    )
    name = models.CharField(
        _('課程名稱'),
        max_length=100
    )
    quantity_options = models.TextField(
        _('數量選項'),
        blank=True,
        help_text=_('以逗號分隔的數字，例如：3,5,8'),
        validators=[validate_comma_separated_numbers]
    )
    price_options = models.TextField(
        _('單價選項'),
        blank=True,
        help_text=_('以逗號分隔的數字，例如：1000,1500,2000'),
        validators=[validate_comma_separated_numbers]
    )
    unlimited_quantity = models.BooleanField(
        _('不限制數量'),
        default=False
    )
    unlimited_price = models.BooleanField(
        _('不限制單價'),
        default=False
    )
    notes = models.TextField(
        _('備註'),
        blank=True
    )
    status = models.CharField(
        _('狀態'),
        max_length=10,
        choices=STATUS_CHOICES,
        default='active'
    )
    created_at = models.DateTimeField(
        _('建立時間'),
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        _('更新時間'),
        auto_now=True
    )

    class Meta:
        db_table = 'courses'
        verbose_name = _('課程')
        verbose_name_plural = _('課程')

    def __str__(self):
        return f"{self.course_code} - {self.name}"

    def clean(self):
        """Custom model validation"""
        if not self.unlimited_quantity and not self.quantity_options:
            raise ValidationError({
                'quantity_options': _('請設定數量選項或勾選不限制數量')
            })
        if not self.unlimited_price and not self.price_options:
            raise ValidationError({
                'price_options': _('請設定單價選項或勾選不限制單價')
            })

    def get_quantity_options(self):
        """Get quantity options as a list of integers"""
        if self.unlimited_quantity:
            return []
        if not self.quantity_options:
            return []
        return [int(x.strip()) for x in self.quantity_options.split(',')]

    def get_price_options(self):
        """Get price options as a list of integers"""
        if self.unlimited_price:
            return []
        if not self.price_options:
            return []
        return [int(x.strip()) for x in self.price_options.split(',')]

    def save(self, *args, **kwargs):
        """Override save method to generate course code"""
        if not self.course_code:
            # Get the last course code
            last_course = Course.objects.order_by('-course_code').first()
            if last_course:
                last_number = int(last_course.course_code[2:])
                new_number = last_number + 1
            else:
                new_number = 1
            self.course_code = f'CR{new_number:06d}'
        super().save(*args, **kwargs)


class Product(models.Model):
    """Model for product management"""
    STATUS_CHOICES = [
        ('active', _('啟用')),
        ('inactive', _('停用')),
    ]

    product_code = models.CharField(
        _('商品編號'),
        max_length=8,
        unique=True,
        help_text=_('系統自動產生，格式：P + 6位數字')
    )
    name = models.CharField(
        _('商品名稱'),
        max_length=100
    )
    quantity_options = models.TextField(
        _('數量選項'),
        blank=True,
        help_text=_('以逗號分隔的數字，例如：3,5,8'),
        validators=[validate_comma_separated_numbers]
    )
    price_options = models.TextField(
        _('單價選項'),
        blank=True,
        help_text=_('以逗號分隔的數字，例如：1000,1500,2000'),
        validators=[validate_comma_separated_numbers]
    )
    unlimited_quantity = models.BooleanField(
        _('不限制數量'),
        default=False
    )
    unlimited_price = models.BooleanField(
        _('不限制單價'),
        default=False
    )
    notes = models.TextField(
        _('備註'),
        blank=True
    )
    status = models.CharField(
        _('狀態'),
        max_length=10,
        choices=STATUS_CHOICES,
        default='active'
    )
    created_at = models.DateTimeField(
        _('建立時間'),
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        _('更新時間'),
        auto_now=True
    )

    class Meta:
        db_table = 'products'
        verbose_name = _('商品')
        verbose_name_plural = _('商品')

    def __str__(self):
        return f"{self.product_code} - {self.name}"

    def clean(self):
        """Custom model validation"""
        if not self.unlimited_quantity and not self.quantity_options:
            raise ValidationError({
                'quantity_options': _('請設定數量選項或勾選不限制數量')
            })
        if not self.unlimited_price and not self.price_options:
            raise ValidationError({
                'price_options': _('請設定單價選項或勾選不限制單價')
            })

    def get_quantity_options(self):
        """Get quantity options as a list of integers"""
        if self.unlimited_quantity:
            return []
        if not self.quantity_options:
            return []
        return [int(x.strip()) for x in self.quantity_options.split(',')]

    def get_price_options(self):
        """Get price options as a list of integers"""
        if self.unlimited_price:
            return []
        if not self.price_options:
            return []
        return [int(x.strip()) for x in self.price_options.split(',')]

    def save(self, *args, **kwargs):
        """Override save method to generate product code"""
        if not self.product_code:
            # Get the last product code
            last_product = Product.objects.order_by('-product_code').first()
            if last_product:
                last_number = int(last_product.product_code[1:])
                new_number = last_number + 1
            else:
                new_number = 1
            self.product_code = f'P{new_number:06d}'
        super().save(*args, **kwargs)


class Order(models.Model):
    """Model for order management"""
    PAYMENT_METHOD_CHOICES = [
        ('cash', _('現金')),
        ('card', _('刷卡')),
        ('transfer', _('轉帳')),
    ]
    
    ORDER_STATUS_CHOICES = [
        ('paid', _('已付款')),
        ('unpaid', _('未付款')),
        ('cancelled', _('已取消')),
    ]

    ORDER_TYPE_CHOICES = [
        ('regular', _('一般訂單')),
        ('refund', _('退費訂單')),
        ('swap', _('換課訂單')),
    ]

    order_code = models.CharField(
        _('訂單編號'),
        max_length=8,
        unique=True,
        help_text=_('系統自動產生，格式：O + 6位數字')
    )
    member = models.ForeignKey(
        'accounts.Member',
        verbose_name=_('會員'),
        on_delete=models.PROTECT,
        related_name='orders'
    )
    order_date = models.DateField(
        _('訂單日期'),
        help_text=_('訂單建立日期')
    )
    payment_method = models.CharField(
        _('付款方式'),
        max_length=10,
        choices=PAYMENT_METHOD_CHOICES
    )
    order_status = models.CharField(
        _('訂單狀態'),
        max_length=10,
        choices=ORDER_STATUS_CHOICES,
        default='unpaid'
    )
    total_amount = models.DecimalField(
        _('總金額'),
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00')
    )
    order_type = models.CharField(
        _('訂單類型'),
        max_length=10,
        choices=ORDER_TYPE_CHOICES,
        default='regular'
    )
    source_order = models.ForeignKey(
        'self',
        verbose_name=_('原始訂單'),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='derived_orders'
    )
    notes = models.TextField(
        _('備註'),
        blank=True
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_('建立者'),
        on_delete=models.PROTECT,
        related_name='created_orders'
    )
    created_at = models.DateTimeField(
        _('建立時間'),
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        _('更新時間'),
        auto_now=True
    )

    class Meta:
        db_table = 'orders'
        verbose_name = _('訂單')
        verbose_name_plural = _('訂單')
        indexes = [
            models.Index(fields=['member']),
            models.Index(fields=['order_date']),
            models.Index(fields=['order_status']),
        ]

    def __str__(self):
        return f"{self.order_code} - {self.member.name}"

    def save(self, *args, **kwargs):
        """Override save method to generate order code.
        
        Note: Inventory handling (course inventory creation, product inventory
        deduction) is intentionally NOT done here. It is handled exclusively
        by the view layer (OrderCreateView, OrderUpdateView) and import
        processors to avoid double-processing.
        """
        # Generate order code if needed
        if not self.order_code:
            # Get the last order code
            last_order = Order.objects.order_by('-order_code').first()
            if last_order:
                last_number = int(last_order.order_code[1:])
                new_number = last_number + 1
            else:
                new_number = 1
            self.order_code = f'O{new_number:06d}'
        
        super().save(*args, **kwargs)

    def calculate_total(self):
        """Calculate total amount from order items"""
        total = sum(item.total_price for item in self.order_items.all())
        self.total_amount = total
        return total




class OrderItem(models.Model):
    """Model for order items (courses or products)"""
    ITEM_TYPE_CHOICES = [
        ('course', _('課程')),
        ('product', _('商品')),
    ]

    order = models.ForeignKey(
        Order,
        verbose_name=_('訂單'),
        on_delete=models.CASCADE,
        related_name='order_items'
    )
    item_type = models.CharField(
        _('項目類型'),
        max_length=10,
        choices=ITEM_TYPE_CHOICES
    )
    item_id = models.PositiveIntegerField(
        _('項目ID'),
        help_text=_('課程或商品的ID')
    )
    quantity = models.PositiveIntegerField(
        _('數量'),
        help_text=_('購買數量')
    )
    unit_price = models.DecimalField(
        _('單價'),
        max_digits=10,
        decimal_places=2,
        help_text=_('單價')
    )
    total_price = models.DecimalField(
        _('總價'),
        max_digits=10,
        decimal_places=2,
        help_text=_('總價（數量 × 單價）')
    )
    created_at = models.DateTimeField(
        _('建立時間'),
        auto_now_add=True
    )

    class Meta:
        db_table = 'order_items'
        verbose_name = _('訂單明細')
        verbose_name_plural = _('訂單明細')
        indexes = [
            models.Index(fields=['order']),
            models.Index(fields=['item_type', 'item_id']),
        ]

    def __str__(self):
        item_name = self.get_item_name()
        return f"{self.order.order_code} - {item_name} (x{self.quantity})"

    def get_item_name(self):
        """Get the name of the course or product"""
        if self.item_type == 'course':
            try:
                course = Course.objects.get(id=self.item_id)
                return course.name
            except Course.DoesNotExist:
                return f"課程 #{self.item_id}"
        elif self.item_type == 'product':
            try:
                product = Product.objects.get(id=self.item_id)
                return product.name
            except Product.DoesNotExist:
                return f"商品 #{self.item_id}"
        return f"項目 #{self.item_id}"

    def save(self, *args, **kwargs):
        """Override save method to calculate total price"""
        self.total_price = self.quantity * self.unit_price
        super().save(*args, **kwargs)
        # Update order total
        self.order.calculate_total()
        self.order.save()


class CourseInventory(models.Model):
    """Model for tracking course inventory/balance for members"""
    STATUS_CHOICES = [
        ('active', _('啟用')),
        ('used_up', _('已用完')),
    ]

    member = models.ForeignKey(
        'accounts.Member',
        verbose_name=_('會員'),
        on_delete=models.CASCADE,
        related_name='course_inventories'
    )
    course = models.ForeignKey(
        Course,
        verbose_name=_('課程'),
        on_delete=models.CASCADE,
        related_name='inventories'
    )
    order = models.ForeignKey(
        Order,
        verbose_name=_('訂單'),
        on_delete=models.CASCADE,
        related_name='course_inventories'
    )
    initial_quantity = models.PositiveIntegerField(
        _('初始數量'),
        help_text=_('購買時的數量')
    )
    remaining_quantity = models.PositiveIntegerField(
        _('剩餘數量'),
        help_text=_('剩餘可使用的數量')
    )
    status = models.CharField(
        _('狀態'),
        max_length=10,
        choices=STATUS_CHOICES,
        default='active'
    )
    created_at = models.DateTimeField(
        _('建立時間'),
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        _('更新時間'),
        auto_now=True
    )

    class Meta:
        db_table = 'course_inventory'
        verbose_name = _('課程庫存')
        verbose_name_plural = _('課程庫存')
        indexes = [
            models.Index(fields=['member']),
            models.Index(fields=['course']),
            models.Index(fields=['order']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.member.name} - {self.course.name} ({self.remaining_quantity}/{self.initial_quantity})"

    def use_quantity(self, quantity=1):
        """Use a quantity from this inventory record"""
        if self.remaining_quantity >= quantity:
            self.remaining_quantity -= quantity
            if self.remaining_quantity == 0:
                self.status = 'used_up'
            self.save()
            return True
        return False


class ProductInventory(models.Model):
    """Model for tracking product inventory/stock"""
    product = models.OneToOneField(
        Product,
        verbose_name=_('商品'),
        on_delete=models.CASCADE,
        related_name='inventory'
    )
    quantity = models.IntegerField(
        _('庫存數量'),
        default=0,
        help_text=_('庫存數量，可為負數（表示缺貨狀態）')
    )
    last_updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_('最後更新者'),
        on_delete=models.PROTECT,
        related_name='updated_inventories'
    )
    created_at = models.DateTimeField(
        _('建立時間'),
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        _('更新時間'),
        auto_now=True
    )

    class Meta:
        db_table = 'product_inventory'
        verbose_name = _('商品庫存')
        verbose_name_plural = _('商品庫存')
        indexes = [
            models.Index(fields=['product']),
            models.Index(fields=['quantity']),
        ]

    def __str__(self):
        return f"{self.product.name} - 庫存: {self.quantity}"

    def adjust_quantity(self, adjustment, updated_by, reason=""):
        """
        Adjust inventory quantity
        adjustment: positive to increase, negative to decrease
        """
        self.quantity += adjustment
        self.last_updated_by = updated_by
        self.save()
        
        # Log the operation
        from .utils import log_operation
        operation_content = f"調整商品庫存：{self.product.product_code} - {self.product.name}，數量{adjustment:+d}，目前庫存：{self.quantity}"
        if reason:
            operation_content += f"，原因：{reason}"
        
        log_operation(
            user=updated_by,
            module="商品庫存管理",
            content=operation_content
        )

    @classmethod
    def get_or_create_for_product(cls, product, updated_by):
        """Get existing inventory or create new one for product"""
        inventory, created = cls.objects.get_or_create(
            product=product,
            defaults={
                'quantity': 0,
                'last_updated_by': updated_by
            }
        )
        return inventory


class Session(models.Model):
    """Model for recording coaching sessions"""
    session_code = models.CharField(
        _('授課編號'),
        max_length=8,
        unique=True,
        help_text=_('系統自動產生，格式：S + 6位數字')
    )
    member = models.ForeignKey(
        'accounts.Member',
        verbose_name=_('會員'),
        on_delete=models.PROTECT,
        related_name='sessions'
    )
    coach = models.ForeignKey(
        'accounts.Coach',
        verbose_name=_('上課教練'),
        on_delete=models.PROTECT,
        related_name='sessions'
    )
    course = models.ForeignKey(
        Course,
        verbose_name=_('課程'),
        on_delete=models.PROTECT,
        related_name='sessions'
    )
    course_inventory = models.ForeignKey(
        CourseInventory,
        verbose_name=_('課程庫存'),
        on_delete=models.PROTECT,
        related_name='sessions'
    )
    session_date = models.DateTimeField(
        _('授課日期與時間'),
        default=timezone.now
    )
    notes = models.TextField(
        _('備註'),
        blank=True
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_('建立者'),
        on_delete=models.PROTECT,
        related_name='created_sessions'
    )
    created_at = models.DateTimeField(
        _('建立時間'),
        auto_now_add=True
    )

    class Meta:
        db_table = 'sessions'
        verbose_name = _('授課紀錄')
        verbose_name_plural = _('授課紀錄')
        indexes = [
            models.Index(fields=['member']),
            models.Index(fields=['coach']),
            models.Index(fields=['session_date']),
        ]

    def __str__(self):
        return f"{self.session_code} - {self.member.name} - {self.course.name}"

    def save(self, *args, **kwargs):
        if not self.session_code:
            last_session = Session.objects.order_by('-session_code').first()
            if last_session:
                last_number = int(last_session.session_code[1:])
                new_number = last_number + 1
            else:
                new_number = 1
            self.session_code = f'S{new_number:06d}'
        super().save(*args, **kwargs)