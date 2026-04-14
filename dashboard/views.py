import json
import os

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.core.paginator import Paginator
from django.db.models import Count, ExpressionWrapper, F, IntegerField, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.csrf import csrf_exempt

from accounts.forms import AdminSelfProfileForm, AdminUserCreationForm, AdminUserUpdateForm
from accounts.models import User
from accounts.services import admin_capability_required, admin_required, has_admin_capability
from books.models import Author, Book, BookCopy, Category, Publisher
from books.selectors import add_copies_to_book, find_duplicate_book_conflict
from circulations.models import Borrowing, Fine, FinePayment, Loan, Reservation
from circulations.services import (
    approve_reservation,
    borrow_book,
    can_member_borrow,
    cancel_reservation,
    complete_reservation,
    describe_fine_units,
    get_book_available_copies,
    reject_renewal_request,
    renew_borrowing,
    return_book,
)
from circulations.timing import calculate_fine_snapshot
from digital_library.models import DigitalLibrary
from logs.models import Log
from members.models import Member

from .branding import get_library_branding
from .forms import (
    AuthorForm,
    BookCopyForm,
    BookForm,
    CategoryForm,
    DigitalLibraryForm,
    LibraryBrandingForm,
    PublisherForm,
)
from emails.member_messages import message_type_from_notification, send_member_message
from .models import LibraryBranding
from notifications.models import Notification
from .notifications import notification_target_url

def _split_names(raw_value):
    values = [name.strip() for name in (raw_value or "").split("-") if name.strip()]
    return list(dict.fromkeys(values))


def _resolve_category(name):
    category = Category.objects.filter(Q(name__iexact=name) | Q(name_en__iexact=name)).first()
    if category:
        return category
    return Category.objects.create(name=name, name_en="")


def _title_from_filename(file_obj):
    filename = os.path.splitext(os.path.basename(file_obj.name or ""))[0]
    title = filename.replace("_", " ").replace("-", " ").strip()
    return title


def _extract_pdf_metadata(pdf_file):
    pages = None
    cover_content = None
    metadata_title = None

    try:
        from pypdf import PdfReader

        pdf_file.seek(0)
        reader = PdfReader(pdf_file)
        pages = len(reader.pages)
        title = getattr(getattr(reader, "metadata", None), "title", None)
        if title:
            metadata_title = str(title).strip()
    except Exception:
        try:
            from PyPDF2 import PdfReader

            pdf_file.seek(0)
            reader = PdfReader(pdf_file)
            pages = len(reader.pages)
            metadata = reader.metadata or {}
            title = metadata.get("/Title")
            if title:
                metadata_title = str(title).strip()
        except Exception:
            pages = None

    try:
        import fitz

        pdf_file.seek(0)
        data = pdf_file.read()
        document = fitz.open(stream=data, filetype="pdf")
        first_page = document.load_page(0)
        pix = first_page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
        cover_content = ContentFile(pix.tobytes("png"))
    except Exception:
        cover_content = None
    finally:
        pdf_file.seek(0)

    return pages, cover_content, metadata_title


def _books_dashboard_queryset():
    return (
        Book.objects.select_related("category", "created_by")
        .annotate(
            total_copies=Count("bookcopy", distinct=True),
            usable_copies=Count("bookcopy", filter=Q(bookcopy__status="new"), distinct=True),
            borrowed_copies=Count("bookcopy__borrowing", filter=Q(bookcopy__borrowing__return_date__isnull=True), distinct=True),
            approved_reservations=Count("reservation", filter=Q(reservation__status="approved"), distinct=True),
            has_digital=Count("digitallibrary", distinct=True),
        )
        .annotate(
            available_copies=ExpressionWrapper(
                F("usable_copies") - F("borrowed_copies") - F("approved_reservations"),
                output_field=IntegerField(),
            )
        )
        .order_by("-created_at")
    )


def _expire_reservation_requests():
    Reservation.objects.filter(
        status__in=["pending", "approved"],
        cancel_date__isnull=False,
        cancel_date__lt=timezone.now(),
    ).update(status="cancelled")


def _chunk_items(items, chunk_size):
    return [items[index : index + chunk_size] for index in range(0, len(items), chunk_size)]


def _format_overdue_duration(delay):
    total_seconds = int(delay.total_seconds())
    days, remaining = divmod(total_seconds, 86400)
    hours, remaining = divmod(remaining, 3600)
    minutes, _ = divmod(remaining, 60)

    parts = []
    if days:
        parts.append(f"{days} يوم")
    if hours:
        parts.append(f"{hours} ساعة")
    if minutes or not parts:
        parts.append(f"{minutes} دقيقة")
    return " و ".join(parts)


def _overdue_report_rows(queryset):
    rows = []
    now = timezone.now()
    for item in queryset:
        fine_snapshot = calculate_fine_snapshot(item.due_date, reference_time=now)
        rows.append(
            [
                item.id,
                item.member.name,
                item.book_copy.book.title,
                item.borrow_date,
                item.due_date,
                _format_overdue_duration(fine_snapshot["delay"]),
                fine_snapshot["amount"] if fine_snapshot["has_fine"] else "-",
            ]
        )
    return rows

def _find_member_for_reports(member_query, member_id):
    members_qs = Member.objects.all().order_by("name")
    selected_member = None
    matches = members_qs.none()

    if member_id:
        try:
            selected_member = members_qs.get(id=int(member_id))
        except (TypeError, ValueError, Member.DoesNotExist):
            selected_member = None

    if member_query:
        query_filter = (
            Q(name__icontains=member_query)
            | Q(membership_number__icontains=member_query)
            | Q(university_id__icontains=member_query)
        )
        if member_query.isdigit():
            query_filter |= Q(id=int(member_query))

        matches = members_qs.filter(query_filter)
        if not selected_member:
            if member_query.isdigit():
                selected_member = matches.filter(id=int(member_query)).first() or matches.first()
            else:
                selected_member = matches.first()

    return selected_member, matches[:8]


def _member_report_snapshot(member):
    now = timezone.now()
    unreturned_borrowings = Borrowing.objects.select_related("book_copy__book").filter(
        member=member,
        return_date__isnull=True,
    )
    overdue_borrowings = unreturned_borrowings.filter(due_date__lt=now)
    unpaid_fines = Fine.objects.select_related("borrowing__book_copy__book").filter(
        borrowing__member=member,
        paid=False,
    )
    unpaid_total = unpaid_fines.aggregate(total=Sum("amount")).get("total") or 0

    return {
        "unreturned_borrowings": unreturned_borrowings,
        "overdue_borrowings": overdue_borrowings,
        "unpaid_fines": unpaid_fines,
        "unreturned_count": unreturned_borrowings.count(),
        "overdue_count": overdue_borrowings.count(),
        "unpaid_fines_count": unpaid_fines.count(),
        "unpaid_fines_total": unpaid_total,
    }

