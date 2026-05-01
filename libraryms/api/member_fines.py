from django.db.models import Exists, OuterRef, Q
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.authentication import TokenAuthentication
from rest_framework.response import Response
from rest_framework.views import APIView

from circulations.models import Borrowing, Fine, FinePayment
from members.models import Member

from .permissions import CanAccessMemberFinanceAPI, CanSubmitExternalFinePayments


class FinePaymentRequestSerializer(serializers.Serializer):
    amount = serializers.IntegerField(min_value=1)
    external_reference = serializers.CharField(max_length=120, required=False, allow_blank=True)


class FinePaymentResponseSerializer(serializers.ModelSerializer):
    created_by = serializers.SerializerMethodField()

    class Meta:
        model = FinePayment
        fields = ["id", "amount", "external_reference", "created_by", "created_at"]

    def get_created_by(self, obj):
        return obj.created_by.username if obj.created_by else None


def _member_basic_info(member):
    return {
        "id": member.id,
        "membership_number": member.membership_number,
        "name": member.name,
        "email": member.email,
        "phone": member.phone,
        "member_type": member.member_type,
        "is_suspended": member.is_suspended,
    }


def _fine_payload(fine):
    return {
        "id": fine.id,
        "borrowing_id": fine.borrowing_id,
        "book_title": fine.borrowing.book_copy.book.title,
        "days_late": fine.days_late,
        "amount": fine.amount,
        "paid_amount": fine.total_paid_amount,
        "unpaid_amount": fine.unpaid_amount,
        "paid": fine.paid,
        "created_at": fine.created_at,
    }


def _member_status_payload(member):
    unreturned_borrowings = list(
        Borrowing.objects.filter(member=member, return_date__isnull=True)
        .select_related("book_copy__book")
        .order_by("-borrow_date", "-id")
    )
    fines = list(
        Fine.objects.filter(borrowing__member=member)
        .select_related("borrowing__book_copy__book")
        .prefetch_related("payments")
        .order_by("-created_at", "-id")
    )

    borrowed_copies = [
        {
            "borrowing_id": borrowing.id,
            "copy_barcode": borrowing.book_copy.barcode,
            "book_title": borrowing.book_copy.book.title,
            "borrow_date": borrowing.borrow_date,
            "due_date": borrowing.due_date,
        }
        for borrowing in unreturned_borrowings
    ]

    fines_payload = [_fine_payload(fine) for fine in fines]
    total_unpaid_amount = sum(fine["unpaid_amount"] for fine in fines_payload)

    return {
        "member": _member_basic_info(member),
        "unreturned_borrowed_copies": borrowed_copies,
        "fines": fines_payload,
        "total_unpaid_amount": total_unpaid_amount,
    }


