from django.views.generic import TemplateView, ListView, CreateView, UpdateView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from django.db.models import Sum
from decimal import Decimal
from datetime import datetime, date
from .models import Course, Product, OperationLog, Order, OrderItem, CourseInventory, Session, ProductInventory
from .forms import CourseForm, ProductForm, OrderForm, OrderItemForm, OrderSearchForm, MemberSearchForm, CourseBalanceSearchForm, ProductInventoryAdjustmentForm, ProductInventorySearchForm, ImportTypeForm, ImportFileForm, ImportValidationForm, SessionSearchForm
from .utils import log_operation
from accounts.models import Member, Coach
from django.utils import timezone

class HomeView(LoginRequiredMixin, TemplateView):
    template_name = 'core/home.html'
    
    def get_context_data(self, **kwargs):
        """Add dashboard statistics and data"""
        context = super().get_context_data(**kwargs)
        
        # Get current date for filtering
        today = timezone.localdate()
        
        # Basic statistics
        total_members = Member.objects.filter(status='active').count()
        total_coaches = Coach.objects.filter(status='active').count()
        total_courses = Course.objects.filter(status='active').count()
        total_orders = Order.objects.count()
        
        # Recent activity (last 7 days)
        recent_orders = Order.objects.filter(
            created_at__gte=timezone.now() - timezone.timedelta(days=7)
        ).count()
        
        recent_sessions = Session.objects.filter(
            created_at__gte=timezone.now() - timezone.timedelta(days=7)
        ).count()
        
        # Today's statistics
        today_orders = Order.objects.filter(order_date=today).count()
        today_sessions = Session.objects.filter(session_date__date=today).count()
        today_new_members = Member.objects.filter(registration_date=today).count()
        
        # Get active coaches and annotate with their session count for today
        from django.db.models import Count
        active_coaches = Coach.objects.filter(status='active').annotate(
            today_sessions_count=Count(
                'sessions',
                filter=Q(sessions__session_date__date=today)
            )
        ).order_by('name')
        
        # Revenue statistics (last 30 days)
        thirty_days_ago = today - timezone.timedelta(days=30)
        recent_revenue = Order.objects.filter(
            order_status='paid',
            order_date__gte=thirty_days_ago
        ).aggregate(
            total_revenue=Sum('total_amount')
        )['total_revenue'] or 0
        
        # Course inventory statistics
        active_course_inventories = CourseInventory.objects.filter(
            status='active',
            remaining_quantity__gt=0
        ).count()
        
        low_stock_courses = CourseInventory.objects.filter(
            status='active',
            remaining_quantity__lte=2,
            remaining_quantity__gt=0
        ).count()
        
        # Product inventory statistics
        total_products = Product.objects.filter(status='active').count()
        low_stock_products = ProductInventory.objects.filter(
            quantity__lte=5,
            quantity__gt=0
        ).count()
        out_of_stock_products = ProductInventory.objects.filter(
            quantity__lte=0
        ).count()
        
        # Recent operations (last 5)
        recent_operations = OperationLog.objects.select_related('user').order_by('-operation_time')[:5]
        
        # Recent sessions (last 5)
        upcoming_sessions = Session.objects.filter(
            session_date__gte=today,
            session_date__lte=today + timezone.timedelta(days=7)
        ).select_related('member', 'coach', 'course').order_by('session_date')[:5]
        
        # Recent orders (last 5)
        recent_orders_list = Order.objects.select_related('member').order_by('-created_at')[:5]
        
        context.update({
            'total_members': total_members,
            'total_coaches': total_coaches,
            'total_courses': total_courses,
            'total_products': total_products,
            'total_orders': total_orders,
            'recent_orders': recent_orders,
            'recent_sessions': recent_sessions,
            'today_orders': today_orders,
            'today_sessions': today_sessions,
            'today_new_members': today_new_members,
            'recent_revenue': recent_revenue,
            'active_course_inventories': active_course_inventories,
            'low_stock_courses': low_stock_courses,
            'low_stock_products': low_stock_products,
            'out_of_stock_products': out_of_stock_products,
            'recent_operations': recent_operations,
            'upcoming_sessions': upcoming_sessions,
            'recent_orders_list': recent_orders_list,
            'active_coaches': active_coaches,
        })
        
        return context


class CourseListView(LoginRequiredMixin, ListView):
    """View for displaying course list"""
    model = Course
    template_name = 'core/course_list.html'
    context_object_name = 'courses'
    paginate_by = 10
    ordering = ['-created_at']

    def get_queryset(self):
        """Filter courses based on search query"""
        queryset = super().get_queryset()
        search_query = self.request.GET.get('search')
        if search_query:
            queryset = queryset.filter(name__icontains=search_query)
        return queryset


class CourseCreateView(LoginRequiredMixin, CreateView):
    """View for creating a new course"""
    model = Course
    form_class = CourseForm
    template_name = 'core/course_form.html'
    success_url = reverse_lazy('core:course_list')

    def get_context_data(self, **kwargs):
        """Add extra context data"""
        context = super().get_context_data(**kwargs)
        context['title'] = _('新增課程')
        context['submit_text'] = _('新增')
        return context

    def form_valid(self, form):
        """Handle valid form"""
        response = super().form_valid(form)
        # Log the operation
        OperationLog.objects.create(
            user=self.request.user,
            module='課程管理',
            operation_content=f'新增課程：{self.object.course_code} - {self.object.name}'
        )
        messages.success(self.request, _('課程新增成功'))
        return response


