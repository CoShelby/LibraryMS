from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from books.models import Author, Book, BookCopy, Category, Publisher
from circulations.models import Borrowing, Fine
from members.models import Member


class MemberDeleteGuardTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="members-admin",
            password="secret",
            is_staff=True,
            can_manage_members=True,
        )
        self.client.force_login(self.user)

    def create_member(self, membership_number="M-1"):
        return Member.objects.create(
            name="Member One",
            membership_number=membership_number,
            phone="111",
            member_type="student",
            membership_expiry=timezone.now().date() + timedelta(days=30),
        )

    def create_borrowing(self, member):
        category = Category.objects.create(name="Category")
        publisher = Publisher.objects.create(name="Publisher")
        author = Author.objects.create(name="Author")
        book = Book.objects.create(
            dewey_decimal_number="100",
            title="Borrowed Book",
            category=category,
            publisher=publisher,
            language="english",
        )
        book.authors.add(author)
        copy = BookCopy.objects.create(book=book, copy_number="1", barcode="copy-1", status="new")
        return Borrowing.objects.create(
            member=member,
            book_copy=copy,
            borrow_date=timezone.now(),
            due_date=timezone.now() + timedelta(days=7),
        )

    def test_delete_member_is_blocked_when_member_has_unreturned_books(self):
        member = self.create_member()
        self.create_borrowing(member)

        response = self.client.post(reverse("delete_member", args=[member.id]), follow=True)

        self.assertTrue(Member.objects.filter(id=member.id).exists())
        self.assertIn(
            "لا يمكن حذف عضو لديه كتب مستعارة أو غرامات غير مدفوعة.",
            [message.message for message in get_messages(response.wsgi_request)],
        )

    def test_delete_member_is_blocked_when_member_has_unpaid_fines(self):
        member = self.create_member("M-2")
        borrowing = self.create_borrowing(member)
        borrowing.return_date = timezone.now()
        borrowing.save(update_fields=["return_date"])
        Fine.objects.create(borrowing=borrowing, days_late=2, amount=50, paid=False)

        response = self.client.post(reverse("delete_member", args=[member.id]), follow=True)

        self.assertTrue(Member.objects.filter(id=member.id).exists())
        self.assertIn(
            "لا يمكن حذف عضو لديه كتب مستعارة أو غرامات غير مدفوعة.",
            [message.message for message in get_messages(response.wsgi_request)],
        )