@admin_required
def dashboard_home(request):
    context = {
        "total_books": Book.objects.count(),
        "total_members": Member.objects.count(),
        "active_borrows": Borrowing.objects.filter(return_date__isnull=True).count(),
        "active_reservations": Reservation.objects.filter(status="pending").count(),
        "overdue_borrows": Borrowing.objects.filter(return_date__isnull=True, due_date__lt=timezone.now()).count(),
        "recent_borrows": Borrowing.objects.select_related("book_copy__book", "member", "created_by").order_by("-borrow_date")[:8],
        "can_manage_books": has_admin_capability(request.user, "can_manage_books"),
        "can_manage_members": has_admin_capability(request.user, "can_manage_members"),
        "can_manage_categories": has_admin_capability(request.user, "can_manage_categories"),
        "can_manage_admins": has_admin_capability(request.user, "can_manage_admins") or request.user.created_admins.exists(),
        "can_manage_circulation": has_admin_capability(request.user, "can_manage_circulation"),
        "unpaid_fines": Fine.objects.filter(paid=False).count(),
    }
    return render(request, "dashboard/home.html", context)


@admin_capability_required("can_manage_books")
def dashboard_books_list(request):
    query = (request.GET.get("q") or "").strip()
    if query:
        from books.selectors import search_books
        books = list(search_books(query=query, search_scope="all"))
    else:
        books = list(_books_dashboard_queryset())

    for book in books:
        if not hasattr(book, "borrowed_copies") and hasattr(book, "active_borrowings"):
            book.borrowed_copies = book.active_borrowings

        available_copies = getattr(book, "available_copies", None)
        if available_copies is not None:
            book.usable_copies = max(available_copies, 0)

    return render(request, "dashboard/books/books_list.html", {"books": books, "query": query})


@admin_capability_required("can_manage_books")
def dashboard_confirm_physical_book(request, book_id):
    book = get_object_or_404(Book, id=book_id)
    if request.method == "POST":
        if not book.bookcopy_set.exists():
            BookCopy.objects.create(book=book, status="new")
            messages.success(request, "تم تأكيد إدراج الكتاب ضمن الكتب الورقية بإضافة أول نسخة.")
        else:
            messages.info(request, "الكتاب لديه نسخ بالفعل.")
    return redirect("dashboard_books_list")



@admin_capability_required("can_manage_books")
def dashboard_add_book(request):
    if request.method == "POST":
        form = BookForm(request.POST, request.FILES)
        if form.is_valid():
            conflict = find_duplicate_book_conflict(
                title=form.cleaned_data.get("title"),
                isbn=form.cleaned_data.get("isbn"),
            )
            duplicate_action = (form.cleaned_data.get("duplicate_action") or "").strip()
            matched_book_id = form.cleaned_data.get("matched_book_id")
            copies_to_add = form.cleaned_data.get("copies_count") or 1

            if conflict["type"] == "exact":
                matched_book = conflict["book"]
                if duplicate_action == "add_copy" and matched_book_id == matched_book.id:
                    add_copies_to_book(matched_book, copies_to_add)
                    messages.success(request, "الكتاب موجود مسبقاً، وتمت إضافة نسخة جديدة إليه.")
                    return redirect("dashboard_books_list")
                form.add_error(None, "تم العثور على كتاب مطابق بنفس ISBN. اختر إضافة نسخة من النافذة المنبثقة للمتابعة.")
            elif conflict["type"] == "similar":
                matched_book = conflict["book"]
                if duplicate_action == "add_copy" and matched_book_id == matched_book.id:
                    add_copies_to_book(matched_book, copies_to_add)
                    messages.success(request, "تم اعتماد الكتاب المشابه كعنوان موجود، وتمت إضافة نسخة جديدة.")
                    return redirect("dashboard_books_list")
                if duplicate_action == "create_new":
                    book = form.save(created_by=request.user)
                    messages.success(request, f"تمت إضافة الكتاب: {book.title}")
                    return redirect("dashboard_books_list")
                form.add_error(None, "تم العثور على كتاب مشابه. اختر من النافذة المنبثقة ما إذا كان نفس الكتاب أو كتاباً جديداً.")
            else:
                book = form.save(created_by=request.user)
                messages.success(request, f"تمت إضافة الكتاب: {book.title}")
                return redirect("dashboard_books_list")
    else:
        form = BookForm()

    return render(
        request,
        "dashboard/books/add_book.html",
        {
            "form": form,
            "title": "إضافة كتاب جديد",
            "submit_label": "حفظ الكتاب",
            "authors_options": Author.objects.order_by("name").values_list("name", flat=True),
            "categories_options": Category.objects.order_by("name").values_list("name", flat=True),
            "publishers_options": Publisher.objects.order_by("name").values_list("name", flat=True),
        },
    )


@admin_capability_required("can_manage_books")
def dashboard_edit_book(request, book_id):
    book = get_object_or_404(Book, id=book_id)
    if request.method == "POST":
        form = BookForm(request.POST, request.FILES, instance=book)
        if form.is_valid():
            form.save()
            messages.success(request, "تم تحديث بيانات الكتاب.")
            return redirect("dashboard_books_list")
    else:
        form = BookForm(instance=book)

    return render(
        request,
        "dashboard/books/edit_book.html",
        {
            "form": form,
            "book": book,
            "title": f"تعديل الكتاب: {book.title}",
            "submit_label": "حفظ التعديلات",
            "authors_options": Author.objects.order_by("name").values_list("name", flat=True),
            "categories_options": Category.objects.order_by("name").values_list("name", flat=True),
            "publishers_options": Publisher.objects.order_by("name").values_list("name", flat=True),
        },
    )


@admin_capability_required("can_manage_books")
def dashboard_book_copies(request, book_id):
    book = Book.objects.filter(id=book_id).first()
    if not book:
        messages.warning(request, "تم حذف الكتاب تلقائياً بعد حذف جميع نسخه المادية.")
        return redirect("dashboard_books_list")
    copy_query = (request.GET.get("q") or "").strip()

    if request.method == "POST":
        form = BookCopyForm(request.POST)
        if form.is_valid():
            copy = form.save(commit=False)
            if copy.copy_number and BookCopy.objects.filter(book=book, copy_number=copy.copy_number).exists():
                messages.error(request, f"رقم النسخة '{copy.copy_number}' موجود مسبقاً لهذا الكتاب.")
                form = BookCopyForm()
            else:
                copy.book = book
                # النسخة الجديدة تعتبر غير مطبوعة حتى تمر عبر صفحة الطباعة.
                copy.is_printed = False
                copy.save()
                messages.success(request, "تمت إضافة النسخة بنجاح.")
                return redirect("dashboard_book_copies", book_id=book.id)
    else:
        form = BookCopyForm()

    copies = book.bookcopy_set.all().order_by("-created_at", "-id")
    if copy_query:
        copies = copies.filter(Q(barcode__icontains=copy_query) | Q(copy_number__icontains=copy_query))

    paginator = Paginator(copies, 24)
    page_obj = paginator.get_page(request.GET.get("page"))

    active_borrowings_by_copy = {
        borrowing.book_copy_id: borrowing
        for borrowing in Borrowing.objects.select_related("member").filter(
            book_copy_id__in=[copy.id for copy in page_obj.object_list],
            return_date__isnull=True,
        )
    }
    for copy in page_obj.object_list:
        copy.current_borrowing = active_borrowings_by_copy.get(copy.id)

    return render(
        request,
        "dashboard/books/copies.html",
        {
            "book": book,
            "form": form,
            "copies": page_obj,
            "copy_query": copy_query,
        },
    )

