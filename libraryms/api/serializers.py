from rest_framework import serializers

SENSITIVE_FIELD_NAMES = {
    "password",
    "groups",
    "user_permissions",
}


def _relation_payload(value):
    if value is None:
        return None
    return {
        "id": value.pk,
        "label": str(value),
    }


def build_serializer(model):
    field_names = []
    extra_fields = []
    attrs = {}

    for field in model._meta.get_fields():
        if getattr(field, "auto_created", False) and not field.concrete:
            continue
        if field.name in SENSITIVE_FIELD_NAMES:
            continue
        if field.many_to_many or field.concrete:
            field_names.append(field.name)
        if field.is_relation and (field.many_to_one or field.one_to_one):
            extra_name = f"{field.name}_detail"
            extra_fields.append(extra_name)
            attrs[extra_name] = serializers.SerializerMethodField(read_only=True)

            def make_fk_getter(field_name):
                def getter(self, obj):
                    return _relation_payload(getattr(obj, field_name, None))
                return getter

            attrs[f"get_{extra_name}"] = make_fk_getter(field.name)
        elif field.many_to_many:
            extra_name = f"{field.name}_details"
            extra_fields.append(extra_name)
            attrs[extra_name] = serializers.SerializerMethodField(read_only=True)

            def make_m2m_getter(field_name):
                def getter(self, obj):
                    manager = getattr(obj, field_name)
                    return [_relation_payload(item) for item in manager.all()]
                return getter

            attrs[f"get_{extra_name}"] = make_m2m_getter(field.name)

    attrs["Meta"] = type("Meta", (), {"model": model, "fields": field_names + extra_fields})
    serializer_name = f"{model.__name__}AutoSerializer"
    return type(serializer_name, (serializers.ModelSerializer,), attrs)