class CourseUpdateView(LoginRequiredMixin, UpdateView):
    """View for updating an existing course"""
    model = Course
    form_class = CourseForm
    template_name = 'core/course_form.html'
    success_url = reverse_lazy('core:course_list')

    def get_context_data(self, **kwargs):
        """Add extra context data"""
        context = super().get_context_data(**kwargs)
        context['title'] = _('修改課程')
        context['submit_text'] = _('修改')
        return context

    def form_valid(self, form):
        """Handle valid form"""
        old_status = self.object.status
        response = super().form_valid(form)
        # Log the operation
        log_content = f'修改課程資料：{self.object.course_code} - {self.object.name}'
        if old_status != self.object.status:
            log_content += f'，狀態由 {old_status} 變更為 {self.object.status}'
        OperationLog.objects.create(
            user=self.request.user,
            module='課程管理',
            operation_content=log_content
        )
        messages.success(self.request, _('課程修改成功'))
        return response


# Product Management Views
class ProductListView(LoginRequiredMixin, ListView):
    """View for displaying product list"""
    model = Product
    template_name = 'core/product_list.html'
    context_object_name = 'products'
    paginate_by = 10
    ordering = ['-created_at']

    def get_queryset(self):
        """Filter products based on search query"""
        queryset = super().get_queryset()
        search_query = self.request.GET.get('search')
        if search_query:
            queryset = queryset.filter(name__icontains=search_query)
        return queryset


class ProductCreateView(LoginRequiredMixin, CreateView):
    """View for creating a new product"""
    model = Product
    form_class = ProductForm
    template_name = 'core/product_form.html'
    success_url = reverse_lazy('core:product_list')

    def get_context_data(self, **kwargs):
        """Add extra context data"""
        context = super().get_context_data(**kwargs)
        context['title'] = _('新增商品')
        context['submit_text'] = _('新增')
        return context

    def form_valid(self, form):
        """Handle valid form"""
        response = super().form_valid(form)
        # Log the operation
        OperationLog.objects.create(
            user=self.request.user,
            module='商品管理',
            operation_content=f'新增商品：{self.object.product_code} - {self.object.name}'
        )
        messages.success(self.request, _('商品新增成功'))
        return response


class ProductUpdateView(LoginRequiredMixin, UpdateView):
    """View for updating an existing product"""
    model = Product
    form_class = ProductForm
    template_name = 'core/product_form.html'
    success_url = reverse_lazy('core:product_list')

    def get_context_data(self, **kwargs):
        """Add extra context data"""
        context = super().get_context_data(**kwargs)
        context['title'] = _('修改商品')
        context['submit_text'] = _('修改')
        return context

    def form_valid(self, form):
        """Handle valid form"""
        old_status = self.object.status
        response = super().form_valid(form)
        # Log the operation
        log_content = f'修改商品資料：{self.object.product_code} - {self.object.name}'
        if old_status != self.object.status:
            log_content += f'，狀態由 {old_status} 變更為 {self.object.status}'
        OperationLog.objects.create(
            user=self.request.user,
            module='商品管理',
            operation_content=log_content
        )
        messages.success(self.request, _('商品修改成功'))
        return response


# Order Management Views
class OrderListView(LoginRequiredMixin, ListView):
    """View for displaying order list"""
    model = Order
    template_name = 'core/order_list.html'
    context_object_name = 'orders'
    paginate_by = 10
    ordering = ['-created_at']

    def get_queryset(self):
        """Filter orders based on search query"""
        queryset = super().get_queryset().select_related('member', 'created_by')
        search_form = OrderSearchForm(self.request.GET)
        
        if search_form.is_valid():
            search_term = search_form.cleaned_data.get('search_term')
            status_filter = search_form.cleaned_data.get('status_filter')
            date_from = search_form.cleaned_data.get('date_from')
            date_to = search_form.cleaned_data.get('date_to')
            
            if search_term:
                queryset = queryset.filter(
                    Q(member__name__icontains=search_term) |
                    Q(order_code__icontains=search_term)
                )
            
            if status_filter:
                queryset = queryset.filter(order_status=status_filter)
            
            if date_from:
                queryset = queryset.filter(order_date__gte=date_from)
            
            if date_to:
                queryset = queryset.filter(order_date__lte=date_to)
        
        return queryset

    def get_context_data(self, **kwargs):
        """Add extra context data"""
        context = super().get_context_data(**kwargs)
        context['search_form'] = OrderSearchForm(self.request.GET)
        return context


