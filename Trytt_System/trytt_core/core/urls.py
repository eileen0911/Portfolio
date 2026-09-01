from django.urls import path
from .views import (
    HomeView,
    CourseListView,
    CourseCreateView,
    CourseUpdateView,
    ProductListView,
    ProductCreateView,
    ProductUpdateView,
    OrderListView,
    OrderCreateView,
    OrderUpdateView,
    OrderDetailView,
    CourseBalanceListView,
    get_courses_json,
    get_products_json,
    search_members_json,
    get_member_details_json,
    SessionListView,
    SessionCreateView,
    get_member_courses_json,
    deduct_course_and_create_session,
    ProductInventoryListView,
    ProductInventoryAdjustView,
    ImportManagementView,
    ImportTypeSelectionView,
    ImportFileUploadView,
    ImportValidationView,
    ImportConfirmationView,
    download_import_template,
    CourseRefundView,
    CourseSwapView,
    get_member_inventory_json,
    get_active_courses_json,
    process_course_refund,
    process_course_swap,
)

app_name = 'core'

urlpatterns = [
    path('', HomeView.as_view(), name='home'),
    
    # Course Management URLs
    path('courses/', CourseListView.as_view(), name='course_list'),
    path('courses/create/', CourseCreateView.as_view(), name='course_create'),
    path('courses/<int:pk>/update/', CourseUpdateView.as_view(), name='course_update'),
    
    # Product Management URLs
    path('products/', ProductListView.as_view(), name='product_list'),
    path('products/create/', ProductCreateView.as_view(), name='product_create'),
    path('products/<int:pk>/update/', ProductUpdateView.as_view(), name='product_update'),
    
    # Order Management URLs
    path('orders/', OrderListView.as_view(), name='order_list'),
    path('orders/create/', OrderCreateView.as_view(), name='order_create'),
    path('orders/<int:pk>/update/', OrderUpdateView.as_view(), name='order_update'),
    path('orders/<int:pk>/', OrderDetailView.as_view(), name='order_detail'),
    
    # Course Balance Management URLs
    path('course-balance/', CourseBalanceListView.as_view(), name='course_balance_list'),
    
    # Product Inventory Management URLs
    path('product-inventory/', ProductInventoryListView.as_view(), name='product_inventory_list'),
    path('product-inventory/adjust/', ProductInventoryAdjustView.as_view(), name='product_inventory_adjust'),
    
    # AJAX URLs
    path('api/courses/', get_courses_json, name='courses_json'),
    path('api/products/', get_products_json, name='products_json'),
    path('api/members/search/', search_members_json, name='members_search_json'),
    path('api/members/<int:member_id>/details/', get_member_details_json, name='member_details_json'),
    
    # Session Management URLs
    path('sessions/', SessionListView.as_view(), name='session_list'),
    path('sessions/create/', SessionCreateView.as_view(), name='session_create'),
    path('api/members/<int:member_id>/courses/', get_member_courses_json, name='member_courses_json'),
    path('api/sessions/deduct/', deduct_course_and_create_session, name='deduct_course_and_create_session'),
    
    # Refund & Swap URLs
    path('refund/', CourseRefundView.as_view(), name='course_refund'),
    path('swap/', CourseSwapView.as_view(), name='course_swap'),
    path('api/members/<int:member_id>/inventory/', get_member_inventory_json, name='member_inventory_json'),
    path('api/courses/active/', get_active_courses_json, name='active_courses_json'),
    path('api/courses/refund/', process_course_refund, name='process_course_refund'),
    path('api/courses/swap/', process_course_swap, name='process_course_swap'),

    # Import Management URLs
    path('import/', ImportManagementView.as_view(), name='import_management'),
    path('import/type-selection/', ImportTypeSelectionView.as_view(), name='import_type_selection'),
    path('import/file-upload/<str:import_type>/', ImportFileUploadView.as_view(), name='import_file_upload'),
    path('import/validation/<str:import_type>/', ImportValidationView.as_view(), name='import_validation'),
    path('import/confirmation/<str:import_type>/', ImportConfirmationView.as_view(), name='import_confirmation'),
    path('import/download-template/<str:import_type>/', download_import_template, name='download_import_template'),
]
