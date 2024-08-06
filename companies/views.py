from rest_framework.views import APIView
from django.shortcuts import render, redirect
from django.urls import reverse
from rest_framework.response import Response
from rest_framework import viewsets, generics
from rest_framework import status
from django.utils.text import slugify
from django.contrib.auth import login, authenticate, get_user_model
from .models import Tenant, Domain
from .serializers import TenantRegistrationSerializer, TenantSerializer, LoginSerializer, \
    RequestPasswordResetSerializer, ResetPasswordSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from .utils import Util
from django.contrib.sites.shortcuts import get_current_site
import jwt
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.core.mail import send_mail
from django.utils.http import urlsafe_base64_decode


class TenantRegistrationViewSet(viewsets.ViewSet):
    serializer_class = TenantRegistrationSerializer

    def create(self, request):
        serializer = TenantRegistrationSerializer(data=request.data)
        if serializer.is_valid(raise_exception=True):
            tenant = serializer.save()
            sanitized_name = slugify(tenant.schema_name, allow_unicode=True)
            current_site = get_current_site(request).domain
            domain = Domain.objects.create(domain=f"{sanitized_name}.{current_site.split(':')[0]}", tenant=tenant)

            user = tenant.user

            # user_data = serializer.data
            # user_email = Tenant.objects.get(email = user_data['email'])

            # login(request, user)  # Log in the user after registration

            token = RefreshToken.for_user(user)
            token['email'] = user.email  # Add email to payload

            relativeLink = reverse('email-verify')
            absurl = f'http://{current_site}{relativeLink}?token={str(token.access_token)}'
            email_body = 'HI ' + str(tenant.company_name) + ' Use the Link below to verify your email \n' + absurl
            data = {'email_body': email_body, 'to_email': user.email, 'email_subject': 'Verify Your Email'}

            Util.send_email(data)

            return Response({'detail': 'Tenant created successfully. Please confirm your email address.'},
                            status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class VerifyEmail(generics.GenericAPIView):
    def get(self, request):
        token = request.GET.get('token')

        if not token:
            return Response({'error': 'No token provided'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return Response({
                'error': 'Activation link expired',
                'resend_link': request.build_absolute_uri(reverse('resend-verification-email', kwargs={'token': token}))
            }, status=status.HTTP_400_BAD_REQUEST)
        except jwt.DecodeError:
            return Response({'error': 'Invalid token'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
            # user = Tenant.objects.get(id=payload['user_id'])
            user = User.objects.get(email=payload['email'])

            if not user.profile.is_verified:
                user.profile.is_verified = True
                user.profile.save()
                # return redirect('http://localhost:3000/login')
                return Response({'detail': 'Email successfully verified'}, status=status.HTTP_200_OK)
            else:
                return Response({'detail': 'Email already verified'}, status=status.HTTP_200_OK)


        except (jwt.exceptions.DecodeError, Tenant.DoesNotExist):
            return Response({'error': 'Activation link is invalid'}, status=status.HTTP_400_BAD_REQUEST)


class ResendVerificationEmail(generics.GenericAPIView):
    def get(self, request, token):
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"], options={"verify_exp": False})
            user = User.objects.get(email=payload['email'])

            if user.profile.is_verified:
                return Response({'detail': 'Email already verified'}, status=status.HTTP_400_BAD_REQUEST)

            new_token = RefreshToken.for_user(user)
            new_token['email'] = user.email

            current_site = get_current_site(request).domain
            relativeLink = reverse('email-verify')
            absurl = f'http://{current_site}{relativeLink}?token={str(new_token.access_token)}'
            email_body = f'Hi {user.username},\nUse the link below to verify your email:\n{absurl}'
            data = {'email_body': email_body, 'to_email': user.email, 'email_subject': 'Verify Your Email'}

            Util.send_email(data)

            return Response({'detail': 'New verification email has been sent.'}, status=status.HTTP_200_OK)
        except jwt.DecodeError:
            return Response({'error': 'Invalid token'}, status=status.HTTP_400_BAD_REQUEST)
        except User.DoesNotExist:
            return Response({'error': 'User with this email does not exist'}, status=status.HTTP_404_NOT_FOUND)


class LoginView(APIView):
    serializer_class = LoginSerializer

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            username = serializer.validated_data['username']
            password = serializer.validated_data['password']
            user = authenticate(request, username=username, password=password)

            if user is not None:
                if user.profile.is_verified:
                    login(request, user)
                    refresh = RefreshToken.for_user(user)
                    # Get the tenant associated with the user
                    try:
                        tenant = Tenant.objects.get(user=user)
                        domain = Domain.objects.get(tenant=tenant)

                        # Construct the tenant-specific URL
                        tenant_url = f"{domain.domain}"

                        return Response({
                            'refresh': str(refresh),
                            'access': str(refresh.access_token),
                            'user': {
                                'id': user.id,
                                'username': user.username,
                                'email': user.email,
                            },
                            'redirect_url': tenant_url
                        }, status=status.HTTP_200_OK)
                    except (Tenant.DoesNotExist, Domain.DoesNotExist):
                        return Response({'error': 'Tenant or domain not found for this user.'},
                                        status=status.HTTP_404_NOT_FOUND)
                else:
                    return Response({'error': 'Please verify your email before logging in.'},
                                    status=status.HTTP_403_FORBIDDEN)
            else:
                return Response({'error': 'Invalid credentials'},
                                status=status.HTTP_401_UNAUTHORIZED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class RequestPasswordResetView(APIView):
    serializer_class = RequestPasswordResetSerializer

    def post(self, request):
        serializer = RequestPasswordResetSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            try:
                user = User.objects.get(email=email)
                if not user.profile.is_verified:
                    return Response({'error': 'Email is not verified.'}, status=status.HTTP_400_BAD_REQUEST)

                token = default_token_generator.make_token(user)
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                current_site = get_current_site(request).domain
                reset_link = f"http://{current_site}/reset-password/{uid}/{token}"

                send_mail(
                    'Password Reset Request',
                    f'Click the following link to reset your password: {reset_link}',
                    settings.DEFAULT_FROM_EMAIL,
                    [email],
                    fail_silently=False,
                )
                return Response({'detail': 'Password reset email has been sent.'}, status=status.HTTP_200_OK)
            except User.DoesNotExist:
                return Response({'error': 'No user found with this email address.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ResetPasswordView(APIView):
    def get(self, request, uidb64, token):
        try:
            uid = urlsafe_base64_decode(uidb64).decode()
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            user = None

        if user is not None and default_token_generator.check_token(user, token):
            return Response({'detail': 'Token is valid'}, status=status.HTTP_200_OK)
        else:
            return Response({'error': 'Invalid token'}, status=status.HTTP_400_BAD_REQUEST)

    serializer_class = ResetPasswordSerializer

    def post(self, request, uidb64, token):
        try:
            uid = urlsafe_base64_decode(uidb64).decode()
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            user = None

        if user is not None and default_token_generator.check_token(user, token):
            serializer = ResetPasswordSerializer(data=request.data)
            if serializer.is_valid():
                user.set_password(serializer.validated_data['password1'])
                user.save()
                return Response({'detail': 'Password has been reset successfully.'}, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({'error': 'Invalid token'}, status=status.HTTP_400_BAD_REQUEST)


class TenantViewSet(viewsets.ModelViewSet):
    queryset = Tenant.objects.all()
    serializer_class = TenantSerializer