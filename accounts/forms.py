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
    class Meta:
        model = User
        fields = [
            "username",
            "first_name",
            "last_name",
            "email",
            "can_manage_books",
            "can_manage_members",
            "can_manage_circulation",
            "can_manage_categories",
            "is_active",
        ]
        labels = {
            "username": "اسم المستخدم",
            "first_name": "الاسم الأول",
            "last_name": "اسم العائلة",
            "email": "البريد الإلكتروني",
            "can_manage_books": "يمكنه إدارة الكتب والنسخ والرقمي",
            "can_manage_members": "يمكنه إدارة الأعضاء",
            "can_manage_circulation": "يمكنه إدارة الاستعارات",
            "can_manage_categories": "يمكنه إدارة الفئات/المؤلفين/الناشرين",
            "is_active": "الحساب مفعل",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if field_name.startswith("can_manage_") or field_name == "is_active":
                field.widget.attrs.update({"class": "h-4 w-4"})
            else:
                field.widget.attrs.update({"class": "input-field"})

    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()
        if not username:
            raise forms.ValidationError("اسم المستخدم مطلوب.")
        query = User.objects.filter(username__iexact=username)
        if query.exists():
            raise forms.ValidationError("اسم المستخدم مستخدم مسبقًا.")
        return username

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip()
        if email and User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("هذا البريد مستخدم مسبقًا.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_staff = True
        user.is_admin = True
        user.can_manage_admins = False
        user.set_unusable_password()
        if commit:
            user.save()
        return user


class AdminUserUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = [
            "username",
            "first_name",
            "last_name",
            "email",
            "can_manage_books",
            "can_manage_members",
            "can_manage_circulation",
            "can_manage_categories",
            "is_active",
        ]
        labels = {
            "username": "اسم المستخدم",
            "first_name": "الاسم الأول",
            "last_name": "اسم العائلة",
            "email": "البريد الإلكتروني",
            "can_manage_books": "يمكنه إدارة الكتب",
            "can_manage_members": "يمكنه إدارة الأعضاء",
            "can_manage_circulation": "يمكنه إدارة الاستعارات",
            "can_manage_categories": "يمكنه إدارة الفئات",
            "is_active": "الحساب مفعل",
        }

    def __init__(self, *args, **kwargs):
        self.instance_user = kwargs.get("instance")
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if field_name.startswith("can_manage_") or field_name == "is_active":
                field.widget.attrs.update({"class": "h-4 w-4"})
            else:
                field.widget.attrs.update({"class": "input-field"})

    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()
        if not username:
            raise forms.ValidationError("اسم المستخدم مطلوب.")
        query = User.objects.filter(username__iexact=username)
        if self.instance_user and self.instance_user.pk:
            query = query.exclude(pk=self.instance_user.pk)
        if query.exists():
            raise forms.ValidationError("اسم المستخدم مستخدم مسبقًا.")
        return username

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip()
        query = User.objects.filter(email__iexact=email)
        if self.instance_user and self.instance_user.pk:
            query = query.exclude(pk=self.instance_user.pk)
        if email and query.exists():
            raise forms.ValidationError("هذا البريد مستخدم مسبقًا.")
        return email


class AdminSelfProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email"]
        labels = {
            "username": "اسم المستخدم",
            "first_name": "الاسم الأول",
            "last_name": "اسم العائلة",
            "email": "البريد الإلكتروني",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({"class": "input-field"})

    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()
        if not username:
            raise forms.ValidationError("اسم المستخدم مطلوب.")
        query = User.objects.filter(username__iexact=username).exclude(pk=self.instance.pk)
        if query.exists():
            raise forms.ValidationError("اسم المستخدم مستخدم مسبقًا.")
        return username

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip()
        query = User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk)
        if email and query.exists():
            raise forms.ValidationError("هذا البريد مستخدم مسبقًا.")
        return email
