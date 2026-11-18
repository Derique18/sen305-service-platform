from django.db.models import Count, Q
from .models import ServiceRequest


def service_request_list(*, user):
    queryset = (
        ServiceRequest.objects
        .select_related("requester", "category")
        .annotate(comment_count=Count("comments"))
        .order_by("-created_at")
    )
    return queryset if user.is_staff else queryset.filter(requester=user)


def service_request_filter(*, user, status="", query=""):
    queryset = service_request_list(user=user)
    if status:
        queryset = queryset.filter(status=status)
    if query:
        queryset = queryset.filter(
            Q(title__icontains=query)
            | Q(description__icontains=query)
            | Q(location__icontains=query)
        )
    return queryset


def service_request_get(*, user, request_id):
    return service_request_list(user=user).get(id=request_id)


def service_request_counts(*, user):
    base_qs = (
        ServiceRequest.objects.all()
        if user.is_staff
        else ServiceRequest.objects.filter(requester=user)
    )
    return base_qs.aggregate(
        open_count=Count("id", filter=Q(status=ServiceRequest.Status.OPEN)),
        assigned_count=Count("id", filter=Q(status=ServiceRequest.Status.ASSIGNED)),
        resolved_count=Count("id", filter=Q(status=ServiceRequest.Status.RESOLVED)),
    )
