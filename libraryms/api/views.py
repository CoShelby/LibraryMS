from django.db import models
from rest_framework import viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response

from books.models import Book
from circulations.models import Fine, FinePayment
from books.selectors import get_popular_books

from .registry import API_MODELS
from .serializers import build_serializer

READ_ONLY_MODELS = {Fine, FinePayment}


def _queryset_for_model(model):
    queryset = model.objects.all()
    select_related_fields = []
    prefetch_related_fields = []

    for field in model._meta.get_fields():
        if getattr(field, "auto_created", False) and not field.concrete:
            continue
        if field.is_relation and field.concrete:
            if field.many_to_many:
                prefetch_related_fields.append(field.name)
            elif field.many_to_one or field.one_to_one:
                select_related_fields.append(field.name)

    if select_related_fields:
        queryset = queryset.select_related(*select_related_fields)
    if prefetch_related_fields:
        queryset = queryset.prefetch_related(*prefetch_related_fields)
    return queryset.order_by("pk")


# def _filterset_fields(model):
#     names = []
#     for field in model._meta.get_fields():
#         if getattr(field, "auto_created", False) and not field.concrete:
#             continue
#         if field.name in {"password", "groups", "user_permissions"}:
#             continue
#         if field.many_to_many or field.concrete:
#             names.append(field.name)
#     return names
def _filterset_fields(model):
    names = []
    for field in model._meta.get_fields():
        if getattr(field, "auto_created", False) and not field.concrete:
            continue

        if field.name in {"password", "groups", "user_permissions"}:
            continue

        # استبعاد الصور والملفات
        if isinstance(field, (models.ImageField, models.FileField)):
            continue

        if field.many_to_many or field.concrete:
            names.append(field.name)

    return names

def _search_fields(model):
    names = []
    for field in model._meta.get_fields():
        if getattr(field, "auto_created", False) and not field.concrete:
            continue
        if isinstance(field, (models.CharField, models.TextField, models.EmailField, models.URLField, models.SlugField)):
            names.append(field.name)
        elif field.is_relation and field.concrete:
            related_model = field.related_model
            if related_model is None:
                continue
            for related_field in related_model._meta.get_fields():
                if getattr(related_field, "auto_created", False) or not getattr(related_field, "concrete", False):
                    continue
                if isinstance(related_field, (models.CharField, models.TextField, models.EmailField)):
                    names.append(f"{field.name}__{related_field.name}")
    return names


def build_viewset(model):
    serializer_class = build_serializer(model)
    attrs = {
        "queryset": _queryset_for_model(model),
        "serializer_class": serializer_class,
        "filterset_fields": _filterset_fields(model),
        "search_fields": _search_fields(model),
    }
    if model in READ_ONLY_MODELS:
        attrs["http_method_names"] = ["get", "head", "options"]
    return type(f"{model.__name__}ViewSet", (viewsets.ModelViewSet,), attrs)


AUTO_VIEWSETS = {model: build_viewset(model) for model in API_MODELS}
BookViewSet = AUTO_VIEWSETS[Book]


@api_view(["GET"])
def most_viewed_books_endpoint(request):
    serializer = build_serializer(Book)
    queryset = get_popular_books(limit=20)
    return Response(serializer(queryset, many=True, context={"request": request}).data)


@api_view(["GET"])
def recent_searches_endpoint(request):
    return Response({"results": request.session.get("recent_searches", [])})

