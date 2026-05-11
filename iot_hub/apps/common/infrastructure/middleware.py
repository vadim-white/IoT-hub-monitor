import logging
from django.utils.deprecation import MiddlewareMixin
from iot_hub.apps.audit.models import AuditLog


logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(MiddlewareMixin):
    """Middleware для логирования всех запросов."""
    
    def process_request(self, request):
        request.start_time = timezone.now()
        return None
    
    def process_response(self, request, response):
        if hasattr(request, 'start_time'):
            duration = (timezone.now() - request.start_time).total_seconds()
            
            logger.info(f"{request.method} {request.path} - {response.status_code} ({duration:.2f}s)")
        
        return response


from django.utils import timezone
