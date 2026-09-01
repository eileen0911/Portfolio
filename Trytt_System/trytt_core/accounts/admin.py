from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _
from .models import User, Coach, Member

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'is_active', 'is_staff', 'created_at', 'last_login')
    list_filter = ('is_active', 'is_staff', 'groups')
    search_fields = ('username',)
    ordering = ('-created_at',)
    
    # These are the default UserAdmin add_fieldsets for proper password handling
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2'),
        }),
    )
    
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        (_('Permissions'), {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
    )
    filter_horizontal = ('groups', 'user_permissions',)

from core.utils import log_operation

@admin.register(Coach)
class CoachAdmin(admin.ModelAdmin):
    list_display = ('coach_code', 'name', 'phone', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('coach_code', 'name', 'phone')
    ordering = ('-created_at',)
    readonly_fields = ('coach_code', 'created_at', 'updated_at')
    fieldsets = (
        (None, {
            'fields': ('coach_code', 'name', 'phone', 'status')
        }),
        (_('Additional Information'), {
            'fields': ('notes',)
        }),
        (_('System Information'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def save_model(self, request, obj, form, change):
        """Override save_model to add operation logging"""
        if change:  # Editing existing coach
            old_obj = self.model.objects.get(pk=obj.pk)
            # Log status change
            if old_obj.status != obj.status:
                log_operation(
                    user=request.user,
                    module='教練管理',
                    content=f'修改教練資料：{obj.coach_code} - {obj.name}，狀態由 {old_obj.get_status_display()} 變更為 {obj.get_status_display()}'
                )
            else:
                log_operation(
                    user=request.user,
                    module='教練管理',
                    content=f'修改教練資料：{obj.coach_code} - {obj.name}'
                )
        else:  # Creating new coach
            log_operation(
                user=request.user,
                module='教練管理',
                content=f'新增教練：{obj.name}'
            )
        super().save_model(request, obj, form, change)

    def delete_model(self, request, obj):
        """Override delete_model to add operation logging"""
        log_operation(
            user=request.user,
            module='教練管理',
            content=f'刪除教練：{obj.coach_code} - {obj.name}'
        )
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        """Override delete_queryset to add operation logging for bulk deletions"""
        for obj in queryset:
            log_operation(
                user=request.user,
                module='教練管理',
                content=f'刪除教練：{obj.coach_code} - {obj.name}'
            )
        super().delete_queryset(request, queryset)

from django import forms

@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ('member_code', 'name', 'phone', 'coach', 'status', 'registration_date')
    list_filter = ('status', 'registration_date', 'coach', 'gender')
    search_fields = ('member_code', 'name', 'phone', 'email')
    ordering = ('-registration_date',)
    readonly_fields = ('member_code', 'created_at', 'updated_at')

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Override to filter inactive coaches from the selection"""
        if db_field.name == "coach":
            kwargs["queryset"] = Coach.objects.filter(status=Coach.ACTIVE_STATUS)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
    fieldsets = (
        (None, {
            'fields': ('member_code', 'name', 'phone', 'email', 'status')
        }),
        (_('Personal Information'), {
            'fields': ('gender', 'birthday', 'address', 'line_id')
        }),
        (_('Emergency Contact'), {
            'fields': ('emergency_contact_name', 'emergency_contact_relation', 'emergency_contact_phone')
        }),
        (_('Membership Information'), {
            'fields': ('registration_date', 'coach', 'notes')
        }),
        (_('System Information'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def save_model(self, request, obj, form, change):
        """Override save_model to add operation logging"""
        if change:  # Editing existing member
            old_obj = self.model.objects.get(pk=obj.pk)
            old_coach_id = old_obj.coach_id
            old_coach_name = old_obj.coach.name if old_obj.coach else ''
            old_status = old_obj.status
            old_status_display = old_obj.get_status_display()
            super().save_model(request, obj, form, change)
            if old_coach_id != obj.coach_id:
                log_operation(
                    user=request.user,
                    module='會員管理',
                    content=f'修改會員資料：{obj.member_code} - {obj.name}，負責教練由 {old_coach_name} 變更為 {obj.coach.name}'
                )
            elif old_status != obj.status:
                log_operation(
                    user=request.user,
                    module='會員管理',
                    content=f'修改會員資料：{obj.member_code} - {obj.name}，狀態由 {old_status_display} 變更為 {obj.get_status_display()}'
                )
            else:
                log_operation(
                    user=request.user,
                    module='會員管理',
                    content=f'修改會員資料：{obj.member_code} - {obj.name}'
                )
        else:  # Creating new member — call super() first so member_code is generated
            super().save_model(request, obj, form, change)
            log_operation(
                user=request.user,
                module='會員管理',
                content=f'新增會員：{obj.member_code} - {obj.name}'
            )

    def delete_model(self, request, obj):
        """Override delete_model to add operation logging"""
        log_operation(
            user=request.user,
            module='會員管理',
            content=f'刪除會員：{obj.member_code} - {obj.name}'
        )
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        """Override delete_queryset to add operation logging for bulk deletions"""
        for obj in queryset:
            log_operation(
                user=request.user,
                module='會員管理',
                content=f'刪除會員：{obj.member_code} - {obj.name}'
            )
        super().delete_queryset(request, queryset)