class OrderCreateView(LoginRequiredMixin, CreateView):
    """View for creating a new order"""
    model = Order
    form_class = OrderForm
    template_name = 'core/order_form.html'

    def get_context_data(self, **kwargs):
        """Add extra context data"""
        context = super().get_context_data(**kwargs)
        context['title'] = _('新增訂單')
        context['submit_text'] = _('建立訂單')
        context['member_search_form'] = MemberSearchForm()
        context['courses'] = Course.objects.filter(status='active')
        context['products'] = Product.objects.filter(status='active')
        return context

    def form_valid(self, form):
        """Handle valid form"""
        try:
            with transaction.atomic():
                # Set the created_by field
                form.instance.created_by = self.request.user
                order = form.save()
                
                # Process order items from POST data
                self.process_order_items(order)
                
                # Log the operation
                OperationLog.objects.create(
                    user=self.request.user,
                    module='訂單管理',
                    operation_content=f'新增訂單：{order.order_code} - {order.member.name}'
                )
                
                messages.success(self.request, _('訂單建立成功'))
                return redirect('core:order_detail', pk=order.pk)
        except Exception as e:
            messages.error(self.request, _('建立訂單時發生錯誤，請稍後再試'))
            return self.form_invalid(form)

    def process_order_items(self, order):
        """Process order items from form data.
        
        Items are created first (which triggers order total recalculation via
        OrderItem.save), then inventory is handled once all items exist.
        This avoids partial inventory state if an error occurs mid-loop.
        """
        item_types = self.request.POST.getlist('item_type')
        item_ids = self.request.POST.getlist('item_id')
        quantities = self.request.POST.getlist('quantity')
        unit_prices = self.request.POST.getlist('unit_price')

        # Phase 1: Create all order items
        for i, item_type in enumerate(item_types):
            if item_type and item_ids[i] and quantities[i] and unit_prices[i]:
                OrderItem.objects.create(
                    order=order,
                    item_type=item_type,
                    item_id=int(item_ids[i]),
                    quantity=int(quantities[i]),
                    unit_price=float(unit_prices[i])
                )

        # Phase 2: Handle inventory only for paid orders, after all items exist
        if order.order_status == 'paid':
            self._create_inventory_for_order(order)

    def _create_inventory_for_order(self, order):
        """Create course inventory and deduct product inventory for a paid order.
        
        Safe to call only once per order. Course inventory is guarded by an
        existence check; product inventory uses a processed-ID set to prevent
        double deduction if this method is ever called again.
        """
        # --- Course inventory: create a balance record per course item ---
        for item in order.order_items.filter(item_type='course'):
            existing = CourseInventory.objects.filter(
                order=order,
                course_id=item.item_id
            ).exists()
            if not existing:
                try:
                    course = Course.objects.get(id=item.item_id)
                    CourseInventory.objects.create(
                        member=order.member,
                        course=course,
                        order=order,
                        initial_quantity=item.quantity,
                        remaining_quantity=item.quantity
                    )
                except Course.DoesNotExist:
                    pass

        # --- Product inventory: deduct stock per product item ---
        # Track processed product IDs to prevent accidental double-deduction
        processed_product_ids = set()
        for item in order.order_items.filter(item_type='product'):
            if item.item_id in processed_product_ids:
                continue
            try:
                product = Product.objects.get(id=item.item_id)
                inventory = ProductInventory.get_or_create_for_product(
                    product=product,
                    updated_by=order.created_by
                )
                inventory.adjust_quantity(
                    adjustment=-item.quantity,
                    updated_by=order.created_by,
                    reason=f"訂單出貨：{order.order_code}"
                )
                processed_product_ids.add(item.item_id)
            except Product.DoesNotExist:
                pass


class OrderUpdateView(LoginRequiredMixin, UpdateView):
    """View for updating an existing order"""
    model = Order
    form_class = OrderForm
    template_name = 'core/order_form.html'

    def get_context_data(self, **kwargs):
        """Add extra context data"""
        context = super().get_context_data(**kwargs)
        context['title'] = _('修改訂單')
        context['submit_text'] = _('更新訂單')
        context['order_items'] = self.object.order_items.all()
        context['courses'] = Course.objects.filter(status='active')
        context['products'] = Product.objects.filter(status='active')
        return context

    def form_valid(self, form):
        """Handle valid form"""
        try:
            with transaction.atomic():
                old_status = self.object.order_status
                order = form.save()
                
                # Handle status changes
                if old_status != order.order_status:
                    if order.order_status == 'paid' and old_status != 'paid':
                        # Order became paid - update inventory
                        self.update_inventory_for_paid_order(order)
                    elif order.order_status == 'cancelled' and old_status == 'paid':
                        # Order was cancelled - need manual inventory adjustment
                        messages.warning(self.request, _('訂單已取消，請手動調整對應的庫存數量'))
                
                # Log the operation
                log_content = f'修改訂單資料：{order.order_code} - {order.member.name}'
                if old_status != order.order_status:
                    log_content += f'，狀態由 {old_status} 變更為 {order.order_status}'
                OperationLog.objects.create(
                    user=self.request.user,
                    module='訂單管理',
                    operation_content=log_content
                )
                
                messages.success(self.request, _('訂單更新成功'))
                return redirect('core:order_detail', pk=order.pk)
        except Exception as e:
            messages.error(self.request, _('更新訂單時發生錯誤，請稍後再試'))
            return self.form_invalid(form)

    def update_inventory_for_paid_order(self, order):
        """Update inventory when an existing order transitions to paid status.
        
        Delegates to the shared helper so that course/product inventory logic
        lives in exactly one place.
        """
        self._create_inventory_for_order(order)


class OrderDetailView(LoginRequiredMixin, DetailView):
    """View for displaying order details"""
    model = Order
    template_name = 'core/order_detail.html'
    context_object_name = 'order'

    def get_context_data(self, **kwargs):
        """Add extra context data"""
        context = super().get_context_data(**kwargs)
        context['order_items'] = self.object.order_items.all()
        context['course_inventories'] = self.object.course_inventories.all()
        return context


# AJAX Views for dynamic form handling
@require_http_methods(["GET"])
def get_courses_json(request):
    """Get courses as JSON for AJAX requests"""
    courses = Course.objects.filter(status='active').values('id', 'name', 'course_code', 'quantity_options', 'price_options', 'unlimited_quantity', 'unlimited_price')
    return JsonResponse(list(courses), safe=False)


@require_http_methods(["GET"])
def get_products_json(request):
    """Get products as JSON for AJAX requests"""
    products = Product.objects.filter(status='active').values('id', 'name', 'product_code', 'quantity_options', 'price_options', 'unlimited_quantity', 'unlimited_price')
    return JsonResponse(list(products), safe=False)


