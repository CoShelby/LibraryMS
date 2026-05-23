from django import forms

from .models import LibrarySystemSettings


class LibrarySystemSettingsForm(forms.ModelForm):
    class Meta:
        model = LibrarySystemSettings
        fields = [
            "fine_amount_per_unit",
            "reservation_days",
            "borrow_days",
            "email_host",
            "email_port",
            "email_use_tls",
            "email_host_user",
            "email_host_password",
            "default_from_email",
        ]
        labels = {
            "fine_amount_per_unit": "مبلغ الغرامة لكل يوم تأخير",
            "reservation_days": "عدد أيام الحجز",
            "borrow_days": "عدد أيام الاستعارة",
            "email_host": "خادم البريد SMTP",
            "email_port": "منفذ البريد",
            "email_use_tls": "استخدام TLS",
            "email_host_user": "بريد الإرسال",
            "email_host_password": "كلمة مرور التطبيق",
            "default_from_email": "بريد المرسل الظاهر",
        }
        help_texts = {
            "email_host_password": "اتركها فارغة إذا كنت لا تريد تغيير كلمة مرور التطبيق المحفوظة.",
            "default_from_email": "يمكن تركه فارغا لاستخدام بريد الإرسال نفسه.",
        }
        widgets = {
            "fine_amount_per_unit": forms.NumberInput(attrs={"min": 1}),
            "reservation_days": forms.NumberInput(attrs={"min": 1}),
            "borrow_days": forms.NumberInput(attrs={"min": 1}),
            "email_host_password": forms.PasswordInput(render_value=False),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._existing_email_password = self.instance.email_host_password if self.instance and self.instance.pk else ""
        self.fields["email_host_password"].required = False
        self.fields["email_use_tls"].widget.attrs.update({"class": "h-4 w-4 rounded border-slate-300"})
        for name, field in self.fields.items():
            if name != "email_use_tls":
                field.widget.attrs.update({"class": "input-field"})

    def clean_email_host_password(self):
        password = self.cleaned_data.get("email_host_password") or ""
        return password or self._existing_email_password

    def clean(self):
        cleaned_data = super().clean()
        email_user = (cleaned_data.get("email_host_user") or "").strip()
        email_password = cleaned_data.get("email_host_password") or ""
        if email_user and not email_password:
            self.add_error("email_host_password", "أدخل كلمة مرور التطبيق لهذا البريد.")
        return cleaned_data