@admin_capability_required("can_manage_books")
def dashboard_delete_book_copy(request, copy_id):
    if request.method == "POST":
        copy = get_object_or_404(BookCopy, id=copy_id)
        book_id = copy.book_id
        copy.delete()
        messages.success(request, "تم حذف النسخة بنجاح.")
        return redirect("dashboard_book_copies", book_id=book_id)
    return redirect("dashboard_books_list")


@admin_capability_required("can_manage_books")
def dashboard_copy_qr_print(request):
    book_id = request.GET.get("book") or request.POST.get("book")
    query = (request.GET.get("q") or request.POST.get("q") or "").strip()
    scope = request.GET.get("scope") or "unprinted"

    copies_queryset = BookCopy.objects.select_related("book").order_by("-created_at", "-id")
    selected_book = None
    if book_id:
        selected_book = get_object_or_404(Book, id=book_id)
        copies_queryset = copies_queryset.filter(book=selected_book)

    if query:
        copies_queryset = copies_queryset.filter(
            Q(barcode__icontains=query) | Q(copy_number__icontains=query) | Q(book__title__icontains=query)
        )

    if scope == "unprinted":
        copies_queryset = copies_queryset.filter(is_printed=False)

    if request.method == "POST":
        print_mode = request.POST.get("print_mode") or "selected"
        selected_ids = []
        for value in request.POST.getlist("copy_ids"):
            try:
                selected_ids.append(int(value))
            except (TypeError, ValueError):
                continue

        printable_queryset = BookCopy.objects.select_related("book").order_by("-created_at", "-id")
        if selected_book:
            printable_queryset = printable_queryset.filter(book=selected_book)

        if query:
            printable_queryset = printable_queryset.filter(
                Q(barcode__icontains=query) | Q(copy_number__icontains=query) | Q(book__title__icontains=query)
            )

        if print_mode == "selected":
            printable_queryset = printable_queryset.filter(id__in=selected_ids)
        elif print_mode == "unprinted":
            printable_queryset = printable_queryset.filter(is_printed=False)

        printable_copies = list(printable_queryset)
        if not printable_copies:
            messages.error(request, "لا توجد نسخ مطابقة للطباعة.")
            return redirect("dashboard_copy_qr_print")

        return render(
            request,
            "dashboard/books/qr_print_sheet.html",
            {
                "pages": _chunk_items(printable_copies, 18),
                "printed_copy_ids": [copy.id for copy in printable_copies],
                "selected_book": selected_book,
                "printed_at": timezone.now(),
            },
        )

    paginator = Paginator(copies_queryset, 24)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "dashboard/books/qr_print_select.html",
        {
            "copies": page_obj,
            "scope": scope,
            "query": query,
            "selected_book": selected_book,
        },
    )



@admin_capability_required("can_manage_books")
def dashboard_mark_copies_printed(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "message": "Invalid request"}, status=400)

    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "message": "Invalid payload"}, status=400)

    copy_ids = payload.get("copy_ids") or []
    clean_ids = []
    for value in copy_ids:
        try:
            clean_ids.append(int(value))
        except (TypeError, ValueError):
            continue

    if clean_ids:
        BookCopy.objects.filter(id__in=clean_ids).update(is_printed=True)

    return JsonResponse({"ok": True, "updated": len(clean_ids)})


@admin_capability_required("can_manage_books")
def dashboard_digital_list(request):
    digital_books = DigitalLibrary.objects.select_related("book").order_by("book__title")
    return render(request, "dashboard/digital/list.html", {"digital_books": digital_books})



@admin_capability_required("can_manage_books")
def dashboard_digital_add(request):
    if request.method == "POST":
        form = DigitalLibraryForm(request.POST, request.FILES)
        if form.is_valid():
            create_new_book = form.cleaned_data.get("create_new_book")

            if create_new_book:
                pdf_file = form.cleaned_data.get("pdf_file")
                detected_pages = None
                extracted_cover = None
                metadata_title = None
                if pdf_file:
                    detected_pages, extracted_cover, metadata_title = _extract_pdf_metadata(pdf_file)

                typed_title = (form.cleaned_data.get("new_title") or "").strip()
                inferred_title = typed_title or metadata_title or (_title_from_filename(pdf_file) if pdf_file else "") or "مورد رقمي"
                pages_value = form.cleaned_data.get("new_pages") or detected_pages
                category = _resolve_category(form.cleaned_data["new_category_name"].strip())
                publisher, _ = Publisher.objects.get_or_create(name=form.cleaned_data["new_publisher_name"].strip())

                book = Book.objects.create(
                    title=inferred_title,
                    isbn=form.cleaned_data.get("new_isbn") or "",
                    doi=form.cleaned_data.get("new_doi") or "",
                    dewey_decimal_number=form.cleaned_data["new_dewey_decimal_number"].strip(),
                    category=category,
                    publisher=publisher,
                    publication_year=form.cleaned_data.get("new_publication_year"),
                    language=form.cleaned_data.get("new_language") or "arabic",
                    pages=pages_value,
                    description=form.cleaned_data.get("new_description") or "",
                    created_by=request.user,
                )

                authors = []
                for author_name in _split_names(form.cleaned_data.get("new_author_names")):
                    author, _ = Author.objects.get_or_create(name=author_name)
                    authors.append(author)
                book.authors.set(authors)

                uploaded_cover = form.cleaned_data.get("new_cover_image")
                if uploaded_cover:
                    book.cover_image = uploaded_cover
                    book.save(update_fields=["cover_image"])
                elif extracted_cover:
                    filename = f"{slugify(book.title) or 'book'}-cover.png"
                    book.cover_image.save(filename, extracted_cover, save=True)

                digital_book = form.save(commit=False)
                digital_book.book = book
                digital_book.save()
            else:
                selected_book = form.cleaned_data["book"]
                pdf_file = form.cleaned_data.get("pdf_file")
                detected_pages = None
                extracted_cover = None
                metadata_title = None
                if pdf_file:
                    detected_pages, extracted_cover, metadata_title = _extract_pdf_metadata(pdf_file)

                update_fields = []
                if metadata_title and not selected_book.title:
                    selected_book.title = metadata_title
                    update_fields.append("title")
                elif pdf_file and not selected_book.title:
                    selected_book.title = _title_from_filename(pdf_file) or selected_book.title
                    update_fields.append("title")

                if detected_pages and not selected_book.pages:
                    selected_book.pages = detected_pages
                    update_fields.append("pages")

                if update_fields:
                    selected_book.save(update_fields=update_fields)

                if extracted_cover and not selected_book.cover_image:
                    filename = f"{slugify(selected_book.title) or 'book'}-cover.png"
                    selected_book.cover_image.save(filename, extracted_cover, save=True)

                form.save()

            messages.success(request, "تمت إضافة المورد الرقمي.")
            return redirect("dashboard_digital_list")
    else:
        form = DigitalLibraryForm()

    return render(
        request,
        "dashboard/digital/form.html",
        {
            "form": form,
            "title": "إضافة مورد رقمي",
            "submit_label": "حفظ",
            "authors_options": Author.objects.order_by("name").values_list("name", flat=True),
            "categories_options": Category.objects.order_by("name").values_list("name", flat=True),
            "publishers_options": Publisher.objects.order_by("name").values_list("name", flat=True),
        },
    )


