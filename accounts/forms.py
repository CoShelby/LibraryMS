from django import forms
from django.contrib.auth.forms import AuthenticationForm

from .models import User


class AdminAuthenticationForm(AuthenticationForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not (user.is_superuser or user.is_staff or getattr(user, "is_admin", False)):
            raise forms.ValidationError(
                "هذا الحساب غير مصرح له بدخول لوحة الإدارة.",
                code="not_admin",
            )


class AdminUserCreationForm(forms.ModelForm):
    password1 = forms.CharField(label="كلمة المرور", widget=forms.PasswordInput)
    password2 = forms.CharField(label="تأكيد كلمة المرور", widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = [
            "username",
            "first_name",
            "last_name",
            "email",
            "can_manage_admins",
            "can_manage_books",
            "can_manage_members",
            "can_manage_circulation",
            "can_manage_categories",
        ]
        labels = {
            "username": "اسم المستخدم",
            "first_name": "الاسم الأول",
            "last_name": "اسم العائلة",
            "email": "البريد الإلكتروني",
            "can_manage_admins": "يمكنه إنشاء/إدارة الأدمنز",
            "can_manage_books": "يمكنه إدارة الكتب والنسخ والرقمي",
            "can_manage_members": "يمكنه إدارة الأعضاء",
            "can_manage_circulation": "يمكنه إدارة الاستعارات",
            "can_manage_categories": "يمكنه إدارة الفئات/المؤلفين/الناشرين",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if field_name.startswith("can_manage_"):
                field.widget.attrs.update({"class": "h-4 w-4"})
            else:
                field.widget.attrs.update({"class": "input-field"})

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "كلمتا المرور غير متطابقتين.")
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_staff = True
        user.is_admin = True
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user

