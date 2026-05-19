import logging
import re
from urllib.parse import unquote
from django.utils.deprecation import MiddlewareMixin
from django.utils import timezone
from django.http import HttpResponse
from iot_hub.apps.audit.models import AuditLog


logger = logging.getLogger(__name__)

# SQL Injection patterns
SQL_INJECTION_PATTERNS = [
    r"(\b(UNION|SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|EXECUTE)\b)",
    r"(--|#|;)",
    r"('|\")\s*(OR|AND)\s*('|\")",
    r"(\*\s*0\s*R\s*1)",
]

# XSS patterns
XSS_PATTERNS = [
    r"<script[^>]*>.*?</script>",
    r"javascript:",
    r"on(load|error|click|submit|focus|blur)=",
    r"<iframe",
    r"<object",
    r"<embed",
]

# Path Traversal patterns
PATH_TRAVERSAL_PATTERNS = [
    r"\.\./",
    r"\.\.",
    r"%2e%2e",
    r"%252e%252e",
]

# Command Injection patterns
COMMAND_INJECTION_PATTERNS = [
    r"(;|&|\||`|\$\()",
    r"\n",
]

# Null byte injection
NULL_BYTE_PATTERNS = [
    r"%00",
    r"\\x00",
]


class SecurityMiddleware(MiddlewareMixin):
    """Middleware для защиты от инъекций и атак."""
    
    EXCLUDED_PATHS = ['/admin/', '/api/auth/register/', '/api/auth/login/']
    
    def _check_patterns(self, value, patterns):
        """Проверка значения на соответствие опасным паттернам."""
        if not isinstance(value, str):
            return False
        
        # Декодируем URL-encoded значения
        value_decoded = unquote(value)
        
        for pattern in patterns:
            if re.search(pattern, value_decoded, re.IGNORECASE):
                return True
        return False
    
    def _is_path_excluded(self, path):
        """Проверка, исключен ли путь из проверки безопасности."""
        for excluded in self.EXCLUDED_PATHS:
            if path.startswith(excluded):
                return True
        return False
    
    def _scan_parameters(self, request):
        """Сканирование параметров запроса на опасные паттерны."""
        # Проверка параметров GET
        for key, value in request.GET.items():
            if isinstance(value, str):
                if self._check_patterns(value, SQL_INJECTION_PATTERNS):
                    return True, 'SQL_INJECTION', key
                if self._check_patterns(value, XSS_PATTERNS):
                    return True, 'XSS', key
                if self._check_patterns(value, PATH_TRAVERSAL_PATTERNS):
                    return True, 'PATH_TRAVERSAL', key
                if self._check_patterns(value, COMMAND_INJECTION_PATTERNS):
                    return True, 'COMMAND_INJECTION', key
                if self._check_patterns(value, NULL_BYTE_PATTERNS):
                    return True, 'NULL_BYTE', key
        
        # Проверка параметров POST
        if request.method == 'POST':
            for key, value in request.POST.items():
                if isinstance(value, str):
                    if self._check_patterns(value, SQL_INJECTION_PATTERNS):
                        return True, 'SQL_INJECTION', key
                    if self._check_patterns(value, XSS_PATTERNS):
                        return True, 'XSS', key
        
        return False, None, None
    
    def process_request(self, request):
        request.start_time = timezone.now()
        
        # Пропускаем исключенные пути
        if self._is_path_excluded(request.path):
            return None
        
        # Сканируем параметры
        has_threat, threat_type, param = self._scan_parameters(request)
        
        if has_threat:
            logger.warning(
                f"Security threat detected: {threat_type} in parameter '{param}' "
                f"from {request.META.get('REMOTE_ADDR')} to {request.path}"
            )
            return HttpResponse(
                '{"error": "Malicious request detected"}',
                status=400,
                content_type='application/json'
            )
        
        return None


class RequestLoggingMiddleware(MiddlewareMixin):
    """Middleware для логирования всех запросов."""
    
    def process_request(self, request):
        if not hasattr(request, 'start_time'):
            request.start_time = timezone.now()
        return None
    
    def process_response(self, request, response):
        if hasattr(request, 'start_time'):
            duration = (timezone.now() - request.start_time).total_seconds()
            
            logger.info(f"{request.method} {request.path} - {response.status_code} ({duration:.2f}s)")
        
        return response