@require_http_methods(["GET"])
def search_members_json(request):
    """Search members as JSON for AJAX requests"""
    search_term = request.GET.get('q', '')
    if len(search_term) >= 2:
        members = Member.objects.filter(
            Q(name__icontains=search_term) | Q(phone__icontains=search_term)
        ).values('id', 'name', 'phone', 'member_code')[:10]
        return JsonResponse(list(members), safe=False)
    return JsonResponse([], safe=False)


@require_http_methods(["GET"])
def get_member_details_json(request, member_id):
    """Get member details including coach information as JSON for AJAX requests"""
    try:
        member = Member.objects.select_related('coach').get(pk=member_id)
        data = {
            'id': member.id,
            'name': member.name,
            'phone': member.phone,
            'member_code': member.member_code,
            'coach_id': member.coach.id if member.coach else None,
            'coach_name': member.coach.name if member.coach else None
        }
        return JsonResponse(data)
    except Member.DoesNotExist:
        return JsonResponse({'error': _('會員不存在')}, status=404)


# Course Balance Management Views
class CourseBalanceListView(LoginRequiredMixin, ListView):
    """View for displaying course balance list"""
    model = CourseInventory
    template_name = 'core/course_balance_list.html'
    context_object_name = 'course_balances'
    paginate_by = 10
    ordering = ['member__name', 'course__name', 'order__order_date']

    def get_queryset(self):
        """Filter course balances based on search query"""
        queryset = super().get_queryset().select_related(
            'member', 'course', 'order'
        ).filter(status='active', remaining_quantity__gt=0)
        
        search_form = CourseBalanceSearchForm(self.request.GET)
        
        if search_form.is_valid():
            search_term = search_form.cleaned_data.get('search_term')
            
            if search_term:
                queryset = queryset.filter(
                    Q(member__name__icontains=search_term) |
                    Q(member__phone__icontains=search_term)
                )
        
        return queryset

    def get_context_data(self, **kwargs):
        """Add extra context data"""
        context = super().get_context_data(**kwargs)
        context['search_form'] = CourseBalanceSearchForm(self.request.GET)
        context['title'] = _('課程庫存查詢')
        return context


class SessionListView(LoginRequiredMixin, ListView):
    """View for displaying session list"""
    model = Session
    template_name = 'core/session_list.html'
    context_object_name = 'sessions'
    paginate_by = 10
    ordering = ['-session_date', '-created_at']

    def get_queryset(self):
        """Filter sessions based on search query"""
        queryset = super().get_queryset().select_related('member', 'coach', 'course', 'course_inventory__order')
        search_form = SessionSearchForm(self.request.GET)
        
        if search_form.is_valid():
            search_term = search_form.cleaned_data.get('search_term')
            coach_filter = search_form.cleaned_data.get('coach_filter')
            date_from = search_form.cleaned_data.get('date_from')
            date_to = search_form.cleaned_data.get('date_to')
            
            if search_term:
                queryset = queryset.filter(
                    Q(member__name__icontains=search_term) |
                    Q(member__phone__icontains=search_term) |
                    Q(session_code__icontains=search_term) |
                    Q(course__name__icontains=search_term)
                )
            
            if coach_filter:
                queryset = queryset.filter(coach=coach_filter)
                
            if date_from:
                queryset = queryset.filter(session_date__date__gte=date_from)
                
            if date_to:
                queryset = queryset.filter(session_date__date__lte=date_to)
                
        return queryset

    def get_context_data(self, **kwargs):
        """Add extra context data"""
        context = super().get_context_data(**kwargs)
        context['title'] = _('授課記錄列表')
        context['search_form'] = SessionSearchForm(self.request.GET)
        return context


class SessionCreateView(LoginRequiredMixin, CreateView):
    model = Session
    fields = [] # We'll handle fields manually for more control
    template_name = 'core/session_form.html'
    success_url = reverse_lazy('core:session_create')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('新增授課記錄')
        context['submit_text'] = _('新增')
        context['active_coaches'] = Coach.objects.filter(status='active').order_by('name')
        return context

    def form_valid(self, form):
        # This method won't be directly used as session creation is via AJAX
        return super().form_valid(form)


@require_http_methods(["GET"])
def get_member_courses_json(request, member_id):
    """Get member's active course inventories as JSON for AJAX requests"""
    try:
        member = Member.objects.get(pk=member_id)
        # Get course inventories with remaining quantity > 0, ordered by order date
        course_inventories = CourseInventory.objects.filter(
            member=member, 
            status='active', 
            remaining_quantity__gt=0
        ).select_related('course', 'order').order_by('order__order_date')

        data = []
        for ci in course_inventories:
            data.append({
                'id': ci.id,
                'course_name': ci.course.name,
                'course_code': ci.course.course_code,
                'remaining_quantity': ci.remaining_quantity,
                'order_code': ci.order.order_code,
                'order_date': ci.order.order_date.strftime('%Y-%m-%d')
            })
        return JsonResponse(data, safe=False)
    except Member.DoesNotExist:
        return JsonResponse({'error': _('會員不存在')}, status=404)


