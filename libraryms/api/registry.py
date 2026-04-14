from books.models import Author, Book, BookCopy, Category, CategorySearchStat, Publisher
from circulations.models import Borrowing, Fine, FinePayment, Loan, Reservation
from dashboard.models import LibraryBranding
from digital_library.models import DigitalLibrary
from members.models import Member

API_MODELS = [
    Category,
    CategorySearchStat,
    Author,
    Publisher,
    Book,
    BookCopy,
    Member,
    Borrowing,
    Reservation,
    Fine,
    FinePayment,
    Loan,
    DigitalLibrary,
    LibraryBranding,
]
