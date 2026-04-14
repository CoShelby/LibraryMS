from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from books.models import Author, Book, BookCopy, Category, Publisher
from circulations.models import Borrowing
from members.models import Member


class DashboardCopyDeleteGuardTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="books-admin",
            password="secret",
            is_staff=True,
            can_manage_books=True,
        )
        self.client.force_login(self.user)

    def test_delete_copy_is_blocked_while_copy_is_borrowed(self):
        member = Member.objects.create(
            name="Member One",
            membership_number="M-10",
            phone="111",
            member_type="student",
            membership_expiry=timezone.now().date() + timedelta(days=30),
        )
        category = Category.objects.create(name="Category")
        publisher = Publisher.objects.create(name="Publisher")
        author = Author.objects.create(name="Author")
        book = Book.objects.create(
            dewey_decimal_number="200",
            title="Checked Out Copy",
            category=category,
            publisher=publisher,
            language="english",
        )
        book.authors.add(author)
        copy = BookCopy.objects.create(book=book, copy_number="1", barcode="copy-10", status="new")
        Borrowing.objects.create(
            member=member,
            book_copy=copy,
            borrow_date=timezone.now(),
            due_date=timezone.now() + timedelta(days=7),
        )

        response = self.client.post(reverse("dashboard_delete_book_copy", args=[copy.id]), follow=True)

        self.assertTrue(BookCopy.objects.filter(id=copy.id).exists())
        self.assertIn(
            "لا يمكن حذف نسخة مستعارة أثناء استعارتها.",
            [message.message for message in get_messages(response.wsgi_request)],
        )