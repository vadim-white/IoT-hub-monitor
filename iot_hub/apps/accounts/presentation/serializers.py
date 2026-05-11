from rest_framework import serializers
from django.contrib.auth.models import User
from iot_hub.apps.accounts.models import UserRole, UserProfile, ApiKey


class UserRoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserRole
        fields = ['id', 'role', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ['id', 'phone', 'organization', 'avatar', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class UserSerializer(serializers.ModelSerializer):
    role = UserRoleSerializer(read_only=True)
    profile = UserProfileSerializer(read_only=True)
    
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'role', 'profile']
        read_only_fields = ['id']


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True)
    password2 = serializers.CharField(write_only=True, required=True, label="Подтвердите пароль")
    
    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'password2', 'first_name', 'last_name']
    
    def validate(self, data):
        if data['password'] != data.pop('password2'):
            raise serializers.ValidationError({"password": "Пароли не совпадают."})
        return data
    
    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', '')
        )
        return user


class UserLoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)


class UserDetailSerializer(serializers.ModelSerializer):
    role = UserRoleSerializer(read_only=True)
    profile = UserProfileSerializer()
    
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'role', 'profile', 'date_joined']
        read_only_fields = ['id', 'username', 'date_joined']
    
    def update(self, instance, validated_data):
        profile_data = validated_data.pop('profile', None)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        if profile_data and hasattr(instance, 'profile'):
            for attr, value in profile_data.items():
                setattr(instance.profile, attr, value)
            instance.profile.save()
        
        return instance


class ApiKeySerializer(serializers.ModelSerializer):
    class Meta:
        model = ApiKey
        fields = ['id', 'key', 'name', 'is_active', 'last_used_at', 'created_at']
        read_only_fields = ['id', 'key', 'last_used_at', 'created_at']
