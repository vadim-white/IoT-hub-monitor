from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from iot_hub.apps.accounts.models import UserRole, UserProfile, ApiKey
from iot_hub.apps.accounts.presentation.serializers import (
    UserSerializer, UserRegistrationSerializer, UserLoginSerializer,
    UserDetailSerializer, ApiKeySerializer
)
import secrets


# ====== WEB VIEWS ======

def login_view(request):
    """Вход пользователя в систему."""
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            return redirect('dashboard')
        else:
            return render(request, 'accounts/login.html', {
                'error': 'Неверное имя пользователя или пароль'
            })
    
    return render(request, 'accounts/login.html')


def register_view(request):
    """Регистрация нового пользователя."""
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        password2 = request.POST.get('password2')
        
        if password != password2:
            return render(request, 'accounts/register.html', {
                'error': 'Пароли не совпадают'
            })
        
        if User.objects.filter(username=username).exists():
            return render(request, 'accounts/register.html', {
                'error': 'Пользователь с таким именем уже существует'
            })
        
        if User.objects.filter(email=email).exists():
            return render(request, 'accounts/register.html', {
                'error': 'Email уже зарегистрирован'
            })
        
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password
        )
        
        return redirect('login')
    
    return render(request, 'accounts/register.html')


def logout_view(request):
    """Выход пользователя из системы."""
    logout(request)
    return redirect('login')


@login_required(login_url='login')
def profile_view(request):
    """Просмотр и редактирование профиля пользователя."""
    if request.method == 'POST':
        user = request.user
        user.first_name = request.POST.get('first_name', user.first_name)
        user.last_name = request.POST.get('last_name', user.last_name)
        user.email = request.POST.get('email', user.email)
        user.save()
        
        profile = user.profile
        profile.phone = request.POST.get('phone', '')
        profile.organization = request.POST.get('organization', '')
        profile.save()
        
        return redirect('profile')
    
    context = {
        'user': request.user,
        'role': request.user.role,
        'profile': request.user.profile
    }
    return render(request, 'accounts/profile.html', context)


# ====== API VIEWS ======

class UserViewSet(viewsets.ModelViewSet):
    """API ViewSet для управления пользователями."""
    queryset = User.objects.select_related('role', 'profile')
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return UserRegistrationSerializer
        elif self.action == 'retrieve' or self.action == 'update':
            return UserDetailSerializer
        return UserSerializer
    
    def get_queryset(self):
        """Фильтр для доступа пользователей только к своим данным и админу."""
        user = self.request.user
        if hasattr(user, 'role') and user.role.is_admin:
            return User.objects.select_related('role', 'profile')
        return User.objects.filter(id=user.id).select_related('role', 'profile')
    
    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def me(self, request):
        """Получить текущего пользователя."""
        serializer = UserDetailSerializer(request.user)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'], permission_classes=[permissions.AllowAny])
    def register(self, request):
        """Регистрация нового пользователя."""
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response(
                {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "message": "Пользователь успешно зарегистрирован"
                },
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'], permission_classes=[permissions.AllowAny])
    def login(self, request):
        """Вход в систему."""
        serializer = UserLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        username = serializer.validated_data['username']
        password = serializer.validated_data['password']
        
        user = authenticate(username=username, password=password)
        if user is not None:
            login(request, user)
            return Response({
                "message": "Успешный вход",
                "user": UserSerializer(user).data
            })
        
        return Response(
            {"error": "Неверные учетные данные"},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def logout(self, request):
        """Выход из системы."""
        logout(request)
        return Response({"message": "Успешный выход"})


class UserRoleViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet для просмотра ролей пользователей."""
    queryset = UserRole.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'role') and user.role.is_admin:
            return UserRole.objects.all()
        return UserRole.objects.filter(user=user)


class ApiKeyViewSet(viewsets.ModelViewSet):
    """ViewSet для управления API ключами."""
    serializer_class = ApiKeySerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return ApiKey.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        # Генерируем уникальный ключ
        key = f"iot_hub_{secrets.token_urlsafe(32)}"
        serializer.save(user=self.request.user, key=key)
