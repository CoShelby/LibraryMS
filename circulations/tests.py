from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from books.models import Author, Book, BookCopy, Category, Publisher
from circulations.models import Borrowing, Reservation
from circulations.services import reserve_book
from members.models import Member


class ReserveBookRenewalFlowTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Category")
        self.publisher = Publisher.objects.create(name="Publisher")
        self.author = Author.objects.create(name="Author")

    def create_member(self, membership_number):
        return Member.objects.create(
            name=f"Member {membership_number}",
            membership_number=membership_number,
            phone="111",
            member_type="student",
            membership_expiry=timezone.now().date() + timedelta(days=30),
        )

    def create_book_with_copy(self, barcode):
        book = Book.objects.create(
            dewey_decimal_number="300",
            title=f"Book {barcode}",
            category=self.category,
            publisher=self.publisher,
            language="english",
        )
        book.authors.add(self.author)
        copy = BookCopy.objects.create(book=book, copy_number="1", barcode=barcode, status="new")
        return book, copy

    def test_reserving_a_borrowed_book_by_the_same_member_creates_a_renewal_request(self):
        member = self.create_member("M-20")
        book, copy = self.create_book_with_copy("copy-20")
        borrowing = Borrowing.objects.create(
            member=member,
            book_copy=copy,
            borrow_date=timezone.now(),
            due_date=timezone.now() + timedelta(days=7),
        )

        result = reserve_book(member, book)
        borrowing.refresh_from_db()

        self.assertIsNone(result["created_reservation"])
        self.assertEqual(result["created_renewal_request"].id, borrowing.id)
        self.assertTrue(borrowing.renewal_requested)
        self.assertEqual(Reservation.objects.count(), 0)

    def test_same_member_reservation_respects_renewal_conflict_rules(self):
        borrower = self.create_member("M-21")
        waiting_member = self.create_member("M-22")
        book, copy = self.create_book_with_copy("copy-21")
        borrowing = Borrowing.objects.create(
            member=borrower,
            book_copy=copy,
            borrow_date=timezone.now(),
            due_date=timezone.now() + timedelta(days=7),
        )
        Reservation.objects.create(member=waiting_member, book=book, status="approved")

        with self.assertRaisesMessage(
            ValueError,
            "التجديد  غير مسموح به بينما يوجد حجز آخر معتمد لهذا الكتاب.",
        ):
            reserve_book(borrower, book)

        borrowing.refresh_from_db()
        self.assertFalse(borrowing.renewal_requested)
        self.assertEqual(Reservation.objects.filter(book=book).count(), 1)