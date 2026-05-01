from datetime import timedelta

from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from accounts.models import User
from books.models import Author, Book, BookCopy, Category, Publisher
from circulations.models import Borrowing, Fine
from members.models import Member


class MemberFinanceApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="finance_api_user",
            password="test-pass-123",
            can_manage_circulation=True,
            is_staff=True,
        )
        token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        category = Category.objects.create(name="Test Category", name_en="Test Category")
        publisher = Publisher.objects.create(name="Test Publisher")
        author = Author.objects.create(name="Test Author")

        self.book = Book.objects.create(
            title="API Book",
            isbn="",
            dewey_decimal_number="100",
            category=category,
            publisher=publisher,
            publication_year=2024,
            language="english",
            pages=120,
        )
        self.book.authors.add(author)
        self.copy = BookCopy.objects.create(book=self.book, status="new")

        self.member = Member.objects.create(
            name="API Member",
            membership_number="MEM-1001",
            phone="770000001",
            member_type="student",
            membership_expiry=timezone.now().date() + timedelta(days=365),
        )

        now = timezone.now()
        self.borrowing = Borrowing.objects.create(
            book_copy=self.copy,
            member=self.member,
            employee=self.user,
            created_by=self.user,
            borrow_date=now - timedelta(days=10),
            due_date=now - timedelta(days=3),
        )
        self.fine = Fine.objects.create(borrowing=self.borrowing, days_late=3, amount=100, paid=False)

    def test_external_payment_endpoint_supports_partial_installments(self):
        response = self.client.post(
            f"/api/fines/{self.fine.id}/payments/",
            {"amount": 40, "external_reference": "TXN-001"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)

        self.fine.refresh_from_db()
        self.assertFalse(self.fine.paid)
        self.assertEqual(self.fine.total_paid_amount, 40)
        self.assertEqual(self.fine.unpaid_amount, 60)

        response = self.client.post(
            f"/api/fines/{self.fine.id}/payments/",
            {"amount": 60, "external_reference": "TXN-002"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)

        self.fine.refresh_from_db()
        self.assertTrue(self.fine.paid)
        self.assertEqual(self.fine.total_paid_amount, 100)
        self.assertEqual(self.fine.unpaid_amount, 0)

    def test_external_payment_rejects_amount_above_remaining(self):
        response = self.client.post(
            f"/api/fines/{self.fine.id}/payments/",
            {"amount": 150},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_member_search_returns_unreturned_copies_and_fines(self):
        response = self.client.get("/api/members/search/", {"membership_number": "MEM-1001"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)

        result = response.data["results"][0]
        self.assertEqual(result["member"]["membership_number"], "MEM-1001")
        self.assertEqual(len(result["unreturned_borrowed_copies"]), 1)
        self.assertEqual(len(result["fines"]), 1)
