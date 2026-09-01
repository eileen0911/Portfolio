from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from .models import Member, Coach

class MemberForm(forms.ModelForm):
    """Form for creating and updating members"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set required fields
        self.fields['name'].required = True
        self.fields['phone'].required = True
        self.fields['coach'].required = True
        
        # Set initial registration date to today for new members
        if not self.instance.pk:  # If creating new member
            self.fields['registration_date'].initial = timezone.now().date()
            self.fields['status'].initial = 'active'
            # Set date input type for new member form
            self.fields['registration_date'].widget = forms.DateInput(
                attrs={'type': 'date'},
                format='%Y-%m-%d'
            )
        else:  # If updating existing member
            # Show registration date as plain text
            formatted_date = self.instance.registration_date.strftime('%Y/%m/%d')
            self.fields['registration_date'].widget = forms.TextInput(
                attrs={
                    'readonly': True,
                    'disabled': True,
                    'value': formatted_date,
                    'class': 'form-control-plaintext'
                }
            )
            # Add a hidden field to preserve the value
            self.fields['registration_date_hidden'] = forms.DateField(
                widget=forms.HiddenInput(),
                initial=self.instance.registration_date
            )
        
        # Only show active coaches in dropdown
        self.fields['coach'].queryset = Coach.objects.filter(status='active')
        
        # List of fields that should use form-select
        select_fields = ['coach', 'gender', 'status']
        
        # Add CSS classes and autocomplete attributes to all fields
        for field_name, field in self.fields.items():
            if field_name == 'registration_date' and self.instance.pk:
                # Keep form-control-plaintext for registration_date on update
                continue
                
            if field_name in select_fields:
                field.widget.attrs.update({
                    'class': 'form-select',
                    'autocomplete': 'off'
                })
            else:
                # Default to form-control
                attrs = {'class': 'form-control'}
                
                # Add autocomplete where appropriate
                autocomplete_map = {
                    'name': 'name',
                    'phone': 'tel',
                    'address': 'street-address',
                    'email': 'email',
                    'birthday': 'bday',
                    'emergency_contact_phone': 'tel',
                }
                
                if field_name in autocomplete_map:
                    attrs['autocomplete'] = autocomplete_map[field_name]
                else:
                    attrs['autocomplete'] = 'off'
                    
                field.widget.attrs.update(attrs)

    class Meta:
        model = Member
        fields = [
            'name', 'phone', 'address', 'gender', 'birthday', 'email',
            'line_id', 'emergency_contact_name', 'emergency_contact_relation',
            'emergency_contact_phone', 'registration_date', 'coach', 'notes',
            'status'
        ]
        widgets = {
            'birthday': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'address': forms.Textarea(attrs={'rows': 3}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def clean(self):
        cleaned_data = super().clean()
        
        # Additional validation for emergency contact
        emergency_name = cleaned_data.get('emergency_contact_name')
        emergency_relation = cleaned_data.get('emergency_contact_relation')
        emergency_phone = cleaned_data.get('emergency_contact_phone')
        
        # If any emergency contact field is filled, all are required
        if any([emergency_name, emergency_relation, emergency_phone]):
            if not all([emergency_name, emergency_relation, emergency_phone]):
                raise forms.ValidationError(
                    _('緊急聯絡人資料必須完整填寫（姓名、關係、電話）')
                )
        
        return cleaned_data

class MemberSearchForm(forms.Form):
    """Form for searching members"""
    search_term = forms.CharField(
        label=_('搜尋'),
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('輸入會員姓名或手機號碼')
        })
    )