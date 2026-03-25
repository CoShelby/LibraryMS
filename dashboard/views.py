import json
import os
import secrets

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.core.mail import send_mail
from django.db.models import Count, ExpressionWrapper, F, IntegerField, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.csrf import csrf_exempt
from accounts.forms import AdminSelfProfileForm, AdminUserCreationForm, AdminUserUpdateForm
from accounts.models import User
from accounts.services import admin_capability_required, admin_required, has_admin_capability
from books.models import Author, Book, BookCopy, Category, Publisher
from circulations.models import Borrowing, Fine, Reservation
from circulations.services import (
    approve_reservation,
    borrow_book,
    cancel_reservation,
    complete_reservation,
    reject_renewal_request,
    renew_borrowing,
    return_book,
)
from digital_library.models import DigitalLibrary
from members.models import Member

from .forms import AuthorForm, BookCopyForm, BookForm, CategoryForm, DigitalLibraryForm, PublisherForm

def _split_names(raw_value):
    prepared = (raw_value or "").replace("،", ",")
    values = [name.strip() for name in prepared.split(",") if name.strip()]
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
        Book.objects.select_related("category")
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


@admin_required
def dashboard_home(request):
    context = {
        "total_books": Book.objects.count(),
        "total_members": Member.objects.count(),
        "active_borrows": Borrowing.objects.filter(return_date__isnull=True).count(),
        "active_reservations": Reservation.objects.filter(status="pending").count(),
        "recent_borrows": Borrowing.objects.select_related("book_copy__book", "member").order_by("-borrow_date")[:8],
        "can_manage_books": has_admin_capability(request.user, "can_manage_books"),
        "can_manage_members": has_admin_capability(request.user, "can_manage_members"),
        "can_manage_categories": has_admin_capability(request.user, "can_manage_categories"),
        "can_manage_admins": request.user.is_superuser,
        "can_manage_circulation": has_admin_capability(request.user, "can_manage_circulation"),
    }
    return render(request, "dashboard/home.html", context)


