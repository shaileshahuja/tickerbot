from django.contrib.auth.models import User
from rest_framework import serializers

from insights.models import TalkUser


class EmailSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)

    def validate_email(self, value):
        """
        To check whether email id already exist or not
        """
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user is already registered with this e-mail address.")
        return value


class RegisterUsernameSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=20)

    def validate_username(self, value):
        """
        To check whether email id already exist or not
        """
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Sorry, this username is taken.")
        return value

    def create(self, validated_data):
        user = User.objects.create_user(validated_data['username'], validated_data['email'], validated_data['password'])
        talk_user = TalkUser.objects.create(user=user)
        return talk_user


class RegisterSerializer(EmailSerializer, RegisterUsernameSerializer):
    password = serializers.CharField(max_length=30, style={'input_type': 'password'})


class LoginUsernameSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=20)


class LoginSerializer(LoginUsernameSerializer):
    password = serializers.CharField(max_length=30, style={'input_type': 'password'})






