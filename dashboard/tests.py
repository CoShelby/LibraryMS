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
from dashboard.forms import BookForm, DigitalLibraryForm
from digital_library.models import DigitalLibrary


class DashboardAuthorSplitTests(TestCase):
    def test_book_form_split_names_uses_dash_separator(self):
        self.assertEqual(BookForm._split_names("Author One - Author Two - Author One"), ["Author One", "Author Two"])


class DigitalLibraryFormQuerysetTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Tech")
        self.publisher = Publisher.objects.create(name="Pub")
        self.author = Author.objects.create(name="Main Author")

    def _build_book(self, title, with_copy=True):
        book = Book.objects.create(
            dewey_decimal_number="100",
            title=title,
            category=self.category,
            publisher=self.publisher,
            language="english",
        )
        book.authors.add(self.author)
        if with_copy:
            BookCopy.objects.create(book=book, copy_number=None, barcode="", status="new")
        return book

    def test_add_form_includes_only_physical_books_without_existing_digital_link(self):
        eligible_book = self._build_book("Eligible", with_copy=True)
        no_copy_book = self._build_book("No Copy", with_copy=False)
        already_digital_book = self._build_book("Already Digital", with_copy=True)
        DigitalLibrary.objects.create(book=already_digital_book)

        form = DigitalLibraryForm()
        queryset_ids = set(form.fields["book"].queryset.values_list("id", flat=True))

        self.assertIn(eligible_book.id, queryset_ids)
        self.assertNotIn(no_copy_book.id, queryset_ids)
        self.assertNotIn(already_digital_book.id, queryset_ids)

    def test_edit_form_keeps_currently_linked_book_available(self):
        linked_book = self._build_book("Linked", with_copy=True)
        digital = DigitalLibrary.objects.create(book=linked_book)

        form = DigitalLibraryForm(instance=digital)
        queryset_ids = set(form.fields["book"].queryset.values_list("id", flat=True))

        self.assertIn(linked_book.id, queryset_ids)


class DashboardDigitalAddAuthorSplitTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="digital-admin",
            password="secret",
            is_staff=True,
            can_manage_books=True,
        )
        self.client.force_login(self.user)

    def test_create_new_digital_book_saves_each_dash_separated_author(self):
        response = self.client.post(
            reverse("dashboard_digital_add"),
            {
                "create_new_book": "on",
                "new_title": "Digital Testing Book",
                "new_author_names": "Alpha Author - Beta Author",
                "new_category_name": "CompSci",
                "new_publisher_name": "Testing House",
                "new_dewey_decimal_number": "005.1",
                "new_publication_year": 2026,
                "new_language": "english",
                "new_pages": 120,            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        book = Book.objects.get(title="Digital Testing Book")
        self.assertTrue(DigitalLibrary.objects.filter(book=book).exists())
        self.assertCountEqual(list(book.authors.values_list("name", flat=True)), ["Alpha Author", "Beta Author"])
