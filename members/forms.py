from django import forms

from libraryms.validation import normalize_contact_email, normalize_yemen_phone

from .models import Member


class MemberForm(forms.ModelForm):
    class Meta:
        model = Member
        fields = [
            "name",
            "membership_number",
            "email",
            "phone",
            "member_type",
            "university_id",
            "major",
            "level",
            "workplace",
            "photo",
            "membership_expiry",
            "is_suspended",
            "suspension_reason",
        ]
        labels = {
            "name": "الاسم",
            "membership_number": "رقم العضوية",
            "email": "البريد الإلكتروني",
            "phone": "رقم الهاتف",
            "member_type": "نوع العضو",
            "university_id": "رقم القيد",
            "major": "التخصص",
            "level": "المستوى الدراسي",
            "workplace": "جهة العمل",
            "photo": "صورة العضو",
            "membership_expiry": "تاريخ انتهاء العضوية",
            "is_suspended": "العضوية موقوفة",
            "suspension_reason": "سبب الإيقاف",
        }
        widgets = {
            "membership_expiry": forms.DateInput(attrs={"type": "date", "class": "input-field"}),
            "photo": forms.ClearableFileInput(attrs={"class": "input-field", "accept": "image/*"}),
            "suspension_reason": forms.TextInput(attrs={"class": "input-field", "placeholder": "اختياري"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if field_name in {"membership_expiry", "is_suspended"}:
                continue
            field.widget.attrs.update({"class": "input-field"})

        self.fields["membership_number"].help_text = "رقم العضوية هو نفس رمز QR."
        self.fields["membership_number"].widget.attrs.update({"placeholder": "رقم العضوية (رمز QR)"})
        self.fields["email"].widget.attrs.update({"placeholder": "example@gmail.com"})
        self.fields["phone"].widget.attrs.update({"placeholder": "+9677XXXXXXX أو 7XXXXXXX"})
        self.fields["is_suspended"].widget.attrs.update({"class": "h-4 w-4 rounded border-slate-300"})

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip()
        if not email:
            return ""

        normalized = normalize_contact_email(email)
        queryset = Member.objects.filter(email__iexact=normalized)
        if self.instance and self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise forms.ValidationError("هذا البريد الإلكتروني مستخدم لعضو آخر.")
        return normalized

    def clean_phone(self):
        return normalize_yemen_phone(self.cleaned_data.get("phone") or "")

    def clean(self):
        cleaned_data = super().clean()
        member_type = cleaned_data.get("member_type")

        if member_type == "student":
            if not (cleaned_data.get("university_id") or "").strip():
                self.add_error("university_id", "رقم القيد مطلوب للطالب.")
            if not (cleaned_data.get("major") or "").strip():
                self.add_error("major", "التخصص مطلوب للطالب.")
            if not cleaned_data.get("level"):
                self.add_error("level", "المستوى الدراسي مطلوب للطالب.")
            cleaned_data["workplace"] = ""

        if member_type in {"staff", "faculty"}:
            if not (cleaned_data.get("workplace") or "").strip():
                self.add_error("workplace", "جهة العمل مطلوبة للموظف وهيئة التدريس.")
            cleaned_data["university_id"] = ""
            cleaned_data["major"] = ""
            cleaned_data["level"] = ""

        if not cleaned_data.get("is_suspended"):
            cleaned_data["suspension_reason"] = ""

        return cleaned_data

