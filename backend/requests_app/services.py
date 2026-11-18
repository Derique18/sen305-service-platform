from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from .models import Comment, ServiceRequest, WorkOrder


@transaction.atomic
def service_request_create(*, requester, category, title, description, location, priority):
    item = ServiceRequest(
        requester=requester,
        category=category,
        title=title.strip(),
        description=description.strip(),
        location=location.strip(),
        priority=priority,
    )
    item.full_clean()
    item.save()
    return item


@transaction.atomic
def service_request_update(*, item, actor, category, title, description, location, priority):
    if not actor.is_staff and item.requester_id != actor.id:
        raise PermissionDenied("Only the requester or staff may update this request.")
    if item.status != ServiceRequest.Status.OPEN:
        raise ValidationError("Only open requests can be edited.")

    item.category = category
    item.title = title.strip()
    item.description = description.strip()
    item.location = location.strip()
    item.priority = priority
    item.full_clean()
    item.save()
    return item


@transaction.atomic
def comment_create(*, item, author, body):
    comment = Comment(service_request=item, author=author, body=body.strip())
    comment.full_clean()
    comment.save()
    return comment


@transaction.atomic
def service_request_assign(*, item, technician, actor):
    if not actor.is_staff:
        raise PermissionDenied("Only staff may assign technicians.")
    if not technician.is_staff or not technician.is_active:
        raise ValidationError("Technician must be an active staff user.")

    locked = ServiceRequest.objects.select_for_update().get(pk=item.pk)
    if locked.status in (ServiceRequest.Status.RESOLVED, ServiceRequest.Status.CLOSED):
        raise ValidationError("Completed requests cannot be assigned.")

    work_order, _ = WorkOrder.objects.update_or_create(
        service_request=locked,
        defaults={"technician": technician},
    )
    locked.status = ServiceRequest.Status.ASSIGNED
    locked.save(update_fields=["status", "updated_at"])
    return work_order


@transaction.atomic
def service_request_resolve(*, item, actor, work_notes):
    locked = ServiceRequest.objects.select_for_update().get(pk=item.pk)
    work_order = getattr(locked, "work_order", None)
    if work_order is None:
        raise ValidationError("Assign a technician before resolving the request.")
    if not actor.is_staff and actor.id != work_order.technician_id:
        raise PermissionDenied("Only the assigned technician or staff may resolve.")

    notes = work_notes.strip()
    if not notes:
        raise ValidationError("Resolution work notes are required.")

    work_order.work_notes = notes
    work_order.completed_at = timezone.now()
    work_order.full_clean()
    work_order.save()

    locked.status = ServiceRequest.Status.RESOLVED
    locked.resolution_summary = notes
    locked.resolved_at = timezone.now()
    locked.full_clean()
    locked.save()
    return locked
