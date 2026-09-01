from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils.translation import gettext_lazy as _

class UserManager(BaseUserManager):
    def create_user(self, username, password=None, **extra_fields):
        if not username:
            raise ValueError('使用者名稱為必填欄位')
        user = self.model(username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        return self.create_user(username, password, **extra_fields)

class User(AbstractBaseUser, PermissionsMixin):
    """Custom user model"""
    username = models.CharField(_('使用者名稱'), max_length=50, unique=True)
    is_active = models.BooleanField(_('啟用'), default=True)
    is_staff = models.BooleanField(_('管理員'), default=False)
    created_at = models.DateTimeField(_('建立時間'), auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = []

    class Meta:
        db_table = 'users'
        verbose_name = _('使用者')
        verbose_name_plural = _('使用者')

    def __str__(self):
        return self.username

class Coach(models.Model):
    """Coach model for storing coach information"""
    ACTIVE_STATUS = 'active'
    INACTIVE_STATUS = 'inactive'
    STATUS_CHOICES = [
        (ACTIVE_STATUS, _('啟用')),
        (INACTIVE_STATUS, _('停用')),
    ]

    coach_code = models.CharField(_('教練編號'), max_length=8, unique=True)
    name = models.CharField(_('教練姓名'), max_length=50)
    phone = models.CharField(_('手機號碼'), max_length=20)
    notes = models.TextField(_('備註'), blank=True, null=True)
    status = models.CharField(
        _('狀態'),
        max_length=10,
        choices=STATUS_CHOICES,
        default=ACTIVE_STATUS
    )
    created_at = models.DateTimeField(_('建立時間'), auto_now_add=True)
    updated_at = models.DateTimeField(_('更新時間'), auto_now=True)

    class Meta:
        db_table = 'coaches'
        verbose_name = _('教練')
        verbose_name_plural = _('教練')
        indexes = [
            models.Index(fields=['phone']),
        ]

    def __str__(self):
        return f"{self.coach_code} - {self.name}"

    def clean(self):
        """Validate model data"""
        from django.core.exceptions import ValidationError
        import re

        # Validate phone number format (Taiwan format)
        phone_pattern = r'^09\d{8}$'
        if not re.match(phone_pattern, self.phone):
            raise ValidationError({
                'phone': _('手機號碼格式不正確，請輸入09開頭的10位數字')
            })

        # Validate status change
        if self.pk:  # Only for existing records
            old_instance = Coach.objects.get(pk=self.pk)
            if old_instance.status == self.ACTIVE_STATUS and self.status == self.INACTIVE_STATUS:
                if self.members.filter(status='active').exists():
                    raise ValidationError({
                        'status': _('此教練尚有啟用中的會員，無法停用')
                    })

    def save(self, *args, **kwargs):
        if not self.coach_code:
            # Generate coach code (C000001, C000002, etc.)
            last_coach = Coach.objects.order_by('-coach_code').first()
            if last_coach:
                last_num = int(last_coach.coach_code[1:])
                self.coach_code = f'C{str(last_num + 1).zfill(6)}'
            else:
                self.coach_code = 'C000001'
        super().save(*args, **kwargs)

class Member(models.Model):
    """Member model for storing member information"""
    GENDER_CHOICES = [
        ('M', _('男')),
        ('F', _('女')),
        ('O', _('其他')),
    ]
    STATUS_CHOICES = [
        ('active', _('啟用')),
        ('inactive', _('停用')),
    ]

    member_code = models.CharField(_('會員編號'), max_length=8, unique=True)
    name = models.CharField(_('姓名'), max_length=50)
    phone = models.CharField(_('手機號碼'), max_length=20, unique=True)
    address = models.TextField(_('地址'), blank=True, null=True)
    gender = models.CharField(_('性別'), max_length=1, choices=GENDER_CHOICES, blank=True, null=True)
    birthday = models.DateField(_('生日'), blank=True, null=True)
    email = models.EmailField(_('Email'), max_length=100, blank=True, null=True)
    line_id = models.CharField(_('Line ID'), max_length=50, blank=True, null=True)
    emergency_contact_name = models.CharField(_('緊急聯絡人姓名'), max_length=50, blank=True, null=True)
    emergency_contact_relation = models.CharField(_('緊急聯絡人關係'), max_length=30, blank=True, null=True)
    emergency_contact_phone = models.CharField(_('緊急聯絡人電話'), max_length=20, blank=True, null=True)
    registration_date = models.DateField(_('註冊日期'))
    coach = models.ForeignKey(
        Coach,
        verbose_name=_('負責教練'),
        on_delete=models.PROTECT,
        related_name='members'
    )
    notes = models.TextField(_('備註'), blank=True, null=True)
    status = models.CharField(
        _('狀態'),
        max_length=10,
        choices=STATUS_CHOICES,
        default='active'
    )
    created_at = models.DateTimeField(_('建立時間'), auto_now_add=True)
    updated_at = models.DateTimeField(_('更新時間'), auto_now=True)

    @property
    def has_active_courses(self):
        """Check if member has any remaining course balance"""
        from core.models import CourseInventory
        return CourseInventory.objects.filter(
            member=self,
            remaining_quantity__gt=0,
            status='active'
        ).exists()

    def clean(self):
        """Validate model data"""
        from django.core.exceptions import ValidationError
        import re

        # Validate phone number format (Taiwan format)
        phone_pattern = r'^09\d{8}$'
        if not re.match(phone_pattern, self.phone):
            raise ValidationError({
                'phone': _('手機號碼格式不正確，請輸入09開頭的10位數字')
            })

        # Validate emergency contact phone if provided
        if self.emergency_contact_phone:
            if not re.match(phone_pattern, self.emergency_contact_phone):
                raise ValidationError({
                    'emergency_contact_phone': _('緊急聯絡人電話格式不正確，請輸入09開頭的10位數字')
                })

        # Validate status change
        if self.pk:  # Only for existing records
            old_instance = Member.objects.get(pk=self.pk)
            if old_instance.status == 'active' and self.status == 'inactive':
                if self.has_active_courses:
                    raise ValidationError({
                        'status': _('此會員尚有未使用完的課程，無法停用')
                    })

    class Meta:
        db_table = 'members'
        verbose_name = _('會員')
        verbose_name_plural = _('會員')
        indexes = [
            models.Index(fields=['phone']),
            models.Index(fields=['coach']),
        ]

    def __str__(self):
        return f"{self.member_code} - {self.name}"

    def save(self, *args, **kwargs):
        if not self.member_code:
            # Generate member code (M000001, M000002, etc.)
            last_member = Member.objects.order_by('-member_code').first()
            if last_member:
                last_num = int(last_member.member_code[1:])
                self.member_code = f'M{str(last_num + 1).zfill(6)}'
            else:
                self.member_code = 'M000001'
        super().save(*args, **kwargs)