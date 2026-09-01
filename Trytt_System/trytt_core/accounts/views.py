from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from .models import Member
from .forms import MemberForm, MemberSearchForm
from core.utils import log_operation

@login_required
def member_list(request):
    """Display list of members with search functionality"""
    search_form = MemberSearchForm(request.GET)
    members = Member.objects.all().order_by('-created_at')
    
    if search_form.is_valid():
        search_term = search_form.cleaned_data.get('search_term')
        if search_term:
            members = members.filter(
                Q(name__icontains=search_term) |
                Q(phone__icontains=search_term)
            )
    
    # Pagination
    paginator = Paginator(members, 10)  # Show 10 members per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'search_form': search_form,
    }
    return render(request, 'accounts/member_list.html', context)

@login_required
def member_create(request):
    """Create new member"""
    if request.method == 'POST':
        form = MemberForm(request.POST)
        if form.is_valid():
            try:
                member = form.save()
                # Log the operation
                log_operation(
                    user=request.user,
                    module='會員管理',
                    content=f'新增會員：{member.member_code} - {member.name}'
                )
                messages.success(request, _(f'會員 {member.name} 建立成功'))
                return redirect('accounts:member_list')
            except Exception as e:
                messages.error(request, _('建立會員時發生錯誤，請稍後再試'))
        else:
            messages.error(request, _('請檢查輸入資料是否正確'))
    else:
        form = MemberForm()
    
    context = {
        'form': form,
        'title': _('新增會員'),
    }
    return render(request, 'accounts/member_form.html', context)

@login_required
def member_update(request, pk):
    """Update existing member"""
    member = get_object_or_404(Member, pk=pk)
    if request.method == 'POST':
        # Create a mutable copy of POST data
        post_data = request.POST.copy()
        # If registration_date is disabled, use the hidden field value
        if 'registration_date_hidden' in post_data:
            post_data['registration_date'] = post_data['registration_date_hidden']
        
        form = MemberForm(post_data, instance=member)
        if form.is_valid():
            try:
                old_status = member.status
                old_status_display = member.get_status_display()
                old_coach_id = member.coach_id
                old_coach_name = member.coach.name if member.coach else ''
                member = form.save()
                # Log coach change, status change, or general update
                if old_coach_id != member.coach_id:
                    log_content = (
                        f'修改會員資料：{member.member_code} - {member.name}'
                        f'，負責教練由 {old_coach_name} 變更為 {member.coach.name}'
                    )
                elif old_status != member.status:
                    log_content = (
                        f'修改會員資料：{member.member_code} - {member.name}'
                        f'，狀態由 {old_status_display} 變更為 {member.get_status_display()}'
                    )
                else:
                    log_content = f'修改會員資料：{member.member_code} - {member.name}'
                log_operation(
                    user=request.user,
                    module='會員管理',
                    content=log_content
                )
                messages.success(request, _(f'會員 {member.name} 資料更新成功'))
                return redirect('accounts:member_list')
            except Exception as e:
                messages.error(request, _('更新會員資料時發生錯誤，請稍後再試'))
        else:
            # Show specific field errors
            for field, errors in form.errors.items():
                if field in form.fields:  # Only show errors for fields that exist in the form
                    field_name = form.fields[field].label
                    for error in errors:
                        messages.error(request, f'{field_name}: {error}')
    else:
        form = MemberForm(instance=member)
    
    context = {
        'form': form,
        'title': _('修改會員資料'),
        'member': member,
    }
    return render(request, 'accounts/member_form.html', context)