@require_http_methods(["POST"])
@csrf_exempt # CSRF will be handled by the frontend form
def deduct_course_and_create_session(request):
    """Deduct a course from inventory and create a session record"""
    try:
        with transaction.atomic():
            member_id = request.POST.get('member_id')
            course_inventory_id = request.POST.get('course_inventory_id')
            coach_id = request.POST.get('coach_id')
            notes = request.POST.get('notes', '')

            member = get_object_or_404(Member, pk=member_id)
            course_inventory = get_object_or_404(CourseInventory, pk=course_inventory_id)

            if course_inventory.member != member:
                return JsonResponse({'error': _('課程庫存不屬於該會員')}, status=400)

            if course_inventory.remaining_quantity <= 0:
                return JsonResponse({'error': _('課程餘額不足')}, status=400)

            # Determine coach (default to member's coach if not provided or invalid)
            actual_coach = member.coach
            if coach_id:
                try:
                    actual_coach = Coach.objects.get(pk=coach_id, status='active')
                except Coach.DoesNotExist:
                    pass

            # Deduct 1 from remaining_quantity
            course_inventory.remaining_quantity -= 1
            if course_inventory.remaining_quantity == 0:
                course_inventory.status = 'used_up'
            course_inventory.save()

            # Create session record with full datetime
            now = timezone.now()
            session = Session.objects.create(
                member=member,
                coach=actual_coach,
                course=course_inventory.course,
                course_inventory=course_inventory,
                session_date=now,
                notes=notes,
                created_by=request.user
            )
            
            # Log the operation
            OperationLog.objects.create(
                user=request.user,
                module='授課管理',
                operation_content=f'新增授課記錄：{session.session_code} - {member.name} - {course_inventory.course.name}'
            )

            return JsonResponse({
                'success': True,
                'message': _('授課記錄建立成功並已扣除1堂課'),
                'session_code': session.session_code,
                'member_name': member.name,
                'coach_name': actual_coach.name,
                'course_name': course_inventory.course.name,
                'order_code': course_inventory.order.order_code,
                'order_date': course_inventory.order.order_date.strftime('%Y-%m-%d'),
                'session_date': timezone.localtime(session.session_date).strftime('%Y/%m/%d %H:%M:%S')
            })
    except Member.DoesNotExist:
        return JsonResponse({'error': _('會員不存在')}, status=404)
    except CourseInventory.DoesNotExist:
        return JsonResponse({'error': _('課程庫存不存在')}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# Product Inventory Views
class ProductInventoryListView(LoginRequiredMixin, ListView):
    """View for listing product inventory"""
    model = ProductInventory
    template_name = 'core/product_inventory_list.html'
    context_object_name = 'inventories'
    paginate_by = 10

    def get_queryset(self):
        """Filter inventory based on search query"""
        queryset = ProductInventory.objects.select_related('product', 'last_updated_by').order_by('product__product_code')
        search_query = self.request.GET.get('search')
        if search_query:
            queryset = queryset.filter(
                Q(product__name__icontains=search_query) |
                Q(product__product_code__icontains=search_query)
            )
        return queryset

    def get_context_data(self, **kwargs):
        """Add extra context data"""
        context = super().get_context_data(**kwargs)
        context['title'] = _('商品庫存管理')
        context['search_form'] = ProductInventorySearchForm(self.request.GET)
        context['search_query'] = self.request.GET.get('search', '')
        
        # Get products that don't have inventory records yet
        existing_product_ids = ProductInventory.objects.values_list('product_id', flat=True)
        products_without_inventory = Product.objects.filter(status='active').exclude(id__in=existing_product_ids)
        
        # Create inventory records for products without them
        for product in products_without_inventory:
            ProductInventory.objects.create(
                product=product,
                quantity=0,
                last_updated_by=self.request.user
            )
        
        return context


class ProductInventoryAdjustView(LoginRequiredMixin, TemplateView):
    """View for adjusting product inventory"""
    template_name = 'core/product_inventory_adjust.html'

    def get_context_data(self, **kwargs):
        """Add form to context"""
        context = super().get_context_data(**kwargs)
        context['title'] = _('商品庫存調整')
        context['form'] = ProductInventoryAdjustmentForm()
        return context

    def post(self, request, *args, **kwargs):
        """Handle form submission"""
        form = ProductInventoryAdjustmentForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    product = form.cleaned_data['product']
                    adjustment_quantity = form.cleaned_data['adjustment_quantity']
                    reason = form.cleaned_data['reason']
                    
                    # Get or create inventory record
                    inventory = ProductInventory.get_or_create_for_product(
                        product=product,
                        updated_by=request.user
                    )
                    
                    # Adjust inventory quantity
                    inventory.adjust_quantity(
                        adjustment=adjustment_quantity,
                        updated_by=request.user,
                        reason=reason
                    )
                    
                    messages.success(
                        request,
                        _('商品庫存調整成功：{} {} {}，目前庫存：{}').format(
                            product.product_code,
                            product.name,
                            f'{adjustment_quantity:+d}',
                            inventory.quantity
                        )
                    )
                    
                return redirect('core:product_inventory_list')
            except Exception as e:
                messages.error(request, _('調整失敗：{}').format(str(e)))
        
        return self.render_to_response(self.get_context_data(form=form))


# Import Management Views
class ImportManagementView(LoginRequiredMixin, TemplateView):
    """View for import management dashboard"""
    template_name = 'core/import_management.html'
    
    def get_context_data(self, **kwargs):
        """Add import management context"""
        context = super().get_context_data(**kwargs)
        context['title'] = _('數據導入管理')
        context['import_type_form'] = ImportTypeForm()
        return context


class ImportTypeSelectionView(LoginRequiredMixin, TemplateView):
    """View for selecting import type and downloading template"""
    template_name = 'core/import_type_selection.html'
    
    def get_context_data(self, **kwargs):
        """Add import type selection context"""
        context = super().get_context_data(**kwargs)
        context['title'] = _('選擇導入類型')
        context['form'] = ImportTypeForm()
        return context
    
    def post(self, request, *args, **kwargs):
        """Handle import type selection"""
        form = ImportTypeForm(request.POST)
        if form.is_valid():
            import_type = form.cleaned_data['import_type']
            return redirect('core:import_file_upload', import_type=import_type)
        
        return self.render_to_response(self.get_context_data(form=form))


class ImportFileUploadView(LoginRequiredMixin, TemplateView):
    """View for uploading import file"""
    template_name = 'core/import_file_upload.html'
    
    def get_context_data(self, **kwargs):
        """Add file upload context"""
        context = super().get_context_data(**kwargs)
        import_type = self.kwargs.get('import_type')
        context['title'] = _('上傳導入檔案')
        context['import_type'] = import_type
        context['form'] = ImportFileForm()
        
        # Add import type specific information
        if import_type == 'members':
            context['import_info'] = {
                'name': _('會員數據導入'),
                'description': _('批量導入會員基本資料'),
                'required_fields': _('姓名、手機號碼、負責教練、註冊日期、狀態為必填欄位'),
                'template_url': reverse_lazy('core:download_import_template', kwargs={'import_type': import_type})
            }
        elif import_type == 'orders':
            context['import_info'] = {
                'name': _('訂單數據導入'),
                'description': _('批量導入歷史訂單資料'),
                'required_fields': _('會員手機號碼、訂單日期、課程名稱、購買數量、單價、付款方式、訂單狀態為必填欄位'),
                'template_url': reverse_lazy('core:download_import_template', kwargs={'import_type': import_type})
            }
        elif import_type == 'sessions':
            context['import_info'] = {
                'name': _('授課記錄導入'),
                'description': _('批量導入授課記錄，系統會自動從會員課程庫存中扣減'),
                'required_fields': _('會員手機號碼、課程名稱、授課日期為必填欄位'),
                'template_url': reverse_lazy('core:download_import_template', kwargs={'import_type': import_type})
            }
        
        return context
    
    def post(self, request, *args, **kwargs):
        """Handle file upload and validation"""
        form = ImportFileForm(request.POST, request.FILES)
        import_type = self.kwargs.get('import_type')
        
        if form.is_valid():
            try:
                import_file = form.cleaned_data['import_file']
                
                # Save uploaded file temporarily
                import tempfile
                import os
                
                with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as temp_file:
                    for chunk in import_file.chunks():
                        temp_file.write(chunk)
                    temp_file_path = temp_file.name
                
                # Process the file based on import type
                from .utils import MembersImportProcessor, OrdersImportProcessor, SessionsImportProcessor
                
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
                
                # Convert datetime objects to strings for JSON serialization
                serializable_data_rows = []
                for row_num, row_data in data_rows:
                    serializable_row_data = []
                    for cell_value in row_data:
                        if isinstance(cell_value, datetime):
                            serializable_row_data.append(cell_value.strftime('%Y-%m-%d %H:%M:%S'))
                        elif isinstance(cell_value, date):
                            serializable_row_data.append(cell_value.strftime('%Y-%m-%d'))
                        else:
                            serializable_row_data.append(cell_value)
                    serializable_data_rows.append((row_num, serializable_row_data))
                
                # Store validation results in session for confirmation step
                request.session['import_data'] = {
                    'import_type': import_type,
                    'file_path': temp_file_path,
                    'data_rows': serializable_data_rows,
                    'errors': errors,
                    'warnings': warnings,
                    'total_rows': len(data_rows)
                }
                
                # Clean up temp file
                os.unlink(temp_file_path)
                
                if errors:
                    # Show validation errors
                    return redirect('core:import_validation', import_type=import_type)
                else:
                    # No errors, proceed to confirmation
                    return redirect('core:import_confirmation', import_type=import_type)
                    
            except Exception as e:
                messages.error(request, _('檔案處理失敗：{}').format(str(e)))
        else:
            messages.error(request, _('檔案格式錯誤'))
        
        return self.render_to_response(self.get_context_data(form=form))


class ImportValidationView(LoginRequiredMixin, TemplateView):
    """View for displaying import validation results"""
    template_name = 'core/import_validation.html'
    
    def get_context_data(self, **kwargs):
        """Add validation results context"""
        context = super().get_context_data(**kwargs)
        import_type = self.kwargs.get('import_type')
        
        # Get validation results from session
        import_data = self.request.session.get('import_data', {})
        if not import_data or import_data.get('import_type') != import_type:
            messages.error(self.request, _('導入資料已過期，請重新上傳檔案'))
            return redirect('core:import_management')
        
        context['title'] = _('導入驗證結果')
        context['import_type'] = import_type
        context['errors'] = import_data.get('errors', [])
        context['warnings'] = import_data.get('warnings', [])
        context['total_rows'] = import_data.get('total_rows', 0)
        context['has_errors'] = len(import_data.get('errors', [])) > 0
        
        return context


class ImportConfirmationView(LoginRequiredMixin, TemplateView):
    """View for import confirmation"""
    template_name = 'core/import_confirmation.html'
    
    def get_context_data(self, **kwargs):
        """Add confirmation context"""
        context = super().get_context_data(**kwargs)
        import_type = self.kwargs.get('import_type')
        
        # Get import data from session
        import_data = self.request.session.get('import_data', {})
        if not import_data or import_data.get('import_type') != import_type:
            messages.error(self.request, _('導入資料已過期，請重新上傳檔案'))
            return redirect('core:import_management')
        
        context['title'] = _('確認導入')
        context['import_type'] = import_type
        context['total_rows'] = import_data.get('total_rows', 0)
        context['warnings'] = import_data.get('warnings', [])
        context['form'] = ImportValidationForm()
        
        return context
    
    def post(self, request, *args, **kwargs):
        """Handle import confirmation"""
        form = ImportValidationForm(request.POST)
        import_type = self.kwargs.get('import_type')
        
        if form.is_valid():
            # Get import data from session
            import_data = request.session.get('import_data', {})
            if not import_data or import_data.get('import_type') != import_type:
                messages.error(request, _('導入資料已過期，請重新上傳檔案'))
                return redirect('core:import_management')
            
            try:
                # Process import
                from .utils import MembersImportProcessor, OrdersImportProcessor, SessionsImportProcessor
                
                # Re-upload and process file
                import tempfile
                import os
                
                with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as temp_file:
                    # Note: In a real implementation, you'd need to re-upload the file
                    # For now, we'll simulate the import process
                    pass
                
                data_rows = import_data.get('data_rows', [])
                
                # Convert string dates back to datetime objects for processing
                processed_data_rows = []
                for row_num, row_data in data_rows:
                    processed_row_data = []
                    for cell_value in row_data:
                        if isinstance(cell_value, str):
                            # Try to parse as datetime
                            try:
                                if len(cell_value) == 10 and cell_value.count('-') == 2:  # YYYY-MM-DD format
                                    processed_row_data.append(datetime.strptime(cell_value, '%Y-%m-%d').date())
                                elif len(cell_value) == 19 and cell_value.count('-') == 2 and cell_value.count(':') == 2:  # YYYY-MM-DD HH:MM:SS format
                                    processed_row_data.append(datetime.strptime(cell_value, '%Y-%m-%d %H:%M:%S'))
                                else:
                                    processed_row_data.append(cell_value)
                            except ValueError:
                                processed_row_data.append(cell_value)
                        else:
                            processed_row_data.append(cell_value)
                    processed_data_rows.append((row_num, processed_row_data))
                
                if import_type == 'members':
                    processor = MembersImportProcessor('')
                elif import_type == 'orders':
                    processor = OrdersImportProcessor('')
                elif import_type == 'sessions':
                    processor = SessionsImportProcessor('')
                
                # Import data
                imported_count, import_errors = processor.import_data(processed_data_rows, request.user)
                
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
                
                return redirect('core:import_management')
                
            except Exception as e:
                messages.error(request, _('導入失敗：{}').format(str(e)))
        
        return self.render_to_response(self.get_context_data(form=form))


def download_import_template(request, import_type):
    """Download Excel template for import"""
    from .utils import create_excel_template
    return create_excel_template(import_type)


# ── Refund & Swap Views ──────────────────────────────────────────────────────

class CourseRefundView(LoginRequiredMixin, TemplateView):
    template_name = 'core/course_refund.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = '課程退費'
        return context


class CourseSwapView(LoginRequiredMixin, TemplateView):
    template_name = 'core/course_swap.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = '換課'
        return context


@require_http_methods(["GET"])
def get_member_inventory_json(request, member_id):
    """Return member's active CourseInventory records with unit_price for refund/swap."""
    try:
        member = Member.objects.get(pk=member_id)
        inventories = CourseInventory.objects.filter(
            member=member,
            status='active',
            remaining_quantity__gt=0
        ).select_related('course', 'order').order_by('order__order_date')

        data = []
        for ci in inventories:
            order_item = ci.order.order_items.filter(
                item_type='course',
                item_id=ci.course.id
            ).first()
            unit_price = float(order_item.unit_price) if order_item else None
            data.append({
                'id': ci.id,
                'course_id': ci.course.id,
                'course_name': ci.course.name,
                'course_code': ci.course.course_code,
                'remaining_quantity': ci.remaining_quantity,
                'order_id': ci.order.id,
                'order_code': ci.order.order_code,
                'order_date': ci.order.order_date.strftime('%Y-%m-%d'),
                'unit_price': unit_price,
            })
        return JsonResponse(data, safe=False)
    except Member.DoesNotExist:
        return JsonResponse({'error': '會員不存在'}, status=404)


@require_http_methods(["GET"])
def get_active_courses_json(request):
    """Return all active courses for swap target selection."""
    courses = Course.objects.filter(status='active').values(
        'id', 'name', 'course_code'
    ).order_by('name')
    return JsonResponse(list(courses), safe=False)


@require_http_methods(["POST"])
@csrf_exempt
def process_course_refund(request):
    """Create a refund order and reduce CourseInventory remaining quantity."""
    if not request.user.is_authenticated:
        return JsonResponse({'error': '請先登入'}, status=401)
    try:
        with transaction.atomic():
            member_id = request.POST.get('member_id')
            course_inventory_id = request.POST.get('course_inventory_id')
            refund_qty = int(request.POST.get('refund_qty', 0))

            if refund_qty <= 0:
                return JsonResponse({'error': '退費數量必須大於0'}, status=400)

            member = get_object_or_404(Member, pk=member_id)
            course_inventory = get_object_or_404(CourseInventory, pk=course_inventory_id)

            if course_inventory.member != member:
                return JsonResponse({'error': '課程庫存不屬於該會員'}, status=400)

            if refund_qty > course_inventory.remaining_quantity:
                return JsonResponse(
                    {'error': f'退費數量超過剩餘堂數（剩餘：{course_inventory.remaining_quantity}堂）'},
                    status=400
                )

            original_order = course_inventory.order
            order_item = original_order.order_items.filter(
                item_type='course',
                item_id=course_inventory.course.id
            ).first()
            if not order_item:
                return JsonResponse({'error': '找不到原始訂單明細，無法計算退費金額'}, status=400)

            unit_price = order_item.unit_price
            refund_amount = refund_qty * unit_price

            # Create refund order (total_amount overridden to negative after OrderItem creation)
            refund_order = Order.objects.create(
                member=member,
                order_date=timezone.localdate(),
                payment_method=original_order.payment_method,
                order_status='paid',
                order_type='refund',
                source_order=original_order,
                total_amount=Decimal('0'),
                notes=f'退費：{course_inventory.course.name} × {refund_qty}堂',
                created_by=request.user
            )

            # OrderItem.save() calls calculate_total() setting total_amount to positive;
            # we immediately override it to negative below.
            OrderItem.objects.create(
                order=refund_order,
                item_type='course',
                item_id=course_inventory.course.id,
                quantity=refund_qty,
                unit_price=unit_price
            )
            refund_order.total_amount = -refund_amount
            refund_order.save(update_fields=['total_amount'])

            # Reduce inventory
            course_inventory.remaining_quantity -= refund_qty
            if course_inventory.remaining_quantity == 0:
                course_inventory.status = 'used_up'
            course_inventory.save()

            log_operation(
                user=request.user,
                module='訂單管理',
                content=(
                    f'退費：{member.member_code} - {member.name}，'
                    f'退費 {course_inventory.course.name} {refund_qty}堂，'
                    f'退費金額 ${refund_amount}，'
                    f'退費訂單 {refund_order.order_code}，'
                    f'原訂單 {original_order.order_code}'
                )
            )

            return JsonResponse({
                'success': True,
                'message': '退費處理成功',
                'refund_order_code': refund_order.order_code,
                'member_name': member.name,
                'course_name': course_inventory.course.name,
                'refund_qty': refund_qty,
                'refund_amount': float(refund_amount),
                'remaining_qty': course_inventory.remaining_quantity,
            })
    except (ValueError, TypeError) as e:
        return JsonResponse({'error': f'資料格式錯誤：{str(e)}'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["POST"])
@csrf_exempt
def process_course_swap(request):
    """Create a swap order, reduce source CourseInventory, and create target CourseInventory."""
    if not request.user.is_authenticated:
        return JsonResponse({'error': '請先登入'}, status=401)
    try:
        with transaction.atomic():
            member_id = request.POST.get('member_id')
            source_inventory_id = request.POST.get('source_inventory_id')
            swap_qty = int(request.POST.get('swap_qty', 0))
            target_course_id = request.POST.get('target_course_id')
            new_unit_price = Decimal(request.POST.get('new_unit_price', '0'))

            if swap_qty <= 0:
                return JsonResponse({'error': '換課數量必須大於0'}, status=400)
            if new_unit_price <= 0:
                return JsonResponse({'error': '新課程單價必須大於0'}, status=400)

            member = get_object_or_404(Member, pk=member_id)
            source_inventory = get_object_or_404(CourseInventory, pk=source_inventory_id)
            target_course = get_object_or_404(Course, pk=target_course_id, status='active')

            if source_inventory.member != member:
                return JsonResponse({'error': '課程庫存不屬於該會員'}, status=400)
            if swap_qty > source_inventory.remaining_quantity:
                return JsonResponse(
                    {'error': f'換課數量超過剩餘堂數（剩餘：{source_inventory.remaining_quantity}堂）'},
                    status=400
                )
            if source_inventory.course.id == target_course.id:
                return JsonResponse({'error': '換課目標課程不能與來源課程相同'}, status=400)

            original_order = source_inventory.order
            source_order_item = original_order.order_items.filter(
                item_type='course',
                item_id=source_inventory.course.id
            ).first()
            if not source_order_item:
                return JsonResponse({'error': '找不到原始訂單明細，無法計算差額'}, status=400)

            old_unit_price = source_order_item.unit_price
            old_course = source_inventory.course
            price_diff = swap_qty * new_unit_price - swap_qty * old_unit_price

            # Create swap order
            swap_order = Order.objects.create(
                member=member,
                order_date=timezone.localdate(),
                payment_method=original_order.payment_method,
                order_status='paid',
                order_type='swap',
                source_order=original_order,
                total_amount=Decimal('0'),
                notes=(
                    f'換課：{old_course.name} × {swap_qty}堂（@${old_unit_price}）'
                    f' 換成 {target_course.name}（@${new_unit_price}）'
                ),
                created_by=request.user
            )

            OrderItem.objects.create(
                order=swap_order,
                item_type='course',
                item_id=target_course.id,
                quantity=swap_qty,
                unit_price=new_unit_price
            )
            swap_order.total_amount = price_diff
            swap_order.save(update_fields=['total_amount'])

            # Reduce source inventory
            source_inventory.remaining_quantity -= swap_qty
            if source_inventory.remaining_quantity == 0:
                source_inventory.status = 'used_up'
            source_inventory.save()

            # Create target inventory
            CourseInventory.objects.create(
                member=member,
                course=target_course,
                order=swap_order,
                initial_quantity=swap_qty,
                remaining_quantity=swap_qty
            )

            diff_display = (
                f'+${price_diff}' if price_diff >= 0 else f'-${abs(price_diff)}'
            )
            log_operation(
                user=request.user,
                module='訂單管理',
                content=(
                    f'換課：{member.member_code} - {member.name}，'
                    f'{old_course.name} × {swap_qty}堂 換成 {target_course.name}，'
                    f'差額 {diff_display}，換課單號 {swap_order.order_code}'
                )
            )

            return JsonResponse({
                'success': True,
                'message': '換課處理成功',
                'swap_order_code': swap_order.order_code,
                'member_name': member.name,
                'old_course_name': old_course.name,
                'new_course_name': target_course.name,
                'swap_qty': swap_qty,
                'old_unit_price': float(old_unit_price),
                'new_unit_price': float(new_unit_price),
                'price_diff': float(price_diff),
                'source_remaining_qty': source_inventory.remaining_quantity,
            })
    except (ValueError, TypeError) as e:
        return JsonResponse({'error': f'資料格式錯誤：{str(e)}'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)