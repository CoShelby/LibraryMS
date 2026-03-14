from django import forms

from .models import Member


class MemberForm(forms.ModelForm):
    class Meta:
        model = Member
        fields = [
            "name",
            "membership_number",
            "phone",
            "member_type",
            "university_id",
            "major",
            "level",
            "workplace",
            "membership_expiry",
        ]
        labels = {
            "name": "الاسم",
            "membership_number": "رقم العضوية",
            "phone": "رقم الهاتف",
            "member_type": "نوع العضو",
            "university_id": "رقم القيد",
            "major": "التخصص",
            "level": "المستوى الدراسي",
            "workplace": "جهة العمل",
            "membership_expiry": "تاريخ انتهاء العضوية",
        }
        widgets = {
            "membership_expiry": forms.DateInput(attrs={"type": "date", "class": "input-field"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if field_name == "membership_expiry":
                continue
            field.widget.attrs.update({"class": "input-field"})

        self.fields["membership_number"].help_text = "رقم العضوية هو نفس رمز QR."
        self.fields["membership_number"].widget.attrs.update({"placeholder": "رقم العضوية (رمز QR)"})

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

        return cleaned_data