@admin_capability_required("can_manage_books")
def dashboard_digital_edit(request, digital_id):
    digital_book = get_object_or_404(DigitalLibrary, id=digital_id)
    if request.method == "POST":
        form = DigitalLibraryForm(request.POST, request.FILES, instance=digital_book)
        if form.is_valid():
            if form.cleaned_data.get("book"):
                form.save()
                messages.success(request, "تم تحديث بيانات المورد الرقمي.")
                return redirect("dashboard_digital_list")
            messages.error(request, "في التعديل اختر كتابًا موجودًا مرتبطًا بالمورد الرقمي.")
    else:
        form = DigitalLibraryForm(instance=digital_book)

    return render(
        request,
        "dashboard/digital/form.html",
        {
            "form": form,
            "title": f"تعديل مورد رقمي: {digital_book.book.title}",
            "submit_label": "حفظ التعديلات",
            "digital_book": digital_book,
            "authors_options": Author.objects.order_by("name").values_list("name", flat=True),
            "categories_options": Category.objects.order_by("name").values_list("name", flat=True),
            "publishers_options": Publisher.objects.order_by("name").values_list("name", flat=True),
        },
    )


@admin_capability_required("can_manage_categories")
def dashboard_categories(request):
    category_form = CategoryForm(prefix="category")
    author_form = AuthorForm(prefix="author")
    publisher_form = PublisherForm(prefix="publisher")

    if request.method == "POST":
        form_type = request.POST.get("form_type")

        if form_type == "category":
            category_form = CategoryForm(request.POST, prefix="category")
            if category_form.is_valid():
                category = category_form.save()
                messages.success(request, f"تمت إضافة الفئة: {category.name}")
                return redirect("dashboard_categories")

        elif form_type == "author":
            author_form = AuthorForm(request.POST, prefix="author")
            if author_form.is_valid():
                author = author_form.save()
                messages.success(request, f"تمت إضافة المؤلف: {author.name}")
                return redirect("dashboard_categories")

        elif form_type == "publisher":
            publisher_form = PublisherForm(request.POST, prefix="publisher")
            if publisher_form.is_valid():
                publisher = publisher_form.save()
                messages.success(request, f"تمت إضافة الناشر: {publisher.name}")
                return redirect("dashboard_categories")

    categories = Category.objects.order_by("name")
    authors = Author.objects.order_by("name")
    publishers = Publisher.objects.order_by("name")

    return render(
        request,
        "dashboard/categories.html",
        {
            "category_form": category_form,
            "author_form": author_form,
            "publisher_form": publisher_form,
            "categories": categories,
            "authors": authors,
            "publishers": publishers,
        },
    )


@admin_capability_required("can_manage_categories")
def dashboard_update_entity(request, entity_type, entity_id):
    if request.method != "POST":
        return redirect("dashboard_categories")

    entity_config = {
        "category": (Category, ["name", "name_en", "shelf_location"]),
        "author": (Author, ["name"]),
        "publisher": (Publisher, ["name", "city", "country"]),
    }

    if entity_type not in entity_config:
        messages.error(request, "نوع الكيان غير مدعوم.")
        return redirect("dashboard_categories")

    model_class, fields = entity_config[entity_type]
    obj = get_object_or_404(model_class, id=entity_id)

    for field_name in fields:
        if field_name in request.POST:
            value = request.POST.get(field_name)
            if isinstance(value, str):
                value = value.strip()
            setattr(obj, field_name, value)

    if entity_type == "category" and not obj.name:
        messages.error(request, "اسم الفئة لا يمكن أن يكون فارغًا.")
        return redirect("dashboard_categories")
    if entity_type in {"author", "publisher"} and not obj.name:
        messages.error(request, "الاسم لا يمكن أن يكون فارغًا.")
        return redirect("dashboard_categories")

    obj.save()
    messages.success(request, "تم التحديث بنجاح.")
    return redirect("dashboard_categories")


@admin_capability_required("can_manage_categories")
def dashboard_delete_entity(request, entity_type, entity_id):
    if request.method != "POST":
        return redirect("dashboard_categories")

    entity_config = {
        "category": Category,
        "author": Author,
        "publisher": Publisher,
    }
    model_class = entity_config.get(entity_type)
    if not model_class:
        messages.error(request, "نوع الكيان غير مدعوم.")
        return redirect("dashboard_categories")

    obj = get_object_or_404(model_class, id=entity_id)
    obj_name = getattr(obj, "name", str(obj))
    obj.delete()
    messages.success(request, f"تم حذف: {obj_name}")
    return redirect("dashboard_categories")

def _build_manual_borrow_preview(membership_number, copy_barcode):
    if not membership_number:
        raise ValueError("رقم العضوية مطلوب.")
    if not copy_barcode:
        raise ValueError("رقم نسخة الكتاب مطلوب.")

    member = Member.objects.get(membership_number=membership_number)
    copy = BookCopy.objects.select_related("book").get(barcode=copy_barcode)
    active_copy_borrowing = (
        Borrowing.objects.select_related("member")
        .filter(book_copy=copy, return_date__isnull=True)
        .order_by("-borrow_date")
        .first()
    )
    active_member_borrows = Borrowing.objects.filter(member=member, return_date__isnull=True).count()
    member_has_limit = can_member_borrow(member)
    member_has_approved_reservation = Reservation.objects.filter(
        member=member,
        book=copy.book,
        status="approved",
    ).exists()
    supply_allows_borrow = member_has_approved_reservation or get_book_available_copies(copy.book) > 0

    preview = {
        "member": member,
        "copy": copy,
        "book": copy.book,
        "active_member_borrows": active_member_borrows,
        "status_label": "متاحة",
        "status_tone": "emerald",
        "status_message": "النسخة جاهزة للاستعارة.",
        "can_confirm": True,
    }

    # نعرض حالة العضو والنسخة قبل التأكيد دون تغيير شروط الاستعارة الفعلية.
    if member.is_suspended:
        preview.update(
            {
                "status_label": "العضوية موقوفة",
                "status_tone": "rose",
                "status_message": "هذا العضو موقوف عن الاستعارة ويجب معالجة سبب الإيقاف أولاً.",
                "can_confirm": False,
            }
        )
    elif copy.status != "new":
        preview.update(
            {
                "status_label": "غير متاحة",
                "status_tone": "amber",
                "status_message": "حالة النسخة الحالية لا تسمح بالاستعارة.",
                "can_confirm": False,
            }
        )
    elif active_copy_borrowing:
        preview.update(
            {
                "status_label": "مستعارة",
                "status_tone": "rose",
                "status_message": f"النسخة معارة حاليًا للعضو {active_copy_borrowing.member.name}.",
                "can_confirm": False,
            }
        )
    elif not member_has_limit:
        preview.update(
            {
                "status_label": "الحد الأقصى مكتمل",
                "status_tone": "amber",
                "status_message": "العضو بلغ الحد الأعلى للاستعارات النشطة.",
                "can_confirm": False,
            }
        )
    elif not supply_allows_borrow:
        preview.update(
            {
                "status_label": "محجوزة",
                "status_tone": "amber",
                "status_message": "لا توجد إتاحة حالية بسبب الحجوزات المعتمدة على هذا الكتاب.",
                "can_confirm": False,
            }
        )

    return preview


