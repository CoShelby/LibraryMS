from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.services import admin_capability_required

from .forms import MemberForm
from .models import Member


@admin_capability_required("can_manage_members")
def member_list(request):
    query = request.GET.get("query", "")
    members = Member.objects.all().order_by("-created_at")

    if query:
        members = members.filter(
            Q(name__icontains=query)
            | Q(membership_number__icontains=query)
            | Q(university_id__icontains=query)
            | Q(email__icontains=query)
            | Q(phone__icontains=query)
        )

    paginator = Paginator(members, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "members/member_list.html",
        {
            "members": page_obj,
            "query": query,
            "today": timezone.now().date(),
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

