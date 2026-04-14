from circulations.models import Borrowing, Fine


def member_has_active_borrowings(member):
    return Borrowing.objects.filter(member=member, return_date__isnull=True).exists()


def member_has_unpaid_fines(member):
    return Fine.objects.filter(borrowing__member=member, paid=False).exists()


def member_can_be_deleted(member):
    return not (member_has_active_borrowings(member) or member_has_unpaid_fines(member))