def _circulation_context(manual_preview=None, manual_form=None):
    _expire_reservation_requests()
    pending_reservations = Reservation.objects.select_related("book", "member").filter(status="pending").order_by(
        "reservation_date"
    )
    approved_reservations = Reservation.objects.select_related("book", "member").filter(status="approved").order_by(
        "reservation_date"
    )
    active_borrowings = Borrowing.objects.select_related("book_copy__book", "member", "created_by").filter(
        return_date__isnull=True
    ).order_by("due_date")

    # مجموعة معرفات الكتب التي عليها حجوزات معتمدة الآن (تمنع التجديد)
    approved_reserved_book_ids = set(
        Reservation.objects.filter(status="approved").values_list("book_id", flat=True)
    )

    return {
        "pending_reservations": pending_reservations,
        "approved_reservations": approved_reservations,
        "active_borrowings": active_borrowings,
        "renewal_requests": active_borrowings.filter(renewal_requested=True),
        "approved_reserved_book_ids": approved_reserved_book_ids,
        "manual_preview": manual_preview,
        "manual_form": manual_form or {"membership_number": "", "copy_barcode": ""},
    }


@admin_capability_required("can_manage_circulation")
def dashboard_circulation(request):
    return render(request, "dashboard/circulation.html", _circulation_context())


@admin_capability_required("can_manage_circulation")
def dashboard_manual_borrow(request):
    if request.method != "POST":
        return redirect("dashboard_circulation")

    membership_number = (request.POST.get("membership_number") or "").strip()
    copy_barcode = (request.POST.get("copy_barcode") or "").strip()
    manual_form = {
        "membership_number": membership_number,
        "copy_barcode": copy_barcode,
    }

    try:
        preview = _build_manual_borrow_preview(membership_number, copy_barcode)
        if request.POST.get("confirm_borrow") == "1":
            borrowing = borrow_book(preview["member"], preview["book"], request.user, preferred_copy=preview["copy"])
            messages.success(
                request,
                f"تم تسجيل الاستعارة بنجاح للعضو {borrowing.member.name} على النسخة {borrowing.book_copy.barcode}.",
            )
            return redirect("dashboard_circulation")

        return render(
            request,
            "dashboard/circulation.html",
            _circulation_context(manual_preview=preview, manual_form=manual_form),
        )
    except Member.DoesNotExist:
        messages.error(request, "رقم العضوية غير صحيح.")
    except BookCopy.DoesNotExist:
        messages.error(request, "رقم النسخة غير صحيح.")
    except ValueError as exc:
        messages.error(request, str(exc))

    return render(request, "dashboard/circulation.html", _circulation_context(manual_form=manual_form))


@admin_capability_required("can_manage_circulation")
def dashboard_approve_reservation(request, reservation_id):
    reservation = get_object_or_404(Reservation.objects.select_related("book", "member"), id=reservation_id)
    if request.method == "POST":
        try:
            approve_reservation(reservation)
            messages.success(request, "تم اعتماد طلب الحجز.")
        except ValueError as exc:
            messages.error(request, str(exc))
    return redirect("dashboard_circulation")


@admin_capability_required("can_manage_circulation")
def dashboard_complete_reservation(request, reservation_id):
    reservation = get_object_or_404(Reservation.objects.select_related("book", "member"), id=reservation_id)
    if request.method == "POST":
        try:
            complete_reservation(reservation, employee=request.user)
            messages.success(request, "تم إتمام الاستعارة من الحجز.")
        except ValueError as exc:
            messages.error(request, str(exc))
    return redirect("dashboard_circulation")


@admin_capability_required("can_manage_circulation")
def dashboard_cancel_reservation(request, reservation_id):
    reservation = get_object_or_404(Reservation, id=reservation_id)
    if request.method == "POST":
        try:
            cancel_reservation(reservation)
            messages.success(request, "تم إلغاء طلب الحجز.")
        except ValueError as exc:
            messages.error(request, str(exc))
    return redirect("dashboard_circulation")


@admin_capability_required("can_manage_circulation")
def dashboard_return_borrowing(request, borrowing_id):
    borrowing = get_object_or_404(Borrowing.objects.select_related("book_copy__book", "member"), id=borrowing_id)
    if request.method == "POST":
        try:
            fine = return_book(borrowing)
            if fine:
                messages.success(
                    request,
                    f"تم تسجيل الإرجاع. تم احتساب غرامة {fine.amount} ({describe_fine_units(fine.days_late)} تأخير).",
                )
            else:
                messages.success(request, "تم تسجيل إرجاع الكتاب.")
        except ValueError as exc:
            messages.error(request, str(exc))
    return redirect("dashboard_circulation")

@admin_capability_required("can_manage_circulation")
def dashboard_approve_renewal(request, borrowing_id):
    borrowing = get_object_or_404(Borrowing, id=borrowing_id)
    if request.method == "POST":
        try:
            renew_borrowing(borrowing)
            messages.success(request, "تمت الموافقة على طلب التجديد.")
        except ValueError as exc:
            messages.error(request, str(exc))
    return redirect("dashboard_circulation")


@admin_capability_required("can_manage_circulation")
def dashboard_direct_renew(request, borrowing_id):
    """تجديد مباشر من قبل الإداري من قائمة الاستعارات النشطة"""
    borrowing = get_object_or_404(Borrowing, id=borrowing_id)
    if request.method == "POST":
        try:
            renew_borrowing(borrowing)
            messages.success(request, f"تم تجديد استعارة {borrowing.member.name} بنجاح.")
        except ValueError as exc:
            messages.error(request, str(exc))
    return redirect("dashboard_circulation")


@admin_capability_required("can_manage_circulation")
def dashboard_reject_renewal(request, borrowing_id):
    borrowing = get_object_or_404(Borrowing, id=borrowing_id)
    if request.method == "POST":
        try:
            reject_renewal_request(borrowing)
            messages.success(request, "تم رفض طلب التجديد.")
        except ValueError as exc:
            messages.error(request, str(exc))
    return redirect("dashboard_circulation")


