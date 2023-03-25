from django.shortcuts import redirect
from django.contrib.auth.hashers import make_password
from django.core.mail import send_mail
from django.template.loader import get_template
from django.http import HttpResponse, JsonResponse
from rest_framework import permissions, status, generics
from rest_framework.decorators import api_view
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
# from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.viewsets import ReadOnlyModelViewSet
from rest_framework.throttling import UserRateThrottle, AnonRateThrottle
from rest_framework.generics import RetrieveAPIView


# from .utils import makeCompany
from .models import CustomUser, Company, InviteToken
from .serializers import UserSerializer, UserSerializerWithToken, UserListSerializer, MyTokenObtainPairSerializer, MessageSerializer
from config import settings

import datetime
import jwt
import pytz
import pyotp
import uuid
from functools import wraps


def get_token_auth_header(request):
    """Obtains the Access Token from the Authorization Header
    """
    print(request.META )
    auth = request.META.get("HTTP_AUTHORIZATION", None)
    parts = auth.split()
    token = parts[1]

    return token

def requires_scope(required_scope):
    """Determines if the required scope is present in the Access Token
    Args:
        required_scope (str): The scope required to access the resource
    """
    def require_scope(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            token = get_token_auth_header(args[0])
            decoded = jwt.decode(token, verify=False)
            if decoded.get("scope"):
                token_scopes = decoded["scope"].split()
                for token_scope in token_scopes:
                    if token_scope == required_scope:
                        return f(*args, **kwargs)
            response = JsonResponse({'message': 'You don\'t have access to this resource'})
            response.status_code = 403
            return response
        return decorated
    return require_scope

class ManageUserView(APIView):
    permission_classes = [IsAuthenticated]
    #TODO: Currently not checking if user email is already in use
    def post(self, request, *args, **kwargs):
        try:
            # Invite User
            if Company.objects.filter(id=self.kwargs['id']).exists():
                try:
                    company = Company.objects.get(id=self.kwargs['id'])
                    admin = CustomUser.objects.filter(company=company, status='admin')[0]
                    if company:
                        user, created = CustomUser.objects.get_or_create(
                            email=request.data['email'],
                            company=company,
                            status='pending',
                        )
                        token, created = InviteToken.objects.get_or_create(company=company, email=request.data['email'])
                        if created:
                            mail_subject = "Account Invite For Is My Customer Moving"                            
                        else:
                            token.expiration = datetime.datetime.utcnow() + datetime.timedelta(days=1)
                            token.save()
                            mail_subject = "Invite Reminder For Is My Customer Moving"

                        messagePlain = f"You have been invited to join Is My Customer Moving by {admin.first_name} {admin.last_name}. Please click the link below to join. https://app.ismycustomermoving.com/addeduser/{str(token.id)}"
                        message = get_template("addUserEmail.html").render({
                            'admin': admin, 'token': token.id
                        })
                        send_mail(subject=mail_subject, message=messagePlain, from_email=settings.EMAIL_HOST_USER, recipient_list=[request.data['email']], html_message=message, fail_silently=False)    
                except Exception as e:
                    print(e)
                    return Response({"status": "Data Error"}, status=status.HTTP_400_BAD_REQUEST)
                users = CustomUser.objects.filter(company=user.company)
                serializer = UserListSerializer(users, many=True)
                return Response(serializer.data)
            # Accept Invite and Make User
            elif InviteToken.objects.filter(id=self.kwargs['id']).exists():
                utc = pytz.UTC
                try:
                    token = InviteToken.objects.get(id=self.kwargs['id'], email=request.data['email'])
                    if token.expiration > utc.localize(datetime.datetime.utcnow()):
                        company = token.company
                        if company:
                            try:
                                user = CustomUser.objects.get(
                                    email=request.data['email'],
                                    company=company,
                                    status='pending'
                                )
                            except Exception as e:
                                print(e)
                                return Response({"status": "Cannot find user"}, status=status.HTTP_400_BAD_REQUEST)

                            user.password = make_password(request.data['password'])
                            user.status = 'active'
                            user.first_name = request.data['firstName']
                            user.last_name = request.data['lastName']
                            user.phone = request.data['phone']
                            user.isVerified = True
                            user.save()                            
                            token.delete()
                    else:
                        return Response({"status": "Token Expired"}, status=status.HTTP_400_BAD_REQUEST)
                except Exception as e:
                    return Response({"status": "Data Error on Invite Token"}, status=status.HTTP_400_BAD_REQUEST)
                serializer = UserSerializerWithToken(user, many=False)
                return Response(serializer.data)
            # Make User an Admin
            elif CustomUser.objects.filter(id=self.kwargs['id']).exists():
                try:
                    user = CustomUser.objects.get(id=self.kwargs['id'])
                    if user:
                        user.status = 'admin'
                        user.save()
                except Exception as e:
                    return Response({"status": "Data Error"}, status=status.HTTP_400_BAD_REQUEST)
                users = CustomUser.objects.filter(company=user.company)
                serializer = UserListSerializer(users, many=True)
                return Response(serializer.data)
            else:
                return Response({"status": "User Not Found"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"status": "Data Error"}, status=status.HTTP_400_BAD_REQUEST)
    def put(self, request, *args, **kwargs):
        try:
            if CustomUser.objects.filter(id=self.kwargs['id']).exists():
                user = CustomUser.objects.get(id=self.kwargs['id'])
                if user:
                    user.first_name = request.data['firstName']
                    user.last_name = request.data['lastName']
                    user.email = request.data['email']
                    user.save()
                serializer = UserSerializerWithToken(user, many=False)
                return Response(serializer.data)
            else:
                return Response({"status": "User Not Found"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            print(e)
            return Response({"status": "Data Error"}, status=status.HTTP_400_BAD_REQUEST)        
    def delete(self, request, *args, **kwargs):
        try:
            if len(request.data) == 1:
                user = CustomUser.objects.get(id=request.data[0])
                user.delete()
            else:
                CustomUser.objects.filter(id__in=request.data).delete()
            users = CustomUser.objects.filter(company=self.kwargs['id'])
            serializer = UserListSerializer(users, many=True)
            return Response(serializer.data)
        except Exception as e:
            print(e)
            return Response({"status": "Data Error"}, status=status.HTTP_400_BAD_REQUEST)

# @api_view(['POST', 'PUT'])
# def company(request):
#     if request.method == 'POST':
#         try:
#             company = request.data['name']
#             email = request.data['email']
#             comp = makeCompany(company, email)
#             if comp == "":
#                 return Response("", status=status.HTTP_201_CREATED, headers="")
#             else:
#                 return Response(comp, status=status.HTTP_400_BAD_REQUEST)
#         except Exception as e:
#             print(e)
#             return Response({"status": "Data Error"}, status=status.HTTP_400_BAD_REQUEST)
#     elif request.method == 'PUT':
#         try:
#             company = Company.objects.get(id=request.data['company'])
#             if request.data['email'] != "":
#                 company.email = request.data['email']
#             if request.data['phone'] != "":
#                 company.phone = request.data['phone']
#             if request.data['tenantID'] != "":
#                 company.tenantID = request.data['tenantID']
#             if request.data['clientID'] != "":
#                 company.clientID = request.data['clientID']
#                 company.clientSecret = request.data['clientSecret']
#             if request.data['forSaleTag'] != "":
#                 company.serviceTitanForSaleTagID = request.data['forSaleTag']
#             if request.data['forRentTag'] != "":
#                 company.serviceTitanForRentTagID = request.data['forRentTag']
#             if request.data['soldTag'] != "":
#                 company.serviceTitanRecentlySoldTagID = request.data['soldTag']
#             if request.data['crm'] != "":
#                 company.crm = request.data['crm']
#             company.save()
#             user = CustomUser.objects.get(id=request.data['user'])
#             serializer = UserSerializerWithToken(user, many=False)
#             return Response( serializer.data , status=status.HTTP_201_CREATED, headers="")
#         except Exception as e:
#             print(e)
#             return Response({"status": "Data Error"}, status=status.HTTP_400_BAD_REQUEST)   

class VerifyRegistrationView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AnonRateThrottle]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        try:
            token = request.data['token']
            try:
                payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
                user = CustomUser.objects.get(id=payload['user_id'])
                if not user.isVerified:
                    user.isVerified = True
                    user.save()
            except jwt.ExpiredSignatureError as identifier:
                return Response({'detail': 'Activation Expired'}, status=status.HTTP_400_BAD_REQUEST)
            except jwt.exceptions.DecodeError as identifier:
                return Response({'detail': 'Invalid token'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            print(e)
            return Response({'detail': 'Invalid token'}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'detail': 'Successfully activated'}, status=status.HTTP_200_OK)

class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AnonRateThrottle]
    authentication_classes = []

    def post(self, request):
        data = request.data
        first_name = data.get('firstName')
        last_name = data.get('lastName')
        email = data.get('email')
        password = data.get('password')
        company = data.get('company')
        accessToken = data.get('accessToken')
        phone = data.get('phone')
        messages = {'errors': []}
        if first_name == None:
            messages['errors'].append('first_name can\'t be empty')
        if last_name == None:
            messages['errors'].append('last_name can\'t be empty')
        if email == None:
            messages['errors'].append('Email can\'t be empty')
        if password == None:
            messages['errors'].append('Password can\'t be empty')
        if company == None:
            messages['errors'].append('Company can\'t be empty')
        if accessToken == None:
            messages['errors'].append('Access Token can\'t be empty')
        
        if CustomUser.objects.filter(email=email).exists():
            messages['errors'].append(
                "Account already exists with this email id.")
        if len(messages['errors']) > 0:
            return Response({"detail": messages['errors']}, status=status.HTTP_400_BAD_REQUEST)
        try:
            company = Company.objects.get(name=company, accessToken=accessToken)
            noAdmin = CustomUser.objects.filter(company=company, isVerified=True)
            if len(noAdmin) == 0:
                user = CustomUser.objects.create(
                    first_name=first_name,
                    last_name=last_name,
                    email=email,
                    password=make_password(password, salt=uuid.uuid4().hex),
                    company=company,
                    status='admin',
                    isVerified=True,
                    phone = phone
                )
                # user = CustomUser.objects.get(email=email)
                # current_site = get_current_site(request)
                # tokenSerializer = UserSerializerWithToken(user, many=False)
                # mail_subject = "Activation Link for Is My Customer Moving"
                # messagePlain = "Verify your account for Is My Customer Moving by going here {}/api/v1/accounts/confirmation/{}/{}/".format(current_site, tokenSerializer.data['refresh'], user.id)
                # message = get_template("registration.html").render({
                #     'current_site': current_site, 'token': tokenSerializer.data['refresh'], 'user_id': user.id
                # })
                # send_mail(subject=mail_subject, message=messagePlain, from_email=settings.EMAIL_HOST_USER, recipient_list=[email], html_message=message, fail_silently=False)
                serializer = UserSerializerWithToken(user, many=False)
            else:
                return Response({'detail': f'Access Token Already Used. Ask an admin to login and create profile for you.'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            print(e)
            return Response({'detail': f'{e}'}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.data)

@api_view(['GET'])
def confirmation(request, pk, uid):
    user = CustomUser.objects.get(id=uid)
    token = jwt.decode(pk, settings.SECRET_KEY, algorithms=["HS256"])

    if user.isVerified == False and datetime.datetime.fromtimestamp(token['exp']) > datetime.datetime.now():
        user.isVerified = True
        user.save()
        return redirect('http://www.ismycustomermoving.com/login')

    elif (datetime.datetime.fromtimestamp(token['exp']) < datetime.datetime.now()):

        # For resending confirmation email use send_mail with the following encryption
        # print(jwt.encode({'user_id': user.user.id, 'exp': datetime.datetime.now() + datetime.timedelta(days=1)}, settings.SECRET_KEY, algorithm='HS256'))
        
        return HttpResponse('Your activation link has been expired')
    else:
        return redirect('http://www.ismycustomermoving.com/login')
        
# class MyTokenObtainPairView(TokenObtainPairView):
#     permission_classes = [IsAuthenticated]
#     serializer_class = MyTokenObtainPairSerializer
    
class AuthenticatedUserView(APIView):
    permission_classes = [IsAuthenticated]   
    def get(self, request, email=None):  
        try:
            user = CustomUser.objects.get(email=email)
            serializer = UserSerializer(user, many=False)
            return Response(serializer.data)
        except Exception as e:
            print(e)
            return Response({'detail': f'{e}'}, status=status.HTTP_400_BAD_REQUEST)      

class UserViewSet(ReadOnlyModelViewSet):
    throttle_classes = [UserRateThrottle]
    serializer_class = UserSerializer
    queryset = CustomUser.objects.all()
    permission_classes = [IsAuthenticated]

class OTPGenerateView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [AnonRateThrottle]
    authentication_classes = []

    def post(self, request):
        try:
            user = CustomUser.objects.get(id=request.data['id'])
            if user == None:
                return Response({'detail': f'User with this email does not exist'}, status=status.HTTP_400_BAD_REQUEST)
            otp_base32 = pyotp.random_base32()
            otp_auth_url = pyotp.totp.TOTP(otp_base32).provisioning_uri(
                name=user.email.lower(), issuer_name='Is My Customer Moving')

            user.otp_auth_url = otp_auth_url
            user.otp_base32 = otp_base32
            user.save()
            serializer = UserSerializerWithToken(user, many=False)
            return Response(serializer.data, status=status.HTTP_200_OK)
            
        except Exception as e:
            print(e)
            return Response({'detail': f'{e}'}, status=status.HTTP_400_BAD_REQUEST)

class OTPVerifyView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [AnonRateThrottle]
    authentication_classes = []

    def post(self, request):
        try:
            user = CustomUser.objects.get(id=request.data['id'])
            if user == None:
                return Response({'detail': f'User with this email does not exist'}, status=status.HTTP_400_BAD_REQUEST)
            if user.otp_base32 == None:
                return Response({'detail': f'OTP not generated for this user'}, status=status.HTTP_400_BAD_REQUEST)
            totp = pyotp.TOTP(user.otp_base32)
            if totp.verify(request.data['otp']):
                user.otp_enabled = True
                user.otp_verified = True
                user.save()
                serializer = UserSerializerWithToken(user, many=False)
                return Response(serializer.data, status=status.HTTP_200_OK)
            else:
                print("verification failed")
                return Response({'detail': f'OTP verification failed'}, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            print(e)
            return Response({'detail': f'{e}'}, status=status.HTTP_400_BAD_REQUEST)       

class OTPValidateView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [AnonRateThrottle]
    authentication_classes = []

    def post(self, request):
        otp = request.data['otp']
        messages = {'errors': []}
        user = CustomUser.objects.get(id=request.data['id'])
        if not user.otp_verified:
            messages['errors'].append('One Time Password incorrect')
        if user.otp_base32 == None:
            return Response({'detail': f'OTP not generated for this user'}, status=status.HTTP_400_BAD_REQUEST)
        if len(messages['errors']) > 0:
            return Response({"detail": messages['errors']}, status=status.HTTP_400_BAD_REQUEST)
        try:                                    
            totp = pyotp.TOTP(user.otp_base32)
            if totp.verify(otp, valid_window=1):
                serializer = UserSerializerWithToken(user, many=False)
                return Response(serializer.data, status=status.HTTP_200_OK)
            else:
                return Response({'detail': f'OTP verification failed'}, status=status.HTTP_400_BAD_REQUEST)            
        except Exception as e:
            print(e)
            return Response({'detail': f'{e}'}, status=status.HTTP_400_BAD_REQUEST)

class OTPDisableView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [AnonRateThrottle]
    authentication_classes = []

    def post(self, request):
        try:            
            user = CustomUser.objects.get(id=request.data['id'])            
            user.otp_enabled = False
            user.otp_verified = False
            user.otp_base32 = None
            user.otp_auth_url = None
            user.save()
            serializer = UserSerializerWithToken(user, many=False)
            return Response(serializer.data, status=status.HTTP_200_OK)
            
        except Exception as e:
            print(e)
            return Response({'detail': f'{e}'}, status=status.HTTP_400_BAD_REQUEST)

class UserListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserListSerializer
    def get_queryset(self):
        return CustomUser.objects.filter(company=self.kwargs['company'])
