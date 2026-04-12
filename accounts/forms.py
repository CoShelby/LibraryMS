from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm

from libraryms.validation import normalize_contact_email

from .models import User


class AdminAuthenticationForm(AuthenticationForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not (user.is_superuser or user.is_staff or getattr(user, "is_admin", False)):
            raise forms.ValidationError(
                "هذا الحساب غير مصرح له بدخول لوحة المشرفين.",
                code="not_admin",
            )


class AdminUserCreationForm(forms.ModelForm):
    password1 = forms.CharField(label='كلمة المرور', widget=forms.PasswordInput(attrs={'class': 'input-field'}))
    password2 = forms.CharField(label='تأكيد كلمة المرور', widget=forms.PasswordInput(attrs={'class': 'input-field'}))
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
            "is_active",
        ]
        labels = {
            "username": "اسم المستخدم",
            "first_name": "الاسم الأول",
            "last_name": "اسم العائلة",
            "email": "البريد الإلكتروني",
            "can_manage_admins": "يمكنه إدارة المشرفين الذين ينشئهم",
            "can_manage_books": "يمكنه إدارة الكتب والنسخ والرقمي",
            "can_manage_members": "يمكنه إدارة الأعضاء",
            "can_manage_circulation": "يمكنه إدارة الاستعارات",
            "can_manage_categories": "يمكنه إدارة الفئات/المؤلفين/الناشرين",
            "is_active": "الحساب مفعل",
        }

    def __init__(self, *args, **kwargs):
        self.allow_admin_management = kwargs.pop("allow_admin_management", False)
        super().__init__(*args, **kwargs)
        if not self.allow_admin_management:
            self.fields.pop("can_manage_admins")

        self.fields["email"].required = True

        for field_name, field in self.fields.items():
            if field_name.startswith("can_manage_") or field_name == "is_active":
                field.widget.attrs.update({"class": "h-4 w-4 rounded border-slate-300"})
            else:
                field.widget.attrs.update({"class": "input-field"})

    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()
        if not username:
            raise forms.ValidationError("اسم المستخدم مطلوب.")
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("اسم المستخدم مستخدم مسبقًا.")
        return username

    def clean_email(self):
        normalized = normalize_contact_email(self.cleaned_data.get("email") or "")
        if User.objects.filter(email__iexact=normalized).exists():
            raise forms.ValidationError("هذا البريد مستخدم مسبقًا.")
        return normalized

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1") or ""
        password2 = self.cleaned_data.get("password2") or ""
        if password1 != password2:
            raise forms.ValidationError("كلمتا المرور غير متطابقتين.")
        password_validation.validate_password(password2)
        return password2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_staff = True
        user.is_admin = True
        user.can_manage_admins = self.cleaned_data.get("can_manage_admins", False) if self.allow_admin_management else False
        user.set_password(self.cleaned_data["password1"])
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
            "can_manage_admins",
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
            "can_manage_admins": "يمكنه إدارة المشرفين الذين ينشئهم",
            "can_manage_books": "يمكنه إدارة الكتب",
            "can_manage_members": "يمكنه إدارة الأعضاء",
            "can_manage_circulation": "يمكنه إدارة الاستعارات",
            "can_manage_categories": "يمكنه إدارة الفئات",
            "is_active": "الحساب مفعل",
        }

    def __init__(self, *args, **kwargs):
        self.instance_user = kwargs.get("instance")
        self.allow_admin_management = kwargs.pop("allow_admin_management", False)
        super().__init__(*args, **kwargs)
        if not self.allow_admin_management:
            self.fields.pop("can_manage_admins")

        self.fields["email"].required = True

        for field_name, field in self.fields.items():
            if field_name.startswith("can_manage_") or field_name == "is_active":
                field.widget.attrs.update({"class": "h-4 w-4 rounded border-slate-300"})
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
        normalized = normalize_contact_email(self.cleaned_data.get("email") or "")
        query = User.objects.filter(email__iexact=normalized)
        if self.instance_user and self.instance_user.pk:
            query = query.exclude(pk=self.instance_user.pk)
        if query.exists():
            raise forms.ValidationError("هذا البريد مستخدم مسبقًا.")
        return normalized

    def save(self, commit=True):
        user = super().save(commit=False)
        user.can_manage_admins = self.cleaned_data.get("can_manage_admins", False) if self.allow_admin_management else False
        if commit:
            user.save()
        return user


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
        self.fields["email"].required = True
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
        normalized = normalize_contact_email(self.cleaned_data.get("email") or "")
        query = User.objects.filter(email__iexact=normalized).exclude(pk=self.instance.pk)
        if query.exists():
            raise forms.ValidationError("هذا البريد مستخدم مسبقًا.")
        return normalized