@admin_required
def dashboard_reports(request):
    table = request.GET.get("table", "books")
    paid_status = request.GET.get("paid_status", "all")
    member_query = (request.GET.get("member_query") or "").strip()
    member_id = (request.GET.get("member_id") or "").strip()

    selected_member, member_matches = _find_member_for_reports(member_query, member_id)
    member_snapshot = _member_report_snapshot(selected_member) if selected_member else None
    books_report_queryset = Book.objects.select_related("category", "publisher", "created_by").prefetch_related("authors").annotate(
        borrowings_total=Count("bookcopy__borrowing", distinct=True),
        reservations_total=Count("reservation", distinct=True),
    )
    borrowings_report_queryset = Borrowing.objects.select_related("book_copy__book", "member", "employee", "created_by").annotate(
        book_borrowings_total=Count("book_copy__book__bookcopy__borrowing", distinct=True),
        book_reservations_total=Count("book_copy__book__reservation", distinct=True),
    )
    report_tables = {
        "books": {
            "label": "الكتب",
            "queryset": books_report_queryset,
            "sort_options": [
                ("title", "العنوان (أ-ي)"),
                ("-title", "العنوان (ي-أ)"),
                ("created_at", "تاريخ الإدراج (أقدم)"),
                ("-created_at", "تاريخ الإدراج (أحدث)"),
                ("view_count", "الأقل مشاهدة"),
                ("-view_count", "الأكثر مشاهدة"),
                ("-reservations_total", "\u0627\u0644\u0623\u0643\u062b\u0631 \u0637\u0644\u0628\u064b\u0627"),
                ("-borrowings_total", "\u0627\u0644\u0623\u0643\u062b\u0631 \u0627\u0633\u062a\u0639\u0627\u0631\u0629"),
            ],
            "headers": ["ID", "العنوان", "المؤلفون", "الفئة", "الناشر", "أضيف بواسطة", "السنة", "اللغة", "الصفحات"],
            "rows": lambda q: [
                [
                    item.id,
                    item.title,
                    " - ".join(item.authors.values_list("name", flat=True)) or "-",
                    item.category.name if item.category else "-",
                    item.publisher.name if item.publisher else "-",
                    item.created_by.username if item.created_by else "-",
                    item.publication_year or "-",
                    item.get_language_display(),
                    item.pages or "-",
                ]
                for item in q
            ],
        },
        "members": {
            "label": "الأعضاء",
            "queryset": Member.objects.all(),
            "sort_options": [
                ("name", "الاسم (أ-ي)"),
                ("-name", "الاسم (ي-أ)"),
                ("membership_expiry", "انتهاء العضوية (الأقرب)"),
                ("-membership_expiry", "انتهاء العضوية (الأبعد)"),
                ("created_at", "الأقدم إضافة"),
                ("-created_at", "الأحدث إضافة"),
            ],
            "headers": ["ID", "الاسم", "رقم العضوية", "النوع", "رقم القيد", "التخصص", "المستوى", "جهة العمل", "انتهاء العضوية"],
            "rows": lambda q: [
                [
                    item.id,
                    item.name,
                    item.membership_number,
                    item.get_member_type_display(),
                    item.university_id or "-",
                    item.major or "-",
                    item.get_level_display() if item.level else "-",
                    item.workplace or "-",
                    item.membership_expiry,
                ]
                for item in q
            ],
        },
        "borrowings": {
            "label": "الاستعارات",
            "queryset": borrowings_report_queryset,
            "sort_options": [
                ("borrow_date", "تاريخ الاستعارة (الأقدم)"),
                ("-borrow_date", "تاريخ الاستعارة (الأحدث)"),
                ("due_date", "تاريخ الاستحقاق (الأقرب)"),
                ("-due_date", "تاريخ الاستحقاق (الأبعد)"),
                ("-book_reservations_total", "\u0627\u0644\u0623\u0643\u062b\u0631 \u0637\u0644\u0628\u064b\u0627"),
                ("-book_borrowings_total", "\u0627\u0644\u0623\u0643\u062b\u0631 \u0627\u0633\u062a\u0639\u0627\u0631\u0629"),
            ],
            "headers": ["ID", "الكتاب", "النسخة", "العضو", "الموظف", "أُنشئت بواسطة", "الاستعارة", "الاستحقاق", "الإرجاع", "طلب تجديد"],
            "rows": lambda q: [
                [
                    item.id,
                    item.book_copy.book.title,
                    item.book_copy.barcode,
                    item.member.name,
                    item.employee.username if item.employee else "-",
                    item.created_by.username if item.created_by else "-",
                    item.borrow_date,
                    item.due_date,
                    item.return_date or "-",
                    "نعم" if item.renewal_requested else "لا",
                ]
                for item in q
            ],
        },
        "overdue": {
            "label": "المتأخرات",
            "queryset": Borrowing.objects.select_related("book_copy__book", "member").filter(return_date__isnull=True, due_date__lt=timezone.now()),
            "sort_options": [
                ("due_date", "الأقرب استحقاقًا"),
                ("-due_date", "الأحدث استحقاقًا"),
                ("borrow_date", "أقدم استعارة"),
                ("-borrow_date", "أحدث استعارة"),

            ],
            "headers": ["ID", "العضو", "الكتاب", "تاريخ الاستعارة", "تاريخ الانتهاء", "مدة التأخير", "الغرامة"],
            "rows": _overdue_report_rows,
        },
        "reservations": {
            "label": "الحجوزات",
            "queryset": Reservation.objects.select_related("book", "member", "related_borrow"),
            "sort_options": [
                ("reservation_date", "تاريخ الطلب (الأقدم)"),
                ("-reservation_date", "تاريخ الطلب (الأحدث)"),
                ("status", "الحالة (تصاعدي)"),
                ("-status", "الحالة (تنازلي)"),
            ],
            "headers": ["ID", "الكتاب", "العضو", "الحالة", "تاريخ الطلب", "ينتهي", "إعارة مرتبطة"],
            "rows": lambda q: [
                [
                    item.id,
                    item.book.title,
                    item.member.name,
                    item.get_status_display(),
                    item.reservation_date,
                    item.cancel_date or "-",
                    item.related_borrow_id or "-",
                ]
                for item in q
            ],
        },
        "copies": {
            "label": "نسخ الكتب",
            "queryset": BookCopy.objects.select_related("book"),
            "sort_options": [
                ("book__title", "عنوان الكتاب (أ-ي)"),
                ("-book__title", "عنوان الكتاب (ي-أ)"),
                ("copy_number", "رقم النسخة (تصاعدي)"),
                ("-copy_number", "رقم النسخة (تنازلي)"),
                ("status", "حالة النسخة"),
            ],
            "headers": ["ID", "الكتاب", "رقم النسخة", "رمز QR", "حالة النسخة"],
            "rows": lambda q: [[item.id, item.book.title, item.copy_number or "-", item.barcode, item.get_status_display()] for item in q],
        },
        "digital": {
            "label": "الكتب الرقمية",
            "queryset": DigitalLibrary.objects.select_related("book"),
            "sort_options": [
                ("book__title", "عنوان الكتاب (أ-ي)"),
                ("-book__title", "عنوان الكتاب (ي-أ)"),
                ("id", "الأقدم"),
                ("-id", "الأحدث"),
            ],
            "headers": ["ID", "الكتاب", "رقم ديوي", "الفئة", "رابط الملف"],
            "rows": lambda q: [
                [
                    item.id,
                    item.book.title,
                    item.book.dewey_decimal_number,
                    item.book.category.name if item.book.category else "-",
                    item.pdf_file.url if item.pdf_file else "-",
                ]
                for item in q
            ],
        },
        "fines": {
            "label": "الغرامات",
            "queryset": Fine.objects.select_related("borrowing__member", "borrowing__book_copy__book", "payment__created_by"),
            "sort_options": [
                ("created_at", "الأقدم"),
                ("-created_at", "الأحدث"),
                ("amount", "المبلغ (تصاعدي)"),
                ("-amount", "المبلغ (تنازلي)"),
            ],
            "headers": ["ID", "العضو", "الكتاب", "أيام التأخير", "المبلغ", "الحالة", "تم الدفع بواسطة", "تاريخ الإنشاء"],
            "rows": lambda q: [
                [
                    item.id,
                    item.borrowing.member.name,
                    item.borrowing.book_copy.book.title,
                    item.days_late,
                    item.amount,
                    "paid" if item.paid else "unpaid",
                    item.payment.created_by.username if hasattr(item, "payment") and item.payment and item.payment.created_by else "-",
                    item.created_at,
                ]
                for item in q
            ],
        },
    }

    if table not in report_tables:
        table = "books"

    config = report_tables[table]
    sort = request.GET.get("sort") or config["sort_options"][0][0]
    allowed_sort_values = [option[0] for option in config["sort_options"]]
    if sort not in allowed_sort_values:
        sort = config["sort_options"][0][0]

    queryset = config["queryset"]
    if table == "fines":
        if paid_status == "paid":
            queryset = queryset.filter(paid=True)
        elif paid_status == "unpaid":
            queryset = queryset.filter(paid=False)
        else:
            paid_status = "all"

    queryset = queryset.order_by(sort)
    rows = config["rows"](queryset[:500])

    return render(
        request,
        "dashboard/reports.html",
        {
            "report_tables": report_tables,
            "active_table": table,
            "active_label": config["label"],
            "headers": config["headers"],
            "rows": rows,
            "sort": sort,
            "sort_options": config["sort_options"],
            "paid_status": paid_status,
            "member_query": member_query,
            "member_matches": member_matches,
            "selected_member": selected_member,
            "member_snapshot": member_snapshot,
            "message_types": [
                ("overdue", "تذكير بالاستعارات المتأخرة"),
                ("reservation_approved", "إشعار اعتماد الحجز"),
                ("book_available", "إشعار توفر كتاب"),
                ("pending_fines", "تنبيه الغرامات"),
                ("suspension_warning", "تحذير قبل إيقاف العضوية"),
            ],
        },
    )


