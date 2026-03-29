from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Case, F, IntegerField, Q, When
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.services import admin_capability_required

from .forms import MemberForm
from .models import Member


def _chunk_members(members, chunk_size=4):
    return [members[index : index + chunk_size] for index in range(0, len(members), chunk_size)]


@admin_capability_required("can_manage_members")
def member_list(request):
    query = request.GET.get("query", "")
    unprinted_only = request.GET.get("unprinted_only", "")
    members = Member.objects.all().order_by("-created_at")

    if query:
        members = members.filter(
            Q(name__icontains=query)
            | Q(membership_number__icontains=query)
            | Q(university_id__icontains=query)
        )
        
    if unprinted_only == "1":
        members = members.filter(is_printed=False)

    paginator = Paginator(members, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "members/member_list.html",
        {
            "members": page_obj,
            "query": query,
            "unprinted_only": unprinted_only,
            "today": timezone.now().date(),
        },
    )


@admin_capability_required("can_manage_members")
def print_member_cards(request):
    if request.method != "POST":
        return redirect("member_list")

    raw_ids = request.POST.getlist("member_ids")
    selected_ids = []
    for value in raw_ids:
        try:
            selected_ids.append(int(value))
        except (TypeError, ValueError):
            continue

    if not selected_ids:
        messages.error(request, "اختر عضوًا واحدًا على الأقل للطباعة.")
        return redirect("member_list")

    ordering = Case(
        *[When(id=member_id, then=position) for position, member_id in enumerate(selected_ids)],
        output_field=IntegerField(),
    )

    members = list(Member.objects.filter(id__in=selected_ids).order_by(ordering))
    if not members:
        messages.error(request, "لم يتم العثور على أعضاء صالحين للطباعة.")
        return redirect("member_list")

    # نحدد حالة "بدل فاقد" قبل الزيادة حتى تظهر فقط عند إعادة طباعة البطاقة.
    for member in members:
        member.is_reprint = member.card_print_count > 0

    with transaction.atomic():
        Member.objects.filter(id__in=[member.id for member in members]).update(
            card_print_count=F("card_print_count") + 1,
            last_card_printed_at=timezone.now(),
            is_printed=True,
        )

    return render(
        request,
        "members/print_cards.html",
        {
            "pages": _chunk_members(members, chunk_size=4),
            "printed_at": timezone.now(),
        },
    )


@admin_capability_required("can_manage_members")
def add_member(request):
    if request.method == "POST":
        form = MemberForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, "Member created successfully.")
            return redirect("member_list")
    else:
        form = MemberForm()

    return render(request, "members/add_member.html", {"form": form, "title": "Add Member"})


@admin_capability_required("can_manage_members")
def edit_member(request, member_id):
    member = get_object_or_404(Member, id=member_id)
    if request.method == "POST":
        form = MemberForm(request.POST, request.FILES, instance=member)
        if form.is_valid():
            form.save()
            messages.success(request, "Member updated successfully.")
            return redirect("member_list")
    else:
        form = MemberForm(instance=member)

    return render(
        request,
        "members/edit_member.html",
        {"form": form, "member": member, "title": f"Edit Member: {member.name}"},
    )


@admin_capability_required("can_manage_members")
def delete_member(request, member_id):
    if request.method == "POST":
        member = get_object_or_404(Member, id=member_id)
        name = member.name
        member.delete()
        messages.success(request, f"تم حذف العضو {name} بنجاح.")
    return redirect("member_list")