class MemberSearchAPIView(APIView):
    permission_classes = [CanAccessMemberFinanceAPI]

    def get(self, request):
        membership_number = (request.query_params.get("membership_number") or "").strip()
        name = (request.query_params.get("name") or "").strip()

        if not membership_number and not name:
            return Response(
                {"detail": "Provide at least one search parameter: membership_number or name."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        queryset = Member.objects.all().order_by("name", "id")
        if membership_number and name:
            queryset = queryset.filter(
                Q(membership_number__icontains=membership_number) | Q(name__icontains=name)
            )
        elif membership_number:
            queryset = queryset.filter(membership_number__icontains=membership_number)
        elif name:
            queryset = queryset.filter(name__icontains=name)

        members = list(queryset[:50])
        return Response(
            {
                "count": len(members),
                "results": [_member_status_payload(member) for member in members],
            }
        )


class MembersWithIssuesAPIView(APIView):
    permission_classes = [CanAccessMemberFinanceAPI]

    ISSUE_UNRETURNED = "unreturned_books"
    ISSUE_UNPAID = "unpaid_fines"
    ISSUE_BOTH = "both"
    ISSUE_ANY = "any"

    def get(self, request):
        issue = (request.query_params.get("issue") or self.ISSUE_ANY).strip().lower()
        allowed = {self.ISSUE_UNRETURNED, self.ISSUE_UNPAID, self.ISSUE_BOTH, self.ISSUE_ANY}
        if issue not in allowed:
            return Response(
                {
                    "detail": "Invalid issue filter. Use one of: unreturned_books, unpaid_fines, both, any."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        unreturned_qs = Borrowing.objects.filter(member_id=OuterRef("pk"), return_date__isnull=True)
        unpaid_qs = Fine.objects.filter(borrowing__member_id=OuterRef("pk"), paid=False)

        members = Member.objects.annotate(
            has_unreturned_books=Exists(unreturned_qs),
            has_unpaid_fines=Exists(unpaid_qs),
        ).order_by("name", "id")

        if issue == self.ISSUE_UNRETURNED:
            members = members.filter(has_unreturned_books=True)
        elif issue == self.ISSUE_UNPAID:
            members = members.filter(has_unpaid_fines=True)
        elif issue == self.ISSUE_BOTH:
            members = members.filter(has_unreturned_books=True, has_unpaid_fines=True)
        else:
            members = members.filter(Q(has_unreturned_books=True) | Q(has_unpaid_fines=True))

        results = []
        for member in members[:200]:
            status_payload = _member_status_payload(member)
            results.append(
                {
                    "member": status_payload["member"],
                    "has_unreturned_books": member.has_unreturned_books,
                    "has_unpaid_fines": member.has_unpaid_fines,
                    "unreturned_count": len(status_payload["unreturned_borrowed_copies"]),
                    "unpaid_fines_count": sum(1 for fine in status_payload["fines"] if fine["unpaid_amount"] > 0),
                    "total_unpaid_amount": status_payload["total_unpaid_amount"],
                }
            )

        return Response({"count": len(results), "results": results})


class MemberFullStatusAPIView(APIView):
    permission_classes = [CanAccessMemberFinanceAPI]

    def get(self, request, member_id):
        member = get_object_or_404(Member, pk=member_id)
        return Response(_member_status_payload(member))


class FineStatusAPIView(APIView):
    permission_classes = [CanAccessMemberFinanceAPI]

    def get(self, request, fine_id):
        fine = get_object_or_404(
            Fine.objects.select_related("borrowing__member", "borrowing__book_copy__book").prefetch_related("payments"),
            pk=fine_id,
        )
        fine.sync_paid_status(save=True)
        return Response(
            {
                "fine": _fine_payload(fine),
                "member": _member_basic_info(fine.borrowing.member),
            }
        )


class ExternalFinePaymentAPIView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [CanSubmitExternalFinePayments]

    def post(self, request, fine_id):
        serializer = FinePaymentRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        fine = get_object_or_404(
            Fine.objects.select_related("borrowing__member", "borrowing__book_copy__book").prefetch_related("payments"),
            pk=fine_id,
        )
        fine.sync_paid_status(save=True)

        requested_amount = serializer.validated_data["amount"]
        remaining_before_payment = fine.unpaid_amount

        if remaining_before_payment <= 0:
            return Response(
                {"detail": "This fine is already fully paid.", "fine": _fine_payload(fine)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if requested_amount > remaining_before_payment:
            return Response(
                {
                    "detail": "Payment amount exceeds remaining unpaid amount.",
                    "remaining_unpaid_amount": remaining_before_payment,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        payment = FinePayment.objects.create(
            fine=fine,
            amount=requested_amount,
            external_reference=serializer.validated_data.get("external_reference", ""),
            created_by=request.user,
        )

        fine.refresh_from_db()
        fine = Fine.objects.select_related("borrowing__member", "borrowing__book_copy__book").prefetch_related("payments").get(pk=fine.pk)
        fine.sync_paid_status(save=True)

        response_payload = {
            "message": "Payment recorded successfully.",
            "payment": FinePaymentResponseSerializer(payment).data,
            "fine": _fine_payload(fine),
        }
        return Response(response_payload, status=status.HTTP_201_CREATED)