@admin_capability_required("can_manage_circulation")
def dashboard_update_fine_payment(request, fine_id):
    fine = get_object_or_404(Fine, id=fine_id)
    next_url = request.POST.get("next") or reverse("dashboard_reports")

    if request.method == "POST":
        is_paid = request.POST.get("paid_status") == "paid"
        fine.paid = is_paid
        fine.save(update_fields=["paid"])

        if is_paid:
            FinePayment.objects.update_or_create(
                fine=fine,
                defaults={"created_by": request.user},
            )
        else:
            FinePayment.objects.filter(fine=fine).delete()

        messages.success(request, "تم تحديث حالة دفع الغرامة.")

    return redirect(next_url)

@admin_required
def dashboard_send_member_message(request, member_id):
    member = get_object_or_404(Member, id=member_id)
    next_url = request.POST.get("next") or reverse("dashboard_reports")

    if request.method == "POST":
        message_type = (request.POST.get("message_type") or "general").strip()
        result = send_member_message(member=member, message_type=message_type, sent_by=request.user)

        if result["email_sent"] or result["sms_prepared"]:
            messages.success(request, "تم إرسال التذكير للعضو بنجاح.")
        else:
            messages.error(request, "تعذر إرسال البريد/تجهيز الرسالة. تأكد من إعدادات الإرسال والبيانات.")

    return redirect(next_url)


@admin_required
def dashboard_send_notification_message(request, notification_id):
    notification = get_object_or_404(
        Notification.objects.select_related("member", "borrowing__member", "reservation__member"),
        id=notification_id,
    )
    next_url = request.POST.get("next") or reverse("dashboard_home")

    if request.method == "POST":
        member = notification.member or (notification.borrowing.member if notification.borrowing_id else None) or (
            notification.reservation.member if notification.reservation_id else None
        )
        if not member:
            messages.error(request, "تعذر تحديد عضو مرتبط بهذا الإشعار.")
            return redirect(next_url)

        result = send_member_message(
            member=member,
            message_type=message_type_from_notification(notification),
            sent_by=request.user,
            notification=notification,
        )
        if result["email_sent"] or result["sms_prepared"]:
            messages.success(request, "تم إرسال رسالة مرتبطة بالإشعار.")
        else:
            messages.error(request, "تعذر إرسال رسالة مرتبطة بالإشعار.")

    return redirect(next_url)


@admin_required
def dashboard_open_notification(request, notification_id):
    notification = get_object_or_404(
        Notification.objects.select_related("member", "borrowing", "reservation"),
        id=notification_id,
    )
    if not notification.is_read:
        notification.is_read = True
        notification.save(update_fields=["is_read"])

    return redirect(notification_target_url(notification, request.user))

def _admin_manager_required(request):
    if not request.user.is_authenticated:
        raise PermissionDenied("ليس لديك صلاحية لإدارة حسابات المشرفين.")
    if request.user.is_superuser or getattr(request.user, "can_manage_admins", False):
        return
    if request.user.created_admins.filter(is_staff=True, is_superuser=False).exists():
        return
    raise PermissionDenied("ليس لديك صلاحية لإدارة حسابات المشرفين.")


def _managed_admins_queryset(actor):
    queryset = User.objects.filter(is_staff=True, is_superuser=False).select_related("created_by").order_by("-id")
    if actor.is_superuser:
        return queryset
    return queryset.filter(created_by=actor)


def _get_managed_admin(request, admin_id):
    return get_object_or_404(_managed_admins_queryset(request.user), id=admin_id)


def _delete_admin_related_data(admin_user):
    # حذف العلاقات المباشرة المرتبطة بالحساب قبل الحذف النهائي لتفادي بيانات يتيمة.
    Log.objects.filter(user=admin_user).delete()
    Loan.objects.filter(user=admin_user).delete()
    Borrowing.objects.filter(employee=admin_user).delete()


def _apply_input_css(form):
    for field in form.fields.values():
        field.widget.attrs.update({"class": "input-field"})


@admin_required
def dashboard_admin_users(request):
    _admin_manager_required(request)

    if request.method == "POST":
        form = AdminUserCreationForm(request.POST, allow_admin_management=request.user.is_superuser)
        if form.is_valid():
            new_admin = form.save(commit=False)
            new_admin.created_by = request.user
            new_admin.save()
            messages.success(request, "تم إنشاء حساب المشرف وتعيين كلمة المرور بنجاح.")
            return redirect("dashboard_supervisor_users")
    else:
        form = AdminUserCreationForm(initial={"is_active": True}, allow_admin_management=request.user.is_superuser)

    admins = _managed_admins_queryset(request.user)
    return render(
        request,
        "dashboard/admin_users.html",
        {
            "form": form,
            "admins": admins,
            "can_manage_all_admins": request.user.is_superuser,
        },
    )


@admin_required
def dashboard_admin_edit(request, admin_id):
    _admin_manager_required(request)
    admin_user = _get_managed_admin(request, admin_id)

    if request.method == "POST":
        form = AdminUserUpdateForm(request.POST, instance=admin_user, allow_admin_management=request.user.is_superuser)
        if form.is_valid():
            form.save()
            messages.success(request, "تم تحديث بيانات المشرف.")
            return redirect("dashboard_supervisor_users")
    else:
        form = AdminUserUpdateForm(instance=admin_user, allow_admin_management=request.user.is_superuser)

    return render(
        request,
        "dashboard/admin_user_edit.html",
        {
            "form": form,
            "admin_user": admin_user,
            "can_manage_all_admins": request.user.is_superuser,
        },
    )


