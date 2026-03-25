from django.db import models


class Member(models.Model):
    MEMBER_TYPE = [
        ("student", "طالب"),
        ("staff", "موظف"),
        ("faculty", "هيئة تدريس"),
    ]

    STUDY_LEVEL = [
        ("first", "الأول"),
        ("second", "الثاني"),
        ("third", "الثالث"),
        ("fourth", "الرابع"),
    ]

    name = models.CharField(max_length=200)
    membership_number = models.CharField(max_length=50, unique=True)
    phone = models.CharField(max_length=20)
    member_type = models.CharField(max_length=20, choices=MEMBER_TYPE)
    university_id = models.CharField(max_length=50, blank=True, null=True)
    major = models.CharField(max_length=200, blank=True, null=True)
    level = models.CharField(max_length=10, choices=STUDY_LEVEL, blank=True, null=True)
    workplace = models.CharField(max_length=200, blank=True, null=True)
    membership_expiry = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    card_print_count = models.PositiveIntegerField(default=0)
    last_card_printed_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return self.name