@admin_capability_required("can_manage_books")
def dashboard_books_list(request):
    books = _books_dashboard_queryset()
    return render(request, "dashboard/books/books_list.html", {"books": books})


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
            book = form.save()
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
    book = get_object_or_404(Book, id=book_id)

    if request.method == "POST":
        form = BookCopyForm(request.POST)
        if form.is_valid():
            copy = form.save(commit=False)
            copy.book = book
            copy.save()
            messages.success(request, "تمت إضافة النسخة بنجاح.")
            return redirect("dashboard_book_copies", book_id=book.id)
    else:
        form = BookCopyForm()

    copies = book.bookcopy_set.all().order_by("id")
    return render(
        request,
        "dashboard/books/copies.html",
        {
            "book": book,
            "form": form,
            "copies": copies,
        },
    )

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
                pdf_file = form.cleaned_data["pdf_file"]
                detected_pages, extracted_cover, metadata_title = _extract_pdf_metadata(pdf_file)

                typed_title = (form.cleaned_data.get("new_title") or "").strip()
                inferred_title = typed_title or metadata_title or _title_from_filename(pdf_file) or "كتاب رقمي"

                pages_value = form.cleaned_data.get("new_pages") or detected_pages
                category = _resolve_category(form.cleaned_data["new_category_name"].strip())
                publisher, _ = Publisher.objects.get_or_create(name=form.cleaned_data["new_publisher_name"].strip())

                book = Book.objects.create(
                    title=inferred_title,
                    dewey_decimal_number=form.cleaned_data["new_dewey_decimal_number"].strip(),
                    category=category,
                    publisher=publisher,
                    publication_year=form.cleaned_data.get("new_publication_year"),
                    language=form.cleaned_data.get("new_language") or "arabic",
                    pages=pages_value,
                    description=form.cleaned_data.get("new_description") or "",
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
                pdf_file = form.cleaned_data["pdf_file"]
                detected_pages, extracted_cover, metadata_title = _extract_pdf_metadata(pdf_file)

                update_fields = []
                if metadata_title and not selected_book.title:
                    selected_book.title = metadata_title
                    update_fields.append("title")
                elif not selected_book.title:
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

            messages.success(request, "تمت إضافة الكتاب الرقمي.")
            return redirect("dashboard_digital_list")
    else:
        form = DigitalLibraryForm()

    return render(
        request,
        "dashboard/digital/form.html",
        {
            "form": form,
            "title": "إضافة كتاب رقمي",
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
                messages.success(request, "تم تحديث الكتاب الرقمي.")
                return redirect("dashboard_digital_list")
            messages.error(request, "في التعديل اختر كتابًا موجودًا مرتبطًا بالنسخة الرقمية.")
    else:
        form = DigitalLibraryForm(instance=digital_book)

    return render(
        request,
        "dashboard/digital/form.html",
        {
            "form": form,
            "title": f"تعديل كتاب رقمي: {digital_book.book.title}",
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

@admin_capability_required("can_manage_circulation")
def dashboard_circulation(request):
    _expire_reservation_requests()

    pending_reservations = Reservation.objects.select_related("book", "member").filter(status="pending").order_by(
        "reservation_date"
    )
    approved_reservations = Reservation.objects.select_related("book", "member").filter(status="approved").order_by(
        "reservation_date"
    )
    active_borrowings = Borrowing.objects.select_related("book_copy__book", "member").filter(
        return_date__isnull=True
    ).order_by("due_date")
    renewal_requests = active_borrowings.filter(renewal_requested=True)

    physical_books = (
        Book.objects.annotate(total_copies=Count("bookcopy", distinct=True))
        .filter(total_copies__gt=0)
        .order_by("title")
    )

    return render(
        request,
        "dashboard/circulation.html",
        {
            "pending_reservations": pending_reservations,
            "approved_reservations": approved_reservations,
            "active_borrowings": active_borrowings,
            "renewal_requests": renewal_requests,
            "books": physical_books,
        },
    )


@admin_capability_required("can_manage_circulation")
def dashboard_manual_borrow(request):
    if request.method == "POST":
        membership_number = (request.POST.get("membership_number") or "").strip()
        book_id = request.POST.get("book_id")
        copy_barcode = (request.POST.get("copy_barcode") or "").strip()

        try:
            member = Member.objects.get(membership_number=membership_number)
            book = Book.objects.get(id=book_id)

            if not book.bookcopy_set.exists():
                raise ValueError("هذا الكتاب غير مدرج ككتاب ورقي بعد.")

            preferred_copy = None
            if copy_barcode:
                preferred_copy = BookCopy.objects.get(book=book, barcode=copy_barcode)

            borrow_book(member, book, request.user, preferred_copy=preferred_copy)
            messages.success(request, "تم تسجيل الاستعارة اليدوية بنجاح.")
        except Member.DoesNotExist:
            messages.error(request, "رقم العضوية غير صحيح.")
        except Book.DoesNotExist:
            messages.error(request, "الكتاب المحدد غير موجود.")
        except BookCopy.DoesNotExist:
            messages.error(request, "رمز النسخة غير صحيح لهذا الكتاب.")
        except ValueError as exc:
            messages.error(request, str(exc))

    return redirect("dashboard_circulation")


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
                    f"تم تسجيل الإرجاع. تم احتساب غرامة {fine.amount} ({fine.days_late} يوم تأخير).",
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

    report_tables = {
        "books": {
            "label": "الكتب",
            "queryset": Book.objects.select_related("category", "publisher").prefetch_related("authors"),
            "sort_options": [
                ("title", "العنوان (أ-ي)"),
                ("-title", "العنوان (ي-أ)"),
                ("created_at", "تاريخ الإدراج (أقدم)"),
                ("-created_at", "تاريخ الإدراج (أحدث)"),
                ("view_count", "الأقل مشاهدة"),
                ("-view_count", "الأكثر مشاهدة"),
            ],
            "headers": ["ID", "العنوان", "المؤلفون", "الفئة", "الناشر", "السنة", "اللغة", "الصفحات"],
            "rows": lambda q: [
                [
                    item.id,
                    item.title,
                    "، ".join(item.authors.values_list("name", flat=True)) or "-",
                    item.category.name if item.category else "-",
                    item.publisher.name if item.publisher else "-",
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
            "queryset": Borrowing.objects.select_related("book_copy__book", "member", "employee"),
            "sort_options": [
                ("borrow_date", "تاريخ الاستعارة (الأقدم)"),
                ("-borrow_date", "تاريخ الاستعارة (الأحدث)"),
                ("due_date", "تاريخ الاستحقاق (الأقرب)"),
                ("-due_date", "تاريخ الاستحقاق (الأبعد)"),
            ],
            "headers": ["ID", "الكتاب", "النسخة", "العضو", "الموظف", "الاستعارة", "الاستحقاق", "الإرجاع", "طلب تجديد"],
            "rows": lambda q: [
                [
                    item.id,
                    item.book_copy.book.title,
                    item.book_copy.barcode,
                    item.member.name,
                    item.employee.username if item.employee else "-",
                    item.borrow_date,
                    item.due_date,
                    item.return_date or "-",
                    "نعم" if item.renewal_requested else "لا",
                ]
                for item in q
            ],
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
            "queryset": Fine.objects.select_related("borrowing__member", "borrowing__book_copy__book"),
            "sort_options": [
                ("created_at", "الأقدم"),
                ("-created_at", "الأحدث"),
                ("amount", "المبلغ (تصاعدي)"),
                ("-amount", "المبلغ (تنازلي)"),
            ],
            "headers": ["ID", "العضو", "الكتاب", "أيام التأخير", "المبلغ", "مدفوع", "تاريخ الإنشاء"],
            "rows": lambda q: [
                [
                    item.id,
                    item.borrowing.member.name,
                    item.borrowing.book_copy.book.title,
                    item.days_late,
                    item.amount,
                    "نعم" if item.paid else "لا",
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

    queryset = config["queryset"].order_by(sort)
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
        },
    )

def _superadmin_required(request):
    if not request.user.is_authenticated or not request.user.is_superuser:
        raise PermissionDenied("Only super admin can manage admin accounts.")


def _manager_email():
    return (getattr(settings, "ADMIN_MANAGER_EMAIL", "") or "").strip()


def _reset_code_cache_key(user_id):
    return f"dashboard:admin-reset-code:{user_id}"


def _generate_reset_code():
    return f"{secrets.randbelow(1000000):06d}"


def _issue_admin_reset_code(user):
    code = _generate_reset_code()
    cache.set(_reset_code_cache_key(user.id), code, timeout=getattr(settings, "ADMIN_RESET_CODE_TTL_SECONDS", 600))
    _send_admin_reset_code(user, code)


def _send_admin_reset_code(user, code):
    manager_email = _manager_email()
    if not manager_email:
        raise ValueError("بريد المدير غير مضبوط. اضبط ADMIN_MANAGER_EMAIL في الإعدادات.")

    send_mail(
        subject="كود تحقق مؤقت لإعادة تعيين كلمة مرور الأدمن",
        message=(
            f"طلب إعادة تعيين كلمة مرور للأدمن: {user.username}\n"
            f"الكود المؤقت: {code}\n"
            f"مدة صلاحية الكود: {getattr(settings, 'ADMIN_RESET_CODE_TTL_SECONDS', 600) // 60} دقائق."
        ),
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@libraryms.local"),
        recipient_list=[manager_email],
        fail_silently=False,
    )


def _apply_input_css(form):
    for field in form.fields.values():
        field.widget.attrs.update({"class": "input-field"})


@admin_required
def dashboard_admin_users(request):
    _superadmin_required(request)

    if request.method == "POST":
        form = AdminUserCreationForm(request.POST)
        if form.is_valid():
            new_admin = form.save()
            try:
                _issue_admin_reset_code(new_admin)
                messages.success(request, "تم إنشاء الأدمن وإرسال كود التحقق المؤقت إلى بريد المدير.")
            except Exception as exc:
                messages.warning(request, f"تم إنشاء الأدمن لكن تعذر إرسال كود التحقق: {exc}")
            return redirect("dashboard_admin_users")
    else:
        form = AdminUserCreationForm(initial={"is_active": True})

    admins = User.objects.filter(is_staff=True, is_superuser=False).order_by("username")
    return render(
        request,
        "dashboard/admin_users.html",
        {
            "form": form,
            "admins": admins,
            "manager_email": _manager_email(),
        },
    )


@admin_required
def dashboard_admin_edit(request, admin_id):
    _superadmin_required(request)
    admin_user = get_object_or_404(User, id=admin_id, is_staff=True, is_superuser=False)

    if request.method == "POST":
        form = AdminUserUpdateForm(request.POST, instance=admin_user)
        if form.is_valid():
            form.save()
            messages.success(request, "تم تحديث بيانات الأدمن.")
            return redirect("dashboard_admin_users")
    else:
        form = AdminUserUpdateForm(instance=admin_user)

    return render(
        request,
        "dashboard/admin_user_edit.html",
        {
            "form": form,
            "admin_user": admin_user,
        },
    )


@admin_required
def dashboard_admin_toggle_active(request, admin_id):
    _superadmin_required(request)
    admin_user = get_object_or_404(User, id=admin_id, is_staff=True, is_superuser=False)

    if request.method == "POST":
        admin_user.is_active = not admin_user.is_active
        admin_user.save(update_fields=["is_active"])
        messages.success(request, "تم تحديث حالة حساب الأدمن.")

    return redirect("dashboard_admin_users")


@admin_required
def dashboard_admin_delete(request, admin_id):
    _superadmin_required(request)
    admin_user = get_object_or_404(User, id=admin_id, is_staff=True, is_superuser=False)

    if request.method == "POST":
        username = admin_user.username
        admin_user.delete()
        messages.success(request, f"تم حذف حساب الأدمن: {username}")

    return redirect("dashboard_admin_users")


@admin_required
def dashboard_admin_send_reset_code(request, admin_id):
    _superadmin_required(request)
    admin_user = get_object_or_404(User, id=admin_id, is_staff=True, is_superuser=False)

    if request.method == "POST":
        try:
            _issue_admin_reset_code(admin_user)
            messages.success(request, "تم إرسال كود التحقق المؤقت إلى بريد المدير.")
        except Exception as exc:
            messages.error(request, f"تعذر إرسال كود التحقق: {exc}")

    return redirect("dashboard_admin_users")


@admin_required
def dashboard_admin_reset_password(request, admin_id):
    _superadmin_required(request)
    admin_user = get_object_or_404(User, id=admin_id, is_staff=True, is_superuser=False)

    verification_code = ""
    form = SetPasswordForm(user=admin_user)
    _apply_input_css(form)

    if request.method == "POST":
        verification_code = (request.POST.get("verification_code") or "").strip()
        expected_code = cache.get(_reset_code_cache_key(admin_user.id))

        if not expected_code:
            messages.error(request, "لا يوجد كود صالح لهذا الحساب أو انتهت صلاحيته. أعد إرسال كود جديد.")
        elif verification_code != str(expected_code):
            messages.error(request, "كود التحقق غير صحيح.")
        else:
            form = SetPasswordForm(user=admin_user, data=request.POST)
            _apply_input_css(form)
            if form.is_valid():
                form.save()  # Django hashing + set_password
                cache.delete(_reset_code_cache_key(admin_user.id))
                messages.success(request, "تم تعيين كلمة المرور بنجاح.")
                return redirect("dashboard_admin_users")

    return render(
        request,
        "dashboard/admin_reset_password.html",
        {
            "form": form,
            "admin_user": admin_user,
            "verification_code": verification_code,
            "manager_email": _manager_email(),
        },
    )


@admin_required
def dashboard_my_account(request):
    profile_form = AdminSelfProfileForm(instance=request.user, prefix="profile")
    password_form = PasswordChangeForm(user=request.user, prefix="password")
    _apply_input_css(password_form)

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

    return render(
        request,
        "dashboard/my_account.html",
        {
            "profile_form": profile_form,
            "password_form": password_form,
        },
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