@admin_required
def dashboard_admin_toggle_active(request, admin_id):
    _admin_manager_required(request)
    admin_user = _get_managed_admin(request, admin_id)

    if request.method == "POST":
        admin_user.is_active = not admin_user.is_active
        admin_user.save(update_fields=["is_active"])
        messages.success(request, "تم تحديث حالة حساب المشرف.")

    return redirect("dashboard_supervisor_users")


@admin_required
def dashboard_admin_delete(request, admin_id):
    _admin_manager_required(request)
    admin_user = _get_managed_admin(request, admin_id)

    if request.method == "POST":
        if admin_user == request.user:
            messages.error(request, "لا يمكنك حذف حسابك من هذه الصفحة.")
            return redirect("dashboard_supervisor_users")

        username = admin_user.username
        _delete_admin_related_data(admin_user)
        admin_user.delete()
        messages.success(request, f"تم حذف حساب المشرف وكل البيانات المرتبطة به: {username}")

    return redirect("dashboard_supervisor_users")


@admin_required
def dashboard_admin_reset_password(request, admin_id):
    _admin_manager_required(request)
    admin_user = _get_managed_admin(request, admin_id)

    form = SetPasswordForm(user=admin_user)
    _apply_input_css(form)
    if request.method == "POST":
        form = SetPasswordForm(user=admin_user, data=request.POST)
        _apply_input_css(form)
        if form.is_valid():
            form.save()
            messages.success(request, "تم تعيين كلمة المرور الجديدة بنجاح.")
            return redirect("dashboard_supervisor_users")

    return render(
        request,
        "dashboard/admin_reset_password.html",
        {
            "form": form,
            "admin_user": admin_user,
        },
    )


@admin_required
def dashboard_my_account(request):
    profile_form = AdminSelfProfileForm(instance=request.user, prefix="profile")
    password_form = PasswordChangeForm(user=request.user, prefix="password")
    _apply_input_css(password_form)

    branding_instance = get_library_branding()
    branding_form = None
    if request.user.is_superuser:
        branding_form = LibraryBrandingForm(instance=branding_instance, prefix="branding")

    if request.method == "POST":
        if "save_profile" in request.POST:
            profile_form = AdminSelfProfileForm(request.POST, instance=request.user, prefix="profile")
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, "تم تحديث بيانات الحساب.")
                return redirect("dashboard_my_account")

        if "change_password" in request.POST:
            password_form = PasswordChangeForm(user=request.user, data=request.POST, prefix="password")
            _apply_input_css(password_form)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, "تم تغيير كلمة المرور بنجاح.")
                return redirect("dashboard_my_account")

        if request.user.is_superuser and "save_branding" in request.POST:
            branding_db_obj = LibraryBranding.objects.order_by("id").first() or LibraryBranding()
            branding_form = LibraryBrandingForm(
                request.POST,
                request.FILES,
                instance=branding_db_obj,
                prefix="branding",
            )
            if branding_form.is_valid():
                branding_form.save()
                messages.success(request, "تم تحديث بيانات هوية المكتبة.")
                return redirect("dashboard_my_account")

    capability_labels = []
    if request.user.is_superuser:
        capability_labels.append("Superuser")
    elif request.user.can_manage_admins:
        capability_labels.append("إدارة المشرفين")
    if request.user.can_manage_books:
        capability_labels.append("الكتب")
    if request.user.can_manage_members:
        capability_labels.append("الأعضاء")
    if request.user.can_manage_circulation:
        capability_labels.append("الاستعارات")
    if request.user.can_manage_categories:
        capability_labels.append("الفئات")

    managed_admins_count = _managed_admins_queryset(request.user).count() if (request.user.is_superuser or request.user.can_manage_admins or request.user.created_admins.filter(is_staff=True, is_superuser=False).exists()) else 0

    return render(
        request,
        "dashboard/my_account.html",
        {
            "profile_form": profile_form,
            "password_form": password_form,
            "capability_labels": capability_labels,
            "managed_admins_count": managed_admins_count,
            "branding_form": branding_form,
        },
    )


@admin_required
def dashboard_mark_notifications_read(request):
    if request.method == "POST":
        Notification.objects.filter(is_read=False).update(is_read=True)
    return redirect(request.POST.get("next") or reverse("dashboard_home"))


@admin_required
def dashboard_mark_single_notification_read(request, notification_id):
    if request.method == "POST":
        Notification.objects.filter(id=notification_id, is_read=False).update(is_read=True)
    return redirect(request.POST.get("next") or reverse("dashboard_home"))


@admin_capability_required("can_manage_books")
def dashboard_book_conflict_check(request):
    if request.method != "POST":
        return JsonResponse({"error": "invalid-request"}, status=400)

    title = (request.POST.get("title") or "").strip()
    isbn = (request.POST.get("isbn") or "").strip()
    conflict = find_duplicate_book_conflict(title=title, isbn=isbn)

    if conflict["type"] == "none":
        return JsonResponse({"type": "none"})

    book = conflict["book"]
    return JsonResponse(
        {
            "type": conflict["type"],
            "score": conflict["score"],
            "book": {
                "id": book.id,
                "title": book.title,
                "isbn": book.isbn,
                "category": book.category.name if book.category else "",
                "publisher": book.publisher.name if book.publisher else "",
                "authors": list(book.authors.values_list("name", flat=True)),
            },
        }
    )


@admin_capability_required("can_manage_books")
def api_check_entity(request):
    entity_type = request.GET.get("type")
    name = (request.GET.get("name") or "").strip()

    if not name or entity_type not in ["author", "category", "publisher"]:
        return JsonResponse({"error": "Invalid parameters"}, status=400)

    model_map = {"author": Author, "category": Category, "publisher": Publisher}
    model_class = model_map[entity_type]

    if entity_type == "category":
        exact = model_class.objects.filter(Q(name__iexact=name) | Q(name_en__iexact=name)).first()
    else:
        exact = model_class.objects.filter(name__iexact=name).first()

    if exact:
        return JsonResponse({"exact": {"id": exact.id, "name": getattr(exact, "name", "")}})

    words = name.split()
    query = Q()
    for word in words:
        if len(word) > 1:
            if entity_type == "category":
                query |= Q(name__icontains=word) | Q(name_en__icontains=word)
            else:
                query |= Q(name__icontains=word)

    similar = model_class.objects.filter(query)[:5] if query else []
    similar_list = [{"id": obj.id, "name": getattr(obj, "name", "")} for obj in similar]

    return JsonResponse({"exact": None, "similar": similar_list})



@admin_capability_required("can_manage_books")
@csrf_exempt
def api_create_entity(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)

    try:
        data = json.loads(request.body)
        entity_type = data.get("type")
        name = (data.get("name") or "").strip()
        name_en = (data.get("name_en") or "").strip()

        if not name or entity_type not in ["author", "category", "publisher"]:
            return JsonResponse({"error": "Invalid parameters"}, status=400)

        if entity_type == "author":
            obj, _ = Author.objects.get_or_create(name=name)
        elif entity_type == "publisher":
            obj, _ = Publisher.objects.get_or_create(name=name)
        else:
            obj, _ = Category.objects.get_or_create(name=name, defaults={"name_en": name_en})
            if name_en and not obj.name_en:
                obj.name_en = name_en
                obj.save(update_fields=["name_en"])

        return JsonResponse({"success": True, "id": obj.id, "name": getattr(obj, "name", "")})
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500)

